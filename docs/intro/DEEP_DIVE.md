# 项目深挖：知识点、亮点与面试题库

本文合并原 **`PROJECT_KNOWLEDGE_AND_HIGHLIGHTS.md`** 与 **`PROJECT_MASTERY_GUIDE.md`** 的去重精华，作为**深挖与面试叙述**入口。

> **文档分层**：**技术参数、API 全表、流水线**以 **[`../AI_PROJECT_CONTEXT.md`](../AI_PROJECT_CONTEXT.md)** 为准；本文不重复抄表，只讲原理、亮点与答题角度。  
> **给谁看**：准备技术面试、答辩或通读代码。  
> **结构导读**：`PROJECT_INTRO_FOR_READERS.md`（文件地图）· **运行**：`../run/GUIDE.md` · **文档地图**：`../README.md`

---

## 一、定位与价值主张

### 1.1 项目解决什么问题？

- **服务侧**：在**高并发**与**部分故障**场景下，验证**稳定性策略**（限流、超时、熔断等）是否**可量化**地改善尾延迟、错误率，并通过**压测报告 + 门禁**固化标准。  
- **Agent 侧**：在**工具调用型应用**（如下单助手）中，验证**规划是否正确**、**故障下重试与成本（token）是否可控**，并通过**对照实验 + 多条件门禁**防止「坏版本」静默上线。

### 1.2 测开（测试开发）在本项目中的体现

- **自动化**：单测、压测脚本、质量门禁、CI 流水线。  
- **可复现**：JSON/Markdown 报告、固定种子、环境变量可调。  
- **可量化**：QPS、P95/P99、成功率、工具准确率、retry、token 增幅等。  
- **风险拦截**：门禁失败即非 0 退出，适合作为合并前置条件。

### 1.3 与「生产级测开平台」的差距（诚实边界）

- 服务规模、链路复杂度、真实流量回放、全链路追踪等**未覆盖**。  
- Agent 为 **demo 数据集 + 规则/本地模型**，**非**完整 NLU 与安全评测体系。  
- **`k8s/`** 为可选学习材料（本地单节点、非生产集群），与 CI 默认流程无关。  
- 详见 `../plan/AGENT_EVAL_PLAN.md` **§2.1**。

---

## 二、服务侧知识点

### 2.1 Flask 订单服务（`app.py`）

**知识点**：RESTful 风格接口、JSON 请求体、HTTP 状态码语义（201 创建、200 幂等命中等）。

**亮点**：同一应用通过环境变量切换 **ENABLE_RESILIENCE**，便于 **A/B** 对照，而非维护两套代码库。

### 2.2 幂等与 Redis

**知识点**：  
- **幂等**：同一业务操作执行多次，结果与执行一次一致（此处侧重「不重复创建订单」）。  
- 客户端传 **`X-Idempotency-Key`**，服务端用 **Redis** 记录「该 key 已对应哪个 order_id」，重复请求返回同一订单。

**亮点**：贴近真实电商/支付场景；单测 `test_idempotency_returns_same_order` 可讲故事。

**边界**：测试里可用 `FakeRedis`；生产还需过期策略、集群一致性等，本仓库不展开。

### 2.3 限流（Rate Limiting）

**知识点**：按 **客户端 IP**（或类似维度）限制 **每秒请求数**，超出返回 **429**，保护下游。

**亮点**：`RATE_LIMIT_PER_SEC` 可配；默认 **Redis ZSET 滑动窗口**（`RATE_LIMIT_ALGORITHM=sliding`），可选 **固定秒桶**（`fixed`）；压测中可观察到限流。

**边界**：多实例共享依赖 Redis；网关层统一限流未展开。

### 2.4 业务超时与降级（Business Timeout）

**知识点**：单请求处理超过 **BUSINESS_TIMEOUT_MS** 时，不无限阻塞，而是返回**降级响应**（如排队提示），避免线程/连接被拖死。

**亮点**：与「慢查询拖垮线程池」类故障对应，可结合 Grafana 看延迟分布。

### 2.5 熔断（Circuit Breaker）

**知识点**：短时间失败次数超过阈值则**打开熔断**，一段时间内**快速失败**或返回降级，避免**雪崩**。

**亮点**：`BREAKER_*` 可配；已实现最小 **Half-Open**（开闸后单探测请求，成功闭合、失败重开）及状态切换日志。

**边界**：熔断状态在进程内内存；多实例未共享；与 Hystrix 等成熟库细节不同，但**概念**一致。

