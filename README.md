# chaos-demo

**定位（面试可背）**：这是一个**轻量级质量工程平台**（**Quality Engineering Platform**）：以受控的混沌注入、HTTP 压测与质量门禁为主线，在多种故障与控制面策略下对服务做**可复现的自动化评估**，用于演示与辅助上线决策；**不是**「一个 Flask 订单 CRUD demo」一句带过。

> **标准说法**：我设计了一个轻量级质量工程平台，通过混沌注入、压测和质量门禁，实现系统在不同故障场景下的自动化评估，并用于辅助上线决策。

底座仍是 **Flask + Redis** 订单 API（限流 / 熔断 / 幂等 / 超时 / 可观测 / **HTTP 故障注入**），配套 **pytest** 分层、`benchmark_compare`、`security_scan`、`quality_gate`、`agent-eval`（辅线）、Grafana/Prometheus 与 GitHub Actions。**测试怎么分层、failure model 怎么说**见 **[`docs/TEST_STRATEGY.md`](docs/TEST_STRATEGY.md)**；**压测报告怎么讲 trade-off**见 **[`docs/PERFORMANCE_ANALYSIS.md`](docs/PERFORMANCE_ANALYSIS.md)**。**接口自动化框架（pytest + httpx + YAML + Allure）保底样例**见 **[`api-automation-demo/README.md`](api-automation-demo/README.md)**。

## 环境要求

| 场景 | 说明 |
|------|------|
| **Python** | 推荐 **3.11**（与 `.github/workflows/qa.yml` 一致）。**3.10+** 一般可运行。 |
| **Docker** | 可选；用于 `docker compose` 起 app + Redis + 监控。镜像内为 **Python 3.9**（见 `Dockerfile`）。 |
| **OS** | Windows / Linux / macOS；下面命令在 Windows 下给出 PowerShell 与跨平台两种写法。 |

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
| `gate` | `quality_gate.py`（需先有 benchmark/security 等报告，见脚本） |
| `qa` | test → bench → 等待 healthz → scan → gate |
| **`qafull`** | 同 `qa`，再 `chaos_compare --strict`（对齐 CI 末尾 Agent 步） |

**注意：** `bench` / `scan` / `qa` / `qafull` / `agenteval` 等依赖**已在运行的 API**（默认 `127.0.0.1:5000`）。请先执行 `.\run.ps1 -Task up` 或自行 `docker compose up -d`，再跑 `qa` 等任务。

对齐 CI 末尾的 agent chaos 对比（严格模式）：

```powershell
.\run.ps1 -Task up
# 等待 healthz 可用后
.\run.ps1 -Task qafull
```

非 Windows 可对照 `run.ps1` 内命令复制执行（或只使用上面的 `docker` + `pytest` + `python xxx.py`）。

## 依赖说明

| 文件 | 用途 |
|------|------|
| `requirements.txt` | 运行 **app / Docker**：`flask`、`redis`、`prometheus-client`、`gunicorn` |
| `requirements-dev.txt` | **开发 / CI**：继承 `requirements.txt`，并包含 `pytest`、`locust`（压测脚本） |

安装开发依赖即包含运行服务所需包，适合本地单测与脚本门禁。

## 测试与标记

配置见根目录 `pytest.ini`（如 `pythonpath`、markers）。

- `-m smoke`：冒烟  
- `-m contract`：HTTP/JSON 契约（`tests/test_api_contract.py`）  
- `-m integration`：需要本机 Redis 等（可能 skip）

## 故障注入 API 与演示（可选）

服务已运行时，可通过 **`/fault/*`** 在 **Redis** 中登记动态故障（**延迟 / 异常 / 随机丢请求 / 慢库模拟**），由 `http_api` 的 **`before_request`** 对业务路径生效；**`/fault`、探活、`/metrics` 路径不套注入**。开关：**`ENABLE_FAULT_INJECTION`**（默认开启）。详细语义与参数见 **`docs/AI_PROJECT_CONTEXT.md`** §4 / §5 / §6。

快速查看状态：

```powershell
curl http://127.0.0.1:5000/fault/status
```

编排演示（写 `reports/fault_demo_latest.json`）：

```powershell
python fault_demo.py
```

## LLM 辅助（可选）

`llm_client.py` / `llm_assist.py` 依赖 **标准库 + 环境变量**（见 `llm_client.py` 文档字符串），无需额外 pip 包即可跑通「auto / ollama / openai 兼容端点」逻辑；云端调用需自行配置 `LLM_API_KEY` 等。子命令示例：`python llm_assist.py generate-tests`、`python llm_assist.py analyze-report --report reports/benchmark_latest.json`。

## CI

- **主链**：`.github/workflows/qa.yml` — 安装 `requirements-dev.txt` → pytest → compose → benchmark → 安全扫描 → `quality_gate` → `chaos_compare --strict`。  
- **接口自动化样例**：`.github/workflows/api-automation-demo.yml` — 独立安装 `api-automation-demo/requirements.txt`，pytest 并上传 **Allure** 原始结果 artifact。

## 目录速览

- `chaos_service/`：领域逻辑（存储、HTTP 路由、韧性、**`fault_injection`**、流量记录）
- `fault_demo.py`：对已起服务跑一轮故障注入演示
- `tests/`：`conftest.py`（FakeRedis、fixtures）、分层测试（含 **`test_fault_injection`**、**`test_llm_client`** 等）
- **`api-automation-demo/`**：pytest + httpx + YAML 驱动 + Allure + CI（与主服务**解耦**）
- `agent-eval/`：**扩展模块** — 工具调用在不稳定环境下的稳定性评估与对照（**非**主线「AI 项目」）
- `k8s/`、`grafana/`、`prometheus*.yml`：运维与可观测性示例
