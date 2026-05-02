# 项目结构速查（文件地图）

> **API、韧性语义、环境变量、CI 步骤、实现方法**：见 **[`../AI_PROJECT_CONTEXT.md`](../AI_PROJECT_CONTEXT.md)**。  
> 本文仅保留**按路径快查**，避免与全景文重复。

---

## 1. 根目录（核心脚本与配置）

| 路径 | 作用 |
|------|------|
| `app.py` | 订单服务**入口**；路由与逻辑在 **`chaos_service/`**（`http_api`、`resilience`、`store`、`fault_injection`、`traffic`） |
| `chaos_service/` | 与 `app.py` 同镜像打包（含 **`fault_injection`**）；见 `AI_PROJECT_CONTEXT` §2.1 A / J |
| `fault_demo.py` | 对已起服务做 **HTTP 故障注入**演示 → `reports/fault_demo_latest.json` |
| `llm_client.py` / `llm_assist.py` | 可选 LLM 调用与 CLI（**不进 CI 主链**） |
| `docker-compose.yml` | `app` 5000、`app_baseline` 5001、redis、prometheus、grafana |
| `Dockerfile` | 应用镜像；`COPY app.py` + `COPY chaos_service` |
| `benchmark_compare.py` | 5000/5001 对照压测 → `reports/benchmark_latest.json`、**`benchmark_history/`**、**`benchmark_trend_latest.*`** |
| `security_scan.py` | 安全扫描 → `reports/security_scan_*.json`、`.md` |
| `quality_gate.py` | 读 benchmark + security 报告，失败则非 0 退出 |
| `replay_traffic.py` | JSONL 重放 |
| `run.ps1` | Windows 一键：compose、pytest、bench、scan、gate、**qa**、**qafull**、agent* 等 |
| `locustfile.py` | 可选 Locust 压测（与 `benchmark_compare` 不同路） |
| `prometheus.yml` + `prometheus_alerts.yml` | 抓取 + 示例告警（compose 挂载） |
| `grafana/provisioning/`、`grafana/dashboards/` | 数据源与大盘 |
| `pytest.ini` | 标记 `smoke`、`contract` |
| `tests/` | 单测与 FakeRedis，见下节 |
| `agent-eval/` | 见 [`../../agent-eval/README.md`](../../agent-eval/README.md) 与全景 §8 |
| `sample-data/` | 示例数据（如 JSONL） |
| `k8s/` | 可选清单与 `CHAOS_LITE.md`，不跑 CI 默认 |
| `.github/workflows/qa.yml` | CI；顺序见 `AI_PROJECT_CONTEXT` §7 |

---

## 2. `tests/`（测开分层）

| 文件 | 内容 |
|------|------|
| `conftest.py` | `app_state`、`FakeRedis`、韧性相关重置 |
| `test_app.py` | 功能与韧性；部分 `smoke` |
| `test_fault_injection.py` | `/fault/*` 与 **`apply_faults`** |
| `test_llm_client.py` | `LLMClient`（mock / 后端选择等） |
| `test_api_contract.py` | 契约；`contract` 标记 |
| `test_benchmark_compare.py` / `test_quality_gate.py` / `test_security_scan.py` / `test_replay_traffic.py` / `test_agent_eval_config.py` / `test_perf_regression.py` / `test_redis_integration.py` | 对应脚本与可选集成；细节见 `AI_PROJECT_CONTEXT` §9 |

**常用**：`pytest -q`；与 CI 一致时先 `pytest -m smoke -q` 再全量（见 `qa.yml`）。

---

## 3. `docker-compose` 端口速记

| 服务 | 宿主机端口 | 说明 |
|------|------------|------|
| `app` | `5000` | 治理版 |
| `app_baseline` | `5001` → 容器 5000 | 基线对照 |
| `redis` | `6379` | 共享数据与韧性状态 |
| `prometheus` | `9090` | 规则含 `prometheus_alerts.yml` |
| `grafana` | `3000` | 账号见根 `README` |

---

## 4. `run.ps1` 任务（详细命令以脚本为准）

| Task | 用途 |
|------|------|
| `up` / `down` | 启动 / 停止 compose |
| `test` | 安装 dev 依赖后全量 `pytest` |
| `bench` / `scan` / `gate` | 压测、安全扫、质量门禁（含与 CI 对齐的若干默认 env） |
| `qa` | test → bench → 等 healthz → scan → gate |
| **`qafull`** | 同 `qa`，再 `chaos_compare --strict`（对齐 CI 含 Agent 步） |
| `agenteval` / `agentchaos` / `agentvariance` | Agent 评测与对照（脚本内注入与 CI 一致的 `TOOLS`/`AGENT` 等并等 healthz） |
| `replay` | 流量重放 |
| `help` | 打印说明 |

*实现以仓库当前 `run.ps1` 为准。*