### 2.6 可观测性：Prometheus + Grafana

**知识点**：  
- **Prometheus**：拉取 **/metrics**（Counter/Histogram 等），用于告警与查询。  
- **Grafana**：对接 Prometheus 数据源，**可视化** QPS、延迟、错误等。

**亮点**：仓库含 **provisioning**，导入即用看板，适合演示「不是只有日志」。

### 2.7 压测：Locust 与 `benchmark_compare.py`

**知识点**：  
- **Locust**：协程并发用户，模拟多用户行为。  
- **对照压测**：同一套压测逻辑，换 **host:port**（5000 vs 5001），对比 **P95/P99、成功率、降级率** 等。

**亮点**：`benchmark_compare.py` 输出结构化 JSON，供 `quality_gate.py` 消费，形成 **bench → gate** 闭环。

### 2.8 安全扫描门禁 `security_scan.py`

**知识点**：轻量 DAST 思路（payload 探测 + 响应内容关键词匹配），在本地 demo 下实现“安全左移”。

**亮点**：生成 `security_scan_latest.json/.md`，可直接接入 CI，发现中高危即阻断。

### 2.9 统一质量门禁 `quality_gate.py`

**知识点**：将「好/坏」从主观变为 **阈值**（性能 + 安全），自动化拒绝不达标构建。

**亮点**：与 CI 结合，体现 **Shift-left**（尽早发现回归）。

### 2.10 流量录制与回放（`app.py` + `replay_traffic.py`）

**知识点**：将真实请求以 JSONL 记录并脱敏，再回放到目标服务，形成更接近业务的数据驱动测试。

**亮点**：回放会输出 `traffic_replay_latest.json/.md`，并支持按接口统计成功率和平均耗时。

### 2.11 Kubernetes 与 Chaos Lite（`k8s/`，可选）

**知识点**：在集群内用 **Service 名**（如 `redis:6379`）访问依赖，无需 Compose 式宿主机端口映射；**Deployment** 控制副本数；**NetworkPolicy** 声明式限制谁可访问 Redis。

**亮点**：`k8s/chaos-lite.ps1` 用最小脚本演示三类故障：**删 Pod 自愈**、**收紧 Redis 网络策略**、**CPU limit 资源压制**，与混沌工程叙事衔接。

**边界**：不引入 Chaos Mesh；NetworkPolicy 是否严格生效依赖 CNI；**非**多节点生产演练。

---

## 三、Agent 侧知识点

### 3.1 工具调用（Tool Calling）评测在测什么？

**知识点**：  
- **Tool Selection**：是否选了正确工具（下单/查询/取消/追问）。  
- **Arguments**：参数是否与预期一致（或是否进入合法追问）。  
- **Sequence**：多步时顺序是否正确（本仓库以**整段工具列表**一致性体现）。  
- **Task Success**：规则上是否算任务成功。

**亮点**：输出 **tool_selection_accuracy、call_sequence_accuracy、arg_accuracy** 等，可直接写在简历。

### 3.2 规则规划器 vs Ollama（`AGENT_MODE`）

**知识点**：  
- **rule**：关键词 + 正则，确定性高，适合 **CI 不依赖 GPU**。  
- **ollama**：本地 LLM 输出 JSON 计划，经 **白名单校验**，不合法则降级 **ask_user**。

**亮点**：可讲「双模式」：回归用 rule，本地实验用 ollama。

**边界**：rule **不是**语义理解；ollama 依赖本地部署。

### 3.3 故障注入（`--chaos` 与 `tools_client`）

**知识点**：在**客户端**对每次 HTTP 调用注入 **延迟**、**随机失败**，驱动 **重试** 与 **指标变化**。

**亮点**：与「后端不稳定」现象类比；可展示 **retry_rate、token** 在故障下上升。

**边界**：多为 **URLError** 路径模拟；**不等价**于对容器/Redis 的真实 kill 实验。若需补充「集群侧」实例/网络/资源故障，可单独讲 **`k8s/` 的 Chaos Lite**（与 Agent 客户端 chaos 互补）。

### 3.4 Token 与成本

**知识点**：  
- **rule 模式**：常用 **启发式**（与输入长度、重试次数等相关），非账单级。  
- **ollama 模式**：可解析 **prompt_eval_count + eval_count** 近似规划阶段 token。  
- **TOKEN_METRIC**：auto / llm / estimated 切换主指标来源。

