# Agent 测试项目计划（测开方向）

> **文档定位（2026-03）**：本仓库按 **个人 demo / 秋招可讲** 维护，Agent 侧为 **约 10 条** `tool_eval.jsonl` + 完整脚本链；不追求大规模数据集与论文级统计。下文保留「理想形态」供日后加深时参考。  
> **答辩口径**：闭环（eval→score→gate→chaos 对照→CI）为真；规则路由、启发式 token、简易幻觉、客户端侧 chaos、工具离线兜底等属 **demo 取舍**，见 **§2.1**。  
> **与全景文关系**：**脚本入口、环境变量、与 `app` 的 URL 关系** 以 [`../AI_PROJECT_CONTEXT.md`](../AI_PROJECT_CONTEXT.md) **§8** 与仓库根 [`agent-eval/README.md`](../../agent-eval/README.md) 为准；**本篇不重复**命令行手册。  
> **导航**：文档地图见 [`../README.md`](../README.md)（面试/速查/深挖另有专篇）。

## 1. 项目目标

构建一个“智能下单”场景的双层质量保障项目：
- 上层：Agent/LLM 工具调用质量评测（正确性、幻觉、安全、鲁棒性）
- 下层：服务稳定性与性能验证（你现有 `chaos-demo` 已覆盖）

最终目标是形成可复现的评测流程：`eval -> score -> gate -> report`，并将在线评测 API 成本降到近似 0（本地判官为主，在线模型仅可选抽检）。

---

## 2. 范围与边界

### 本期要做（MVP）
- 单 Agent 工具调用测试（下单、查询、取消）
- 自动打分与质量门禁
- 输出结构化报告（JSON + Markdown）
- 接入本地脚本执行与后续 CI

### 个人 demo 边界（当前）
- 数据集：**手写 JSONL，约 10 条**（正常 + 攻击/异常），按需自增。
- 运行：`AGENT_MODE=rule` 即可展示闭环；Ollama 为可选。
- CI：`.github/workflows/qa.yml` 已包含 `chaos_compare.py --strict`（`AGENT_EVAL_SKIP_JUDGE=1`，不依赖判官服务）。

### 本期不做
- 多 Agent 协作编排
- 复杂 RAG 管道评测
- 在线流量灰度平台

### 诚实边界（简化、半实现、未实现）

面试/自评时建议主动区分三类，避免被追问时口径漂移。

**A. 基本未做（或仅存在于配置/文档中的概念）**

| 项 | 说明 |
|----|------|
| 多轮对话评测 | 仍为单轮 `input` → 规划 → 工具，无会话状态机。 |
| 云端 API 与 `usage` | 未接 OpenAI 等；账单级 token 对齐未做。 |
| 双模型 A/B | 无 baseline/candidate 两套 Planner 对照；现有为 **无 chaos / mixed chaos** 环境对照。 |
| 多判官、一致性、置信区间 | 未实现。 |
| 安全/越权独立指标 | 无单独统计，主要靠规则 + 少量样例。 |
| 错别字、长输入等鲁棒专项 | 未做。 |
| `eval_config` 中 `baseline_model` / `candidate_model` | 字段保留，**执行逻辑未使用**。 |

**B. 做了一半（能展示，但非生产测开平台）**

| 项 | 说明 |
|----|------|
| LLM Judge | 单路本地 Ollama；可抽检、可关；非多判官、非云端 GPT。 |
| 差分与波动 | `eval_variance` 有均值/极差/标准差；无双模型、无置信区间。 |
| Call Sequence 指标 | 与「整段工具列表是否一致」同口径；未单独拆「顺序错、集合对」。 |
| 故障注入 | 在 **工具客户端**侧模拟延迟/失败；**不等价于**对 Flask/Redis 进程的真实故障实验（服务侧压测为另一条线）。 |
| CI 中 Agent | `AGENT_EVAL_SKIP_JUDGE=1`，不跑判官。 |

**C. 简化实现或模拟（demo 常见取舍）**

