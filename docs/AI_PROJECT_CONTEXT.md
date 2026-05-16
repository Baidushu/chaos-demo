# chaos-demo 单一全景文档（只读本文件即可理解项目）

> **给 AI 的硬要求**：改代码或回答问题前，**只依赖本文**应能建立正确心智模型；**不要求**再读 `docs/` 下其他 Markdown，也**不要求**通读源码才能做常规任务。  
> **维护约定**：改架构、新主干行为、新默认环境变量、新 CI 步骤时，**必须同步改本文**；细项表格仍可在 `plan/OPTIMIZATION_BACKLOG.md` 记账，但**不是**读项目的必经入口。  
> **其它 `docs/*.md`**：人类导航、面试、长跑题与**工程债表**；**不**重复作为第二套技术事实，见 `docs/README.md` 分层说明。  
> **根路径**：本文件位于 `docs/AI_PROJECT_CONTEXT.md`；下文中「根目录」指仓库根 `chaos-demo/`。  

**对外叙事（面试主线）**：本仓库是 **轻量级质量工程平台（QEP）**——用 **混沌/故障注入、压测、门禁脚本与 CI** 把「不同策略与故障场景下的行为与指标」固化成可重复的评估闭环；**`agent-eval/` 为辅线扩展**（工具调用稳定性），**不是**「AI 主项目」。口述模板见根目录 [`README.md`](../README.md) 文首；**「问题→解决」、CI 决策链、降权话术**见 **§1.0**。测试分层与 failure model 见 [`TEST_STRATEGY.md`](TEST_STRATEGY.md)；benchmark 行为解读见 [`PERFORMANCE_ANALYSIS.md`](PERFORMANCE_ANALYSIS.md)。

---

## 1. 项目目标（为何存在）

- **平台主线（质量工程）**：在可部署的订单服务上，把 **韧性治理**（限流、熔断、超时、幂等、可观测、流量录制）与 **HTTP 故障注入**（可建模的失败）串成可测对象；用 **压测对照**（治理 vs 基线）、**安全扫描** 与 **质量门禁** 把指标与阈值自动化，支撑「是否可发」的**工程化判断**（教学/演示量级）。  
- **服务载体**：Flask + Redis 实现订单语义与治理钩子；详见 §2.1。  
- **扩展辅线（`agent-eval/`）**：**非核心 AI 产品**，而是一个**简单的扩展模块** —— 在 **HTTP 工具调用**路径上，用规则/可选 LLM 规划器模拟「调下单接口」等行为，结合**客户端 chaos** 做 **无故障 vs 故障** 对照与门禁，用于回答「**不稳定环境下工具调用与重试策略是否失控**」；与订单服务**进程隔离**，面试中应**降级叙述**，避免喧宾夺主。  

### 1.0 面试叙事与口径（问题 → 解决 · CI · 降权）

> 本节给**人类面试**：先讲**解决了什么问题**，再讲手段；技术事实仍以本文后续章节与代码为准。

#### 「问题 → 解决」（不要只报「我实现了限流/熔断」）

面试官要听的是 **发现或预设了什么风险**，以及 **为什么选这个手段**。可按下表口述（数值以压测报告与门禁为准，教学/演示量级）：

| 现象或风险 | 你怎么知道 / 怎么证 | 引入的手段 |
|------------|---------------------|------------|
| **高并发下错误率、尾延迟波动大**，容易发生**过载级联** | **压测对照**（治理 **5000** vs 基线 **5001**）可重复观察 | **限流**削峰；**熔断**快速失败、避免雪崩；**超时预算** → **202** 提前降级，释放临界区 |
| **重复请求导致重复写单** | 并发与重试场景 | **Redis 幂等**（占位 → 成功态），同 key 冲突 **409** |
| **下游 Redis 不可用或抖动** | 单测 + 真 Redis 集成 | 限流/熔断对 Redis 异常 **fail-open**（与「业务读 Redis 失败 503」策略区分，见 §2.1） |
| **故障场景依赖手工点、难回归** | 演示与压测里不易稳定复现「坏」 | **可编程故障注入**（见下段） |

#### 可编程故障注入（从「功能」升级到「亮点」）

- **一句话**：实现了一套 **可编程故障注入**：通过 **`/fault/*` HTTP API** 动态注入 **latency / drop / exception / slow_db**，故障状态落在 **Redis 键 `fault:{type}`**，带 **`TTL` / `ttl_sec`**，**到期自动恢复**，无需改代码、发版才能切场景。  
- **结合测试**：`tests/test_fault_injection.py`、`fault_demo.py` 可把场景**固化**；**主 CI（`qa.yml`）** 当前以单测 + 压测 + gate + `chaos_compare` 为主，**故障注入能力是可插的验证钩子**——面试可讲：「可在流水线里加一步注入/清除，自动验证抗故障行为」（扩展空间如实说即可）。  

#### CI 主线 = **发布决策**，不是「跑完测试图个心安」

建议按顺序背：**单测**（FakeRedis，快）→ **起真实栈**（compose）→ **压测**（`benchmark_compare` → `benchmark_latest.json`）→ **安全扫描** → **`chaos_compare --strict`**（辅线）→ **`trace_timeline.py`**（从 trace 生成 **`reports/trace_timeline_latest.{mmd,html}`**，默认 chaos arm）→ **`unified_quality_gate.py`**（读 benchmark + security + **`agent_eval_latest.json`**，**任一 FAIL 则 `exit 1`**）→ **`unified_summary.py`**（**平台统一摘要**：`final_decision`、`reasons[]`、`signals[]`、**`artifacts[]`** 与 **`metrics_snapshot`**；**只读汇总**，Gate 失败时 CI 仍生成便于排障）。仅压测+安全、不跑 agent 时仍可用 **`quality_gate.py`**，或设 **`UNIFIED_GATE_SKIP_AGENT=1`**。  

**要点**：`quality_gate` 的目标是 **基于指标的合入/发布判断**，不是单纯「全绿」；详见 **§7**、**§10**。

#### `agent-eval` 必须降权（面试勿当主线）

- ❌ 「我做了 **AI Agent** 评估项目」  
- ✅ 「**扩展模块**，看 **HTTP 工具调用**在不稳定条件下 **重试与失败** 是否越线；**主线仍是质量工程平台（QEP）**」。  

#### 少讲 Flask 实现细节，多讲**治理切面**

- 面试优先讲：**请求进入后的治理顺序**、**故障注入作用点**、**Prometheus `/metrics`**、**结构化日志**利于 **ELK/Loki**。  
- **`before_request` / 路由注册**等见 **§2.1 A**，回答时**一句 Web 框架带过即可**，除非面试官追问实现。

#### 性能回归与历史趋势（王炸说法 + 诚实边界）

- **门禁已做的回归**：`quality_gate.py` 对 **protected** 相对同一次压测里的 **baseline** 校验 **p95 回归倍数**（`QUALITY_GATE_P95_REGRESSION_FACTOR_MAX` 等），并约束 **error / p99 / unstable / p95 抖动** —— **变差可 fail**。  
- **历史归档**：`benchmark_history/` + **`benchmark_trend_latest.*`** 与**历史中位数**对比 delta，适合**讲波动、讲趋势**；**`quality_gate.py` 主链仍不读 trend**；**可选**在 **`unified_quality_gate.py`** 中通过 **`UNIFIED_GATE_TREND_ENABLED=1`** 启用 **P3** 与历史 P95 比值的单条规则（默认关，见 **§10**）。  

#### 测试分层一句（对齐 [`TEST_STRATEGY.md`](TEST_STRATEGY.md)）

**单测（FakeRedis）→ 接口/契约 → 系统（compose + 故障注入）→ 压测 → 质量门禁**；分层表以 `TEST_STRATEGY` 为准。  

#### 结构化日志（你已具备，面试要主动说）

- 服务侧 **`LOG_FORMAT=json`（默认）** 时，关键路径可输出 **JSON 行**（含 **`event`**、**`request_id`** 等），便于 **ELK/Loki** 解析与检索；见 **§2.1 A**、**§6**。  

### 1.1 近期已落地工程化（维护者速览）

