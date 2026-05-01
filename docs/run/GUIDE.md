# 运行与排查指南

本文合并原 `RUN_STEPS.md` 与 `TROUBLESHOOTING.md`：**上半部分按顺序跑通，下半部分按现象排查**。

> **环境变量、端口、CI 顺序、韧性细节**见 **[`../AI_PROJECT_CONTEXT.md`](../AI_PROJECT_CONTEXT.md)**；本文只写**操作步骤与现象排查**，不重复事实表。  
> 文档索引导航见 [`../README.md`](../README.md)。

---

# 第一部分：按顺序运行

第一次跑只要跟着 **数字顺序** 做，不要跳步。

**第一次来、只想先跑通时，你真正要执行的其实只有这些**（其它 A～H 是「以后按需」）：

| 顺序 | 做什么 | 命令（在项目根 `d:\chaos-demo`） |
|------|--------|----------------------------------|
| 1 | 开 Docker Desktop | 图形界面里等到引擎就绪 |
| 2 | 进目录 | `cd d:\chaos-demo`（路径按你本机改） |
| 3 | 起服务 | `docker compose up --build -d`（第一次会久一点） |
| 4 | 验证容器 | 可选：`docker compose ps` |
| 5 | 验证能访问 | 浏览器打开 `http://127.0.0.1:5000/healthz` 有反应即成功 |
| 6 | （选做）本机单测不依赖容器 | `pip install -r requirements-dev.txt` 然后 `pytest tests/ -q` |

**到第 5 步 = 服务已跑通。** 压测、安全扫、Agent、一键 `qa` 等见下文 **「第五步 A～H」**，**初学不用第一天全跑**。

---

## 你需要先准备什么？

| 东西 | 用来干什么 |
|------|------------|
| **Docker Desktop**（Windows） | 一键把订单服务、Redis、监控等全拉起来 |
| **Python 3.10+** | 跑压测脚本、Agent 评测、单元测试（本机已装即可） |

没有 Docker：服务起不来，`http://127.0.0.1:5000` 也打不开。

---

## 第一步：打开 Docker Desktop

- 在开始菜单打开 **Docker Desktop**。  
- 等右下角/托盘里的 Docker **不再转圈**，变成「正在运行」。

---

## 第二步：进入项目文件夹

用 PowerShell 或 CMD：

```powershell
cd d:\chaos-demo
```

（如果你的项目在别的盘，改成你的路径。）

---

## 第三步：启动所有服务（最重要）

```powershell
docker compose up --build -d
```

- **第一次**会下载镜像、编译，可能要几分钟。  
- `-d` 表示在后台跑，终端可以继续输入命令。

**怎么算成功？**  
没有大红报错；或者再执行：

```powershell
docker compose ps
```

能看到 `app`、`app_baseline`、`redis` 等状态是 `running` 或 `Up`。

---

## 第四步：确认网页能打开

浏览器打开：

- **健康检查**：http://127.0.0.1:5000/healthz  
- **存活探针**（可选）：http://127.0.0.1:5000/live  
- **就绪探针**（可选）：http://127.0.0.1:5000/ready  

再试：

- **治理版服务**：http://127.0.0.1:5000  
- **基线版**（对照用）：http://127.0.0.1:5001  

（可选）监控：

- Prometheus：http://127.0.0.1:9090  
- Grafana：http://127.0.0.1:3000（账号见仓库根目录 [`README.md`](../../README.md)）

**到这一步 = 项目已经「跑起来了」。**

---

## 第五步：你想做哪一类操作？（选一种）

### A. 单元测试

**须在本仓库根目录**（能直接看到 `app.py`、`pytest.ini` 的那一级）执行；单测**不**依赖 Docker 里服务，可与第三步并行。