| 项 | 说明 |
|----|------|
| `AGENT_MODE=rule` | 关键词 + 正则，**非**语义理解级 NLU。 |
| Token | `rule` 下多为 **启发式**；`ollama` 时用 Ollama 返回计数，仍非官方 `usage`。 |
| 幻觉率 | 代码内 **极少规则**（如特定输入+输出模式），非通用幻觉检测。 |
| `tools_client` 离线兜底 | 不可达时返回假订单号等，**便于本地调试**；严肃评测建议服务可用。 |
| `parse_simple_yaml` | 自写极简解析，**非**完整 YAML。 |
| 单测中 Redis | `FakeRedis`，测 Flask 逻辑，不测真实 Redis 协议。 |

---

## 3. 目录规划

**状态（2026）**：`agent-eval/` 目录结构**已落地**（`datasets/`、`scripts/`、`reports/`、`config/`），与上节 MVP 一致。具体文件名、产物路径、CI 中 `chaos_compare --strict` 等以 **[`../AI_PROJECT_CONTEXT.md`](../AI_PROJECT_CONTEXT.md) §8** 与 **[`../../agent-eval/README.md`](../../agent-eval/README.md)** 为准；下文 **§4 起**为指标愿景与长期增强，**不等价**于当前脚本已全部实现。

---

## 4. 评测维度与指标

### A. 工具调用正确性（核心）
- Tool Selection Accuracy（工具选择准确率）
- Argument Accuracy（参数准确率）
- Call Sequence Accuracy（调用顺序准确率）
- Task Success Rate（任务完成率）

### B. 幻觉（Factuality/Hallucination）
- Hallucination Rate（幻觉率）
- Proper Refusal Rate（不可回答场景下的正确拒答率）

### C. 安全（Safety）
- Safety Violation Rate（违规输出率）
- Over-permission Tool Call Rate（越权调用率）

### D. 鲁棒性（Robustness）
- Typo Robust Pass Rate（错别字输入通过率）
- Long Input Stability（长输入稳定性）
- Multi-turn Consistency（多轮一致性）

### E. 差分测试（Differential Testing）
- Judge Consistency（判官一致性）
- Candidate vs Baseline Delta（候选模型相对基线变化）
- Variance Under Multi-run（多次运行波动）

---

## 4.1 硬核增强项（建议强制纳入）

### 1) 差分测试（必须）
- 不是只看单模型绝对分，而是做 `baseline_model` vs `candidate_model` 对照。
- 引入 LLM-as-a-Judge（如 GPT-4o-mini）作为辅助判官，降低单一规则误判。
- 对同一 case 运行多次，统计波动，避免一次性随机结果误导结论。

### 2) 工具调用攻击性边界测试（必须）
- 参数污染：在用户输入中注入越权/恶意指令。
- 状态机矛盾：如“先取消订单再查物流”。
- 缺参依赖：只给 `item_name` 不给 `item_id`，观察是否追问而非瞎猜。

### 3) 与底层故障联动（强烈建议）
- 复用 `chaos-demo` 的故障注入能力（500/高延迟），不强依赖 Chaos Mesh。
- 观察 Agent 在异常下行为：重试策略、用户提示、是否出现死循环。
- 增加成本指标：每任务平均工具调用次数、失败时 token 浪费风险。

---

## 4.2 学生低成本执行策略（强制遵守）

### A. Judge 分层策略（避免烧钱）
- 第一层：规则判分（工具选择、参数、调用顺序、重试次数），覆盖 100% 样例。
- 第二层：LLM Judge 只做争议样例抽检（建议 10%~20% 样本）。
- 第三层：人工复核小样本（建议 10 条）校验 Judge 可靠性。

### B. 模型使用建议（按预算）
- 预算低：候选模型用本地/开源模型，Judge 用 GPT-4o-mini 抽检。
- 预算中：关键里程碑时增加一次更强 Judge 复核（非每次都跑）。
- 不建议：全量样本都走大模型 Judge（成本高且收益有限）。
- 本地 Judge 推荐：`Qwen2.5-7B-Instruct` 或 `Gemma-2-9B`（通过 Ollama/vLLM 部署）。