**亮点**：体现「测开关心成本」；报告中有 **ollama_token_coverage** 等。

**边界**：与 OpenAI **`usage` 账单**不对齐；多轮会话累计未做。

### 3.5 Token by outcome 与 Retry Tax

**知识点**：  
- 按 **规则通过/失败**、**是否发生重试** 拆分平均 token，观察「失败路径是否更费钱」。  
- **Retry tax（重试税）**：有重试样本相对无重试样本的 **token 增幅比例**，用于抓「重试拖高成本」。

**亮点**：`chaos_compare` 将基线与故障轮对照，并设 **CHAOS_*** 环境变量作为门禁上限。

### 3.6 Token 黑洞门禁（对照场景）

**知识点**：不只盯 **平均 token 增幅**，还约束 **retry 增幅**、**规则失败路径上的 token 增幅**、**重试路径**（两侧均有重试样本时）、以及 **故障轮内重试税**。

**亮点**：可讲「防止只在失败样本或重试样本上疯狂消耗 token」；`--strict` 对接 CI。

### 3.7 本地 Judge（`judge_local.py`）

**知识点**：对 **attack** 类样例用 LLM 判 **PASS/FAIL**；失败可进复核池。

**亮点**：`eval_config.yaml` 中 **enabled + sample_rate** 控制成本；**EVAL_SEED** 复现抽检序列。

**边界**：单判官；CI 常 **SKIP_JUDGE**；非 GPT-4 云端仲裁。

### 3.8 单轮门禁 `gate_agent_eval.py`

**知识点**：阈值统一从 **`eval_config.yaml` 的 gate** 读取，与代码硬编码解耦。

**亮点**：改 YAML 即可调门槛，符合「配置化门禁」叙事。

### 3.9 多次运行波动 `eval_variance.py`

**知识点**：固定 chaos 参数，**改变随机种子**多轮跑，对 **retry_rate、avg_token** 等做 **mean/min/max/stdev**。

**亮点**：回应「只跑一次是否偶然」；比单点分数更像实验。

### 3.10 配置解析 `parse_simple_yaml`

**知识点**：极简 YAML 子集解析，避免重依赖。

**边界**：**非**完整 YAML 规范；复杂配置需换 PyYAML 等。

---

## 四、工程与 CI 亮点

### 4.1 Docker Compose

一键拉起 **应用 + Redis + Prometheus + Grafana**，降低导师/面试官复现成本。

### 4.2 GitHub Actions（`qa.yml`）

**知识点**：流水线阶段：**`pytest -m smoke`（快速失败）→ 全量 pytest** → 起服务 → 健康检查 → 压测 → 安全扫描 → 统一门禁 → **Agent chaos 对照 strict**。

**亮点**：**服务与 Agent** 同一流水线；Agent 报告可 **artifact** 归档。

### 4.3 `run.ps1`

统一 **Windows** 下入口，降低「命令记不住」问题。

---

## 五、面试可讲的「故事线」（串联亮点）

1. **问题**：订单服务在压测下尾延迟与错误如何？治理策略是否有效？→ **双实例对照 + benchmark + gate**。  
2. **延伸**：若上层是 **工具型 Agent**，后端不稳时是否乱重试、token 是否暴涨？→ **chaos + chaos_compare + Token 黑洞门禁**。  
3. **严谨性**：单次结果是否偶然？→ **eval_variance**。  
4. **成本与抽检**：Judge 是否太贵？→ **sample_rate + SKIP_JUDGE in CI**。  
5. **诚实**：哪些是 demo 简化？→ **AGENT_EVAL_PLAN §2.1**。

---

## 六、推荐阅读顺序

1. `PROJECT_INTRO_FOR_READERS.md`（结构）  
2. 本文（原理 + 题库）  
3. 根目录 `README.md` + `agent-eval/README.md`（命令与路径）  
4. `../plan/AGENT_EVAL_PLAN.md` §2.1（边界）  
5. `../interview/INTERVIEW_PREP.md`（简历、讲稿、填空、压测样例）

---

*文档随仓库迭代；数值与阈值以代码及 `eval_config.yaml` 为准。*

---

## 七、可改造需求清单（面试常问）

你要能独立改出这类需求（或讲清思路）：

1. **限流**：从按 IP 改为 `user_id + API`；白名单不限流。  
2. **幂等**：key 冲突时返回摘要校验；避免不同请求复用同一 key。  
3. **熔断**：已有半开；可深化 **按依赖拆分熔断器**（库存/支付）。  
4. **观测**：业务成功率指标；失败原因标签（timeout/rate_limit/inventory_busy）。  
5. **测试**：熔断开闭、幂等冲突等更多自动化用例。

