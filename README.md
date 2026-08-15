# Chaos Demo — AI-Native 质量工程平台

> **版本**: 3.0.0 · **日期**: 2026-07-25

Chaos Demo 是一个双引擎质量工程平台，展示 **AI Agent 质量保障**与**韧性工程**两大实践的交叉融合。平台提供构建、加固、评估、持续测试 AI Agent 的完整流水线，并以一个生产级混沌工程系统作为被测对象。

---

## 架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Chaos Demo Platform v3                          │
│                                                                     │
│   ┌──────────────────────────┐   ┌─────────────────────────────────┐│
│   │   Chaos Service          │   │   AI Platform (FastAPI :8000)   ││
│   │   (Flask :5000)          │   │                                 ││
│   │                          │   │   AIPlatformService             ││
│   │   Order API              │   │     │                           ││
│   │   Fault Injection (4种)  │   │     ▼                           ││
│   │   Resilience Layers (4层)│   │   SecurityGuard (4层洋葱模型)   ││
│   │   Traffic Replay         │   │     │                           ││
│   │   Prometheus + Grafana   │   │     ▼                           ││
│   │                          │   │   AgentRuntime                  ││
│   │   ── 被测系统 ──────────  │   │     │                           ││
│   └──────────────────────────┘   │     ▼                           ││
│                                   │   WorkflowEngine → Tools       ││
│                                   │     │                           ││
│                                   │     ▼                           ││
│                                   │   LLM Gateway (4种Provider)    ││
│                                   │     │                           ││
│                                   │     ▼                           ││
│                                   │   EvaluationEngine → Gate      ││
│                                   │     │                           ││
│                                   │     ▼                           ││
│                                   │   Observability Collector      ││
│                                   └─────────────────────────────────┘│
│                                       │                              │
│                                       ▼                              │
│                          Redis · Prometheus · Grafana                │
└─────────────────────────────────────────────────────────────────────┘
```

Chaos Service 扮演**被测系统**角色 — 一个带有故意注入故障模式的真实 Flask 应用。AI Platform 提供**质量保障层** — 执行 Agent、安全检查、输出评估、质量门禁。

---

## 核心能力

### 1. AI Platform Core

中心编排层。`AIPlatformService` 管理完整请求生命周期：

```
Request → Security → Agent → Workflow → Tools → LLM → Evaluation → Gate → Result
```

每个阶段通过可观测性收集器发出 Trace Event。配置集中在 `PlatformConfig`，支持文件化配置（`to_dict`/`from_dict`）。`PlatformFactory` 创建全部 9 种组件类型（collector、security_guard、security_policy、workflow_engine、tool_registry、tool_executor、evaluation_engine、quality_gate、agent_runtime）。所有组件均可注入、可替换。

**API 端点** (`/api/v1/`)：
- `POST /agent/run` — 执行 Agent，走完整流水线
- `GET /health` — 服务健康检查
- 响应包含：`success`、`answer`、`score`、`security_score`、`trace_id`、`evaluation`、`gate`、`violations`

### 2. Agent Runtime

`AgentRuntime` 是 AI Agent 的执行上下文。它包装 `WorkflowEngine`，集成 `SecurityGuard` 进行请求校验，并通过可观测性收集器记录每一次生命周期事件（`agent.run.start`、`agent.run.end`、`agent.error`）。

关键设计决策：
- **无状态执行**：每次 `run()` 调用创建新的 `AgentState`，请求之间无共享可变状态
- **默认可观测**：追踪默认开启，除非显式禁用
- **安全集成**：可选注入 `SecurityGuard` 或 `SecurityPolicy`，Runtime 在工作流执行前进行安全检查
- **元数据透传**：调用方可附加任意元数据，贯穿整条链路

### 3. Workflow Engine

`WorkflowEngine` 按序执行 `Node` 实例。每个节点接收 `AgentState` 和 `AgentContext`，返回修改后的状态。

- **可插拔节点**：节点按名称注册，运行时可查找
- **Router 支持**：可选 `WorkflowRouter`，根据状态进行条件化节点排序
- **完整可观测**：`WorkflowEvent` 记录每次执行的节点数量、名称、耗时和错误
- **错误韧性**：节点失败记录为 `SpanStatus.ERROR`，并传播为 `AgentExecutionError`

### 4. Tool Framework

Tool 是动作层 — Agent 调用 Tool 查询数据、执行命令或调用外部 API。

- **`BaseTool`**：抽象基类，包含 `name`、`description`、`schema`（基于 dict 的参数定义）和 `execute(params, context)` 方法
- **`ToolRegistry`**：命名 Tool 容器，含重复注册检测
- **`ToolExecutor`**：执行 Tool 并集成安全检查。每次执行记录 `ToolEvent`（参数、结果、耗时、成功/失败状态）
- **内置演示 Tool**：`QueryLogsTool`、`QueryMetricsTool`、`AnalyzeIncidentTool` — 演示故障诊断工作流的编排链路；后端为内置模拟日志/指标数据（`_SIMULATED_LOGS`），用于跑通「工具调用 → 根因分析」的端到端流程，非真实线上诊断

### 5. LLM Gateway

`LLMGateway` 提供跨多种 LLM 后端的统一接口：

| Provider | 模式 | 适用场景 |
|---|---|---|
| `MockProvider` | 确定性响应 | 快速迭代、CI 测试 |
| `OllamaChatProvider` | 本地对话模型 | 开发环境、离线环境 |
| `OllamaGenerateProvider` | 本地补全模型 | 文本生成任务 |
| `OpenAICompatibleProvider` | API 兼容端点 | 生产环境，任何 OpenAI 兼容服务 |

关键特性：
- **`GatewayConfig`**：基于文件的 provider/model/timeout 配置
- **`LLMRequest`/`LLMResponse`**：所有 Provider 统一的请求/响应类型
- **Provider 切换**：配置驱动，支持单次请求覆盖
- **错误分类**：`LLMError` 带有类型化错误分类（`provider_not_found`、`timeout`、`model_error`）和可重试标志

### 6. Security Layer

`SecurityGuard` 实现 4 层纵深防御模型：

```
InputValidator → PromptGuard → PermissionChecker → OutputChecker
```

- **InputValidator**：长度约束（`max_input_length: 4096`）、屏蔽关键词、正则模式匹配
- **PromptGuard**：22 种注入检测模式，覆盖直接指令覆盖（"忽略前面的指令"）、角色扮演（"假装你是"）、越狱攻击（"DAN 模式"）、系统提示词提取。支持按模式单独启用/禁用
- **PermissionChecker**：Tool 级别访问控制 — 验证 Agent 是否有权调用请求的每个 Tool
- **OutputChecker**：执行后输出扫描，检测敏感数据泄漏和策略违规

`SecurityPolicy` 完全可序列化（`to_dict`/`from_dict`），支持按环境配置安全策略。`SecurityResult` 携带结构化违规数据（规则名称、严重级别、匹配模式）贯穿流水线。`SecurityEvent` 集成可观测性收集器，生成审计追踪。

### 7. AI Evaluation

评估引擎提供 Agent 输出的多维度质量打分：

| 评估器 | 方法 | 指标 |
|---|---|---|
| `ScoreEvaluator` | 启发式打分 | `tool_selection_accuracy`、`arg_accuracy`、`retry_rate`、`hallucination_rate`、`planner_invalid_rate` |
| `JudgeEvaluator` | LLM-as-Judge | 二元 PASS/FAIL + 结构化推理 |
| `RegressionEvaluator` | 基线对比 | 每个指标的 delta 与阈值门禁 |

**`EvaluationEngine`** 依次执行已注册的评估器，汇总结果到 `EvaluationResult`（success、score、metrics、details、errors、metadata），并记录 `EvaluationEvent` 追踪。

**`QualityGate`** 强制执行 6 项可配置阈值：
- `tool_selection_accuracy_min`（默认 0.70）
- `arg_accuracy_min`（默认 0.70）
- `avg_tool_calls_per_task_max`（默认 10.0）
- `retry_rate_max`（默认 0.30）
- `hallucination_rate_max`（默认 0.10）
- `planner_invalid_rate_max`（默认 0.10）

`RegressionEvaluator` 增加额外的逐指标回归容忍度检查 — 每个指标的退化不能超过其配置边界（例如 tool_selection_accuracy 下降不能超过 0.05）。

阈值被违反时，抛出 `AgentGateError` 并附带详细失败原因。门禁结果作为 `GateEvent` 记录在 Trace 中。

### 8. Regression Testing

Prompt 回归是一等公民工作流，用于验证模型或 Prompt 变更不会导致质量退化：

1. 从参考版本加载**基线指标**（`baseline.json`）
2. 将**候选版本**通过同一评估流水线运行
3. `RegressionEvaluator` 计算每个指标的 delta，对照可配置的容忍度
4. `QualityGate` 发出 **PASS**（可以部署）或 **FAIL**（检测到退化）决策

回归工作流在 `demo/scenarios/regression/` 中演示，通过 `tests/demo/test_regression_demo.py` 测试。

### 9. Chaos Engineering

Chaos Service 为韧性和质量测试提供真实目标：

- **故障注入**（4 种）：`latency`（人为延迟）、`exception`（强制 500）、`drop`（连接中断）、`slow_db`（数据库减速）
- **韧性防护**（4 层）：Rate Limiter（固定/滑动窗口）、Circuit Breaker（CLOSED/OPEN/HALF_OPEN 状态机，阈值可配置）、Idempotency（4 状态模型，Redis 去重）、Retry（指数退避 + jitter）
- **可观测性**：Prometheus 指标端点、5 个 Grafana 仪表盘、JSON 结构化日志、流量录制/回放
- **Docker Compose**：完整技术栈（app + Redis + Prometheus + baseline 变体用于 A/B 对比）

---

## 工程实践

### 测试

```bash
# 全量测试
pytest tests/ -v