### C. 成本观测与门禁（防 Token 黑洞）
- 在 `run_agent_eval.py` 记录：每任务 token（启发式 + 可选 Ollama 真实计数）、重试次数、工具调用次数。
- 单轮门禁：`gate_agent_eval.py`（工具/参数/幻觉率、planner 无效率、retry 等，见脚本内阈值）。
- **对照门禁**（`chaos_compare.py`，可选 `--strict`），环境变量示例：
  - `CHAOS_TOKEN_SURGE_MAX`：全量 `avg_token_per_task` 相对基线增幅上限（默认 0.30）
  - `CHAOS_RETRY_SURGE_MAX`：`retry_rate` 相对基线增幅上限（默认 0.25）
  - `CHAOS_FAIL_PATH_TOKEN_SURGE_MAX`：`avg_token_rule_fail` 相对基线增幅（默认 0.50）
  - `CHAOS_RETRY_PATH_TOKEN_SURGE_MAX`：两侧均有重试样本时，`avg_token_with_retry` 跨轮增幅（默认 0.60）
  - `CHAOS_RETRY_TAX_MAX`：故障轮内 **重试税** `(有重试均值-无重试均值)/无重试均值`（默认 **0.60**，小样本可调低为 0.50）

### D. 核心原则
- 面试目标不是“刷到 95 分”，而是“60 分版本能被门禁拦住，不进生产”。
- 任何高分必须可复现、可解释、可追溯到样例。
- 对外表述使用“近似 0 API 成本”，避免使用“完全 0 成本”。

---

## 5. 里程碑计划（参考排期；当前仓库已覆盖核心）

以下为 **理想 10～14 天** 拆解，便于理解模块先后；**个人 demo 已落在 M1～M4 + 对照门禁 + CI**，不必再凑样本数量。

| 阶段 | 内容 | 当前状态 |
|------|------|----------|
| M1 | `agent-eval/` 骨架、数据字段、`tool_eval.jsonl` | **已完成**（样例约 10 条即可） |
| M2 | `run_agent_eval.py`、统一原始结果格式 | **已完成** |
| M3 | `score_agent_eval.py`、`chaos_compare.py`、可选 `judge_local.py` | **已完成** |
| M4 | `gate_agent_eval.py`、成本/重试门禁 | **已完成** |
| M5 | 更多攻击样例、与后端故障联动、简历话术 | **部分完成**（联动与对照已有；扩样本为可选） |

### M5（可选加深）
- 扩充 `tool_eval.jsonl`、补标签与多轮场景。
- 与 `chaos-demo` 后端故障注入做更多组对照、沉淀案例库。
- 验收：能讲清 **1 组**「故障前后 Agent 指标变化」即可，不强制多次回归。

---

## 6. 推荐门禁阈值（初版）

> **实际以代码为准**：单轮硬门禁见 `gate_agent_eval.py`；故障对照见 `chaos_compare.py` 与环境变量 `CHAOS_*`。下表可作面试口径与日后收紧参考。

- Tool Selection Accuracy >= 90%
- Argument Accuracy >= 85%
- Call Sequence Accuracy >= 85%
- Hallucination Rate <= 8%
- Safety Violation Rate <= 1%
- Task Success Rate >= 85%
- Candidate 相比 Baseline 的核心指标退化不超过 3%
- 单任务平均工具调用次数 <= 3.5（防止失控重试）
- 重试率 <= 20%
- 平均 Token 消耗相对 Baseline 上升 <= 30%

> 说明：初版阈值用于“先跑通流程”，后续按历史数据逐步收紧。

---

## 7. 你问的关键问题：Agent 要自己写吗？

结论：**不一定要自己从零实现 Agent。**

### 更推荐做法（面试性价比最高）
- **用现成 Agent 框架或模型工具调用能力**（如 OpenAI function calling / LangChain / LlamaIndex）
- 你重点做：
  - 测试数据设计
  - 评测与打分
  - 质量门禁
  - 回归报告

### 为什么这样更好
- 测开岗位核心是“质量体系能力”，不是重复造轮子
- 你能更快做出可量化成果
- 面试官更关注你如何定义问题、评估与拦截风险

### 什么时候需要自己写 Agent
- 你应聘“Agent平台研发/框架开发”才需要深入实现调度器
- 测开岗位通常不要求从零写 Agent 内核

---

## 8. 可选深化（有精力再做）

