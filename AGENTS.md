# Chaos Demo — 项目记忆（AI Coding Agent 快速上手）

> 本文件由 DeepSeek Harness 等编码代理在会话开始时自动加载（同级的 `AGENTS.local.md` 为个人覆盖层，不提交）。
> 维护约定：架构、新环境变量、新 CI 步骤变更时，须同步更新本文件与 `docs/archive/reference/AI_PROJECT_CONTEXT.md`。

## 一、定位与当前阶段

**定位**：轻量级质量工程平台（QEP）。**Chaos Service**（Flask，被测系统）承载订单业务 + 韧性治理 + 故障注入；**AI Platform**（FastAPI，质量保障层）做 Agent 执行、安全防护、输出评估与质量门禁；`agent-eval/` 是工具调用稳定性的辅线。

> 叙事口径（重要）：README 偏「AI-Native 双引擎」，但权威文档 `docs/archive/reference/AI_PROJECT_CONTEXT.md` 要求主线讲成「轻量级质量工程平台（QEP）」，`agent-eval/` 只是辅线，不要讲成「AI Agent 主项目」。

**当前阶段**：功能完整、可本地/Docker 运行；70 个测试文件 / 722 用例（本机 Redis 可用时全跑；2 个真 Redis 集成用例无 Redis 时自动 skip；含 hypothesis 状态机属性测试、密钥边界/policy-as-code 测试、schemathesis 契约测试）；4 个 GitHub Actions 工作流（ci / ai-quality / qa / supply-chain）。另有 8 周学习计划（`PROJECT_OWNERSHIP_MASTER_PLAN_V2.md`）与进度记录（`PROJECT_LEARNING_PROGRESS.md`，Phase 2）、面试题库（`learning/秋招知识点治理与面试题库.md`）。

## 二、技术栈

- **语言/运行时**：Python；本地 `.venv` 为 3.14.3，`pyproject.toml` 目标 py3.11，Chaos 服务 Dockerfile 用 python:3.9。
- **被测系统（Chaos Service :5000）**：Flask + Redis（订单/幂等/限流/熔断共享状态）+ prometheus-client + gunicorn（`--workers 2`）。
- **质量保障层（AI Platform :8000）**：FastAPI + pydantic v2 + uvicorn；`ai_platform/` 含 core/agent/workflow/tools/llm/security/evaluation/observability 八块。
- **LLM**：`LLMGateway` 四种 Provider：Mock（确定性）/ OllamaChat / OllamaGenerate / OpenAICompatible（DeepSeek、DashScope 等）。
- **测试/质量工具**：pytest + pytest-cov、hypothesis（状态机属性测试，`tests/unit/*_stateful.py`）、schemathesis（契约测试，`tests/contract/`）、locust、httpx、PyYAML、allure-pytest、black、ruff、mypy。
- **基础设施**：Docker Compose（app + app_baseline + redis + prometheus + grafana）、K8s 清单（可选）、Lua 限流脚本、Grafana 5 个大盘。
- **SLO/告警**：`docs/slo.md` 定义可用性 99.9% / 延迟合规 99%（30 天窗口，错误预算制）；`prometheus_alerts.yml` 的 `slo-burn-rate-recording`（8 条 recording rules）+ `slo-burn-rate-alerts`（多窗口燃烧率：快烧 14.4× page / 慢烧 6× warning，双窗同时越界才告警）；与 CI 门禁构成「门禁挡回归、SLO 兜线上」两层防线。

## 三、目录导览

