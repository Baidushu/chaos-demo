# 评测卡（EVAL CARD）— agent-eval

> 对标行业惯例：模型卡（Model Card）/ 数据集说明书（Datasheet）的核心要素——**对象、方法、指标、限制、防污染**。评测结论离开这些上下文就不可解释，故随仓库版本化。

## 1. 评测对象

| 项 | 说明 |
|---|---|
| 被测系统 | Chaos Service 订单 API（:5000）+ 工具调用 Agent（`agent-eval/scripts/run_agent_eval.py`） |
| 被测能力 | 工具选择与参数、调用时序、上下文防捏造、权限边界、安全边界 |
| Agent 规划器 | `AGENT_MODE=rule`（确定性规则，CI 默认）/ `llm`（真实大模型）/ `ollama`（本地模型） |
| 工具执行 | 真实 HTTP 客户端（`tools_client`），接口不可达时离线兜底 |

## 2. 评测集构成

| 数据集 | 规模 | 组织方式 | 用途 |
|---|---|---|---|
| `datasets/tool_eval.jsonl` | 78 条 | 四维行为矩阵：工具选择(normal/workflow/ask_user) / 安全边界(attack) / 上下文防捏造(context) / 权限边界(permission) | 主评测 + 门禁 |
| `datasets/judge_bias_pairs.jsonl` | 8 组 | 成对答案 + 人工参考标注 | Judge 位置偏置实验 |

**期望值来源**：人工编写并与实现语义对齐（如"熔断打开条件在每个 outcome 评估""quantity 缺省 1 为既有契约"）。期望值写"理想"而实现是"现实"时，测出的失败属**校准错误**，须先改期望。

## 3. 评测方法

| 评估器 | 机制 | 指标 |
|---|---|---|
| ScoreEvaluator | 启发式规则 | `tool_selection_accuracy`、`arg_accuracy`、`retry_rate`、`hallucination_rate`、`planner_invalid_rate`、`permission_denial_accuracy` |
| JudgeEvaluator | LLM-as-Judge（二元 PASS/FAIL + 结构化推理，可配采样率） | `judge_pass_rate`、`judge_checked_cases` |
| RegressionEvaluator | 基线快照 vs 候选，逐指标 delta + 容忍度 | 各指标 delta 与门禁判定 |

**门禁阈值**（`config/eval_config.yaml` 与 `ai_platform/evaluation/gate.py`）：tool_selection ≥0.70、arg_accuracy ≥0.70、avg_tool_calls ≤10、retry ≤0.30、hallucination ≤0.10、planner_invalid ≤0.10。阈值随业务场景校准，**非行业统一标准**。

**混沌联动**：`chaos_compare.py --strict` 做"无故障 vs 混合故障"对照，附加 token 黑洞门禁（token_surge ≤30%、retry_surge ≤25%、重试税 ≤150%，重试样本 <5 条时跳过）。

## 4. 已知限制（诚实边界）

1. **规模小**：78 条覆盖四维行为，不等于真实流量的分布；机制与行业 golden set 同构，规模是刻意控制的。
2. **评测环境为单机**：压测与故障注入均为应用内协作式模拟，不含网络层故障。
3. **Judge 不可靠**：位置偏置实验（8 组 × 3 轮，deepseek-chat）测得 flip_rate 4.2%(±7.2%)、首位胜率 48.9%(±1.9%)——**样本量不足以判定该模型是否存在位置偏好**，但已证实"Judge 单轮结论不可直接采信"（首轮曾出现 12.5%/56.2% 的偏离，多轮后回落）。工程上需双向判定/多 judge 投票/人工抽检校准。
4. **token 为启发式估算**：未接真实模型时按提示词长度估算（`TOKEN_METRIC=auto`），接入 Ollama 后可用真实计数。
5. **规则规划器与 LLM 规划器行为不同**：CI 默认 rule 保证确定性，LLM 模式的结果波动需用 `eval_variance.py` 单独度量。

## 5. 防污染声明

- 两个数据集均为**本项目手写**，未摘录公开基准或模型训练语料。
- 用例主题限定本仓库业务域，与 MMLU/HumanEval/GSM8K 等公开评测集**无交集**。
- 后续若引入公开基准或线上失败案例回流，须在 PR 标注来源与时间，优先用改写变体复测。

## 6. 版本与可追溯性

- 数据集、评分脚本、门禁阈值同仓版本化：变更走 git diff + CI。
- 报告（`reports/agent_eval_latest.*`、`chaos_compare_latest.*`、`judge_bias_latest.*`）记录生成时间、模型/provider、阈值版本，保证结论可复现、可追溯。
