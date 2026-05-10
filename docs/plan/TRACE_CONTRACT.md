# Agent Runtime Trace 契约（轻量，P0）

> **范围**：`run_trace.new_trace_document` 聚合 JSON 与每 case 的 **`steps[]`**（`tools_client` 写入）。**不**绑定 protobuf / OpenTelemetry；字段以当前实现为准，变更时请改 `schema_version` 并更新本文件。

## 文件与入口

| 场景 | 典型路径 |
|------|----------|
| 单次 `run_agent_eval`（默认） | `agent-eval/reports/agent_eval_trace_latest.json`（或环境变量 **`AGENT_TRACE_FILE`**） |
| `chaos_compare` 两轮 | `agent-eval/reports/agent_trace_baseline.json`、`agent_trace_chaos.json`；摘要里 **`chaos_compare_latest.json` → `agent_trace_files`** |
| 静态时间线（P6） | **`python trace_timeline.py`** → `reports/trace_timeline_latest.{mmd,html}`；输入优先级见脚本 docstring（**`TRACE_TIMELINE_INPUT`** / `--input`） |

关闭落盘：**`AGENT_TRACE_ENABLED=0`**。

## 文档顶层（聚合 Trace Document）

| 字段 | 类型 | 说明 |
|------|------|------|
| `trace_id` | string (UUID) | 本次 trace 文档 ID |
| `run_id` | string (UUID) | 与评测 run 关联 |
| `generated_at` | int | Unix 秒 |
| `schema_version` | int | 当前 **`1`** |
| `eval_kind` | string | 如 `run_agent_eval` |
| `tools_base_url` | string | 工具 HTTP 基址 |
| `chaos_mode` | string | 混沌模式名 |
| `chaos_fail_rate` | number | 失败率注入参数 |
| `chaos_latency_ms` | int | 延迟注入参数（毫秒） |
| `cases` | array | 见下 |

## 每个 `cases[]` 元素

| 字段 | 类型 | 说明 |
|------|------|------|
| `case_id` | string | 用例 ID |
| `category` | string \| null | 可选分类 |
| `input` | string | 用户输入 |
| `steps` | array | HTTP 工具步骤，见下 |

## 每个 `steps[]` 元素（`type`: `tool_call`）

| 字段 | 类型 | 说明 |
|------|------|------|
| `step` | int | 序号（缓冲区内递增） |
| `type` | string | 固定 **`tool_call`** |
| `tool` | string | 逻辑工具名（如 `create_order`） |
| `method` | string | HTTP 方法 |
| `path` | string | 请求路径 |
| `retry_index` | int | 当前工具调用的重试下标（从 0 起） |
| `latency_ms` | number | 耗时（毫秒，约三位小数） |
| `http_status` | int | HTTP 状态码；异常时可能为 **0** |
| `error` | string \| null | 错误摘要 |
| `injected_fault` | bool | 是否经混沌注入失败 |

## 示例（节选）

```json
{
  "trace_id": "b1c2d3e4-...",
  "run_id": "a0f9e8d7-...",
  "generated_at": 1710000000,
  "schema_version": 1,
  "eval_kind": "run_agent_eval",
  "tools_base_url": "http://127.0.0.1:5000",
  "chaos_mode": "mixed",
  "chaos_fail_rate": 0.45,
  "chaos_latency_ms": 180,
  "cases": [
    {
      "case_id": "demo-1",
      "category": "order",
      "input": "宫保鸡丁两份",
      "steps": [
        {
          "step": 1,
          "type": "tool_call",
          "tool": "place_order",
          "method": "POST",
          "path": "/order",
          "retry_index": 0,
          "latency_ms": 42.5,
          "http_status": 201,
          "error": null,
          "injected_fault": false
        }
      ]
    }
  ]
}
```

## 兼容说明

- 若仅有顶层 **`steps[]`** 而无 **`cases`**，**`trace_timeline.py`** 会当作单 case **`run`** 渲染（向后兼容极简格式）。
- **`retry_count`** 等旧草案字段以 **`retry_index`** 为准（实现名）。
