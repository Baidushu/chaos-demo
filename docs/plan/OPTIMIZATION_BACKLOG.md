# 优化待办（OPTIMIZATION_BACKLOG）

> **用途**：读代码时记录可改进点，**不急着改代码**。  
> **维护**：新问题**追加表格行**；已落地可标 `[done]` 或移到文尾「已解决」。  
> **与全景文**：**实现状态、环境变量、API** 以 [`../AI_PROJECT_CONTEXT.md`](../AI_PROJECT_CONTEXT.md) 为准；本文件为**表格式工程债/历史**，不充当第二本「项目说明书」。


---

## 图例（全文统一）

| 优先级 | 含义 |
|--------|------|
| **P0** | 影响 **CI 可信度**或**频繁踩坑**，建议优先做 |
| **P1** | 核心能力或**明显工程收益**，值得排期 |
| **P2** | 增强质量、扩展场景，**有空再做** |
| **P3** | **叙述/选型/演示扩展**，成本低或仅文档 |

| 难度 | 含义 |
|------|------|
| **低** | 小范围改动、或mostly 配置/文档 |
| **中** | 需设计分支/状态机/联调 |
| **高** | 分布式一致性、大改协议或长期维护成本 |

---

## 快速索引（按文件/模块）

| 模块 | 小节 | 典型优先级范围 |
|------|------|------------------|
| `app.py` | §1 韧性 / 接口 / 2+1 方案 | P1～P2，难度中～高 |
| `benchmark_compare` / `quality_gate` / `qa` | §2 | P0～P2 |
| `security_scan.py` | §3 | P1～P2 |
| `replay_traffic.py` | §4 | P2 |
| `chaos_compare.py` / agent-eval | §5 | P2 |
| `tests/test_app.py` FakeRedis | §6 | P1～P2 |
| 技术栈扩展（Playwright/k6 等） | §7 | P3 |

---

## 1. `app.py`：限流、熔断、观测与接口

### 1.1 韧性逻辑（待办明细）

| 优先级 | 难度 | 位置/主题 | 问题 | 解决方向 |
|--------|------|-----------|------|----------|
| P2 | 中 | `allow_request_by_rate_limit` | 固定**秒窗口**，边界两秒可各打满配额，短时突刺高于预期 | **[done]** 默认 `RATE_LIMIT_ALGORITHM=sliding`（Redis ZSET + Lua）；`fixed` 保留旧 INCR 桶 |
| P2 | 高 | `is_circuit_open` / `record_*` | **已落地最小 Half-Open**（单探测请求）；仍可继续增强失败率窗口与更细状态机 | 深化 Half-Open 策略、失败率窗口；对齐 Sentinel/Hystrix 等 |
| P2 | 低 | `breaker_failures`（历史） | `list` 头删 O(n) | **[done]** 失败时间窗在 **Redis ZSET** `cb:failures`；非进程内 `list` |
| P2 | 高 | 熔断多实例各跳各闸 | 多进程/多副本不一致 | **[done]** 熔断与半开在 **Redis**（`cb:*`），与 Gunicorn worker 共享 |
| P2 | 低 | 熔断打开瞬间 | 已增加 Open / Half-Open / Reopen / Close 结构化日志；可继续补 Prometheus 专项指标 | Open 时打日志 + Prometheus Counter/Gauge |

### 1.2 「2 + 1」方案组合（方向备忘）

| 优先级 | 难度 | 项 | 说明 |
|--------|------|-----|------|
| P2 | 中 | **半开 (Half-Open)** | 已落地单探测请求版本；可继续细化为分级探测/多阈值策略 |
| P2 | 中～高 | **熔断状态进 Redis** | **[done]** 与限流同源；`cb:open_until` / `cb:failures` / `cb:probe` + Lua |
| P2 | 低 | **指标/日志** | 状态切换可观测，便于演示与排障 |

**建议顺序**：半开 → 指标/日志 → 再 Redis 多副本。

### 1.3 接口与其它（健壮性 / 安全 / 探针）

| 优先级 | 难度 | 主题 | 问题 | 方向 |
|--------|------|------|------|------|
| P2 | 中 | `cancel_order` | 并发双取消等非幂等副作用竞态 | `db_lock` 或行锁/乐观锁 |
| P2 | 低 | `get_order` | `**order` 可能过度暴露字段 | 响应白名单 |
| P2 | 低 | `healthz` | Redis 差即 degraded，易与 **Liveness** 混淆误杀 Pod | **[done]** 已加 `/live`、`/ready`；`/healthz` 保留兼容；`k8s/app-redis.yaml` 示例探针 |
| P2 | 低 | `/metrics` | 无鉴权 | 内网隔离、mTLS、白名单 |