1. 将 `AGENT_MODE=ollama` 与本地模型跑通，对比规则路由差异。
2. 在 `tool_eval.jsonl` 中增加多轮、越权、注入等标签化样例。
3. 差分测试：同数据集多次运行，记录方差（需样本量与脚本支持时再上）。
4. 将 `../interview/RESUME_PITCH.md` 与一次真实 `chaos_compare_latest.md` 对齐，固定面试叙事。

---

## 9. 当前仓库怎么用（个人 demo）

- **服务**：`docker compose up -d`，治理版 `http://127.0.0.1:5000`。
- **Agent 评测**（仓库根目录）：见 `../agent-eval/README.md`；快捷：`.\run.ps1 -Task agenteval` 或 `.\run.ps1 -Task agentchaos`。
- **全链路 QA**：`.\run.ps1 -Task qa`（含单测、压测、安全扫描、统一门禁；含 Agent `chaos_compare --strict`）。
- **产物**：`agent-eval/reports/agent_eval_latest.*`、`chaos_compare_latest.*`；CI 同路径 artifact。
- **可选 K8s**：本地启用 Kubernetes 后，可按 `k8s/CHAOS_LITE.md` 体验 `app`+`redis` 的 Deployment/Service 与轻量混沌（**不参与 GitHub Actions 默认流水线**）。

---

## 10. 当前进度（已完成）

以下内容已在仓库中落地：

0. **定位**：个人 demo；`datasets/tool_eval.jsonl` **约 10 条**，不维护大规模生成脚本。

1. `agent-eval/` 模块骨架已完成  
   - 数据集、脚本、配置、报告目录已建好。

2. 最小评测闭环已跑通  
   - 已实现：`run_agent_eval.py -> score_agent_eval.py -> gate_agent_eval.py`。

3. 工具调用从 mock 升级为真实调用  
   - 已接入下单/查询/取消工具客户端（优先真实接口，异常时可离线兜底）。
   - 主服务已补充取消接口，支持完整工具链路验证。

4. Planner 严格校验与降级机制已完成  
   - `ollama` 模式输出增加 JSON 结构与白名单校验。
   - 非法输出自动降级 `ask_user` 并计入评测指标。

5. 人工复核池已自动生成  
   - 规则冲突、Judge 冲突、Planner 回退样例自动写入复核池文件。

6. 故障联动评测已落地  
   - `run_agent_eval.py` 已支持 `--chaos`（`none/latency/error/mixed`）。
   - 可注入延迟与错误，观察 retry/token 等指标变化。

7. 对照报告自动化已完成  
   - 已新增 `chaos_compare.py`，可一键生成无故障 vs 故障场景对照报告（JSON + MD）。

8. **Token 黑洞门禁（对照场景）已完成**  
   - `chaos_compare.py` 会计算故障相对基线的 `token_surge_ratio` 与 `retry_rate` 增幅。  
   - 另对 **规则失败路径**（`avg_token_rule_fail`）计算 `fail_path_token_surge_ratio`，防止故障下只在失败样本上疯狂堆 token。  
   - 对 **重试路径**（`avg_token_with_retry`，且两侧均有重试样本）计算 `retry_path_token_surge_ratio`，约束重试场景下的 token 膨胀。  
   - 增加 **重试税（retry tax）**：在单轮（尤其故障轮）内比较「有重试 / 无重试」样本的平均 token 比，基线无重试时仍可约束故障轮。  
   - 阈值：`CHAOS_TOKEN_SURGE_MAX`、`CHAOS_RETRY_SURGE_MAX`、`CHAOS_FAIL_PATH_TOKEN_SURGE_MAX`、`CHAOS_RETRY_PATH_TOKEN_SURGE_MAX`、`CHAOS_RETRY_TAX_MAX`（重试税）。  
   - 加 `--strict` 时门禁失败会 `exit 1`，便于接入 CI。

9. **单轮 Token 拆分与 retry tax 已完成**  
   - `score_agent_eval` 输出：`avg_token_rule_pass` / `avg_token_rule_fail`、`avg_token_with_retry` / `avg_token_no_retry`。  
   - 单轮报告含 `retry_tax_ratio`（与 `chaos_compare` 中重试税含义一致）。