| 域 | 已做 |
|----|------|
| **工程结构** | 业务与韧性实现拆到 **`chaos_service/`**（`http_api` / `resilience` / `store` / **`fault_injection`** / `traffic`），`app.py` 持 **Flask `app`**、**Prometheus 指标**、**配置常量** 并 `register_routes`；**`Dockerfile`** 同时 `COPY app.py` 与 **`COPY chaos_service ./chaos_service`**。 |
| **压测/门禁** | 同上；另 **`BENCHMARK_RUNS`（多轮中位数）**、**`reports/benchmark_history/`** 归档、**`benchmark_trend_latest.json` / `.md`**（与历史**中位数**比 delta）；**CI** 在 Benchmark 步设 `BENCHMARK_RUNS: "3"` 等。 |
| **可观测** | 仓库内 **`prometheus_alerts.yml`** 示例告警，compose 挂载到 Prometheus；**无 Alertmanager** 时仅 Prometheus UI 中可见 firing。 |
| **限流/熔断** | **限流**早先即 **Redis** 键（按 IP 滑动/固定桶），**多 worker/多实例共享同一上限**；**熔断**自本迭代起也落在 **Redis**（`cb:open_until` / `cb:failures` / `cb:probe`），与进程解耦，**多 gunicorn worker 行为一致**；`CIRCUIT_PROBE_TTL_SEC` 控半开探测占坑 TTL。 |
| **应用语义** | 建单 **202 超时**按 **`elapsed+计划时间` 与 `BUSINESS_TIMEOUT_MS` 的端到端预算**；**`X-Request-Id`** 回显；韧性关键路径 **JSON 行日志**；**`validate_resilience_config()`**（import 不 ping Redis）。 |
| **订单与部署** | 订单在 **Redis** `order:{id}`，**`ORDER_TTL_SEC`**（compose/k8s/默认一致）；**`Dockerfile` `gunicorn --workers 2`**。 |
| **agent-eval** | **辅线**：见 **§8**；CI 用 `rule` + `AGENT_EVAL_SKIP_JUDGE` 等**能跑、能门禁**；**`chaos_compare`** 子进程设 **`CHAOS_SUBPROC_TIMEOUT_SEC`（默认 1200s）** 防挂起。**叙事上**强调「工具调用稳定性评估」，**不要**把本仓讲成 AI 主项目。 |
| **HTTP 故障注入** | **可编程故障注入**：`/fault/*` **HTTP 动态**注册 **`latency` / `exception` / `drop` / `slow_db`**，Redis **`fault:{type}` + TTL 自动恢复**；`http_api` 在**业务请求入口**调用 **`apply_faults`**（探活/指标/`/fault` 自身不套娃）；关 **`ENABLE_FAULT_INJECTION`** 则跳过。 |
| **可选 LLM 辅助** | 根目录 **`llm_client.py`**（Ollama / OpenAI 兼容端点）、**`llm_assist.py`**（CLI：测试草稿、`analyze-report`、`analyze-logs`、`complete-cases`、`explain-code`、`contract-audit`）；**不进 CI 主链**，无额外 pip 依赖。 |
| **接口自动化样例** | **`api-automation-demo/`**：**独立** pytest 工程（**httpx**、**YAML** 参数化、**Allure**、重试与日志封装）；在子目录本地 **`pytest`**（可选 **`--alluredir`**）；不设 **`API_AUTOMATION_BASE_URL`** 时常为 **MockTransport**，设后可对已起的 **5000** 联调。见 **§2.1 L**。 |

---

## 2. 根目录与一级结构（你会在仓库里看到什么）

| 路径 | 作用 |
|------|------|
| `app.py` | Flask 入口与指标、配置、委托 **`chaos_service`** 注册路由与钩子（见 §2.1 A） |
| `chaos_service/` | **`http_api`**（路由/钩子）、**`resilience`**（限流/熔断/日志）、**`store`**（订单与幂等 Redis 语义）、**`fault_injection`**（动态故障与 `/fault/*` 逻辑）、**`traffic`**（录制与脱敏） |
| `docker-compose.yml` | 起 `app`(5000)、`app_baseline`(5001)、`redis`、`prometheus`、`grafana` |
| `Dockerfile` | 构建应用镜像；复制 `app.py` 与 `chaos_service/` |
| `benchmark_compare.py` | HTTP 压测 5000 vs 5001；写 `reports/benchmark_latest.json`、**历史归档**、**`benchmark_trend_latest.*`**（见 §2.1 B） |
| `security_scan.py` | 对 `SECURITY_SCAN_BASE_URL` 做轻量安全扫描，写 `reports/security_scan_latest.json` 与 `.md` |
| `quality_gate.py` | 读 benchmark + security 报告，超阈值或报告过旧则 `exit 1`（**不含** agent-eval；CI 主链已改用 **`unified_quality_gate.py`**） |
| `unified_quality_gate.py` | **P2 + P3**：串联 benchmark/security、**可选 benchmark_trend**、**`gate_agent_eval`**；写 **`reports/unified_quality_gate_latest.json`**（见 **§10**） |
| `unified_summary.py` | **平台统一摘要（P0/P6）**：聚合 gate / benchmark / trend / eval / chaos / prompt / trace 路径，写 **`reports/unified_summary_latest.json`** 与 **`.md`**（**`schema_version`**）；不改变子报告格式 |
| `trace_timeline.py` | **P6 静态时间线**：读 Agent trace JSON，写 **`reports/trace_timeline_latest.{mmd,html}`** 与 **`trace_timeline_meta.json`**；契约见 **`docs/plan/TRACE_CONTRACT.md`** |
| `replay_traffic.py` | 从 JSONL 流式读请求并重放，写 `reports/traffic_replay_*.json/.md` |
| `fault_demo.py` | 需**已运行**的 API：编排注入延迟/丢包/清除，写 **`reports/fault_demo_latest.json`**（演示用） |
| `llm_client.py` | 可选 LLM 客户端（**`LLM_BACKEND`** 等，见 §6） |
| `llm_assist.py` | 可选 CLI：**`generate-tests`**、**`analyze-report`**、**`analyze-logs`**（抽样日志）、**`complete-cases`**（jsonl/yaml 草稿）、**`explain-code`**、**`contract-audit`**（均须人审；见模块 docstring） |
| `run.ps1` | Windows 下一键：compose、pytest、bench、scan、gate、qa、agent 相关等 |
| `pytest.ini` | 注册标记 `smoke`、`contract` 等（见 `pytest.ini` 正文） |
| `sample-data/` | 示例 JSONL 等，供回放/学习 |
| `locustfile.py` | 可选 Locust 压测，与 `benchmark_compare` 不同路 |
| `prometheus.yml` | Prometheus 主配置（含 **rule_files** 指向同挂载目录下告警） |
| `prometheus_alerts.yml` | 示例 **告警规则**（5xx/限流/降级等），与 compose 中 Prometheus 卷挂载；未配 Alertmanager 时仅在 Prometheus **/alerts** 可见 |
| `grafana/provisioning/`、`grafana/dashboards/` | 数据源与大盘 |
| `tests/` | 全部单测，见 §9 |
| `agent-eval/` | **扩展**：工具调用稳定性评估脚本与数据集，见 **§8**（**非**质量工程主线） |
| `api-automation-demo/` | **独立**：pytest + httpx + **YAML** 数据驱动 + **Allure**；在子目录本地运行，证明接口自动化范式，**不与** `app.py` 同进程 |
| `k8s/` | 可选 K8s 清单、`CHAOS_LITE.md`、Chaos 脚本，**不跑 CI 默认流程** |
| `.github/workflows/qa.yml` | CI 流水线，见 §7 |
| `reports/` | 运行产物（benchmark、**benchmark_history**、**benchmark_trend**、security、replay、流量录制等） |

---

## 2.1 各文件**实现方法**与技术选型（读本节即知「怎么做的」）

以下按**源文件**说明**算法/库/ I/O 方式**；与 §5 业务语义配合阅读。

### A. `app.py` 与 `chaos_service/`（Flask 与拆分模块）

