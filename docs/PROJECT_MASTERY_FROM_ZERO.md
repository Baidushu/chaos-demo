# 从 0 开始吃透这个项目：学习路线、读码顺序、合格标准

> 这篇文档的目标不是“介绍项目”，而是帮你**真的吃透**这个项目。  
> 适合你现在这种情况：项目已经有了，但要为了 **2026 秋招**，把它变成你能独立讲、独立改、独立扩展的项目。

**与 `docs/AI_PROJECT_CONTEXT.md` 的同一口径**  
- **技术事实**（环境变量、CI 逐步、文件职责、实现细节、报告路径）以 **[`AI_PROJECT_CONTEXT.md`](AI_PROJECT_CONTEXT.md)** 为**准**；**本文若与之一句冲突，以全景文 + 源码为准**。  
- **主服务形态**：`app.py` 为**薄入口**（Flask 实例、Prometheus 指标定义、环境常量、`validate_resilience_config`、委托注册）；业务与韧性**实现**在 **`chaos_service/`**（`http_api`、`resilience`、`store`、**`fault_injection`**、`traffic`）。**不要**把旧版「所有逻辑挤在一个 `app.py`」的心智带进来。  
- **压测产物**：`benchmark_compare` 会写 `reports/benchmark_latest.json`、**`reports/benchmark_history/`** 归档、**`reports/benchmark_trend_latest.*`** 与历史对比；**`quality_gate.py` 当前门禁主读** `benchmark_latest.json`（及 security 报告）——trend 用于**人读/面试讲波动**，不替代上述门禁输入（见全景 §10～§11）。  
- 更短「阶段 + 自测」路线见 [`LEARNING_PLAN_0BASIS_SDET.md`](LEARNING_PLAN_0BASIS_SDET.md)（与本文互补，不重复维护两套事实表）。

---

## 1. 先说结论：什么叫“吃透”

不是：
- 能跑起来
- 能背 README
- 能说几个术语

而是你要做到这 5 件事：

1. **能讲清主链路**
   - 一个 `POST /order` 请求进来后，代码怎么走，为什么返回 201 / 200 / 202 / 429 / 503

2. **能讲清设计原因**
   - 为什么要 Redis
   - 为什么幂等要做成占位 + 完成态
   - 为什么 benchmark 要多轮中位数，不看单次

3. **能独立改代码**
   - 给接口加字段、改门禁阈值、补测试、修 bug，不靠 AI 逐行带

4. **能回答面试追问**
   - 如果 Redis 挂了怎么办
   - 幂等并发冲突怎么处理
   - 为什么 protected 不一定每次都比 baseline 漂亮

5. **能做小扩展**
   - 比如补一个新测试、加一个新门禁、加一个小指标、改一条 replay 流程

如果这 5 条做到了，才算“基本吃透”。

---

## 2. 这个项目到底是什么

这个仓库不是单一 Flask demo，而是 **3 层组合**：

### A. 服务治理主项目
核心目标：
- 模拟订单服务
- 做稳定性治理
- 做质量验证

你主要会看到：
- `app.py`
- `chaos_service/`
- `tests/`
- `benchmark_compare.py`
- `quality_gate.py`
- `security_scan.py`
- `replay_traffic.py`
- **`fault_demo.py`**（HTTP 故障注入演示，可选）
- **`llm_client.py` / `llm_assist.py`**（可选 LLM 辅助，不进 CI 主链）

### B. Agent 评测子项目
核心目标：
- 测工具调用型 Agent 在正常/故障场景下的表现

主要目录：
- `agent-eval/`

### C. BIOS / CI 自动化（岗位叙事，**非**本仓库独立代码树）
核心目标：
- 贴近 **BIOS / 固件 CI** 岗面试时，用同一套「**解析日志 → Markdown/JSON 报告 → gate**」方法论**类比讲解**。

**当前仓库**：没有单独的 BIOS 日志解析子目录；技术面仍以 **§3.1 服务主链路** 与 **`agent-eval/`** 为主。叙事模板见 [`PROJECT_POSITIONING_THREE_VERSIONS.md`](PROJECT_POSITIONING_THREE_VERSIONS.md)；应用内 **`/fault/*`** 与 **`quality_gate`** 可作为「可控故障 + 门禁」的演示对照。

所以你面试时可以把它理解为：

> 一个“服务稳定性 + 质量门禁 + Agent 评测 + BIOS/CI 自动化小样”的组合型项目。

---

## 3. 现在的项目框架是什么

## 3.1 服务主链路框架

### 入口层
- `app.py`