**测开用例备忘**：并发重复取消；Redis 故障时探针语义；`get_order` 字段契约。

---

## 2. 压测、门禁与 `qa` 流水线

### 2.1 `benchmark_compare.py`（职业测开四条 + 代码）

| 优先级 | 难度 | 维度 | 问题摘要 | 改进方向 |
|--------|------|------|----------|----------|
| P3 | 中 | 真实环境 | 本机 RTT，难现网延迟 | 跨机/TC/镜像流量 |
| P2 | 中 | 负载模型 | 无 Ramp-up、无预热 | **[部分 done]** `benchmark_compare` 已支持 **`--warmup`**、**`BENCHMARK_WARMUP`**、分阶段/Ramp 仍可加 |
| P2 | 中 | 连接模型 | `urllib` 短连接 | 连接池、Keep-Alive 对照 |
| P2 | 低 | 可观测 | 压测窗口未对齐 Grafana | 时间轴对齐大盘 |

| 优先级 | 难度 | `run_benchmark` / `one_request` | 问题 | 方向 |
|--------|------|-----------------------------------|------|------|
| P2 | 中 | 参数与客户端固定 | demo 量级 | **[部分 done]** **`-n/-c/--seed`**、**`BENCHMARK_*`**、报告 `params`；httpx 连接池为可选 |

### 2.2 `quality_gate.py`

| 优先级 | 难度 | 维度 | 问题 | 方向 |
|--------|------|------|------|------|
| P1 | 中 | 数据新鲜度 | 只读 `*_latest.json`，可能读到**上次**残留 | 校验 `generated_at` 或 run id |
| P2 | 低 | 阈值 | 写死在代码里 | 环境变量/YAML |
| P2 | 中 | 误报 | 已支持质量门禁重试去抖；仍可继续做滑动窗口/多样本策略 | CI 重试 gate、去抖 |

### 2.3 `qa`：`bench` 后立刻 `scan` 偶发失败

| 优先级 | 难度 | 问题 | 方向 |
|--------|------|------|------|
| **P0** | 低 | `security_scan` 先打 `/healthz`，压测后瞬时失败 → **high**，同命令忽绿忽红 | bench 与 scan 之间 **sleep / 重试 healthz**；scan 首跳 retry |

---

## 3. `security_scan.py`（扫描能力 + 延伸）

### 3.1 扫描能力扩展

| 优先级 | 难度 | 项 | 方案摘要 |
|--------|------|-----|----------|
| P1 | 低 | 并发扫描 | Payload/多接口用 **线程池**，配超时 |
| P1 | 中 | 上下文感知 | **[done]** `analyze_sqli_probe`：`SECURITY_SCAN_CONTEXT_AWARE`；报告 JSON 含 `context_aware`；单测 `tests/test_security_scan.py` |
| P2 | 中 | XSS 探测 | `XSS_PAYLOADS` + 反射检测 |
| P1 | 低 | 鉴权 | `AUTH_TOKEN` → `Authorization: Bearer` |

### 3.2 盲注与鉴权（延伸）

| 优先级 | 难度 | 主题 | 方向 |
|--------|------|------|------|
| P2 | 高 | 盲注 (Time-based) | 基线延迟 vs 睡眠 Payload；多次采样减噪 |
| P1 | 低 | 请求头统一鉴权 | `do_request` 内 header 工厂，敏感不落日志 |

---

## 4. `replay_traffic.py`

| 优先级 | 难度 | # | 问题 | 方向 |
|--------|------|---|------|------|
| P2 | 中 | 1 | 串行回放 | 线程池/asyncio |
| P2 | 中 | 2 | 已改按行流式读取；可继续补并发/分片回放 | 按行流式 `yield` |
| P2 | 低 | 3 | 仅 avg 耗时 | P50/P95/P99 |
| P2 | 中 | 4 | 静态 Token/时间 | 动态注入 |
| P1 | 中 | 5 | 无脱敏 | load 阶段掩码 |

---

## 5. `chaos_compare.py` / Agent 混沌对比