| 目录/文件 | 一句话职责 |
|---|---|
| `app.py` | Flask 入口（3 行薄入口），路由与钩子委托给 `chaos_service`。 |
| `ai_platform_api.py` | FastAPI 入口（:8000），`/api/v1/agent/run` 走 Security→Agent→Workflow→LLM→Evaluation→Gate 全链路。 |
| `ai_platform/` | 质量保障层包：core/agent/workflow/tools/llm/security（4 层洋葱）/evaluation/observability。 |
| `chaos_service/` | 被测系统：fault_injection（4 种故障 `/fault/*`）、resilience（breaker/idempotency/limiter/retry）、store（订单/幂等 Redis 语义）、traffic（录制脱敏）、http_api。 |
| `app/` | 订单业务分层（api/service/repository/infrastructure/config/exceptions/observability），被 chaos_service 复用。 |
| `agent-eval/` | 辅线：工具调用稳定性评估（datasets/tool_eval.jsonl 78 条四维用例：工具选择/上下文防捏造/权限边界/安全边界 + run/score/gate/chaos_compare/eval_variance/prompt_regression 脚本；权限维度联动 config/security_policy.yaml 的 role 裁决，评分输出含 dimension_breakdown 矩阵与 permission_denial_accuracy 指标）。 |
| `demo/` | 三大演示场景 runner（incident_analysis / security_test / regression），进程内装配组件、不起服务可跑。 |
| `tests/` | 主 pytest 树：conftest（FakeRedis/FailingRedis）、unit/integration/e2e/demo/deployment 分层。 |
| `scripts/` | 旧版 AI 平台门禁脚本（generate_evaluation_report.py、run_quality_gate.py）+ `dsh.ps1`（DSH 启动器）。 |
| `k8s/` | 可选 K8s 清单 + chaos-lite.ps1 混沌脚本 + CHAOS_LITE.md（不跑 CI 默认流程）。 |
| `grafana/` | provisioning + 5 个预置大盘 JSON。 |
| `docs/` | 文档库（api/architecture/engineering/interview/modules/testing/overview/archive/adr/slo 等），**仅本地保留不入库**。 |
| `learning/` | 学习产出（面试题库、七日课笔记等），**仅本地保留不入库**。 |
| `lua/` | 限流 Lua 脚本（fixed_window.lua / sliding_window.lua）。 |
| `api-automation-demo/` | 独立 pytest 工程：httpx + YAML 数据驱动 + Allure，不与 app 同进程。 |
| `sample-data/` | 示例流量 JSONL，供回放/学习。 |
| `reports/`、`agent-eval/reports/` | 运行产物（benchmark/security/门禁/摘要等，gitignored）。 |
| `.github/workflows/` | ci.yml、ai-quality.yml、qa.yml（主 CI：压测+扫描+chaos+统一门禁）、supply-chain.yml（pip-audit+SBOM+Trivy+mutmut 变异测试）。 |
| `.agents/` | 空目录（可放 `.agents/skills/` 项目级技能）。 |

## 四、常用命令速查（工作目录 = 仓库根 `D:\chaos-demo`）

