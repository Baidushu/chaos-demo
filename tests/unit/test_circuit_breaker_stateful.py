"""熔断器状态机的基于属性测试（hypothesis RuleBasedStateMachine）。

与 ``test_circuit_breaker.py`` 的场景式用例互补：不写具体剧本，让 hypothesis
随机生成「放行 / 记录成功 / 记录失败 / 推进时间 / 竞争请求」的操作序列，
并在每一步之后校验状态机不变量。

调用契约（与 app/service/order_service.py 的真实用法一致）：

- 每个被放行的请求恰好记录一次成功或失败；
- 被拒绝的请求不产生任何记录；
- 生产中每次请求新建 breaker 实例；本测试用单个实例模拟顺序客户端，
  并额外注入「竞争请求」规则，回归验证：探针被占用期间，竞争请求的
  allow_request() 不得破坏在途探针的归属（历史上 ``_probe_acquired``
  会被竞争请求清掉，导致探针结果走错记录路径）。

被验证的性质：

1. OPEN     ⇔ open_until > now（打开必须由未来到期时间背书）；
2. HALF_OPEN ⇔ 0 < open_until <= now（探测期由过期但非零的 open_until 标识）；
3. CLOSED   ⇔ open_until == 0（闭合时窗口/探针状态全部清理）；
4. 探针独占：探针在途时竞争请求必须被拒；
5. 打开条件模型：opened == (总量达标 且 失败率达标 且 当前未处于打开态)，
   且该条件在**每次** outcome 记录时评估——record_success 也可能触发打开
   （与 lua/circuit_breaker.lua 语义一致）；
6. 探针成功 → 立即 CLOSED 且 open_until 归零；探针失败 → 立即重新 OPEN；
7. 窗口快照一致性：failure_count <= total，failure_rate 与计数自洽。

时钟完全可控（FakeClock），Redis 用 tests/conftest.FakeRedis 的 Lua 模拟。
"""

from __future__ import annotations

from types import SimpleNamespace

from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from chaos_service.resilience.breaker.breaker import CircuitBreaker
from chaos_service.resilience.breaker.metrics import CircuitBreakerMetrics
from chaos_service.resilience.breaker.rule import CircuitBreakerRule
from chaos_service.resilience.breaker.state import CircuitState
from chaos_service.resilience.breaker.storage import RedisCircuitBreakerStorage
from tests.conftest import FakeRedis


class FakeClock:
    """单调递增的可控时钟。"""

    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += max(seconds, 0.0)


def _make_ctx(redis_client: FakeRedis) -> SimpleNamespace:
    return SimpleNamespace(
        redis_client=redis_client,
        BREAKER_RESOURCE="order",
        CB_KEY_OPEN_UNTIL="cb:stateful:open_until",
        CB_KEY_FAILURES="cb:stateful:failures",
        CB_KEY_TOTAL_REQUESTS="cb:stateful:totals",
        CB_KEY_PROBE="cb:stateful:probe",
        CIRCUIT_PROBE_TTL_SEC=30,
        RETRY_MAX_ATTEMPTS=1,
        RETRY_BASE_DELAY_MS=0.0,
        RETRY_MAX_DELAY_MS=0.0,
    )