| 方面 | 实现方法 |
|------|----------|
| **面试优先讲** | **治理与观测切面**：请求进入后的 **限流→熔断→幂等→超时预算** 顺序、**故障注入**在**业务入口**的生效点、**Prometheus** 延迟/计数、**JSON 行日志**（ELK/Loki）；**不必**展开 Flask **路由表**除非对方追问。 |
| 分工 | `app.py` 创建 **`Flask(__name__)`**、**`redis_client`**、**`prometheus_client` 各 Counter/Histogram**、从环境读**全局配置常量**，执行 **`validate_resilience_config()`** 后由 **`http_api.register_hooks` / `register_routes(app, CTX)`** 挂路由；`CTX` 为 **`sys.modules[__name__]`**，子模块经 `ctx` 读同一套配置与客户端。 |
| `chaos_service/http_api.py` | 注册 **`before_request` / `after_request`**、**业务路由**（建单/查单/取消/健康/指标等）；**`before_request`** 中（路径非 `/fault`、非探活/指标）调用 **`fault_injection.apply_faults`**：`drop`→**503**，`exception`→**RuntimeError**（框架转 500），`latency`/`slow_db`→**sleep** 后继续；**`/fault/*`** 路由注册在同一文件。 |
| `chaos_service/fault_injection.py` | **`inject_fault` / `clear_fault` / `list_faults`** 等；**`apply_faults`** 返回 `drop`/`exception`/`latency` 语义供钩子处理；参数校验与 **`FAULT_*`** 上限见模块顶。 |
| `chaos_service/resilience.py` | 限流 Lua、**熔断** ZSET/SET、超时判断、**JSON 行日志**辅助。 |
| `chaos_service/store.py` | **订单** `order:{id}`、幂等 **`idem:{key}`**（`processing` 占位、**`IDEM_PENDING_TTL_SEC`**、冲突检测、**`IDEM_WAIT_*` 轮询**等，与 §5 幂等一致）。 |
| `chaos_service/traffic.py` | 流量录制线程与脱敏。 |
| Web 框架 | 标准 **Flask**；路由**实现**在 `http_api` 中集中注册。 |
| 指标 | 各 Counter/Histogram 在 **`app.py` 模块级定义**，由路由与钩子代码路径递增（与拆分前**同一**指标名/语义）。 |
| 请求 ID / 可追踪 | `before_request`：无/非法 `X-Request-Id`（空、>256 字符）则生成 uuid；合法则截断至 128 字符。`after_request`：所有响应回写 **`X-Request-Id`** 头。 |
| 请求耗时可观测 | `before_request` 记 `request._start_time`；`after_request` 用耗时写 `Histogram`/`Counter`，5xx 计 `REQUEST_ERRORS`。 |
| 配置校验 | `validate_resilience_config()` 在模块 import 后执行：限流/熔断/窗口/`INVENTORY_BUSY_PROB` 等**数值与枚举**非法则 **`SystemExit(1)`**；**不**在 import 时 `ping` Redis（以免本机无 Redis 时 pytest 无法 import）。 |
| 限流-滑动 | **Redis ZSET**；键 `rl:sw:{ip}`。通过 **`redis.client.register_script` 注册 Lua 脚本**（`ZREMRANGEBYSCORE` 清窗口外、`ZCARD` 计数、`ZADD` 记本次、`EXPIRE`），保证原子性。成员名 `时间戳+uuid` 防碰撞。单测用 `FakeRedis.rate_limit_sliding_allow` 复现同一语义。 |
| 限流-固定桶 | `RATE_LIMIT_ALGORITHM=fixed` 时，键 `rl:{ip}:{epoch秒}`，**`INCR` + 短 TTL(2s)**。 |
| 限流-异常 | 任意 `redis.RedisError` → **允许通过**（fail-open），避免 Redis 全挂时业务全死。 |
| 幂等 | Redis 键 `idem:{X-Idempotency-Key}`；先 **`SET NX + TTL`** 占位 `processing`，成功后写 `succeeded + order_id`，重复请求可 **200 回放**；同 key 不同 payload **409**；旧版「直接存 order_id」格式仍兼容读取。 |
| 订单 | 订单 JSON 存 **`order:{order_id}`**，**`setex` + `ORDER_TTL_SEC`**；`GET/PUT` 查改；与幂等 `idem:` **分离**；**多 gunicorn worker** 共享。 |
| 熔断 | **Redis 全局**：`cb:open_until` 存「开闸截止时间」、**`cb:failures` 为 ZSET**（分数字段=失败时间）、`cb:probe` 为半开**SET NX+TTL** 占坑；**多 worker/多容器共享**；`BREAKER_WINDOW_SEC` 内用 `ZREMRANGEBYSCORE` 清窗后 `ZCARD` 与阈值比；`CIRCUIT_PROBE_TTL_SEC` 控探测键 TTL；`is_circuit_open` 在 **Redis 异常时 fail-open**（放行，与限流对 Redis 异常策略区分）。 |
| 半开 | 当 `open_until>0` 且 `now>=open_until`：若 `cb:probe` 已存在则他 worker 在探测、本请求 **202**；否则 **SET NX** 抢探测权；成功/失败/计数仍写 Redis。 |
| 结构化日志 | 限流 429、熔断 202、超时 202、库存 503 等路径打 **JSON 单行** `app.logger.info`，含 **`event`**、**`request_id`** 与关键数字（如 `elapsed_ms`、`budget_ms`），便于日志系统解析。 |
| 超时预判（进锁前） | 先抽 `processing_time = random.uniform(0.01, 0.05)`（与锁内 sleep 相同）。**端到端预算**：`elapsed = now - request._start_time`，若 **`ENABLE_RESILIENCE` 且 `elapsed + processing_time > BUSINESS_TIMEOUT_MS/1000`** 则 **202**（`reason` 仍为 **`timeout protected`**），不进锁（与限流/幂等前排队时间**同一时钟**）。 |
| 业务临界区 | `db_lock` 只包住**建单**路径中的 sleep + 模拟 503 + **`_put_order_in_store` 之前**（写 Redis 在锁内失败则 503）。查单/取消**不**持该锁。 |
| 健康检查 | `/live` 不访问 Redis；`/ready` `redis.ping()`；`/healthz` 始终 200 兼容脚本。 |
| 流量录制 | 若 `TRAFFIC_RECORD_ENABLED`：后台**守护线程**从 `queue.Queue` 取事件写 JSONL，主线程在 `after_request` 中 **无阻塞 `put_nowait`**，队满则丢；`before_request/after` 不录健康/指标等路径。脱敏用正则+字典处理 `body/query`；**实现**在 `traffic` 中。 |
| 指标出口 | 模块级 `Counter`/`Histogram` 在 `app.py` 定义，**`generate_latest()`** 出 **`/metrics`**。 |

### B. `benchmark_compare.py`（压测与对照）

| 方面 | 实现方法 |
|------|----------|
| HTTP 客户端 | 标准库 **`urllib.request`**（**短连接**每次 `Request`+`urlopen`），**非** 持久连接池。 |
| 并发 | `concurrent.futures.ThreadPoolExecutor`；`main` 中基线与治理**各**重复 `runs` 轮，最后输出**中位数聚合**。 |
| 参数与可复现 | **`argparse`**：`-n/-c`、`--baseline-url` / `--protected-url`、**`--seed`**、**`--warmup`**、**`--runs`**。环境变量：**`BENCHMARK_*`**，其中 `BENCHMARK_RUNS` 默认 `3`。同一脚本运行内额外生成 `session_id`，降低重复跑时与旧 Redis 幂等数据串单。 |
| 幂等键 | **无 `seed`** 时每请求 `uuid4()`。**有 `seed`** 时为 `bench-{run_label}-s{seed}-n{序号}`；实际 `run_label` 会带 **session + scenario + round**，既避免两实例共 Redis 时串单，也避免多轮统计时复用同键。 |
| 单次请求 | `POST {base}/order`，JSON 体；`timeout=5` 秒。 |
| 延迟分位 | 收集所有样本延迟后，用 **`statistics.quantiles(latencies, n=100)`** 取近似 **P50/P95/P99**（下标 49/94/98）。**非**HdrHistogram 库。 |
| 健康预检 | 压测前对**两 URL** 各 `urlopen(…/healthz, timeout=3)`，失败则 `sys.exit(1)` 并打印中文提示。 |
| 报告 | `result = { generated_at, params, baseline, protected, … }`；顶层 `baseline/protected` 为**多轮中位数聚合**；`generated_at` 供门禁新鲜度；另写 **`reports/benchmark_latest.json`**。 |
| 历史与趋势 | 快照归档到 **`reports/benchmark_history/benchmark_*.json`**，保留份数由 **`BENCHMARK_HISTORY_KEEP`**（默认 **20**）控制；与最近 **`BENCHMARK_TREND_WINDOW`**（默认 **10**）份历史比 **中位数**，输出 **`reports/benchmark_trend_latest.json`** 与 **`.md`**。 |
| 打印 | 控制台输出**中位数表**、**Run Spread**（含 P95 波动）与聚合状态计数；并提示 trend 落盘路径。 |

### C. `security_scan.py`（安全扫描）

| 方面 | 实现方法 |
|------|----------|
| HTTP | 同 **`urllib.request`**，统一 `do_request(method, path, …)` 返回 `status, text, elapsed_ms`。支持 Bearer 与 `X-Api-Key` 类头。 |
| 健康 | `health_check_with_retry`：循环 `GET /healthz`，`SECURITY_HEALTH_RETRY_*` 控制次数与睡间隔。 |
| SQLi | 多 payload 对 `POST /order`；`ThreadPoolExecutor`（`SECURITY_SCAN_WORKERS`）与串行两模式，结果有序合并。每 payload 用纯函数 **`analyze_sqli_probe(status, text, payload)`** 产 findings（与 UI 解耦、可单测）。 |
| 上下文感知 | 开关 **`SECURITY_SCAN_CONTEXT_AWARE`**；5xx/0 时若体用 **`re`（`SQL_BODY_DB_SIGNAL`）** 匹配到 DB/SQL 栈才 high，否则仅 medium；2xx/4xx 对 payload 回显分档 severity。 |
| 其他检查 | 路径风路径探测、多 endpoint 的敏感词 **`SENSITIVE_PATTERNS` 正则** 扫 body。 |
| 失败策略 | 报告 JSON 内 `findings`；`main` 中 `should_fail` 用 **`SEVERITY_RANK` 与 `SECURITY_FAIL_ON`** 比等级，`sys.exit(1)`。写 JSON + MD。 |