# 快速反馈（smoke 标记）
pytest tests/ -q -m "smoke"

# AI Platform 测试
pytest tests/ tests/demo/ tests/core_platform/ -v

# 演示场景
python demo/run_demo.py all
pytest tests/demo/ -v
```

**测试分布**（61 个测试文件）：

| 层级 | 目录 | 关注点 |
|---|---|---|
| 单元 | `tests/unit/` | 熔断器、限流器、重试策略、故障注入、日志、可观测性 |
| AI 模块 | `tests/core_platform/` | Agent Runtime、Workflow、Tool、LLM Gateway、评估、可观测性、安全 |
| 平台 | `tests/core_platform/` | Config、Factory、Service、API 端点 |
| 集成 | `tests/integration/` | API 契约、混沌实验、Redis 集成 |
| 演示 | `tests/demo/` | 故障诊断、安全测试、回归门禁 |
| 端到端 | `tests/e2e/` | 全栈、性能回归 |
| 部署 | `tests/deployment/` | Docker 配置验证 |

**测试实践**：基于 pytest fixture 的组件准备、Mock LLM Provider 保证确定性测试、smoke 标记用于 CI 快速反馈、参数化测试覆盖边界情况、`monkeypatch` 进行环境隔离。

### CI/CD

三个 GitHub Actions 工作流：

- **`ci.yml`**：代码质量（lint、类型检查）+ 单元/集成测试 + Docker 构建
- **`ai-quality.yml`**：AI 评估门禁 — 在每个 PR 上运行完整评估流水线，Quality Gate 未通过则阻塞合并
- **`qa.yml`**：安全扫描 + 基准对比 + 回归检测

### 可观测性

覆盖两个引擎的双栈可观测性：

- **AI Platform**：`Collector` 记录结构化 Trace/Span/Event/Metrics。Event 遵循类型化层次结构（`AgentEvent`、`NodeEvent`、`ToolEvent`、`LLMEvent`、`EvaluationEvent`、`GateEvent`、`WorkflowEvent`）。每个 Event 携带 `trace_id`、`span_id`、`timestamp` 用于关联。
- **Chaos Service**：Prometheus 指标（请求数、延迟直方图、错误率、熔断器状态、限流器使用量）+ JSON 结构化日志 + Grafana 仪表盘
- **Trace 契约**：每个 AI Platform 请求获得唯一 `trace_id`，贯穿所有流水线阶段，支持端到端请求回放。

---

## 快速开始

### 环境要求

- Python 3.11+
- Redis（Chaos Service 需要）
- Docker & Docker Compose（可选）

### Chaos Service

```bash
docker compose up -d
curl http://localhost:5000/healthz
curl -X POST http://localhost:5000/order \
  -H "Content-Type: application/json" \
  -d '{"item_id": "item-42", "quantity": 3}'
