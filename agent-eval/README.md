# agent-eval

> 面向工具调用路径的**本地低成本**评测（`tool_eval.jsonl` 78 条样例，按四维组织），用于评估在**不稳定环境下**「按规划调用 HTTP 工具（下单/查询等）」的稳定性（重试、失败率、启发式 token 等）。

## 目标
- 测试 Agent 的工具调用是否正确（工具、参数、顺序）。
- 检测异常行为（幻觉、盲目下单、重试过多）。
- 形成门禁（不达标直接失败）。

## 数据集与四维回归矩阵
- **`datasets/tool_eval.jsonl`**：手写 JSONL，按需自增条目即可；78 条用例按 `category` 归入四个行为维度：

| 维度 | category | 测什么 |
|---|---|---|
| 工具选择 | normal / workflow / ask_user | 工具、参数、时序正确性 |
| 上下文（防捏造） | context | 引用不存在的历史信息（"上次那个地址"）时必须 ask_user，不得捏造 |
| 权限边界 | permission | 带 `role` 字段的用例按 `config/security_policy.yaml`（policy-as-code）裁决，被拒工具不得下发；新指标 `permission_denial_accuracy` |
| 安全边界 | attack | 注入 / 越狱 / 幻觉诱导 / 盲目下单 |

- 评分报告（`agent_eval_latest.json/.md`）含 `dimension_breakdown` 四维矩阵，任一维度退化在矩阵中可见（聚合门禁阈值不变）。
- 权限维度联动仓库安全策略文件：角色语义（analyst 只读 / operator 不可取消 / admin 不限 / 未知角色 fail-closed）见 `config/security_policy.yaml` 与 `tests/core_platform/test_sec_policy_file.py`。

## 门禁阈值

单轮门禁 `gate_agent_eval.py` 的阈值与 **`config/eval_config.yaml` 中 `gate:`** 一致（含 `hallucination_rate_max`、`planner_invalid_rate_max`）；改 YAML 即可调参，无需改脚本。

## 快速运行
在仓库根目录执行：

```powershell
python .\agent-eval\scripts\run_agent_eval.py
python .\agent-eval\scripts\score_agent_eval.py
python .\agent-eval\scripts\gate_agent_eval.py
```

仓库根目录也可用 `.\run.ps1 -Task agenteval`（跑完上述三步）或 `.\run.ps1 -Task agentchaos`（仅 `chaos_compare.py`）。

带故障注入评测（示例）：

```powershell
python .\agent-eval\scripts\run_agent_eval.py --chaos mixed --fail-rate 0.2 --latency-ms 120
python .\agent-eval\scripts\score_agent_eval.py
python .\agent-eval\scripts\gate_agent_eval.py
```

一键生成“无故障 vs 混合故障”对照报告：

```powershell
python .\agent-eval\scripts\chaos_compare.py
```

严格模式（Token 黑洞 + 重试增幅门禁失败时退出码 1，便于 CI）：

```powershell
python .\agent-eval\scripts\chaos_compare.py --strict
```

**多次运行波动（差分「大概意思」）**：同一 chaos 配置跑多轮，汇总均值 / 极差 / 标准差（需服务可达）。

```powershell
python .\agent-eval\scripts\eval_variance.py --runs 5 --chaos mixed --fail-rate 0.45 --latency-ms 180
```

产物：`agent-eval/reports/eval_variance_latest.json`、`.md`。每轮使用不同 `EVAL_SEED`（默认从 42 递增），故障注入序列会变化。

输出文件：
- `agent-eval/reports/chaos_compare_latest.json`
- `agent-eval/reports/chaos_compare_latest.md`
- `agent-eval/reports/eval_variance_latest.json` / `.md`（仅 `eval_variance.py`）