### D. `quality_gate.py`（质量门禁）

| 方面 | 实现方法 |
|------|----------|
| 输入 | 读**磁盘**上 `reports/benchmark_latest.json`、`reports/security_scan_latest.json`（`open`+`json.load`），**不**调 HTTP 再测。 |
| 重试 | `run_check_with_retries`：循环调用子检查函数，子检查内部 **`fail()` 为 `print`+`sys.exit(1)`**，被包装成 `SystemExit` 后用 **`except SystemExit: raise` 在次数未用尽时 `sleep` 再试**。即重试=重新跑**同一进程内**的读文件+判定。 |
| benchmark 规则 | 从 JSON 取顶层 `data["baseline"]` / `data["protected"]` 的**中位数聚合结果**与可选 `protected_summary.summary.p95_ms.stdev`；对 absolute error/p99、protected p95 相对 baseline 的倍数、**unstable=degraded_rate+error_rate** 上界做判断，必要时可再校验 **P95 抖动**。 |
| 新鲜度 | 读 `generated_at` 与当前时间差，超 `QUALITY_GATE_MAX_REPORT_AGE_SEC` 则失败。 |
| 安全子检查 | 统计 findings 的 severity 与 `SECURITY_FAIL_ON` 比较；`security_report_meta` 从 JSON 里取 `context_aware`、`base_url` 打日志。 |
| 无依赖 | 仅用 **stdlib + pathlib**，**无** pandas/科学计算库。 |

### E. `replay_traffic.py`（流量回放）

| 方面 | 实现方法 |
|------|----------|
| 读入 | **`iter_events`**：对 JSONL **按行** `read()` → `json.loads` **流式 yield**，**不** `read_text` 整文件，防大文件 OOM。 |
| 重放 | 每行事件拼 URL（path+query），`urllib.request.Request` 按 method/body/headers 发送；`argparse` 支持 `base_url`、`--limit`、`--timeout` 等。 |
| 报告 | 汇总成功数、按 path 聚合计数、写 JSON 与 MD。 |

### F. `tests/conftest.py` 与 `FakeRedis`

| 方面 | 实现方法 |
|------|----------|
| 测试双模 | 替换 `app_module.redis_client` 为 `FakeRedis()`，在内存用 **dict+锁** 模拟 `get/setex/incr/expire/ping` 等。 |
| 滑动限流 | `rate_limit_sliding_allow(…)` 在锁内做与 Lua 等价的裁窗+计数+拒绝逻辑。 |
| 故障 | `broken=True` 时 `ping/get` 等抛 **`redis.ConnectionError`**，走应用 fail-open 等分支。 |
| 夹具 | 新 **`FakeRedis()`** 每测隔离；`FakeRedis` 补 **`set`/`delete`/`zadd`/`zremrangebyscore`/`zcard`** 以支撑熔断键；重置 `BUSINESS_TIMEOUT_MS`/`ORDER_TTL_SEC`/`RATE_LIMIT_ALGORITHM` 等。 |

### G. `run.ps1`（Windows 编排）

| 方面 | 实现方法 |
|------|----------|
| 实现语言 | **PowerShell**；`param([ValidateSet(...)])` 子命令。 |
| 健康等待 | 函数 `Wait-AppHealthz`：`Invoke-WebRequest` 轮询 `SECURITY_SCAN_BASE_URL` 或默认 `http://127.0.0.1:5000/healthz`，失败睡间隔再试，超限 `throw`。 |
| 环境注入 | `Set-DefaultSecurityScanRetryEnv` / `Set-DefaultQualityGateEnv` 仅在变量未设时写默认值。 |

### H. `agent-eval/scripts`（共性与差异）

| 方面 | 实现方法 |
|------|----------|
| 语言与配置 | 纯 Python；**gate 门槛** 多数从 **`config/eval_config.yaml` 的 `gate:` 解析**（`gate_agent_eval.py` / `judge_local` 等，部分用极简 YAML 解析或 PyYAML 视脚本而定—以该脚本为准）。 |
| HTTP 工具侧 | `tools_client` 等对 **ORDERS 服务** 发真实 HTTP，可注入 chaos（延迟/失败）模拟不稳定后端。 |
| 对照 | `chaos_compare.py`：两轮跑分（如 none vs mixed），比 retry、token、**CHAOS_*** 系列门禁，**`--strict` 时失败即 `sys.exit(1)`**（适合 CI）。 |
| 方差 | `eval_variance.py`：改 `EVAL_SEED` 多轮，汇总 mean/min/max/stdev。 |
| 报告 | 写 `agent-eval/reports/*.json` 与 `.md`。 |

### I. 可观测与编排（基础设施）

| 方面 | 实现方法 |
|------|----------|
| Prometheus | 拉 `app:5000/metrics`；`prometheus.yml` + **`prometheus_alerts.yml`** 在 compose 里挂卷；规则评估 **5xx/限流/降级** 等（demo 量级阈值）。 |
| Grafana | 预置 **provisioning** 自动数据源与看板（JSON 在 `grafana/`）。**未**在仓库内用 Terraform。 |
| Compose | 多服务 **bridge 网络**；`app` 可带 `cap_add: NET_ADMIN` 供本仓库网络实验/演示（与上表应用逻辑无强耦合）。 |
| 应用镜像 | **`Dockerfile`**：`gunicorn` 绑定 `0.0.0.0:5000`，**`--workers 2`（默认可调）**；**订单在 Redis** `order:{order_id}`（JSON、TTL 见 `ORDER_TTL_SEC`），多 worker **共享**同一 Redis，查单/取消与进程数一致。 |

### J. 可编程 HTTP 故障注入 API 与 `fault_demo.py`

| 方面 | 实现方法 |
|------|----------|
| 管理端点 | **`GET /fault/status`**：列出活跃故障与默认上限；**`POST /fault/inject`**：JSON `type`（`latency`/`exception`/`drop`/`slow_db`）、`params`、可选 **`ttl_sec`** → **201**；**`POST /fault/clear`**：`type` 清除单类；**`POST /fault/clear-all`**；**`DELETE /fault/inject/<fault_type>`** 同清除。 |
| `fault_demo.py` | **`urllib.request`** 调上述 API；对比基线与故障下延迟/错误，汇总写入 **`reports/fault_demo_latest.json`**。 |

### K. `llm_client.py` / `llm_assist.py`（可选）

| 方面 | 实现方法 |
|------|----------|
| HTTP | 标准库 **`urllib.request`**；**Ollama** 走 `/api/chat`，**OpenAI 兼容**走 `/chat/completions`。 |
| `LLMClient` | **`LLM_BACKEND`**：`auto`（先探 Ollama `/api/tags`，再需 **`LLM_API_KEY`**）、`ollama`、`openai`；**`OLLAMA_ENDPOINT`**、**`LLM_BASE_URL`**、**`LLM_MODEL`**、**`LLM_TIMEOUT_SEC`** 等见 §6。 |
| `llm_assist.py` | **`argparse`** 子命令：**`generate-tests`**、**`analyze-report --report <path>`**、**`analyze-logs --input <jsonl>`**、**`complete-cases --format jsonl|yaml`**、**`explain-code --path <py>`**、**`contract-audit`**；提示词内嵌 API 说明（含 **`/fault/*`**）。产出默认在 **`reports/llm_*`**，**不**代替 pytest/门禁。 |

### L. `api-automation-demo/`（独立接口自动化样例）

| 方面 | 实现方法 |
|------|----------|
| 与主服务关系 | **同仓、不同进程、不 import `app`**；自有 **`requirements.txt`**，证明「pytest + HTTP 客户端 + 数据驱动」范式，**不替代**根目录 `tests/`。 |
| HTTP | **httpx**；**`lib/client.py`** 的 **`LoggingHttpClient`** 打印 method、路径、状态码与耗时。 |
| 数据驱动 | **`data/api_cases.yaml`**（或增改同目录 YAML）；**`conftest.py`** 中 **`pytest_generate_tests`** 按 `cases` 列表参数化。 |
| 双模式 | 未设 **`API_AUTOMATION_BASE_URL`**：**`httpx.MockTransport`** 按用例 `mock` 或特例（如 **`flaky_ok_mock`** 的前两次 503）返回；设置 base URL 时对**真实服务**发请求（联调用例需与快照一致）。 |
| 重试 | **`lib/retry.py`** 的 **`retry_call`**；YAML 中 **`retry: true`** 且对 **5xx** 在测试中转为异常以触发重试。 |
| Allure | **`allure-pytest`**；本地/CI 使用 **`pytest --alluredir=allure-results`**；工作流上传 **artifact**（原始结果，非必须再跑 `allure generate`）。 |
| 面试总述 | 本仓库「测什么、怎么分层、failure model」见 **[`TEST_STRATEGY.md`](TEST_STRATEGY.md)**；压测口径见 **[`PERFORMANCE_ANALYSIS.md`](PERFORMANCE_ANALYSIS.md)**。 |