10. **Ollama 真实 token 计数（规划阶段）已接入**  
   - `run_agent_eval.py` 在 `AGENT_MODE=ollama` 时解析 `/api/generate` 的 `prompt_eval_count` + `eval_count`。  
   - 每条 case 记录 `token_usage_llm`、`token_usage_estimated`、`token_usage_source`；`score_agent_eval.py` 汇总 `ollama_token_coverage` 与 `avg_token_llm_per_task`。  
   - `TOKEN_METRIC=auto|llm|estimated` 控制主指标 `token_usage` 的取值策略。

11. **多次运行波动与可复现随机性**  
   - `EVAL_SEED`：`run_agent_eval` / `score_agent_eval` 共用，控制工具客户端故障注入序列与 Judge 抽检。  
   - `eval_variance.py`：同一 chaos 参数下重复多轮（种子递增），输出 `eval_variance_latest.json` / `.md`（均值、极差、标准差）。

12. **Judge 抽检与指标命名对齐**  
   - `config/eval_config.yaml` 中 `judge.enabled`、`judge.sample_rate` 在打分阶段生效（`AGENT_EVAL_SKIP_JUDGE=1` 时仍整体跳过判官）。  
   - 报告增加 `call_sequence_accuracy`（与当前「整段工具列表匹配」同口径，便于对齐计划文档用语）。

---

## 11. 后续任务（暂缓，之后再做）

以下任务保留为下一阶段：

1. **Token 统计（再进阶）**  
   - 已完成：单轮内规则通过/失败、有重试/无重试拆分；`chaos_compare` 下全量/失败路径/重试路径/重试税多重门禁；单轮报告 `agent_eval_latest.md` / `.json` 中已含 **retry_tax_ratio** 与参考上限说明。  
   - 待做：**多轮对话**累计 token；与 **OpenAI 等 API** 的 `usage` 字段对齐。

2. **差分测试增强**  
   - **已有「大概意思」**：`eval_variance.py` 对同一 chaos 配置多次运行（`EVAL_SEED` 递增），输出均值/极差/标准差（见 `eval_variance_latest.md`）。  
   - 待做：双 **模型** baseline/candidate 对照；**置信区间** 等更严统计。

3. **Judge 体系增强**  
   - **已有「大概意思」**：`eval_config.yaml` 中 `judge.enabled` + `judge.sample_rate` 已作用于 `score_agent_eval`（与 `AGENT_EVAL_SKIP_JUDGE` 独立；抽检用 `EVAL_SEED` 复现）。  
   - 待做：多判官投票、一致性分析、冲突样例自动升优先级。

4. **数据集扩充与标签细化**  
   - 当前仓库为 **个人 demo**：`tool_eval.jsonl` 仅少量手写样例；若要做作品集深度，再扩样本与标签即可。

5. **CI 一体化接入 Agent 评测**  
   - **已完成**：`.github/workflows/qa.yml` 在服务就绪后执行 `chaos_compare.py --strict`（`TOOLS_BASE_URL` 指向 CI 内 `app`、`AGENT_MODE=rule`、`AGENT_EVAL_SKIP_JUDGE=1`）；报告以 artifact `agent-eval-reports` 归档。  
   - 可选后续：拆 Job、或 PR 只跑 `gate_agent_eval`。

6. **简历/汇报材料增强**  
   - **已提供**：`../interview/FAULT_BEFORE_AFTER_TEMPLATE.md`（对照 `chaos_compare_latest`；可选补充 `eval_variance_latest` 波动一句）。  
   - 可选：积累多条对照报告，形成个人案例库（按日期/分支归档 `reports/`）。

---

## 12. 当前执行策略

- **已完成**：`agent-eval` 从数据 → 执行 → 打分 → 单轮门禁 → 故障对照 → 多条件 Token 黑洞门禁的闭环。  
- **下一步**（若想加深作品集）：双模型对照、OpenAI `usage`、多轮对话；或扩样本标签。个人 demo 已有 **单次对照 + 多次波动（eval_variance）**，可停在当前闭环。  
- **简历 / 答辩**：可直接使用 `../interview/RESUME_PITCH.md` + 报告路径；**简化与未实现清单**见 **§2.1**，与面试官对齐预期。

---

## 13. 四个月升级路线（冲 L3 定级）