可选环境变量：
- `EVAL_SEED`（默认 `42`）：`run_agent_eval` 与 `score_agent_eval` 共用随机种子；故障注入与 Judge 抽检可复现；`eval_variance.py` 每轮自动递增。
- `config/eval_config.yaml` 中 **`judge.enabled`**、**`judge.sample_rate`**：控制是否对 attack 样例调用本地 Judge、以及抽检比例（`AGENT_EVAL_SKIP_JUDGE=1` 时仍不调用判官）。
- `AGENT_EVAL_SKIP_JUDGE=1`：跳过 attack 样例的本地 LLM Judge（规则分与其它指标仍计算；**GitHub Actions 默认开启**，避免 CI 依赖 Ollama）。
- `AGENT_MODE=rule|ollama`（默认 `rule`）
- `OLLAMA_ENDPOINT`（默认 `http://localhost:11434/api/generate`）
- `OLLAMA_MODEL`（默认 `qwen2.5:7b`）
- `TOOLS_BASE_URL`（默认 `http://127.0.0.1:5000`）
- **`TOOLS_HTTP_TIMEOUT_SEC`**（默认 `12`）：下单/查单等 HTTP 读超时秒数（混故障 + 注入延迟时略放大，避免误杀）
- **`SKIP_TOOLS_HEALTH_CHECK`**：默认**执行** `run_agent_eval` 启动前 **GET** `TOOLS_BASE_URL/healthz`；不需要（离线实验）时设为 `1` 或 `true`
- `AGENT_MAX_RETRY`（默认 `2`，工具调用失败时最大重试次数）
- **`CHAOS_SUBPROC_TIMEOUT_SEC`**（默认 `1200`）：`chaos_compare.py` 子进程最大等待秒数，机器慢或评测拉长时可调大
- `CHAOS_TOKEN_SURGE_MAX`（默认 `0.30`，故障场景相对基线平均 token 最大允许增幅比例）
- `CHAOS_RETRY_SURGE_MAX`（默认 `0.25`，故障场景相对基线 retry_rate 最大允许增幅）
- `CHAOS_FAIL_PATH_TOKEN_SURGE_MAX`（默认 `0.50`，**规则失败样本**上平均 token 相对基线的最大允许增幅；`chaos_compare.py` 使用）
- `CHAOS_RETRY_PATH_TOKEN_SURGE_MAX`（默认 `0.60`，**仅含重试的 case** 上平均 token 的增幅上限；两侧均有 `retry_case_count>0` 时才启用）
- `CHAOS_RETRY_TAX_MAX`（默认 `1.50`，重试样本 ≥5 条时启用：**故障轮次内**「有重试样本 / 无重试样本」平均 token 的相对增幅上限；阈值须高于规则模式 planner 重试的结构成本，只拦病态放大。门禁逻辑与单测见 `tests/test_chaos_gate.py`）
- `TOKEN_METRIC`（默认 `auto`：`AGENT_MODE=ollama` 且 Ollama 返回 `prompt_eval_count`/`eval_count` 时用真实 token，否则用启发式；可选 `llm` / `estimated`）

## 输入与输出
- 输入：`agent-eval/datasets/tool_eval.jsonl`
- 原始输出：`agent-eval/reports/agent_raw_latest.json`
- 评分输出：`agent-eval/reports/agent_eval_latest.json`
- 报告：`agent-eval/reports/agent_eval_latest.md`
- 人工复核池：`agent-eval/reports/manual_review_pool.jsonl`
- 故障对照报告：`agent-eval/reports/chaos_compare_latest.md`
- 多次运行波动：`agent-eval/reports/eval_variance_latest.json` / `.md`（见上文 `eval_variance.py`）

评分报告中的 **Token by outcome**：按「规则通过/失败」与「是否发生工具重试」拆分平均 `token_usage`，用于观察失败路径或重试路径是否出现 Token 黑洞。

## 说明
- 当前版本默认使用规则规划器（`rule`）+ 真实工具客户端调用。
- 当你本地部署 Ollama 后，可切换到 `AGENT_MODE=ollama` 做本地模型规划。
- 工具客户端优先调用真实接口（下单/查询/取消），接口不可达时会离线兜底，便于本地调试。
- `ollama` 模式包含严格 JSON 结构校验，不合法输出会自动降级到 `ask_user` 并进入复核池。