---

## 3. 如何运行（最低限度命令，读到这里就能动手）

**前置**：本机有 **Docker**（开发常用 Docker Desktop on Windows）与 **Python 3.10+**。

1. 启动全部服务：在根目录  
   `docker compose up --build -d`  
2. 浏览器访问 `http://127.0.0.1:5000/healthz`（应返回 JSON）。治理版 5000，基线 5001。  
3. 单测：  
   `pip install -r requirements-dev.txt`  
   `pytest tests/ -m smoke -q`（快）再 `pytest tests/ -q`（全量，与 GitHub CI 二段式一致）  
4. 压测（需服务已起）：`python benchmark_compare.py` → 生成 `reports/benchmark_latest.json`；可选 `-n`、`-c`、`--seed`、`--warmup` 或 `BENCHMARK_*`（见 §2.1 B）。**CI** 通常设 `BENCHMARK_WARMUP` 与 `BENCHMARK_SEED` 以稳定首轮。    
5. 安全扫描：`python security_scan.py`（默认打 `http://127.0.0.1:5000`）  
6. **仅主链后半**时：先跑通 agent 评分（如 `agent-eval/scripts/chaos_compare.py` 或 `run_agent_eval` → `score_agent_eval`），再 `python unified_quality_gate.py`（依赖 **`agent-eval/reports/agent_eval_latest.json`**）。若只做压测+安全、不跑 agent，可用 `python quality_gate.py`，或设 **`UNIFIED_GATE_SKIP_AGENT=1`**。  
7. （可选）故障演示：服务已起时 `python fault_demo.py`；或自行 `curl` 调 **`/fault/inject`** 等（见 §4）。  
8. （可选）LLM：`python llm_assist.py --help`（需 Ollama 或 **`LLM_API_KEY`**，见 §6）。  
9. （可选）**`api-automation-demo`**：在 `api-automation-demo/` 下 `pip install -r requirements.txt` 后 **`pytest`**（或带 **`--alluredir`**）；联调已起服务时设 **`API_AUTOMATION_BASE_URL`**；见 **§2.1 L**。

**Windows 脚本**（在根目录 PowerShell，必须用 `.\run.ps1 -Task <名>`，不能直接敲 `agenteval`）：  
| Task | 作用 |
|------|------|
| `up` / `down` | compose 起 / 停 |
| `test` | 装 dev 依赖 + `pytest -q` 全量 |
| `bench` / `scan` / `gate` / **`unified`** | 压测 / 安全扫描 / 仅主链 **`quality_gate`** / **P2 汇总门禁** |
| `qa` | pip + 全量 pytest + bench + 循环等 healthz + scan + gate |
| **`qafull`** | 同 `qa` 但去掉单独 `quality_gate`，在 **`chaos_compare --strict`** → **`trace_timeline.py`** → **`unified_quality_gate.py`** → **`unified_summary.py`**（与 CI 主链一致） |
| `agenteval` | 依次跑 `run_agent_eval` → `score` → `gate` |
| `agentchaos` | 仅 `chaos_compare.py` |
| `replay` | 默认读 `reports/traffic_record_latest.jsonl` 回放 |
| `help` | 打印说明 |

**常见坑**：**未** `docker compose up` 就跑 bench/scan 会连不上 5000；PowerShell 里 `pytest / .\run.ps1` 是错误写法，应分号或分两行；Agent 与订单服务用同一 `5000` 时必须先起应用容器。

---

## 4. HTTP 接口与典型状态码（`app.py`）

| 方法 | 路径 | 行为摘要 |
|------|------|----------|
| POST | `/order` | 体为 JSON `item_id`、`quantity`；可带 `X-Idempotency-Key`、**`X-Request-Id`**（可缺省，响应回显）。`ENABLE_RESILIENCE=true` 时：限流 → 熔断 → 幂等 → **若自请求开始至计划锁内耗时之和将超** `BUSINESS_TIMEOUT_MS` 则 **202**（`timeout protected`）；否则进锁，小概率 **503**；成功 **201** 或幂等 **200**。`ENABLE_RESILIENCE=false` 时多数韧性链不执行。 |
| GET | `/order/<order_id>` | 从 **Redis** 读 `order:{id}`。返回白名单字段；无单 **404**；Redis 不可用约 **`order store unavailable` + 503**。 |
| POST | `/order/<order_id>/cancel` | **Redis** 读改写 `status=cancelled`；**200**，体含 `cancelled` 或 `already_cancelled`（**不再**用进程内 `db_lock` 包全路径，多 worker 下竞态为幂等取消可接受）。 |
| GET | `/live` | **存活探针**，不访问 Redis，**200**，JSON 体含 `liveness` 标记。 |
| GET | `/ready` | **就绪探针**，`redis.ping()` 成功 **200**，失败 **503**。 |
| GET | `/healthz` | **始终 200**（便于旧探针/脚本）；体中 `status` 为 `healthy`/`degraded` 等反映 Redis 是否通；含 `note` 提示生产用 live/ready。 |
| GET | `/metrics` | Prometheus 指标文本。 |
| GET | `/fault/status` | JSON：是否启用注入、活跃故障列表、默认 `ttl`/上限（见 `build_fault_api_response`）。 |
| POST | `/fault/inject` | 体 **`{"type":"latency|exception|drop|slow_db","params":{...},"ttl_sec":60}`**；成功 **201**。`latency` 用 **`latency_ms`**；`exception` 用 **`error_type`**；`drop` 用 **`drop_rate`**；`slow_db` 用 **`base_ms`** / **`jitter_ms`** / **`timeout_rate`**。 |
| POST | `/fault/clear` | 体 **`{"type":"<fault_type>"}`**，清除该类。 |
| POST | `/fault/clear-all` | 清除全部 `fault:*` 键。 |
| DELETE | `/fault/inject/<fault_type>` | 同按类型清除。 |

**韧性关闭时**（`ENABLE_RESILIENCE=false`）：用于基线容器对比，不走路径上的限流/熔断等（具体以 `app.py` 中 `if ENABLE_RESILIENCE` 为界）。**故障注入**由 **`ENABLE_FAULT_INJECTION`** 单独控制，与韧性开关正交（关韧性时仍可注入延迟/丢包等，除非一并关闭故障注入）。

---

## 5. 韧性机制（读本文即可，不必再翻源码结构）

- **限流**  
  - 维度：客户端 IP（`X-Forwarded-For` 或 `request.remote_addr`）。  
  - 默认算法：`RATE_LIMIT_ALGORITHM=sliding`，用 **Redis ZSET + Lua 脚本** 做滑动时间窗计数；`fixed` 为原 **每秒 INCR** 键。  
  - 超限时 **429**，JSON 约 `{"error": "rate limit exceeded"}`。  
  - Redis 异常时 **fail-open**（放行请求），避免 Redis 挂导致全站不可访问。

- **熔断**（**Redis**，多 worker 共享 `cb:*` 键）  
  - 失败在滑动时间窗内（`cb:failures` ZSET）达 `BREAKER_FAIL_THRESHOLD` 则设 `cb:open_until=now+OPEN`；**打开期间** 请求走 **202**；窗口过后进入半开，由 **`SET cb:probe NX`** 抢一条探测。  
  - 成功 `record_success` 清三键、写 `open_until=0`；半开再次失败会 **reopen** 并打日志。  
  - 状态切换有 **`[CIRCUIT]` 前缀的文本日志**（或 JSON 行中的 circuit 类事件在其它路径会扩展）。

- **超时降级**  
  - 在进锁前，`elapsed`（自 `before_request` 起）+ 与锁内相同的计划 `processing_time` 若 **严格大于** `BUSINESS_TIMEOUT_MS` 换算的秒上限，则 **202**（`timeout protected`）。与**仅比较随机数与门限**相比，此语义把**限流/幂等 Redis 等此前已耗时间**计入同一 SLA，更贴近工程上的**截止时间**。**熔断**仍可能 **202**（`circuit open`）。