现在 `app.py` 是**薄入口**，主要做：
- Flask app 初始化
- 全局配置加载
- Counter / Histogram 注册
- 把路由、韧性、存储、**故障注入钩子依赖**、流量录制拼起来

你不要再把它当成“全部业务都在里面”的文件看。

---

### 服务模块层
- `chaos_service/http_api.py`
- `chaos_service/fault_injection.py`
- `chaos_service/resilience.py`
- `chaos_service/store.py`
- `chaos_service/traffic.py`

职责分工：

#### `http_api.py`
管：
- Flask hooks
- 路由注册
- `/order`
- `/order/<id>`
- `/order/<id>/cancel`
- `/live` `/ready` `/healthz` `/metrics`
- **`/fault/status`、`/fault/inject`、`/fault/clear*`**（故障管理 API）
- **`before_request`** 中对业务路径调用 **`fault_injection.apply_faults`**（`/fault` 与探活/指标路径除外）

你可以理解为：
> “接口和请求流程层”

#### `fault_injection.py`
管：
- Redis 中 **`fault:{type}`** 活跃故障记录（TTL）
- **`inject` / `clear` / `list` / `apply_faults`**（延迟、异常、随机拒请求、慢库模拟）

你可以理解为：
> “应用内协作式混沌 / 演示用故障层”

#### `resilience.py`
管：
- 限流
- 熔断
- 半开
- 配置校验
- SLA 超时判断
- 结构化日志

你可以理解为：
> “稳定性治理层”

#### `store.py`
管：
- 订单读写
- 幂等 key 占位/完成态
- 并发幂等等待

你可以理解为：
> “Redis 状态与一致性层”

#### `traffic.py`
管：
- 流量录制
- 请求脱敏
- 队列写 JSONL

你可以理解为：
> “可回放测试数据层”

---

## 3.2 质量验证框架

### 测试
- `tests/`

包含：
- 功能测试
- 契约测试
- benchmark 测试
- quality gate 测试
- replay 测试
- **故障注入**（`test_fault_injection.py`）
- **LLM 客户端**（`test_llm_client.py`，多 mock）
- Redis integration 测试

### 压测与门禁
- `benchmark_compare.py`（可额外生成 **history / trend** 文件，见上节「同一口径」）
- `quality_gate.py`（**主要**用 `reports/benchmark_latest.json` + `security_scan_*.json` 判通过）
- `security_scan.py`

流程是：

1. benchmark 生成**主**报告（及可选 **trend** 辅助阅读）  
2. security scan 生成报告  
3. quality gate 读取**约定路径上的**报告并决定是否 fail

这就是一个小型的 **QA pipeline**。

---

## 3.3 辅助与编排层

- `docker-compose.yml`
- `run.ps1`
- `.github/workflows/qa.yml`

职责：
- 本地一键运行
- CI 自动跑
- 报告归档

---

## 4. 你应该从哪些代码开始看

正确顺序不是“从头到尾硬啃 app.py”，而是：

## 第 1 层：先看“外部行为”

### 第一步先看这些文件
1. `README.md`
2. `docs/run/GUIDE.md`
3. `docs/intro/PROJECT_INTRO_FOR_READERS.md`

目标：
- 知道项目有哪些模块
- 知道怎么跑
- 知道主要入口文件在哪

你这一阶段不要急着深究实现。

---

## 第 2 层：先看测试，再看实现

### 第二步重点看
1. `tests/test_app.py`
2. `tests/test_api_contract.py`
3. `tests/test_fault_injection.py`
4. `tests/conftest.py`

为什么先看测试：
- 测试会告诉你“系统承诺了什么行为”
- 比直接啃实现更容易抓住重点

你要重点回答：
- 成功建单是什么行为
- 幂等重复请求是什么行为
- payload 冲突是什么行为
- 限流是什么行为
- 熔断半开是什么行为
- cancel 幂等是什么行为
- **`/fault/inject` 与 `apply_faults` 对业务路径的影响**（503 / 延迟 / 异常）

如果测试看不懂，就说明你还没抓住系统的“对外语义”。

---

## 第 3 层：再看主链路实现

### 第三步读这个顺序
1. `app.py`
2. `chaos_service/http_api.py`
3. `chaos_service/fault_injection.py`
4. `chaos_service/store.py`
5. `chaos_service/resilience.py`
6. `chaos_service/traffic.py`

推荐方式：

#### 先只盯住一个接口
先只看：
- `POST /order`

你要手画出这条链：

1. before_request 做了什么  
2. 进入 `/order` 后先检查什么  
3. 什么时候会 429  
4. 什么时候会 202  
5. 幂等怎么占位  
6. 什么时候真正写订单  
7. 成功后为什么返回 201  
8. 重复请求为什么返回 200

