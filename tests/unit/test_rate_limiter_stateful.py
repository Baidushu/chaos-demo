"""限流器状态机的基于属性测试（hypothesis RuleBasedStateMachine）。

对两种限流算法各建一个状态机，随机「发起请求 / 推进时间」并校验核心不变量：

- 滑动窗口：任意长度为 window 的时间区间内，放行次数 <= limit；
- 固定窗口：同一个桶内的放行次数 <= limit，且放行判定与桶内计数模型一致。

这是限流语义的正确性证明式测试——不依赖具体请求序列剧本，
hypothesis 会自动探索边界（恰好到达 limit、跨桶、窗口滑出等）。
"""

from __future__ import annotations

import math
from pathlib import Path

from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from chaos_service import rate_limiter
from tests.conftest import FakeRedis

LUA_DIR = Path(__file__).resolve().parents[2] / "lua"


class FakeClock:
    def __init__(self, start: float = 10_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += max(seconds, 0.0)


class SlidingWindowLimiterMachine(RuleBasedStateMachine):
    """滑动窗口：任意 (now-window, now] 内放行数 <= limit。"""

    LIMIT = 3
    WINDOW = 2.0

    def __init__(self) -> None:
        super().__init__()
        self.clock = FakeClock()
        self.redis = FakeRedis()
        self.backend = rate_limiter.RedisBackend(
            self.redis,
            service_name="stateful-svc",
            script_dir=LUA_DIR,
            clock=self.clock,
        )
        self.rule = rate_limiter.RateLimitRule(
            resource="order",
            algorithm="sliding",
            limit=self.LIMIT,
            window=self.WINDOW,
            dimension="client_ip",
        )
        self.allowed_times: list[float] = []

    @rule()
    def allow(self) -> None:
        decision = self.backend.allow(self.rule, "1.2.3.4")
        assert not decision.backend_error
        if decision.allowed:
            self.allowed_times.append(self.clock.now)

    @rule(seconds=st.floats(min_value=0.0, max_value=6.0))
    def advance_time(self, seconds: float) -> None:
        self.clock.advance(seconds)

    @invariant()
    def window_capacity_never_exceeded(self) -> None:
        cutoff = self.clock.now - self.rule.window
        in_window = [t for t in self.allowed_times if t > cutoff]
        assert len(in_window) <= self.rule.limit, (
            f"滑动窗口被突破：{len(in_window)} 次放行落在 "
            f"({cutoff:.3f}, {self.clock.now:.3f}]，limit={self.rule.limit}"
        )


SlidingWindowLimiterMachine.TestCase.settings = settings(
    max_examples=50,
    stateful_step_count=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
TestSlidingWindowLimiterMachine = SlidingWindowLimiterMachine.TestCase


class FixedWindowLimiterMachine(RuleBasedStateMachine):
    """固定窗口：桶内放行数 <= limit，且放行判定 == (桶内已放行数 < limit)。"""

    LIMIT = 3
    WINDOW = 2.0

    def __init__(self) -> None:
        super().__init__()
        self.clock = FakeClock()
        self.redis = FakeRedis()
        self.backend = rate_limiter.RedisBackend(
            self.redis,
            service_name="stateful-svc",
            script_dir=LUA_DIR,
            clock=self.clock,
        )
        self.rule = rate_limiter.RateLimitRule(
            resource="order",
            algorithm="fixed",
            limit=self.LIMIT,
            window=self.WINDOW,
            dimension="client_ip",
        )
        self.allowed_per_bucket: dict[int, int] = {}

    @rule()
    def allow(self) -> None:
        bucket = int(math.floor(self.clock.now / self.rule.window))
        already_allowed = self.allowed_per_bucket.get(bucket, 0)
        decision = self.backend.allow(self.rule, "1.2.3.4")
        assert not decision.backend_error
        # 放行判定必须与「桶内已放行数 < limit」的模型完全一致。
        assert decision.allowed == (already_allowed < self.rule.limit), (
            f"桶 {bucket} 放行判定 {decision.allowed} 与模型不符"
            f"（桶内已放行 {already_allowed}，limit={self.rule.limit}）"
        )
        if decision.allowed:
            self.allowed_per_bucket[bucket] = already_allowed + 1

    @rule(seconds=st.floats(min_value=0.0, max_value=6.0))
    def advance_time(self, seconds: float) -> None:
        self.clock.advance(seconds)

    @invariant()
    def bucket_capacity_never_exceeded(self) -> None:
        for bucket, count in self.allowed_per_bucket.items():
            assert count <= self.rule.limit, f"固定桶 {bucket} 放行 {count} 次超过 limit={self.rule.limit}"


FixedWindowLimiterMachine.TestCase.settings = settings(
    max_examples=50,
    stateful_step_count=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
TestFixedWindowLimiterMachine = FixedWindowLimiterMachine.TestCase