- **幂等**  
  - 头 `X-Idempotency-Key`：先写 Redis `processing` 占位，完成后写 `succeeded + order_id`；重复请求优先 **200** 回放，处理中可短暂等待后返回 **202**，同 key 不同 payload 返回 **409**。

- **订单与锁**（重要）  
  - 订单**正文**在 **Redis**（`order:{id}`，TTL **`ORDER_TTL_SEC`** 默认 7d）；建单时 **`db_lock` 仅在本 worker 内**串行化模拟 sleep/503；**多 gunicorn worker** 时各 worker 可并行建单，**订单全局可见**于 Redis。  
  - 取消：直接 **Redis 读-改-写**（不跨 worker 的 Python 锁），幂等。  
  - 查单/写单若 Redis 异常返回 **503** / 建单写失败也 **503** 并计熔断等侧逻辑。  
  - 单 worker 上整体吞吐仍受 `db_lock` 与**单进程**模型约束；**水平扩 worker** 时建单可并行度提高，**Redis 与单键仍会成为后续瓶颈**（真实系统需分片等）。

- **可观测**  
  - `prometheus_client`：HTTP 请求与延迟直方图、各业务 Counter（如限流、熔断、超时、建单、拒绝等）。见 `/metrics` 与 Grafana 看板名（仓库内已 provision）。

- **流量录制**  
  - 环境变量 `TRAFFIC_RECORD_ENABLED=true` 时，后台队列写 `TRAFFIC_RECORD_FILE` 默认 `reports/traffic_record_latest.jsonl`；**不记录**仅健康检查/指标类路径；敏感字段有简单脱敏。  

- **可编程 HTTP 故障注入**（`ENABLE_FAULT_INJECTION=true` 时）  
  - **编程模型**：运维/测试通过 **`/fault/inject`** 等 API **在线**写入故障，**`/fault/clear*`** 或 **TTL 到期**关闭；无需改业务代码。  
  - 状态在 **Redis** `fault:{type}`，**TTL** 到期自动失效；**多 worker 共享**。  
  - **`drop`**：按概率在请求入口早返回 **503**（`ORDER_DEGRADED` 递增）。  
  - **`exception`**：在钩子中 **`raise RuntimeError`**（表现为 **500** 类错误路径）。  
  - **`latency` / `slow_db`**：在进业务逻辑前 **`time.sleep`**；**`slow_db`** 还可按 **`timeout_rate`** 模拟超时（内部按 **`drop`** 返回）。  
  - **`/fault/*`** 路径**不**套用注入，避免无法自恢复。  

---

## 6. 主要环境变量（服务 `app` / 本地跑 `app.py`）

| 变量 | 含义 | 典型默认 |
|------|------|----------|
| `REDIS_HOST` / `REDIS_PORT` | Redis 地址 | `localhost` / `6379` |
| `ENABLE_RESILIENCE` | 是否启用整段韧性逻辑 | `true` |
| `RATE_LIMIT_PER_SEC` | 每窗口内允许请求数 | 见 compose |
| `RATE_LIMIT_ALGORITHM` | `sliding` 或 `fixed` | `sliding` |
| `RATE_LIMIT_WINDOW_SEC` | 滑动窗长（秒） | `1` |
| `BUSINESS_TIMEOUT_MS` | 进锁**前**若预计处理时间超此值则 202；代码侧默认 `45` | `docker compose` 中 `app` 为 **`50`**（与模拟 10–50ms 上界对齐，避免约 12% 无意义 202；基线 `app_baseline` 不启用该链） |
| `BREAKER_FAIL_THRESHOLD` / `BREAKER_WINDOW_SEC` / `BREAKER_OPEN_SEC` | 熔断三参数 | 见 compose / 代码（状态在 **Redis** `cb:*`） |
| `CIRCUIT_PROBE_TTL_SEC` | 半开探测键 `cb:probe` 的 **TTL 秒** | 默认 `30`；**≥1**（启动校验） |
| `INVENTORY_BUSY_PROB` | 建单锁内返回 **503** 的概率 | 默认 `0.03`；`docker compose` 的 `app` 为 **`0.025`**（与压测样本量一起降低 error_rate 方差） |
| `ORDER_TTL_SEC` | 订单 `order:{id}` 的 **TTL 秒** | 默认 **`604800`**（7d）；须 **≥60**（启动校验） |
| `ORDER_KEY_PREFIX` | 订单 Redis 键前缀 | 默认 `order:` |
| `IDEM_TTL_SEC` | 幂等键「已成功」类记录的 TTL（秒） | 默认 `300` 等，以代码为准 |
| `IDEM_PENDING_TTL_SEC` | 幂等 **`processing` 占位** 的 NX 键 TTL（秒） | 默认如 `15`；防永远占坑 |
| `IDEM_WAIT_TIMEOUT_MS` / `IDEM_WAIT_POLL_MS` | 同 key 并发时轮询**等待**首请求完成的上限与步进 | 与 **409/200** 协同语义，见 `chaos_service/store.py` |
| `TRAFFIC_RECORD_ENABLED` / `TRAFFIC_RECORD_FILE` / `TRAFFIC_RECORD_MAX_QUEUE` | 录制开关与路径、队列长 | 默认关 |
| `LOG_FORMAT` | `json` 时 `app.py` 用 **JSONFormatter** 统一日志行（便于聚合）；非 `json` 则用默认格式 | 默认 **`json`** |
| `ENABLE_FAULT_INJECTION` | 是否执行 **`apply_faults`** 故障链 | 默认 **`true`**（`1`/`true`/`yes`/`on`） |
| `FAULT_DEFAULT_TTL_SEC` | 注入记录 **Redis TTL** 默认秒 | 默认 **`60`** |
| `FAULT_MAX_LATENCY_MS` | **`latency_ms`** 上限 | 默认 **`5000`** |
| `FAULT_MAX_DROP_RATE` | **`drop_rate`** 上界（可 **`1.0`**） | 默认 **`1.0`** |

**LLM 辅助（`llm_client.py`，可选）**：`LLM_BACKEND`（`auto`/`ollama`/`openai`）、`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、`LLM_TIMEOUT_SEC`、`OLLAMA_ENDPOINT`；云端 OpenAI 兼容模式未设 base 时默认通义兼容端点（以代码为准）。

**压测相关环境变量**（`benchmark_compare.py`）：`BENCHMARK_BASELINE_URL`、`BENCHMARK_PROTECTED_URL`、`BENCHMARK_TOTAL_REQUESTS`、`BENCHMARK_CONCURRENCY`、`BENCHMARK_SEED`、`BENCHMARK_WARMUP`、**`BENCHMARK_RUNS`**、**`BENCHMARK_HISTORY_KEEP`**、**`BENCHMARK_TREND_WINDOW`** 等，以脚本 `os.getenv` / `argparse` 为准。

**compose**：`app` 与 `app_baseline` 用不同 `ENABLE_RESILIENCE` 等，实现 **同镜像、不同配置** 对照。

---

## 7. CI 流水线（`.github/workflows/qa.yml` 摘要）

**面试口径**：这条流水线本质是在做 **发布/合入决策**——在 agent 评测产出报告后，由 **`unified_quality_gate.py`** 汇总 **压测 + 安全 +（可选）相对历史的 P95 趋势 + agent 分数** 并写出 **`final_decision`**，失败则 **fail 掉 PR**。**`unified_summary.py`** 在门禁之后 **始终生成**（`if: always()`）单一 **Markdown + JSON 摘要**（`reasons` / `signals` / 产物路径表 / `metrics_snapshot`），便于 PR 与面试官一眼看清「平台级」结论，**不改变** gate 的退出语义。

单 job 内顺序（与**本地**可略有工具差异，但意图一致）：

1. 安装 `requirements-dev.txt`  
2. `pytest tests/ -m smoke -q`  
3. `pytest tests/ -q`  
4. `docker compose up --build -d`  
5. 等待 `http://127.0.0.1:5000/healthz` 可用  
6. `python benchmark_compare.py`（CI 常设 **`BENCHMARK_WARMUP`**、**`BENCHMARK_SEED`**、**`BENCHMARK_RUNS: "3"`** 等以稳态/多轮中位数）  
7. `python security_scan.py`（`SECURITY_SCAN_BASE_URL` 等）  
8. `python agent-eval/scripts/chaos_compare.py --strict`（`TOOLS_BASE_URL`、`AGENT_MODE`、`AGENT_EVAL_SKIP_JUDGE` 等）—— **辅线**：工具调用稳定性对照，**非**「AI 主能力」叙事  
9. `python trace_timeline.py`：从 trace JSON 生成 **Mermaid + 静态 HTML**（`if: always()`，先于门禁，保证失败时仍有图可读）  
10. `python unified_quality_gate.py`（`SECURITY_FAIL_ON` 等）：再校验 **benchmark + security + agent_eval** 报告，写 **`reports/unified_quality_gate_latest.json`**  
11. `python unified_summary.py`：写 **`reports/unified_summary_latest.json`** 与 **`.md`**（Gate 失败时仍执行，便于留档）  
12. 上传 `reports/` 与 `agent-eval/reports/` 部分产物为 artifact（含 **`unified_quality_gate_latest.json`**、**`unified_summary_latest.*`**、**`trace_timeline_latest.*`**；上传步常用 **`if: always()`** 以便失败时仍能取报告）  