如果这一条链画不出来，就不要急着看别的模块。

---

## 第 4 层：再看验证链路

### 第四步看这些
1. `benchmark_compare.py`
2. `quality_gate.py`
3. `security_scan.py`
4. `replay_traffic.py`

你要理解的不是“代码每行做什么”，而是：

#### `benchmark_compare.py`
- 为什么有 baseline 和 protected
- 为什么要多轮跑
- 为什么看 median
- 为什么还要写 trend report

#### `quality_gate.py`
- gate 读什么报告
- 怎么判 fail
- 为什么新鲜度要检查
- 为什么可以加抖动阈值

#### `security_scan.py`
- 它不是专业 DAST，而是轻量演示版
- 价值在“安全左移 + CI 门禁”

#### `replay_traffic.py`
- 它的意义是把请求录下来再回放
- 用于更接近真实请求模式

---

## 第 5 层：最后看子项目

### 第五步

#### `agent-eval/`
你要知道：
- 在评测什么
- 为什么有 chaos compare
- 为什么有 token black hole gate

不用一开始就钻太深。

你要知道：
- 这个是为了贴近 BIOS / CI / 自动化岗位
- 它做的是“启动日志解析 + 门禁”

这个模块不复杂，但很适合你和实习绑定。

---

## 5. 从“怎么看代码”这个角度，推荐你这样读

## 方法 1：测试驱动读码

每次按下面步骤：

1. 先找一个测试  
2. 读测试名字  
3. 猜它在验证什么  
4. 去路由实现找对应代码  
5. 去模块实现找根因  
6. 回到测试确认理解

比如：
- `test_concurrent_same_idempotency_key_does_not_duplicate_order`

你就应该反推出：
- 这是在测并发幂等
- 那就去看 `http_api.py` 的 `/order`
- 再看 `store.py` 的占位逻辑

---

## 方法 2：按“状态码”读

围绕 `/order`，分别回答：

- 为什么返回 `201`
- 为什么返回 `200`
- 为什么返回 `202`
- 为什么返回 `409`
- 为什么返回 `429`
- 为什么返回 `503`

只要这 6 个状态码你能讲透，主链路就过半了。

---

## 方法 3：按“故障场景”读

分别看：

1. Redis 正常
2. Redis 异常
3. 幂等 key 重复
4. 幂等 key 冲突
5. 限流触发
6. 熔断打开
7. 半开探测
8. 超时保护

这会比“按文件顺序看”更接近面试思维。

---

## 6. 你应该先吃透哪些点

我建议分成 **必须吃透** 和 **第二优先级**。

## 6.1 必须吃透

### 1）`POST /order` 完整链路
必须做到脱稿讲清。

### 2）幂等为什么这样做
必须知道：
- 为什么不能只 `GET -> SETEX`
- 为什么要先占位
- 为什么有 `processing`
- 为什么会有 `409`

### 3）限流和熔断
必须知道：
- fixed 和 sliding 的区别
- 熔断为什么放 Redis
- 半开怎么做

### 4）benchmark / gate
必须知道：
- 为什么 benchmark 不是单次
- 为什么 gate 读的是报告，不是重测

### 5）测试体系
必须知道：
- 单测测什么
- integration test 测什么
- 为什么真实 Redis 集成测试有价值

---

## 6.2 第二优先级

### 1）traffic record / replay
知道作用和边界即可。

### 2）security scan
知道它是轻量演示版，不是专业扫描器。

### 3）agent-eval
知道评测目标、门禁思想、与主服务关系。

知道它的定位和门禁逻辑，能讲清它和实习方向的关系。

---

## 7. 从 0 学到吃透，建议分 4 个阶段

## 阶段 1：跑通和认路
目标：
- 能启动项目
- 知道文件结构
- 知道每个模块大概干什么

最低动作：
- 跑 `.\run.ps1 -Task up`
- 跑 `.\run.ps1 -Task test`
- 看根 README
- 看 `docs/README.md`

合格标准：
- 你知道哪些文件是“主文件”
- 你知道服务、测试、benchmark、agent、bios 子项目分别在哪

---

## 阶段 2：吃透主链路
目标：
- 吃透 `/order`

最低动作：
- 精读 `tests/test_app.py`
- 精读 `chaos_service/http_api.py`
- 精读 `chaos_service/store.py`
- 画请求流程图

合格标准：
- 你能脱稿讲 201/200/202/409/429/503 的触发条件

---

## 阶段 3：吃透质量验证链路
目标：
- 明白项目为什么不是普通 CRUD