```powershell
# 激活虚拟环境（若禁止运行脚本：Set-ExecutionPolicy -Scope Process Bypass）
.\.venv\Scripts\Activate.ps1

# 测试
python -m pytest tests/ -q -m smoke          # 冒烟 5 个，约 3 秒
python -m pytest tests/ -q                    # 全量 722 用例，约 57 秒（本机，确定性通过）
python -m pytest tests/unit/test_circuit_breaker.py -v
python -m pytest tests/ -q -k idempotency

# 起服务
python -m uvicorn ai_platform_api:app --host 127.0.0.1 --port 8000   # AI Platform
python app.py                                   # Chaos Service（:5000）
docker compose up --build -d                    # 完整栈 app+baseline+redis+prometheus+grafana
docker compose down
docker-compose -f docker-compose.ai.yml up -d   # AI Platform 容器（文件头是 v1 语法）

# 质量门禁（需先起服务跑过 bench/scan）
python benchmark_compare.py                     # 压测对照 5000 vs 5001 → reports/benchmark_latest.json
python security_scan.py                         # 安全扫描 → reports/security_scan_latest.json
python quality_gate.py                          # 门禁：benchmark+security（不含 agent，主链已弃用）
python unified_quality_gate.py                  # P2+P3 统一门禁：+agent_eval(+可选 trend)
python unified_summary.py                       # 一页摘要 → reports/unified_summary_latest.{json,md}

# Agent 评估（需先起 Chaos Service :5000）
$env:AGENT_MODE="rule"
python agent-eval/scripts/run_agent_eval.py     # 跑数据集
python agent-eval/scripts/score_agent_eval.py   # 打分
python agent-eval/scripts/gate_agent_eval.py    # 门禁
python agent-eval/scripts/chaos_compare.py --strict   # 无故障 vs 混故障对照（CI 用）

# 一键脚本 run.ps1（必须 .\run.ps1 -Task <名>，不能裸敲任务名）
.\run.ps1 test | up | down | bench | scan | gate | unified | qa | qafull | agenteval | agentchaos | replay | faultdemo | llmassist

# 演示场景（不起服务可跑）
python demo/run_demo.py all
python demo/scenarios/incident_analysis/runner.py --llm   # 根因分析走真 LLM

# 可选 LLM 辅助（需 Ollama 或 LLM_API_KEY）
python llm_assist.py --help
python llm_assist.py analyze-report --report reports/benchmark_latest.json
```

## 五、环境配置要点

- **`.env`**（gitignored，绝不提交）：LLM Gateway 配置块 `LLM_GATEWAY_PROVIDER/ENDPOINT/MODEL/API_KEY/TIMEOUT_SEC`、`AGENT_MODE`；参考 `.env.example`。
- **本地 LLM**：`local_llm_env.example.ps1` 复制为 `local_llm_env.ps1`（gitignored），填 DashScope key；`run.ps1` 会自动加载。
- **LLM 后端切换**：`LLMClient` 用 `LLM_BACKEND=auto|ollama|openai`、`OLLAMA_ENDPOINT`、`LLM_MODEL`、`LLM_BASE_URL`；`LLMGateway` 用 `load_gateway_config`（已设环境变量优先）。
- **Docker**：`docker-compose.yml` 起 app(5000,韧性开)/app_baseline(5001,ENABLE_RESILIENCE=false)/redis(6379)/prometheus(9090)/grafana(3000,admin/admin123)；app 容器加 `NET_ADMIN`。`docker-compose.ai.yml` 起 ai-platform(8000)+redis+mysql(占位)。
- **常用环境变量**：`REDIS_HOST/PORT`、`ENABLE_RESILIENCE`、`RATE_LIMIT_*`、`BREAKER_*`、`BUSINESS_TIMEOUT_MS`、`INVENTORY_BUSY_PROB`、`ORDER_TTL_SEC`、`TRAFFIC_RECORD_ENABLED/FILE`、`LOG_FORMAT`、`ENABLE_FAULT_INJECTION`、`CHAOS_SERVICE_URL`、`CHAOS_LOG_FILE`、`INCIDENT_LLM_ENABLED`、`AGENT_MODE`、`AGENT_EVAL_SKIP_JUDGE`、`TOOLS_BASE_URL`、`PLATFORM_SECURITY_POLICY`（安全策略文件路径覆盖，默认 `config/security_policy.yaml`，策略文件即代码：版本化角色工具权限，schema 严格校验，未知角色 fail-closed；显式传 config 时不做文件覆盖）。
- **密钥边界**：`GatewayConfig.api_key` 不进 repr；AI Platform 所有 HTTP 错误响应经 `ai_platform/security/redaction.py` 脱敏（密钥值 + sk-/Bearer/键值对形态兜底），由 `tests/core_platform/test_secret_boundary.py` 回归守护。
- **API 契约测试**：`tests/contract/openapi_order_api.yaml`（契约先行、随仓库评审）+ `tests/contract/test_order_api_contract.py`（schemathesis 4.x 进程内 WSGI：挂载 /openapi.json 的包装器 + from_wsgi；负向生成验证非法数据 4xx 拒绝）。schemathesis 属 dev 依赖。历史战果：负向 fuzz 发现两处真实缺陷——item_id 传 list 穿透 truthy 校验、JSON body 非 object 触发 AttributeError→500，均已修复于 `app/api/order_controller.py`。
- **声明式混沌实验**：`agent-eval/experiments/mixed_fault.yaml`（Chaos Toolkit 风格：稳态假设/方法/容忍上界/回滚，schema 严格校验）+ `agent-eval/scripts/run_experiment.py`（驱动 chaos_compare、新鲜度守卫防旧报告误判、产出 experiment_*_latest.{json,md}）。运行：`python agent-eval/scripts/run_experiment.py`；离线验证加 `SKIP_TOOLS_HEALTH_CHECK=1`。注意 method.mode 显式声明 planner 模式（阻断本地 .env 的 AGENT_MODE=llm 泄漏——曾致离线实验静默调用真实 LLM）。