```

### AI Platform

```bash
docker compose -f docker-compose.ai.yml up -d
curl http://localhost:8000/api/v1/health
curl -X POST http://localhost:8000/api/v1/agent/run \
  -H "Content-Type: application/json" \
  -d '{"request": "诊断 Redis 连接池耗尽问题", "mode": "rule"}'
```

### 本地开发

```bash
pip install -r requirements.txt -r requirements-ai.txt
python app.py                                    # Chaos Service (port 5000)
uvicorn ai_platform_api:app --port 8000          # AI Platform (port 8000)
```

---

## 项目亮点

**面向测试开发 / 质量工程岗位：**

- **AI 评估流水线**：设计并实现多评估器质量框架（Score、Judge、Regression），配有 6 阈值 Quality Gate — 与前沿 AI 公司验证模型部署的模式一致
- **LLM-as-Judge**：构建 JudgeEvaluator，使用一个 LLM 评估另一个 LLM 的输出质量，支持可配置采样率和结构化 PASS/FAIL 推理
- **AI 回归测试**：创建基线-vs-候选对比系统，在 Prompt 或模型变更时检测逐指标退化，支持 AI 功能的安全持续部署
- **安全测试自动化**：实现 4 层安全防护，包含 22 种注入检测模式，以及自动化安全扫描，通过对响应体进行上下文感知的严重级别分类来分析 SQLi 信号
- **全栈测试架构**：64+ 测试文件覆盖单元、集成、E2E、演示和部署层 — 按测试类型组织，配合 smoke 标记实现 CI 快速反馈
- **CI/CD 质量门禁**：3 个 GitHub Actions 工作流，其中一个 AI 专属质量门禁在评估阈值被违反时阻塞 PR
- **可观测性驱动测试**：自定义 Trace/Span/Event 收集器，带类型化事件层次结构 — 每次 AI 请求生成完整、可查询的执行记录，用于调试和审计

---

## 面试讨论话题

**LLM 驱动的系统怎么测试？**

平台采用分层方法。`ScoreEvaluator` 验证结构正确性（Agent 是否选了正确的 Tool？参数是否正确？）。`JudgeEvaluator` 使用 LLM 评估语义质量（回答是否真的有帮助且正确？）。`QualityGate` 对两个维度的数值阈值进行强制检查。核心洞察：不能用简单的 pass/fail 断言测试 LLM 输出 — 需要结合启发式指标、参考基准对比和 LLM-as-Judge 评估。

**如何保证 Agent 在不同版本间的稳定性？**

Prompt 回归是关键。从已知良好版本捕获评估指标的基线快照（tool 选择准确率、参数准确率、重试率、幻觉率）。每个候选变更通过相同的评估流水线运行。`RegressionEvaluator` 计算逐指标 delta，`QualityGate` 在任何指标超过配置容忍度时阻塞部署。这在概念上等同于性能回归测试 — 但应用于 LLM 质量指标。

**如何设计一个 AI Evaluation 框架？**

框架需要三种评估器类型：启发式（基于规则的结构属性打分）、Judge（LLM-as-Judge 语义评估）、回归（基线-vs-候选对比）。每种评估器产生标准化的 `EvaluationResult`（success、score、结构化 metrics）。`EvaluationEngine` 按序运行并汇总结果。带有可配置阈值的 `QualityGate` 做出最终 PASS/FAIL 决策。可观测性至关重要 — 每次评估运行必须产生 Trace Event 以保证可审计性。

**如何加固一个执行 Tool 的 AI Agent？**

纵深防御。`InputValidator` 在边界阻断恶意输入模式。`PromptGuard` 检测 22 种已知注入技术。`PermissionChecker` 执行 Tool 级别访问控制 — Agent 只能执行其被授权的 Tool。`OutputChecker` 在响应到达用户前扫描敏感数据泄漏。每一层产生带有结构化违规数据的 `SecurityResult`，同时流入评估流水线和可观测性 Trace。

**AI 系统的 CI/CD 流水线应该是什么样的？**

在标准的 lint/build/test 之外，AI 流水线需要评估门禁。本项目中的 `ai-quality.yml` 在每个 PR 上运行完整评估引擎 — 如果 `QualityGate.check()` 抛出 `AgentGateError`，PR 被阻塞。这可以阻止意外质量退化进入生产环境。`qa.yml` 工作流增加安全扫描和基准对比，实现纵深防御。