**`api-automation-demo/`**：可在子目录**本地**安装依赖并跑 **pytest + Allure**（**不参与**主链 Docker/decision）；Allure 原始目录建议保持 **`.gitignore`**，不上库。

**本地 `run.ps1 -Task qa`**：含 pip、**全量** pytest、bench、**Wait-AppHealthz**、scan、gate；**不**一定包含与 CI 完全相同的 smoke 分步，以脚本为准。

---

## 8. `agent-eval/` 扩展模块（辅线：工具调用稳定性）

> **面试口径**：Agent 模块**不是核心**；它做的是在**不稳定环境**下，对「按规划去调 HTTP 工具（下单/查询等）」的路径做对照与门禁，重点看 **重试、失败率、Token/启发式指标** 是否越线。**主线叙事**应始终回到 **quality engineering**：压测、门禁、故障注入与韧性。

- **目的（工程）**：用 `datasets/tool_eval.jsonl` 等驱动**规划器**产生工具调用计划，**真实 HTTP** 调订单服务（或离线兜底），输出正确率、重试、token 启发式等，并与 **`config/eval_config.yaml` 的 `gate:`** 比较；`chaos_compare` 提供 **无故障 vs 混故障** 轮次对照（**`--strict`** 用于 CI）。  
- **不是什么**：不是大模型产品化、不是完整 Agent 平台；**小数据集**、**`AGENT_MODE=rule`** 为 CI 默认；**`ollama` 模式**环境差异大。  
- **主脚本**（`agent-eval/scripts/`）：`run_agent_eval.py`、`score_agent_eval.py`、`gate_agent_eval.py`、`chaos_compare.py`（CI 常见）、**`prompt_regression.py`（P4：Prompt A/B 两遍跑分 + 对比门禁）**、`eval_variance.py`、`judge_local.py`。  
- **P4（Prompt / 规划器 A/B）**：`python agent-eval/scripts/prompt_regression.py` 依次跑 **baseline / candidate**（可通过 **`--baseline-suffix` / `--candidate-suffix`** 写入 **`AGENT_PROMPT_SUFFIX`**，在 **`AGENT_MODE=ollama`** 下附加到路由规划提示；规则模式两遍通常相同，用于验证流水线）。产物 **`agent-eval/reports/prompt_regression_latest.json`**、**`.md`**；阈值来自 **`eval_config.yaml`** 的 **`prompt_regression:`**。单次评测可通过 **`AGENT_EVAL_RAW_JSON`**、**`AGENT_EVAL_SCORE_JSON`**、**`AGENT_EVAL_SCORE_MD`**、**`AGENT_EVAL_REVIEW_POOL_JSON`** 指定路径，避免互相覆盖。Judge 仍由 **`AGENT_EVAL_SKIP_JUDGE`** 等与 `score_agent_eval` 一致。  
- **与订单服务关系**：`TOOLS_BASE_URL` 指向已起的 `5000`；`SKIP_TOOLS_HEALTH_CHECK`、`TOOLS_HTTP_TIMEOUT_SEC` 等见脚本与根 `run.ps1`。  
- **局限**：客户端 chaos **不等价**于杀容器；token 指标**非**账单级。详见 [`agent-eval/README.md`](../agent-eval/README.md)（该 README 与本文 **§8** 口径一致）。

---

## 9. 测试与标记（`tests/`）

- **`conftest.py`**：`app_state` 换 `FakeRedis`；重置 `BUSINESS_TIMEOUT_MS`、`RATE_LIMIT_ALGORITHM` 等。  
- **`@pytest.mark.smoke`**：少量快路径。  
- **`@pytest.mark.contract`**：整个 `test_api_contract.py` 为契约/形状类用例。  
- **`@pytest.mark.integration`**：需本机 Redis 等（可能 skip），见 `pytest.ini`。  
- **文件速查**：`test_app.py`（主功能/韧性）、`test_fault_injection.py`（`/fault/*` 与 **`apply_faults`**）、`test_llm_client.py`（`LLMClient` 解析/后端选择，多 mock）、**`test_llm_assist_helpers.py`（`llm_assist` 采样/报告类型等纯函数）**、`test_api_contract.py`、`test_benchmark_compare.py`、`test_quality_gate.py`、`test_security_scan.py`、`test_replay_traffic.py`、`test_agent_eval_config.py`、**`test_prompt_regression.py`（P4 对比逻辑）**、**`test_unified_summary.py`（平台摘要）**、**`test_trace_timeline.py`（P6 Mermaid）**、`test_perf_regression.py`、`test_redis_integration.py`。
- **`api-automation-demo/tests/`**：**另一棵** pytest 树（YAML + httpx + Allure），**不属于**本节「根 `tests/`」集合；细节 **§2.1 L**。  

**不要在未起 Docker 时假设集成环境一定绿**；单测用 Fake Redis，不依赖真 Redis 容器即可跑大部分用例（以实际 import 与 fixture 为准）。

---

## 10. 安全扫描与质量门禁（脚本级行为，本文够用）

**`security_scan.py`**

- 先 **GET 健康**（可 `SECURITY_SCAN_BASE_URL/healthz` 或同类），带 **重试**（`SECURITY_HEALTH_RETRY_*`）。  
- SQLi 探针：`POST /order`，**多 payload** 可 **线程池** `SECURITY_SCAN_WORKERS`。  
- **上下文感知**（默认开）：`SECURITY_SCAN_CONTEXT_AWARE` → 函数 **`analyze_sqli_probe`** 按 **状态码 + 体** 分级 severity（2xx 回显、泛化 5xx、体含 SQL/DB 信号等），避免「只认 5xx=高」的误报。可鉴权：Bearer / API Key 头。  
- 输出 `reports/security_scan_latest.json`（含 `context_aware`、`findings`）和 `.md`。

**`quality_gate.py`**

- 读 `reports/benchmark_latest.json`：校验 `generated_at` 新鲜度（可关/可调最大年龄 `QUALITY_GATE_MAX_REPORT_AGE_SEC`）；对 **protected** 与 **baseline** 的**中位数结果**比较 **error_rate、p99、protected p95 相对 baseline 的回归系数、degraded+error 不稳定度** 等，且可选校验 **`QUALITY_GATE_P95_STDEV_MAX`**。  
- 读 `reports/security_scan_latest.json`：按 `SECURITY_FAIL_ON`（`low`/`medium`/`high`）看 findings 是否超线；可 `QUALITY_GATE_REQUIRE_SECURITY=0` 无报告时跳过（「跳过」在输出里记为 **`SKIPPED`**）。  
- **`run_check_with_retries`**：benchmark 与 security 子检查可 **重试**次与间隔。  
- 失败时抛出 **`QualityGateError`**（供 **`unified_quality_gate.py`** 汇总）；直接运行本脚本仍以 **退出码 1** 结束。  
- 控制台打印 `security_report_meta`：含 **`context_aware`** 与报告里的 **`base_url`（以 target= 打日志）**。

**`unified_quality_gate.py`（P2 + P3）**

- 依次调用与 `quality_gate` **相同**的 benchmark/security 校验逻辑，并对 **`agent-eval/reports/agent_eval_latest.json`** 执行与 **`gate_agent_eval.py`** **相同**的阈值比较。  
- **P3（可选）**：若 **`UNIFIED_GATE_TREND_ENABLED=1`**，读取 **`reports/benchmark_trend_latest.json`**：当存在 **历史中位数 `protected_p95_ms`** 时，要求当前 protected P95 相对该中位数的比值 ≤ **`UNIFIED_GATE_TREND_PROTECTED_P95_RATIO_MAX`**（默认 **1.15**）；无历史或缺字段时该项为 **`SKIPPED`**。可设 **`UNIFIED_GATE_TREND_REQUIRE_REPORT=0`** 在缺文件时跳过；**`UNIFIED_GATE_TREND_CHECK_FRESHNESS=1`** 时对 trend 报告做与 §10 相同风格的新鲜度校验。  
- 写出 **`reports/unified_quality_gate_latest.json`**：`final_decision`（`PASS`/`FAIL`）、`reasons[]`、`checks`（含 **`benchmark_trend`**：`PASS`/`FAIL`/`SKIPPED`，以及 `benchmark` / `security` / `agent_eval`）。  
- **`UNIFIED_GATE_SKIP_AGENT=1`**：不读 agent 报告（`checks.agent_eval` 为 **`SKIPPED`**），适用于只做压测+安全的本地片段。