## 六、质量门禁与测试约定

- **测试分层**（`pytest.ini` 9 个 marker）：unit / smoke / contract / integration / e2e / chaos / slow / redis / resilience；`addopts = --strict-markers`，`pythonpath = .`，`testpaths = tests`。
- **FakeRedis 约定**：`tests/conftest.py` 手写内存版 Redis（dict+锁 + Lua 模拟）+ FailingRedis 故障注入，依赖 Redis 的测试确定、无外部依赖；真 Redis 集成用例标记 `redis`，无 Redis 自动 skip。测试产物一律写 pytest `tmp_path`（每用例隔离、框架清理）——曾因测试写共享 `tests/fixtures/` 目录 + Windows unlink 文件锁导致顺序污染 flaky，已根治（见 tests/test_unified_summary.py、test_trace_timeline.py 头注释）。
- **门禁阈值**：`quality_gate.py`（error_rate≤0.05、p99≤450ms、p95 回归倍数≤1.10、unstable≤0.35 等，可 `QUALITY_GATE_*` 环境变量覆盖）；AI 评估 6 阈值（tool_selection_accuracy≥0.70、arg_accuracy≥0.70、avg_tool_calls≤10、retry≤0.30、hallucination≤0.10、planner_invalid≤0.10）见 `ai_platform/evaluation/gate.py` 与 `agent-eval/config/eval_config.yaml`。
- **门禁脚本分工**：`quality_gate.py`（仅 benchmark+security）→ `unified_quality_gate.py`（+agent_eval，可 `UNIFIED_GATE_SKIP_AGENT=1` 跳过，`UNIFIED_GATE_TREND_ENABLED=1` 开趋势）→ `unified_summary.py`（只读汇总，Gate 失败仍生成）。
- **门禁失败**：抛 `QualityGateError` / `AgentGateError`，exit 1；统一门禁写 `reports/unified_quality_gate_latest.json`。
- **CI 主链**（qa.yml）：install → pytest smoke → pytest full → compose up → wait healthz → bench → security_scan → chaos_compare --strict → trace_timeline → unified_quality_gate → unified_summary（`if: always()`）。
- **供应链安全/变异测试**（supply-chain.yml，push/PR 跑前三个 + 夜间跑 mutation）：① `dependency-audit`（pip-audit 扫三份 requirements，有已知漏洞即失败；本地实测零漏洞）→ ② `sbom`（cyclonedx-py 生成 CycloneDX JSON SBOM 产物，本地实测通过）→ ③ `trivy-scan`（fs 扫描 vuln+secret，HIGH/CRITICAL 失败，skip tests/.venc 防哨兵密钥误报）→ ④ `mutation-testing`（mutmut 仅夜间/手动，**Docker Linux 容器实测通过**：609 变异体 65s，360 killed / 218 survived / 31 no-tests，得分 62.3%（剔除 no-tests）；幸存者集中在 metrics/日志副作用与 tests/unit 未覆盖的 build_default_rule/resolve_subject_id；配置见 pyproject `[tool.mutmut]`，注意 `also_copy` 必须含 app/lua/chaos_service/pytest.ini，否则 mutants/ 内收集失败）。
- **供应链本地命令**：`pip-audit -r requirements.txt -r requirements-ai.txt`；`cyclonedx-py environment -o reports/sbom_runtime.json --output-format JSON --validate`；`mutmut run`（**仅 Linux/WSL/容器，Windows 原生不支持**；本地 Docker 验证方式见 memory 2026-08-21）；`pre-commit run --all-files`（配置 `.pre-commit-config.yaml`，ruff/black 作用域与 CI 一致仅 app/，hygiene hook 全仓）。

