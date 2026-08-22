# ADR-0002：自研 agent-eval 评测管线，不引入 promptfoo/DeepEval

- 状态：已采纳（2026-08）
- 背景：工具调用稳定性评估（`agent-eval/`），78 条四维用例 + 质量门禁
- 决策人：仓库作者（个人项目）

## 背景

需要对「Agent 在不稳定环境下调用 HTTP 工具」的行为做回归评测并接入 CI 门禁。
业界方案：promptfoo（YAML 驱动、assert 丰富）、DeepEval（pytest 原生、指标库）。

## 决策

自研 run/score/gate 三段式管线（JSONL 数据集 + JSON/MD 报告 + 阈值门禁），
按四维组织：工具选择 / 上下文防捏造 / 权限边界 / 安全边界。

## 理由

1. **故障注入是第一公民**：核心评测场景是「无故障 vs 混合故障对照」
   （`chaos_compare.py --strict`）与多轮波动分析（`eval_variance.py`），
   需要与被测系统的 `/fault/*` 接口深度联动——这是框架不提供的能力。
2. **CI 确定性与离线可跑**：rule 模式 0 外部依赖、78 条 3 秒跑完、
   EVAL_SEED 固定可复现；CI 中不依赖 Node.js（promptfoo）或 LLM 网关。
3. **指标与门禁直连**：tool/arg 准确率、重试率、token 黑洞、探针独占等
   指标直接进 `unified_quality_gate.py` 统一门禁，无格式转换层。
4. **权限维度联动 policy-as-code**：评测 runner 直接调
   `PermissionChecker`（config/security_policy.yaml）做实测裁决，
   评测即安全边界的回归测试（框架无此概念）。

## 代价与权衡（诚实边界）

- 没有 promptfoo 的 Web UI、prompt 版本管理与 provider 生态。
- 没有 DeepEval 的 LLM 指标库（faithfulness、answer relevancy 等）。
- judge 抽检是本地 LLM 的简化判定，不是框架级 RAG 指标。

## 后续验证计划

- 引入 DeepEval 跑同一 `tool_eval.jsonl` 的对照评分，报告与自研 scorer
  的偏差（预期：rule 模式下两者一致，LLM 模式下 DeepEval 指标更丰富）。
  该实验完成后回填本 ADR 的「对照结果」一节。
