# ADR-0001：自研轻量 Workflow Engine，不引入 LangGraph/LangChain

- 状态：已采纳（2026-08）
- 背景：AI Platform 的 agent 执行链需要节点编排（planner → tool → judge）
- 决策人：仓库作者（个人项目）

## 背景

`/api/v1/agent/run` 需要 Security → Planner → Tool → Judge 的编排能力。业界主流
方案是 LangGraph（或 LangChain），功能完善、社区活跃。

## 决策

自研约 100 行的 `WorkflowEngine`（`ai_platform/workflow/`）：Node 注册 +
Router 排序 + 状态传递 + span 级 trace。

## 理由

1. **可测性**：整个引擎无外部依赖，单测直接构造 Node/State 即可覆盖
   （含 hypothesis 状态机式探索），不需要 mock LangGraph 的执行模型。
2. **CI 确定性**：LangGraph 版本迭代快、抽象层多，CI 里失败原因难以归因；
   自研引擎的行为完全由本仓库代码定义。
3. **依赖面**：requirements-ai.txt 只需 fastapi/pydantic/uvicorn/PyYAML，
   镜像小、供应链审计面小（见 supply-chain.yml 的 pip-audit/SBOM）。
4. **教学目的**：本项目是质量工程项目，理解「编排引擎的本质是状态机」
   比会调框架 API 更重要——熔断器状态机测试（tests/unit/*_stateful.py）
   与 workflow 引擎共享同一套思维方式。

## 代价与权衡（诚实边界）

- 没有 LangGraph 的 checkpoint/persistence/流式回调/生态集成。
- 编排语义简单（顺序 + 路由），不支持条件分支图、并行节点。
- 如果未来需要 human-in-the-loop、跨会话状态恢复、多 agent 协作，
  **应迁移到 LangGraph**，本引擎不追求覆盖这些场景。

## 后续验证计划

- 用同一评测数据集分别跑自研引擎与 LangGraph 实现的对照实验，
  报告行为一致性（记录于 PROJECT_OWNERSHIP_MASTER_PLAN_V2.md）。