```powershell
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

- 已用 `pytest.ini` 里的 **`pythonpath = .`** 避免 `import app` 报 `ModuleNotFoundError`；若仍失败，把 **pytest 升到 7+**：`python -m pip install -U pytest`  
- 也等价于：`pytest tests/ -q`（同上目录）

分层（与 CI 一致可先 smoke 再全量）：

```powershell
pytest tests/ -m smoke -q
pytest tests/ -q
```

或用脚本（当前 `run.ps1 -Task test` 为全量一次）：

```powershell
.\run.ps1 -Task test
```

### B. 压测对比（需要第三步已成功）

```powershell
python benchmark_compare.py
```

或：`.\run.ps1 -Task bench` → 生成 `reports/benchmark_latest.json`。

- **`.\run.ps1 -Task bench` / 一键 `qa` 中压测前**：若未设环境变量，会注入与 **GitHub CI** 相同的 **`BENCHMARK_WARMUP`**、**`BENCHMARK_SEED`**，便于与流水线报告可比。  
- 可自定义：`python benchmark_compare.py -n 300 -c 20 --seed 7 --warmup 20`，或设 **`BENCHMARK_*`**。详见 **[`../AI_PROJECT_CONTEXT.md`](../AI_PROJECT_CONTEXT.md) §2.1 B**；同 **seed** 连跑时注意 Redis 幂等键，必要时换 **seed** 或清 Redis（脚本会向 stderr 提示）。

### C. 安全扫描（需要服务在跑）

```powershell
.\run.ps1 -Task scan
```

→ `reports/security_scan_latest.json`、`.md`

### D. 统一质量门禁（需先有 benchmark + security 报告，或先跑 B+C）

```powershell
.\run.ps1 -Task gate
```

### E. 流量录制与回放

```powershell
$env:TRAFFIC_RECORD_ENABLED="true"
.\run.ps1 -Task up
```

录制：`reports/traffic_record_latest.jsonl`。回放：`.\run.ps1 -Task replay`。

### F. Agent 评测（需要 5000 可访问）

```powershell
.\run.ps1 -Task agenteval
```

### G. 一键 QA（测试 + 压测 + 等 healthz + scan + gate）

```powershell
.\run.ps1 -Task qa
```

### H. Agent 混沌对照

```powershell
.\run.ps1 -Task agentchaos
```

---

## 第六步：关掉服务

```powershell
docker compose down
```

---

## PowerShell 易错写法

| 错误写法 | 为什么错 | 正确写法 |
|----------|----------|----------|
| `pytest / .\run.ps1 test` | `/` 不是「或者」 | 分开执行或用分号：`pytest -q; .\run.ps1 -Task test` |
| 直接输入 `agenteval` | 不是系统命令 | `.\run.ps1 -Task agenteval` |

---

## 常用命令表

| 你想做的事 | 命令 |
|------------|------|
| 看任务列表 | `.\run.ps1 -Task help` |
| 启动 / 停止服务 | `docker compose up --build -d` / `docker compose down` |
| 测试 / 压测 / 扫描 / 门禁 / 一键 QA | `.\run.ps1 -Task test` / `bench` / `scan` / `gate` / `qa` |
| 回放 | `.\run.ps1 -Task replay` |
| Agent | `.\run.ps1 -Task agenteval` / `agentchaos` |

---

## 与其它文档

| 文档 | 用途 |
|------|------|
| 本文 | 运行顺序 + 排查 |
| 根目录 [`README.md`](../../README.md) | 端口、环境变量、技术栈 |
| [`../intro/PROJECT_INTRO_FOR_READERS.md`](../intro/PROJECT_INTRO_FOR_READERS.md) | 结构说明 |
| [`../../agent-eval/README.md`](../../agent-eval/README.md) | Agent 专篇 |

---

# 第二部分：常见问题与排查

按**实际报错**对号入座；多数是 **Docker 未启动**或**未先起服务就跑压测/扫描**。

---

## 1. PowerShell：`pytest / .\run.ps1 test`、`agenteval` 无法识别

见上文 **PowerShell 易错写法**。

---

## 2. `docker compose`：`pipe\dockerDesktopLinuxEngine` / `cannot find the file specified`

**原因**：Docker Desktop 未启动或引擎未就绪。

**处理**：打开 Docker Desktop 等就绪后重试 `docker compose up --build -d`；检查 WSL2 是否按官方文档启用。

---

## 3. `qa` / `benchmark_compare.py` 很慢或结果异常

**原因**：订单服务未在 `5000`/`5001` 监听。

**处理**：先 `docker compose up --build -d`，确认 `http://127.0.0.1:5000/healthz` 可访问，再跑压测。

---

## 4. Agent：`Connection refused` / 卡住

**原因**：`TOOLS_BASE_URL` 默认 `http://127.0.0.1:5000`，服务未起。

**处理**：先保证 5000 可访问，再在项目根目录跑 `run_agent_eval` / `score` 等。

---

## 5. `pytest` 失败

```powershell
pip install -r requirements-dev.txt
pytest tests/ -q
```

若仅 Agent 配置测试失败，检查 `agent-eval/config/eval_config.yaml` 是否被改坏。

---

## 6. 端口被占用（5000 / 5001 / 6379）

关掉占用进程，或改 `docker-compose.yml` 的 `ports`（同时改 `benchmark_compare`、文档中的 URL）。

---

## 7. GitHub Actions 与本地不一致

以 **CI 日志**为准；本地至少保证 `pytest` + `docker compose` + `benchmark_compare` 可通过。

---

## 8. `scan` / `gate` 失败：不可达或安全门禁失败

1. `docker compose up --build -d`  
2. 确认 `http://127.0.0.1:5000/healthz`  
3. 顺序：`bench` → `scan` → `gate`（或 `run.ps1 -Task qa`）

---

## 9. `replay`：no events found

需先 `TRAFFIC_RECORD_ENABLED=true` 再起服务并打一些请求；见第一部分 **E**。

---

## 仍解决不了时

请备齐：**完整命令**、**终端完整报错**、Docker 是否运行、`/healthz` 浏览器能否打开。
