# 平台收敛路线图（Trace → 统一门禁 → …）

> **用途**：把仓库从「能力清单」收敛成 **一条可讲的 AI 系统质量工程平台**；**实现状态以代码与 [`../AI_PROJECT_CONTEXT.md`](../AI_PROJECT_CONTEXT.md) 为准**，本表**随迭代更新「状态」列**。  
> **原则**：AI 能力尽量作为 **被测对象 / pipeline 阶段**；**不**往 RAG/MCP/多 Agent 热点堆功能。  
> **叙事口径**：见全景文 **§1.0**、[`../TEST_STRATEGY.md`](../TEST_STRATEGY.md)。

---

## 总览计划表（执行顺序）

| 阶段 | 优先级 | 目标（一句话） | 交付物 / 验收 | 主要代码与配置（预估） | 估时（参考） | 状态                                                         |
|------|--------|----------------|---------------|-------------------------|--------------|--------------------------------------------------------------|
| **P0** | P0     | **Trace 契约** | `trace_id`/`run_id`、**`steps[]`** 字段约定文档 + 示例 JSON；与现有 report 目录规则一致 | 本文件 + `agent-eval/scripts/*`（后续） | 0.5～1 天    | 进行中（本文已建）                                           |
| **P1** | P0     | **最小 Runtime Trace 落盘** | 每次 `run_agent_eval` 或 `chaos_compare` 一轮产生 **`agent-eval/reports/*trace*.json`**（或并入 eval JSON 的 `trace` 字段）；每步含 **tool、latency_ms、http_status、retry_count**（token 可选） | `agent-eval/scripts/tools_client.py`、`run_agent_eval.py`、`chaos_compare.py` | 3～7 天     | 未开始                                                       |
| **P2** | P0     | **Unified Quality Gate（初版）** | 单一入口或薄编排：**`final_decision` + `reasons[]`** JSON；先 **串联** 根目录 `quality_gate.py` 逻辑 +（可选）`agent-eval` gate，**不**一夜重写 | 新建如 `unified_quality_gate.py` 或扩展 `quality_gate.py`；`qa.yml` 最后一步 | 5～10 天    | 未开始                                                       |
| **P3** | P1     | **Trend / 历史进门禁（可选规则）** | `benchmark_trend_latest` 或 history 中位数 **一条规则** 接入 unified gate；**可开关** | `quality_gate.py` 或 unified 脚本 | 2～5 天     | 未开始（当前根 gate **不读** trend，见全景 §1.0）           |
| **P4** | P1     | **Semantic / Prompt A/B 回归（小步）** | 同数据集 **baseline vs candidate** 两次跑分 + 对比报告 + gate 阈值；Judge **抽检/可选** | `agent-eval` 配置 + 小脚本 `prompt_regression.py`（名可调整） | 1～2 周     | 未开始                                                       |
| **P5** | P2     | **Agent Runtime 混沌** | 对 **trace 中某一步** 注入失败/延迟，观测 retry/循环/token；**后置** | `agent-eval` + 或 fault 编排 | 1～2 周+     | 未开始                                                       |
| **P6** | P2     | **Trace 静态可视化** | 从 trace JSON 生成 **HTML/Mermaid** 时间线；**不做**复杂 SPA | 小脚本 + `reports/` 或 `agent-eval/reports/` | 2～5 天     | 未开始                                                       |

**图例**：`未开始` → `进行中` → `已完成`；完成后在本表与 **`AI_PROJECT_CONTEXT` §11/§13** 回写路径与行为。

---

## 阶段 P1：Trace JSON（最低成本草案）

以下为 **v0 草稿**，实现时可微调字段名，但**尽量少改**以免破坏回放/对比。

```json
{
  "trace_id": "uuid",
  "run_id": "same-as-or-derived-from-eval-run",
  "generated_at": 1710000000,
  "scenario": "optional",
  "steps": [
    {
      "step": 1,
      "type": "tool_call",
      "tool": "create_order",
      "method": "POST",
      "path": "/order",
      "latency_ms": 42.0,
      "http_status": 201,
      "retry_count": 0,
      "error": null
    }
  ]
}
```

---

## 阶段 P2：Unified Gate 输出（草案）

```json
{
  "final_decision": "PASS",
  "generated_at": 1710000000,
  "reasons": [],
  "checks": {
    "benchmark": "PASS",
    "security": "PASS",
    "agent_eval": "SKIPPED"
  }
}
```

**失败示例**：`final_decision`: `FAIL`，`reasons`: `["benchmark: protected p95 regression", "..."]`。

---

## 明确不做（本路线图内）

| 项 | 原因 |
|----|------|
| 重做大型 RAG | 同质化、与主线弱相关 |
| MCP / 多 Agent 平台 | 易变 Demo，工程边界难控 |
| 复杂前端 Trace UI | 秋招时间性价比低 |

---

## 维护约定

1. 合并 PR 若完成某阶段，**更新本表「状态」**并改 **`AI_PROJECT_CONTEXT`** 对应小节（§7 CI、§10 gate、§11 报告路径等）。  
2. 不写「已完成」除非 **CI 或本地标准命令**可复现。