class CircuitBreakerMachine(RuleBasedStateMachine):
    """熔断器状态机：随机操作序列 + 全程不变量校验。"""

    def __init__(self) -> None:
        super().__init__()
        self.clock = FakeClock()
        self.redis = FakeRedis()
        ctx = _make_ctx(self.redis)
        self.rule = CircuitBreakerRule(
            resource="order",
            failure_rate_threshold=0.5,
            # min=2：降低打开门槛，让 hypothesis 更快探索 OPEN/HALF_OPEN 路径
            min_request_count=2,
            window_seconds=10,
            open_timeout_seconds=5,
        )
        self.storage = RedisCircuitBreakerStorage(ctx, clock=self.clock)
        self.breaker = CircuitBreaker(
            self.rule, self.storage, CircuitBreakerMetrics(SimpleNamespace())
        )
        # None=空闲；"probe"=在途探针请求；"normal"=在途普通请求。
        self.outstanding: str | None = None

    # ------------------------------------------------------------------
    # 规则：状态机的驱动操作
    # ------------------------------------------------------------------
    @precondition(lambda self: self.outstanding is None)
    @rule()
    def allow_request(self) -> None:
        state = self.breaker.state()
        allowed = self.breaker.allow_request()

        if state is CircuitState.OPEN:
            assert not allowed, "OPEN 态必须拒绝请求"
        elif state is CircuitState.CLOSED:
            assert allowed, "CLOSED 态必须放行请求"
            self.outstanding = "normal"
        else:  # HALF_OPEN 且无在途请求 → 探针必然可得（探针未被占用）
            assert allowed, "HALF_OPEN 空闲时探针获取不应失败"
            self.outstanding = "probe"

    @precondition(lambda self: self.outstanding == "probe")
    @rule()
    def competing_request_during_probe(self) -> None:
        """竞争请求落在同一实例上：必须被拒，且不得破坏在途探针归属。

        探针归属不被破坏由后续 record_* 的探针路径断言间接验证——
        若 _probe_acquired 被竞争请求清掉，记录会走普通路径，
        「探针成功必须闭合」等断言即失败。
        """
        allowed = self.breaker.allow_request()
        assert not allowed, "探针被占用期间，竞争请求必须被拒绝"

    @precondition(lambda self: self.outstanding == "normal")
    @rule()
    def competing_request_during_normal(self) -> None:
        """CLOSED 态的竞争请求同样放行（其结果在生产中由各自实例记录）。"""
        allowed = self.breaker.allow_request()
        assert allowed, "CLOSED 态竞争请求必须放行"

    @precondition(lambda self: self.outstanding is not None)
    @rule()
    def record_success(self) -> None:
        kind = self.outstanding
        pre_open_until = self.storage.get_open_until(self.rule)
        now = self.clock.now
        result = self.breaker.record_success()
        self.outstanding = None

        if kind == "probe":
            # 探针成功 → 立即闭合并清理窗口。
            assert self.breaker.state() is CircuitState.CLOSED, "探针成功后必须闭合"
            assert self.storage.get_open_until(self.rule) == 0.0, "闭合后 open_until 必须归零"
        else:
            self._assert_open_condition_model(result, pre_open_until, now)

    @precondition(lambda self: self.outstanding is not None)
    @rule()
    def record_failure(self) -> None:
        kind = self.outstanding
        pre_open_until = self.storage.get_open_until(self.rule)
        now = self.clock.now
        result = self.breaker.record_failure()
        self.outstanding = None

        if kind == "probe":
            # 探针失败 → 立即重新打开。
            assert result is not None and result.opened, "探针失败必须重新打开"
            assert self.breaker.state() is CircuitState.OPEN
            assert self.storage.get_open_until(self.rule) > now
        else:
            self._assert_open_condition_model(result, pre_open_until, now)

    @rule(seconds=st.floats(min_value=0.0, max_value=20.0))
    def advance_time(self, seconds: float) -> None:
        self.clock.advance(seconds)

    # ------------------------------------------------------------------
    # 打开条件模型（与 lua/circuit_breaker.lua 逐条对应）
    # ------------------------------------------------------------------
    def _assert_open_condition_model(self, result, pre_open_until: float, now: float) -> None:
        assert result is not None
        snap = result.snapshot
        should_open = (
            snap.total_request_count >= self.rule.min_request_count
            and snap.failure_rate >= self.rule.failure_rate_threshold
            and pre_open_until <= now
        )
        assert result.opened == should_open, (
            f"opened={result.opened} 与模型预期 {should_open} 不符 "
            f"(total={snap.total_request_count}, rate={snap.failure_rate:.3f}, "
            f"pre_open_until={pre_open_until:.3f}, now={now:.3f})"
        )
        if result.opened:
            assert self.breaker.state() is CircuitState.OPEN
            assert self.storage.get_open_until(self.rule) > now

    # ------------------------------------------------------------------
    # 不变量：每条规则执行后都校验
    # ------------------------------------------------------------------
    @invariant()
    def state_matches_open_until(self) -> None:
        state = self.breaker.state()
        open_until = self.storage.get_open_until(self.rule)
        now = self.clock.now

        if state is CircuitState.OPEN:
            assert open_until > now, f"OPEN 态要求 open_until({open_until:.3f}) > now({now:.3f})"
        elif state is CircuitState.HALF_OPEN:
            assert 0 < open_until <= now, (
                f"HALF_OPEN 态要求 0 < open_until({open_until:.3f}) <= now({now:.3f})"
            )
        else:
            assert open_until == 0.0, f"CLOSED 态要求 open_until 归零，实际 {open_until:.3f}"

    @invariant()
    def outstanding_matches_state(self) -> None:
        if self.outstanding == "probe":
            assert self.breaker.state() is CircuitState.HALF_OPEN, "探针在途期间必须处于 HALF_OPEN"
        elif self.outstanding == "normal":
            assert self.breaker.state() is CircuitState.CLOSED, "普通请求在途期间必须处于 CLOSED"

    @invariant()
    def snapshot_is_self_consistent(self) -> None:
        snap = self.storage.snapshot(self.rule)
        assert snap.failure_count <= snap.total_request_count, "失败数不可能超过总请求数"
        if snap.total_request_count > 0:
            expected_rate = snap.failure_count / snap.total_request_count
            assert abs(snap.failure_rate - expected_rate) < 1e-9, "failure_rate 与计数不一致"
        else:
            assert snap.failure_rate == 0.0


CircuitBreakerMachine.TestCase.settings = settings(
    max_examples=150,
    stateful_step_count=40,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
TestCircuitBreakerMachine = CircuitBreakerMachine.TestCase


def test_probe_ownership_survives_competing_request():
    """回归（确定性钉死）：探针在途时，竞争请求不得破坏探针归属。

    旧实现 ``self._probe_acquired = acquired`` 在竞争请求获取探针失败时
    把归属清掉，探针成功因此走普通记录路径：轻则不闭合，重则因窗口
    失败率仍越界而重新打开。该交错序列在随机状态机中命中概率偏低，
    故用本确定性场景钉死（状态机负责广度，本用例负责钉住该回归点）。
    """
    clock = FakeClock()
    redis = FakeRedis()
    rule = CircuitBreakerRule(
        resource="order",
        failure_rate_threshold=0.5,
        min_request_count=4,
        window_seconds=10,
        open_timeout_seconds=5,
    )
    storage = RedisCircuitBreakerStorage(_make_ctx(redis), clock=clock)
    breaker = CircuitBreaker(rule, storage, CircuitBreakerMetrics(SimpleNamespace()))

    # 四连失败 → 打开
    for _ in range(4):
        assert breaker.allow_request() is True
        breaker.record_failure()
    assert breaker.state() is CircuitState.OPEN

    # 超时 → HALF_OPEN，放行探针
    clock.advance(5.0)
    assert breaker.state() is CircuitState.HALF_OPEN
    assert breaker.allow_request() is True

    # 竞争请求落在同一实例 → 必须被拒，且不得清掉探针归属
    assert breaker.allow_request() is False

    # 探针成功 → 必须立即闭合
    breaker.record_success()
    assert breaker.state() is CircuitState.CLOSED
    assert storage.get_open_until(rule) == 0.0