| 优先级 | 难度 | # | 问题 | 方向 |
|--------|------|---|------|------|
| P2 | 中 | 1 | baseline 与 chaos **串行** | 多进程 / 双 Job artifact 合并 |
| P3 | 高 | 2 | 单点 fail_rate | 阶梯混沌、成本-成功率曲线 |
| P1 | 中 | 3 | 仅 **avg token** | max/P99 门禁 |
| P2 | 低 | 4 | 已新增 Top-K 高 token case 表；可继续做轨迹聚类/自动根因 | 报告 Top-K + 轨迹摘要（脱敏） |
| P2 | 高 | 5 | 固定 `CHAOS_TOKEN_SURGE_MAX` | 按任务复杂度分桶动态阈值 |

---

## 6. `tests/test_app.py` / `FakeRedis`

| 优先级 | 难度 | # | 问题 | 方向 |
|--------|------|---|------|------|
| P1 | 低 | 1 | `incr` 非原子 | `threading.Lock` |
| P1 | 中 | 2 | 假 TTL | `expire_at` + `get` 时过期 |
| P2 | 中 | 3 | `setup_function` 硬清全局 | Fixtures / `mock.patch` |
| P1 | 低 | 4 | 无 Redis 故障路径 | `broken` → `ConnectionError` |

---

## 7. 技术栈与演示扩展（多为 P3）

| 优先级 | 难度 | 方向 | 备注 |
|--------|------|------|------|
| P3 | 低 | 生产级叙述（分布式限流、脱敏、Chaos Mesh） | 文档/面试边界即可 |
| P2 | 中 | agent-eval 小步增强 | 不改大盘 |
| P3 | 高 | Playwright + Pytest | **有前端**后再做 |
| P3 | 中 | k6 + Grafana | 与 Locust 并存学习 |

---

## 维护约定

- **追加**表格行，不删历史（可 `[done]` 备注）。  
- 与 `AGENT_EVAL_PLAN.md`：本文件偏**工程债与实现**；计划文档偏**功能路线与边界**。  
- **与当前实现一致**时，以 **[`../AI_PROJECT_CONTEXT.md`](../AI_PROJECT_CONTEXT.md)** 为技术事实源；本表 §1.1 中「已 [done]」以源码为准。

---

## 已解决（本轮已落地）