**`unified_summary.py`（平台一页汇总）**

- **只读**既有子报告，写出 **`reports/unified_summary_latest.json`**（**`schema_version`: 1**）与 **`.md`**：顶层 **Release 风格 Markdown**（`Decision` / `Checks`：benchmark、benchmark_trend、security、**semantic_eval** / `Key regressions` / `Trace highlights` / `Trend` / `Artifacts`，其后为 Reasons、Signals 等详情）；JSON 同步 **`checks_summary`**、**`key_regressions[]`**、**`trace_highlights[]`**、**`trend_bullets[]`**（`final_decision`、`reasons[]`、`signals[]`、`artifacts[]`、`metrics_snapshot` 不变更语义）。  
- 环境变量 **`UNIFIED_SUMMARY_P95_REGRESSION_WARN`**、**`UNIFIED_SUMMARY_RETRY_SURGE_WARN`** 控制写入 `signals` 的阈值。

---

## 11. 报告文件路径速查

| 文件 | 产生方式 |
|------|----------|
| `reports/benchmark_latest.json` | `benchmark_compare.py` |
| `reports/benchmark_history/benchmark_*.json` | 每次压测归档，见 **`BENCHMARK_HISTORY_KEEP`** |
| `reports/benchmark_trend_latest.json`、`.md` | 与历史窗口的 delta，见 **`BENCHMARK_TREND_WINDOW`** |
| `reports/security_scan_latest.json`、`.md` | `security_scan.py` |
| `reports/traffic_replay_latest.json`、`.md` | `replay_traffic.py` |
| `reports/traffic_record_latest.jsonl` | 应用侧录制（`app.py`） |
| `reports/fault_demo_latest.json` | `fault_demo.py` |
| `reports/unified_quality_gate_latest.json` | **`unified_quality_gate.py`**（`final_decision`、`reasons[]`、分项 `checks`） |
| `reports/unified_summary_latest.json`、`.md` | **`unified_summary.py`**（平台一页汇总；**`artifacts[]`** 指向 benchmark / trend / gate / eval / trace / prompt 等） |
| `reports/trace_timeline_latest.mmd`、`.html` | **`trace_timeline.py`**（无 `--input` 且存在 baseline/chaos 两份 trace 时为 **HTML 上下双 Mermaid**；`.mmd` 内两段图以 `%% ===` 分隔） |
| `reports/trace_timeline_meta.json` | **`trace_timeline.py`** 写出（`source`、输出相对路径等） |
| `agent-eval/reports/*` | 各 `agent-eval/scripts` 脚本 |
| `agent-eval/reports/agent_eval_trace_latest.json` | **`run_agent_eval.py`** 的 **HTTP 工具调用 trace**（每轮一步 `steps[]`：tool / latency_ms / http_status / retry_index 等）；路径可用环境变量 **`AGENT_TRACE_FILE`** 覆盖；**`AGENT_TRACE_ENABLED=0`** 可关闭落盘。 |
| `agent-eval/reports/agent_trace_baseline.json`、`agent_trace_chaos.json` | **`chaos_compare.py`** 两轮各写一份聚合 trace（**`chaos_compare_latest.json`** 内 **`agent_trace_files`**） |
| `agent-eval/reports/prompt_regression_latest.json`、`.md` | **`prompt_regression.py`**（baseline vs candidate 指标 delta + **`gate_pass` / `gate_reasons`**） |
| `agent-eval/reports/agent_raw_prompt_*.json`、`agent_eval_prompt_*.json` | **`prompt_regression.py`** 子轮次输出（与默认 **`agent_raw_latest.json`** 区分） |

## 12. 诚实边界（避免 AI 过读、瞎改）

- **不是** 金融级生产系统；**多地域/多独立 Redis/跨集群** 的限流与熔断**一致** 未在核心路径解决；**同 compose / 同 Redis 实例** 下，**限流与熔断已为共享状态**（见 §1.1/§2.1 A）。  
- **压测脚本** 短连接、单机；压力上来时**客户端/宿主机**可能先瓶颈。  
- **Grafana 大盘** 为教学展示，**不承诺**「全链路根因一步定位」。  
- **Agent 扩展（`agent-eval/`）** 为 **工具调用稳定性** 对照与门禁，**小样本 demo**；**面试主线**应强调 **质量工程平台**，避免把仓库讲成「AI 主项目」。  
- **HTTP 故障注入**（`/fault/*`，Redis 状态）为**应用内协作式**模拟；**不等价**于网络 `tc`、杀 Pod 或客户端-only chaos。  

---

## 13. 后续优化与演进方向（规划收纳，**尚未实现**者勿当已完成）

**可执行计划表（阶段 / 交付物 / 状态）**：见 **[`plan/PLATFORM_CONVERGENCE_ROADMAP.md`](plan/PLATFORM_CONVERGENCE_ROADMAP.md)**（Trace → 统一门禁 → 语义回归等）；本节保留**条目式**补充，避免与路线图重复维护两套「阶段名」。

以下与维护者/秋招学习路线对齐，**实现时需改代码并回写本文相关章节**。

1. **质量门禁**  
   - 历史多份 `benchmark_*.json` 归档，做 **中位数/分位** 或与上版 **偏差** 再判失败，降低单次抖动误杀；**P3（可选）**已在 **`unified_quality_gate`** 中接 **`benchmark_trend_latest`**（默认关，见 **§10**）。  
   - **统一门禁出口**（`final_decision` + `reasons[]`）见 **[`plan/PLATFORM_CONVERGENCE_ROADMAP.md`](plan/PLATFORM_CONVERGENCE_ROADMAP.md)** **P2**。  
   - 保持阈值**可配置、可解释**，避免为「过关」随意放宽。

2. **混沌与亚健康**  
   - **已实现**：应用内 **HTTP 故障注入**（§5 故障注入、`/fault/*`），与韧性/订单共用 Redis，便于演示与单测。  
   - **未做**：在 **Linux** 用 **`tc`** 等做 **网络层** 延迟/丢包，与 **k8s 杀容器/限 CPU**、**Agent 端 chaos** 互补叙事。  
   - **I/O/异步日志** 属架构级，单独立项。

3. **Agent**  
   - 深挖 **Retry–Token**、重试死循环风险、**chaos_compare** 严门禁、**eval_variance**；可选未来 **工具依赖/顺序的静态检查**；未落地前**勿称已实现「逻辑拓扑检查器」**。

4. **可观测**  
   - 可选 `trace_id` 贯穿日志与响应头；Grafana 增加 **2～3 个** 有因果关系的 panel（不必大而全）。  
   - **平台向**：**Agent / tool 调用的 Run Trace**（`steps[]` 落盘）见 **[`plan/PLATFORM_CONVERGENCE_ROADMAP.md`](plan/PLATFORM_CONVERGENCE_ROADMAP.md)** **P1**。  

5. **显式不采纳（默认）**  
   - 在 `quality_gate` 主链绑 **假 CPU 温度/假 PCIe** 当硬条件（易与真实质量混淆）；若做演示，用**独立 mock 报告**并标明模拟。  
   - 在 Web 里调真实 **`lspci` 等硬件**（与本仓库目标不一致）。

6. **已知工程债**（设计层）  
   - 每 worker 内 `POST /order` 仍用 **`db_lock` + 同步 sleep** 模拟，**单进程内**为瓶颈；多 worker 可并行建单，**Redis/热点键** 仍可能顶满。  
   - **多 Redis/多分片** 下的**全局**配额与强一致 SLO 未做；`chaos_compare` 仅 **子进程 timeout**，非完整分布式评测平台。  

---

## 14. 可选补充（人类读者，**非** AI 必读）

**全部 Markdown 的导航表**见 **`docs/README.md`**。面试向：测试分层 / failure model → **[`TEST_STRATEGY.md`](TEST_STRATEGY.md)**；压测 trade-off → **[`PERFORMANCE_ANALYSIS.md`](PERFORMANCE_ANALYSIS.md)**；**问题→解决、CI 发布决策、可编程故障注入口径** → **§1.0**。  
**处理自动化任务、代码修改时，以本文 1–13 节为权威上下文**；其它 md 不重复当第二套事实源。  
零基础测开读者可从 **`docs/LEARNING_PLAN_0BASIS_SDET.md`** 按阶段自测推进，再回读本文对应章节。

*文档版本以仓库主分支与上述文件名一致时为准；若与运行结果冲突，以当前 `app.py` 与各脚本**实际行为**为最终准绳并应回写本文。*