## 七、给 AI agent 的注意事项

- **只读权威文档**：`docs/archive/reference/AI_PROJECT_CONTEXT.md`（545 行）是「只读本文件即可理解项目」的全景文档。
- **文档漂移缺口**：`agent-eval/README.md`、`k8s/CHAOS_LITE.md` 仍引用 `../docs/AI_PROJECT_CONTEXT.md`、`../docs/plan/AGENT_EVAL_PLAN.md`、`docs/TEST_STRATEGY.md` 等旧路径（已迁入 `docs/archive/`，原路径 404）。引用前先确认文件存在。
- **密钥安全**：`.env`（DeepSeek key）与 `local_llm_env.ps1`（DashScope key）含真实密钥且已 gitignore——切勿提交、切勿把含密钥日志发给公网模型。
- **生成物勿手改**：`reports/*`、`agent-eval/reports/*`、`api-automation-demo/allure-results/` 均为运行产物；`docs/`、`PROJECT_LEARNING_PROGRESS.md`、`.claude/` 仅本地保留。
- **耗时/前置命令**：`benchmark_compare.py`、`security_scan.py`、`chaos_compare.py`、`fault_demo.py` 要求服务已起；`qafull` 本地复现完整 CI，耗时数分钟；`chaos_compare` 子进程超时默认 1200s。
- **Windows 坑**：`.\run.ps1 -Task <名>`（不能裸敲任务名）；全量 pytest 若报 Temp `PermissionError`，加 `--basetemp=D:\chaos-demo\.pytest-tmp`；`.venv` 已装齐依赖。
- **两棵 pytest 树**：根 `tests/` 与 `api-automation-demo/tests/` 是不同工程，后者不 import app。
- **诚实边界**：`agent-eval` 是小样本辅线；HTTP 故障注入是应用内协作式模拟，不等价 tc/杀容器；存储只用 Redis、无 MySQL（MySQL 仅 compose 占位）。

## 八、DeepSeek Harness 使用（本仓库专属）

- **启动 DSH**：`.\scripts\dsh.ps1`（固定版本 0.1.0-rc.6、固定工作区、默认 web GUI；全局安装后优先用全局 `dsh` 命令）。headless 一次性任务：`.\scripts\dsh.ps1 --profile headless "<任务>"`。
- **项目记忆**：DSH 会自动加载本文件（根 `AGENTS.md`）与 `C:\Users\27349\.dsh\AGENTS.md`（用户全局）；同级 `AGENTS.local.md` 为个人覆盖（gitignored）。全部指令合计有 64 KiB 预算，保持精简。
- **项目级技能**：放在 `.agents/skills/<name>/SKILL.md`（或 `.dsh/skills/`），DSH 自动发现，供 agent 按需加载。
- **沙箱/审批**：DSH 会话默认 workspace-write 沙箱（仅能写本仓库）；跑 pytest/docker 等命令一般直接可用，需要越界写（如全局安装、写 `C:\Users\27349` 下文件）时会弹审批，如实说明理由即可。
- **高频任务**：跑测试、质量门禁、demo、读文档（首选 `docs/archive/reference/AI_PROJECT_CONTEXT.md`）。