| 日期 | 项 | 变更摘要 | 关联文件 |
|------|----|----------|----------|
| 2026-04-09 | `qa` 偶发红（bench 后 scan） | `qa` 增加 `Wait-AppHealthz`（重试 + 上限），替代固定等待；`scan`/`qa` 统一注入 scan health 重试默认 env | `run.ps1` |
| 2026-04-09 | `security_scan` 首跳健康检查脆弱 | `/healthz` 增加重试与退避，检查项新增 `attempts`，失败 detail 标注 `after N attempts` | `security_scan.py` |
| 2026-04-09 | `quality_gate` 报告可能读旧数据 | 新增报告新鲜度校验（可开关 + 最大年龄可配）并接入 benchmark/security 两段 | `quality_gate.py` |
| 2026-04-09 | `quality_gate` 阈值硬编码 | benchmark 门禁阈值环境变量化（error/p99/p95 factor/unstable）；`run.ps1` 统一默认值 | `quality_gate.py`, `run.ps1` |
| 2026-04-09 | 测试工程化薄弱 | 引入 `conftest.py` + fixtures；FakeRedis 增强（锁/TTL/故障注入）；补参数化与异常路径测试 | `tests/conftest.py`, `tests/test_app.py` |
| 2026-04-09 | 缺少质量门禁单测 | 新增新鲜度与阈值加载测试 | `tests/test_quality_gate.py` |
| 2026-04-09 | 文档与代码偏差 | intro 文档同步新增 env 与 `run.ps1` 新流程说明 | `docs/intro/PROJECT_INTRO_FOR_READERS.md` |
| 2026-04-09 | 熔断恢复语义过于粗糙 | 落地最小 Half-Open（开闸后单探测请求；成功关闭、失败重开），并补 3 条相关测试 | `app.py`, `tests/conftest.py`, `tests/test_app.py` |
| 2026-04-09 | Agent token 仅均值门禁 | 新增 `max_token_per_task` / `p99_token_per_task` 指标与门禁阈值（`chaos_compare`） | `agent-eval/scripts/score_agent_eval.py`, `agent-eval/scripts/chaos_compare.py` |
| 2026-04-09 | `security_scan` 无鉴权头 | 增加 Bearer/API Key 注入支持（环境变量驱动） | `security_scan.py` |
| 2026-04-09 | `quality_gate` 单次抖动易误杀 | 新增可配置重试去抖（attempts + delay），并补对应单测；`run.ps1` 注入默认去抖参数 | `quality_gate.py`, `tests/test_quality_gate.py`, `run.ps1` |
| 2026-04-09 | `replay_traffic` 大文件 OOM 风险 | `load_events` 改流式逐行读取，避免整文件入内存 | `replay_traffic.py` |
| 2026-04-09 | `chaos_compare` 失败定位慢 | 报告新增 No Chaos / Mixed Chaos 的 Top-K 高 token case 表格 | `agent-eval/scripts/chaos_compare.py` |
| 2026-04-09 | 熔断状态不可观测 | 新增状态切换结构化日志（open / half_open / reopen_from_half_open / closed） | `app.py` |
| 2026-04-10 | `healthz` 与 Liveness 语义混淆 | 新增 `/live`（不查 Redis）、`/ready`（Redis 失败 503）；`/healthz` 仍 200 + degraded；流量录制排除新路径；K8s 示例 Deployment 增加探针 | `app.py`, `tests/test_app.py`, `k8s/app-redis.yaml`, `docs/intro/PROJECT_INTRO_FOR_READERS.md` |
| 2026-04-10 | 限流固定秒窗口边界突刺 | 默认改为 Redis 滑动窗口（ZSET + Lua 原子脚本）；`RATE_LIMIT_WINDOW_SEC`；`RATE_LIMIT_ALGORITHM=fixed` 回退旧逻辑；FakeRedis 实现 `rate_limit_sliding_allow` | `app.py`, `tests/conftest.py`, `tests/test_app.py`, `docs/intro/PROJECT_INTRO_FOR_READERS.md` |
| 2026-04-10 | 测开向：扫描误报 + 契约回归 | `security_scan` SQLi 探针上下文分级；`pytest.ini` 标记；`test_api_contract.py` / `test_security_scan.py`；intro 补充命令说明 | `security_scan.py`, `pytest.ini`, `tests/`, `docs/intro/PROJECT_INTRO_FOR_READERS.md` |
| 2026-04-10 | 门禁日志与扫描策略脱节 | `quality_gate.security_report_meta` 摘要 `context_aware` / `target`；契约补幂等命中与 429 体 | `quality_gate.py`, `tests/test_quality_gate.py`, `tests/test_api_contract.py`, `docs/intro/PROJECT_INTRO_FOR_READERS.md` |
| 2026-04-10 | CI 单步 pytest、契约对 503/202 脆弱 | `qa.yml` 先 smoke 再全量；契约补熔断/超时 202 形状；`conftest` 重置 `BUSINESS_TIMEOUT_MS` / `RATE_LIMIT_ALGORITHM`；成功用例重试避 503 | `.github/workflows/qa.yml`, `tests/conftest.py`, `tests/test_api_contract.py`, `docs/intro/PROJECT_INTRO_FOR_READERS.md` |
| 2026-04-10 | `docs/` 下 md 过多难维护 | 合并为 `docs/README.md` 索引；`run/GUIDE.md`（步骤+排查）；`intro/DEEP_DIVE.md`（知识点+题库）；`interview/INTERVIEW_PREP.md`；删旧 8 篇；补 `k8s/CHAOS_LITE.md` | `docs/`、`README.md`、`k8s/CHAOS_LITE.md` |
| 2026-04-10 | 多文档与实现再次漂移 | 新增/强化 **`docs/AI_PROJECT_CONTEXT.md`** 为单页技术事实；根 `README`、`docs/README`、`run/GUIDE`、`intro/PROJECT_INTRO`、本表 §1.1/§2.1 与 **订单 Redis、cb:* 熔断、prometheus_alerts、压测 params** 对齐 | `docs/AI_PROJECT_CONTEXT.md` 等 |

---

## 附录：原「待办列表」一行汇总（已并入上表，便于检索）

| 代码位置 | 并入章节 |
|----------|----------|
| `app.py` 限流/熔断/Redis/观测 | §1.1～1.2 |
| `security_scan` + `run.ps1 qa` 衔接 | §2.3 |
| `benchmark_compare` / `quality_gate` | §2.1～2.2 |
| `security_scan` 扩展与盲注 | §3 |
| `replay_traffic` | §4 |
| `chaos_compare` | §5 |
| `tests` FakeRedis | §6 |

*实现细节以仓库内源码为准；难度/优先级为主观估计，落地时可再调。*