---

## 八、高频简答（必须能答）

### Q1：为什么治理版成功率变低了还说优化了？

- 目标不是单接口 100% 成功，而是整体可恢复。  
- 部分流量主动 `202` 降级，避免大量 `503` 与长尾超时。  
- 结合吞吐、P99、error+degraded 一起看。

### Q2：为什么不用消息队列做真异步？

- 当前 `202 queued` 为轻量演示。  
- 线上可接 MQ 做最终一致；当前重点在策略可量化验证。

### Q3：限流为什么用 Redis？

- 多实例时本地计数不一致；Redis 共享状态更接近生产。  
- 默认滑动窗口用 ZSET + Lua；可选固定秒桶。

### Q4：怎么证明改动有效？

- baseline / protected 对照；同脚本复跑；Prometheus 与 `reports/benchmark_latest.json` 沉淀。

---

## 九、实操清单与「吃透」标准

**建议练 2～3 轮**：`up` → `test`（或 `pytest -m smoke` + 全量）→ `bench` → `scan` → `gate` → Grafana → 调 `RATE_LIMIT_*` / `BUSINESS_TIMEOUT_MS` / `BREAKER_*` 复测 →（可选）录制回放。

**吃透参考**：3 分钟讲清目标/架构/结果；解释主要状态码；手改一策略能预判指标；会 PromQL 基础查询；能定位一次压测异常；诚实说局限与演进。

---

## 十、进阶路线（摘要）

分层测试 + 测试数据管理 + 门禁与报告归档 + 更多故障场景（CPU/网络/Redis 故障）自动化。

---

## 十一、测开面试追问题库（20 题）

每题准备 30～60 秒口述；用**自己跑出的报告数字**替换空话。

### 1) 与普通后端项目最大区别？

质量闭环（test/bench/scan/gate/report）+ 对照实验 + 可复现。

### 2) 为何 baseline / protected 双实例？

无对照无法证明优化；同代码开关减少变量污染。

### 3) 降级 202 的价值？

有损可用、保资源与尾延迟；可接异步。

### 4) 门禁如何通过？

绝对阈值（error、p99）+ 相对回归 + degraded+error 组合；见 `quality_gate.py` 与环境变量。

### 5) 门禁误报？

多轮取中位数；固定环境；重试去抖（本仓库已部分支持）。

### 6) 压测可重复性？

固定并发/总量/版本；JSON 报告归档。

### 7) 限流为何按 IP？

Demo 低成本；生产可切用户/租户维度。

### 8) Redis 不可用？

幂等/限流等 fail-open 或退化路径；见代码与单测。

### 9) 熔断局限？（已与实现对齐）

- **已有**最小半开与窗口内失败计数。  
- **仍缺**：按依赖拆分熔断、多实例共享状态、更细粒度统计。

### 10) 为何看 P95/P99？

均值掩盖长尾；体验与 SLO 常看尾部。

### 11) 最重要测试类型？

接口回归 + 压测 +（可选）故障注入 + 门禁前置。

### 12) 故障注入用例怎么设计？

从依赖出发；定义观测与退出条件；验证降级是否符合预期。

### 13) CI 最有价值步骤？

benchmark + quality_gate + security；性能与安全可阻断。

### 14) 防止为过关调松阈值？

阈值对齐历史与 SLO；变更留痕；报告归档。

### 15) protected 成功率低于 baseline？

含主动 202 降级；结合 error/degraded/p99。

### 16) 要求绝不丢单？

MQ + 重试 + 死信 + 补偿，最终一致。

### 17) 如何验证幂等？

同 key 同 order_id；并发重放；冲突策略可继续加强。

### 18) 团队协作扩展？

统一入口（`run.ps1`/CI）、标准报告 JSON、文档化阈值。

### 19) 发布质量评估？

发布前 qa；对比近 N 次指标；门禁阻断。

### 20) 再做一周优先做什么？

故障注入进 CI 定时；压测趋势聚合；**MQ 异步闭环**（半开已具备，不必重复列为首项）。

---

## 十二、本库使用方法

每天抽 30 分钟练 5 题口述；结构：**背景 → 动作 → 结果 → 反思**；对照 `reports/` 与 `agent-eval/reports/` 填真实数字。