> 目标：围绕「两加一减」做可落地升级。  
> 两加：流量回放 + 安全扫描；一减：少写业务 CRUD，更多做复合故障与成本拦截。

### Month 1：流量回放 MVP（Traffic Replay）【已完成（轻量版）】

交付：
- 已在 `app.py` 增加开关式录制（`TRAFFIC_RECORD_ENABLED=true`），按 JSONL 记录请求（含基础脱敏）。
- 已新增 `replay_traffic.py`，可回放录制流量到 `:5000`，并输出聚合报告。
- 当前产物：`reports/traffic_replay_latest.json` + `.md`（总览 + 按接口统计 + 样例明细）。

验收标准：
- 能用一份真实捕获样本复跑并产出报告。
- 回放不会因为重复写请求造成“脏数据放大”。

### Month 2：安全扫描接入 CI（DAST）【已完成（轻量版）】

交付：
- 已新增 `security_scan.py`（动态接口扫描，最小覆盖 SQL 注入风格 payload、路径探测、敏感信息泄露关键词）。
- 输出：`reports/security_scan_latest.json` + `.md`。
- `.github/workflows/qa.yml` 已接入安全扫描步骤，失败时阻断；`quality_gate.py` 已统一校验性能 + 安全。

验收标准：
- 至少 1 组恶意 payload 能触发预期拦截/告警。
- CI 中安全扫描失败可阻断流水线。

### Month 3：复合故障与 Agent 成本失控防护

交付：
- 在 `tools_client.py` 增加 `compound` 故障模式（例如：高延迟 + 间歇错误 + 慢失败）。
- 在 `chaos_compare.py` 或新脚本中加入 compound 对照（保留 strict 门禁语义）。
- 增加“Token 爆炸”专项对照项：重点跟踪 `retry_rate`、`avg_token_per_task`、`retry_tax_ratio` 在复合故障下的变化。

验收标准：
- 能稳定复现实验：同配置多轮运行有一致趋势。
- 门禁可明确拦截“重试策略导致 token 成本失控”的场景。

### Month 4：成果打包与答辩材料

交付：
- 更新 `../interview/FAULT_BEFORE_AFTER_TEMPLATE.md`，加入「流量回放结论」与「安全扫描结论」模板段。
- 更新 `../interview/RESUME_PITCH.md`，补 2-3 条可量化 bullet（回放真实性、安全拦截、复合故障成本控制）。
- 汇总案例库（按日期归档 `reports/` 关键报告：replay/security/chaos/variance）。

验收标准：
- 能在 3-5 分钟内讲清「真实性 + 安全性 + 故障鲁棒性」三条主线。
- 面试追问时可落到具体脚本、报告文件和门禁结果。

---

## 14. 开工前实现清单（历史参考；多数已完成）

以下原为启动顺序；**当前仓库已覆盖 Step 1～4 + CI**，Step 0（Ollama/Judge）在 **rule + SKIP_JUDGE** 路径下可跳过。

### Step 0：环境准备（可选）
- **规则评测 + CI**：仅需 Docker 与 Python，无需本地大模型。
- **Ollama 规划 / 本地判官**：安装 Ollama（或 vLLM），拉取 `qwen2.5:7b` 等；验证 `localhost` 可调用。

### Step 1：最小数据集（当天完成）
- **当前**：约 **10 条** JSONL（5 正常 + 5 攻击/异常即可）。
- 字段：`input`、`expected_tools`、`expected_args`、`forbidden_behavior`、`category`。
- 明确“必须追问”的 case（缺参不允许瞎猜）。

### Step 2：最小可运行脚本（当天完成）
- `run_agent_eval.py`、`score_agent_eval.py`、`judge_local.py`（可选）。

### Step 3：首版门禁（当天或次日）
- `gate_agent_eval.py`：工具/参数/重试/幻觉等阈值（与 **`config/eval_config.yaml` 的 `gate:`** 同步），失败非 0 退出。

### Step 4：首轮验收（次日）
- 本地或 CI 跑通，生成 `agent_eval_latest.*`；对照跑 `chaos_compare.py`。
- （可选）多次运行看波动；个人 demo 不强制。

### Step 5：再扩样本（可选）
- 按需增加 `tool_eval.jsonl` 条数；再考虑 LLM 抽检比例与复核池策略。
