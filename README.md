# chaos-demo

轻量级质量工程示例：围绕受控混沌注入、HTTP 压测与质量门禁，在多种故障与控制面策略下对服务做**可复现的自动化评估**。演示用 Flask + Redis **订单 API**（限流 / 熔断 / 幂等 / 超时 / 可观测 / **HTTP 故障注入**），并配套 **pytest** 分层、`benchmark_compare`、`security_scan`、**`quality_gate`** / **`unified_quality_gate`** / **`unified_summary`**、`agent-eval`、Grafana/Prometheus 与 GitHub Actions。

---

## 文档怎么读（与 `docs/README.md` 同源分层）

本项目把说明拆成几层，**避免在多份 Markdown 里重复维护**「全量环境变量表」「全量 HTTP API 表」。**约定**：与实现不一致时，以 **源码**、`docker-compose.yml`、`.github/workflows/qa.yml` 为准。

| 层级 | 位置 | 职责 |
|------|------|------|
| **0. 事实源** | 代码、compose、CI | 接口、开关、流水线步骤以运行中的行为为准 |
| **1. 跑通入口** | **本 README**、[可选本地] `docs/run/GUIDE.md` | 命令、端口、`run.ps1` 任务 |
| **2. 子模块** | [`agent-eval/README.md`](agent-eval/README.md)、[`api-automation-demo/README.md`](api-automation-demo/README.md)、[`k8s/CHAOS_LITE.md`](k8s/CHAOS_LITE.md) | 辅线评测、接口自动化样例、可选 K8s |

**关于 `docs/`**：根目录 `.gitignore` 默认不把 `docs/` 推到远端。若本机保留该目录，**导航地图以 `docs/README.md` 为准**；远端只需本 README 与上表「子模块」链接。**请勿**在多份 Markdown 里复制同一套变量全表，应让读者直接查代码或单一事实源。

**阅读顺序**：本 README → 跑通单测/Docker → 按需打开各子模块 README → 更长说明见本地 `docs/`（若有）。

### 仓库内 Markdown（推送到 GitHub 后仍可点开）

| 路径 | 说明 |
|------|------|
| `README.md` | 本页：概览、环境与命令、目录速览 |
| `agent-eval/README.md` | Agent 工具调用评测（可选扩展） |
| `api-automation-demo/README.md` | pytest + httpx + YAML + Allure，与主服务解耦 |
| `k8s/CHAOS_LITE.md` | 可选 K8s / 运维说明 |

---

## 环境要求

| 场景 | 说明 |
|------|------|
| **Python** | 推荐 **3.11**（与 `.github/workflows/qa.yml` 一致）。**3.10+** 一般可运行。 |
| **Docker** | 可选；用于 `docker compose` 起 app + Redis + 监控。镜像内为 **Python 3.9**（见 `Dockerfile`）。 |
| **OS** | Windows / Linux / macOS；下面命令在 Windows 下给出 PowerShell 与跨平台两种写法。 |

---

## 一眼跑通：只做单测（不启 Docker）

```powershell
cd chaos-demo
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

冒烟（与 CI 第一步一致）：

```powershell
python -m pytest tests/ -m smoke -q
```

Linux / macOS：

```bash
cd chaos-demo
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements-dev.txt
pytest tests/ -q
```

---

## Docker Compose：起服务

```powershell
docker compose up --build -d
```

健康检查（需等服务就绪）：

```powershell
curl http://127.0.0.1:5000/healthz
```

- App：**5000**（`ENABLE_RESILIENCE` 等见 `docker-compose.yml`）
- 对照实例：**5001**（`app_baseline`）
- Redis：**6379**
- Prometheus：**9090**；Grafana：**3000**（若启用 compose 中的监控服务）

停止：

```powershell
docker compose down
```

---

## Windows：`run.ps1` 任务

查看所有任务：

```powershell
.\run.ps1 -Task help
```

常用：

| Task | 作用 |
|------|------|
| `up` / `down` | `docker compose up --build -d` / `down` |
| `test` | 安装 dev 依赖并 **pytest 全量** |
| `bench` | `benchmark_compare.py`（默认压测相关环境变量见脚本内说明） |
| `scan` | `security_scan.py`（需可访问 `SECURITY_SCAN_BASE_URL`，默认 `http://127.0.0.1:5000`） |
| `gate` | `quality_gate.py`（仅 benchmark+security，需先有报告） |
| `unified` | `unified_quality_gate.py`（汇总 + agent_eval；与 CI 末步一致，需先有 **chaos_compare** 或等价产物） |
| `qa` | test → bench → 等待 healthz → scan → gate |
| **`qafull`** | 同 `qa`，再 `chaos_compare --strict`、`trace_timeline`、`unified`、平台摘要（对齐 CI） |
| **`llmassist`** | **`python llm_assist.py --help`**（可选 LLM 辅助；不需起 Docker） |

**注意：** `bench` / `scan` / `qa` / `qafull` / `agenteval` 等依赖**已在运行的 API**（默认 `127.0.0.1:5000`）。请先执行 `.\run.ps1 -Task up` 或自行 `docker compose up -d`，再跑 `qa` 等任务。