最低动作：
- 看 `benchmark_compare.py`
- 看 `quality_gate.py`
- 看 `security_scan.py`
- 看 `replay_traffic.py`

合格标准：
- 你能说清 benchmark → report → gate 的闭环

---

## 阶段 4：吃透扩展和岗位绑定
目标：
- 能讲项目价值，不只是讲功能

最低动作：
- 看 `agent-eval/README.md`
- 看 `docs/interview/INTERVIEW_PREP.md`

合格标准：
- 你能把这个项目和“测开 / 质量平台 / BIOS CI 自动化”岗位连接起来

---

## 8. 最后要吃透到什么程度才算合格

## 8.1 基本合格

你至少要做到：

### A. 能讲
- 3 分钟讲清项目
- 1 分钟讲清 `/order`
- 1 分钟讲清 benchmark + gate

### B. 能改
- 自己补一个测试
- 自己改一个阈值
- 自己改一个返回字段

### C. 能答
至少能回答下面问题：
- 为什么幂等不能只靠 GET/SET
- 为什么 protected 不一定总比 baseline 好
- 为什么要多轮 benchmark
- 为什么 gate 读报告而不是重压
- Redis 异常时为什么限流 fail-open

如果这些做不到，就还不算吃透。

---

## 8.2 面试合格

如果你想拿去打秋招，建议达到这个标准：

### 1）你能自己从空白白板画出架构
至少画出：
- Flask 入口
- route 层
- resilience 层
- store 层
- Redis
- benchmark/gate

### 2）你能自己解释一次请求生命周期
包括：
- before_request
- 幂等
- 超时预算
- 锁内业务
- Redis 存储
- metrics
- after_request

### 3）你能自己说出项目边界
比如：
- 这是 demo，不是生产大规模系统
- security scan 是轻量版
- agent-eval 数据集仍然偏小

面试官反而会更相信你。

---

## 8.3 真正算“吃透”

满足下面 4 条，基本就是真吃透了：

1. **能独立跑通**
2. **能独立解释**
3. **能独立改动**
4. **能独立发现问题并提优化**

如果你还必须每次靠 AI 告诉你“这段代码是什么意思”，那还没吃透。

---

## 9. 我建议你的实际学习顺序

就按这个来：

### Day 1
- 看 `README.md`
- 看 `docs/run/GUIDE.md`
- 跑 `test`
- 跑 `bench`

### Day 2
- 看 `tests/test_app.py`
- 看 `app.py`
- 看 `chaos_service/http_api.py`

### Day 3
- 看 `chaos_service/store.py`
- 看 `chaos_service/resilience.py`
- 自己画 `/order` 流程图

### Day 4
- 看 `benchmark_compare.py`
- 看 `quality_gate.py`
- 看 `tests/test_benchmark_compare.py`

### Day 5
- 看 `replay_traffic.py`
- 跑 `.\run.ps1 -Task replay`
- 看 `reports/`

### Day 6
- 看 `agent-eval/README.md`

### Day 7
- 不看代码，自己脱稿讲一遍项目

如果讲不顺，再回头补。

---

## 10. 学习时最容易犯的错

### 错误 1：一上来硬啃所有代码
结果会乱。

### 错误 2：只看文档，不看测试
结果会停留在“会背”。

### 错误 3：只看功能，不看 trade-off
面试会挂在追问上。

### 错误 4：只会顺着讲，不会逆着问
面试官经常是反着问：
- 为什么这样设计
- 不这样会怎样

---

## 11. 你学习完后，最少要自己完成这 5 个动作

1. 自己解释 `/order` 整条链路
2. 自己跑一次 benchmark 并读懂报告
3. 自己跑一次 gate 并说明为什么 pass/fail
4. 自己给某个测试加一个新 case
5. 自己用 **`POST /fault/inject`** 与 **`fault_demo.py`** 跑通一轮注入/恢复，并读 **`reports/fault_demo_latest.json`**；若要练「报告 → gate」，仍以 **`benchmark_latest` + `security_scan` + `quality_gate.py`** 为主；BIOS 岗位叙事见 `PROJECT_POSITIONING_THREE_VERSIONS.md`

做完这 5 个动作，你对这个项目的掌控感会高很多。

---

## 12. 最后一句话

你吃透这个项目，不是为了“证明项目很牛”，而是为了让面试官相信：

> **这个项目真的是你能掌控、能解释、能修改、能继续演进的项目。**

这才是秋招里最值钱的东西。

---

## 配套执行版

如果你想按天打卡、量化每天工作量，继续看：

- [`PROJECT_MASTERY_DAILY_CHECKLIST.md`](PROJECT_MASTERY_DAILY_CHECKLIST.md)