对齐 CI 末尾的 agent chaos 对比（严格模式）：

```powershell
.\run.ps1 -Task up
# 等待 healthz 可用后
.\run.ps1 -Task qafull
```

非 Windows 可对照 `run.ps1` 内命令复制执行（或只使用上面的 `docker` + `pytest` + `python xxx.py`）。

---

## 依赖说明

| 文件 | 用途 |
|------|------|
| `requirements.txt` | 运行 **app / Docker**：`flask`、`redis`、`prometheus-client`、`gunicorn` |
| `requirements-dev.txt` | **开发 / CI**：继承 `requirements.txt`，并包含 `pytest`、`locust`（压测脚本） |

安装开发依赖即包含运行服务所需包，适合本地单测与脚本门禁。

---

## 测试与标记

配置见根目录 `pytest.ini`（如 `pythonpath`、markers）。

- `-m smoke`：冒烟
- `-m contract`：HTTP/JSON 契约（`tests/test_api_contract.py`）
- `-m integration`：需要本机 Redis 等（可能 skip）

---

## 故障注入 API 与演示（可选）

服务已运行时，可通过 **`/fault/*`** 在 **Redis** 中登记动态故障（**延迟 / 异常 / 随机丢请求 / 慢库模拟**），由 `chaos_service/http_api.py` 的 **`before_request`** 对业务路径调用 `fault_injection.apply_faults`；**`/fault`、探活、`/metrics` 路径不套注入**。开关：**`ENABLE_FAULT_INJECTION`**（默认开启，`docker-compose.yml`）。语义、校验与数据结构见 **`chaos_service/fault_injection.py`**、`http_api.py` 中 `/fault/*` 路由，以及 **`tests/test_fault_injection.py`**。

快速查看状态：

```powershell
curl http://127.0.0.1:5000/fault/status
```

编排演示（写 `reports/fault_demo_latest.json`）：

```powershell
python fault_demo.py
```

---

## LLM 辅助（可选）

**长期本机配置（不必每次手敲 Key）**：复制 **`local_llm_env.example.ps1`** 为 **`local_llm_env.ps1`**，在后者里填写 **`LLM_API_KEY`**（该文件已 **`.gitignore`**，勿提交）。之后运行 **`.\run.ps1 -Task ...`** 会自动加载；若直接运行 **`python llm_assist.py`**，请先在同一终端执行 **`. .\local_llm_env.ps1`**。若 Key 曾在聊天/PR 中泄露，请在云控制台**作废并轮换**。

`llm_client.py` / `llm_assist.py` 说明见模块内注释与 **`python llm_assist.py --help`**；云端需配置 **`LLM_API_KEY`** 等，本地可 **`LLM_BACKEND=ollama`**。**不进 CI 主链**，产出默认在 **`reports/llm_*`**（与 `reports/` 一同被 `.gitignore` 忽略，需自留备份）。

常用子命令（均需先能连上模型）：

```powershell
python llm_assist.py --help
python llm_assist.py generate-tests
python llm_assist.py analyze-report --report reports/benchmark_latest.json
python llm_assist.py analyze-logs --input reports/traffic_record_latest.jsonl
python llm_assist.py complete-cases --format jsonl -n 2 --input agent-eval/datasets/tool_eval.jsonl
python llm_assist.py complete-cases --format yaml -n 2 --input api-automation-demo/data/api_cases.yaml
python llm_assist.py explain-code --path chaos_service/resilience.py --question "限流 Redis 异常时行为"
python llm_assist.py contract-audit
```

输出均为**草稿**，合并进仓库或数据集前请**人工审查**并跑 **`pytest`**。

---

## CI

- **主链**：`.github/workflows/qa.yml` — 安装 `requirements-dev.txt` → pytest → compose → benchmark → 安全扫描 → **`chaos_compare --strict`** → **`trace_timeline.py`** → **`unified_quality_gate.py`** → **`unified_summary.py`**（**`reports/unified_summary_latest.*`** 等；Gate 失败时仍生成摘要并随 artifact 上传）。
- **`api-automation-demo/`**：独立子工程，本地可 `pytest` + `--alluredir=allure-results`；Allure 原始结果目录已写入 `.gitignore`，勿提交。

---

## 目录速览

- `chaos_service/`：领域逻辑（存储、HTTP 路由、韧性、**`fault_injection`**、流量记录）
- `fault_demo.py`：对已起服务跑一轮故障注入演示
- `tests/`：`conftest.py`（FakeRedis、fixtures）、分层测试（含 **`test_fault_injection`**、**`test_llm_client`** 等）
- **`api-automation-demo/`**：pytest + httpx + YAML 驱动 + Allure + CI（与主服务**解耦**）
- `agent-eval/`：**扩展模块** — 工具调用在不稳定环境下的稳定性评估与对照
- `k8s/`、`grafana/`、`prometheus*.yml`：运维与可观测性示例
