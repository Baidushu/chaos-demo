# 零基础测开：用本仓库学习的路线（可执行版）

> **适用**：测试开发方向入门，希望**跑通 + 能讲清 + 会改会查**，而不是泛泛了解。  
> **核心原则**：先**动起手**看现象，再**对照唯一事实源**建立概念，最后用**单测/契约/报告**把知识钉死。技术细节以 [`AI_PROJECT_CONTEXT.md`](AI_PROJECT_CONTEXT.md) 为准，本文是**学习顺序与自测标准**，不复制第二套参数表。

---

## 你要准备什么（最低限度）

| 项 | 用途 |
|----|------|
| 会装 [Python 3.10+](https://www.python.org/)、能在终端执行 `python -m pip`、`pytest` | 跑脚本与单测 |
| 会开 **Docker Desktop**、知道「容器=隔离环境」 | 起本项目的订单服务、Redis、监控 |
| 知道 **HTTP**：GET/POST、状态码 2xx/4xx/5xx 大致含义 | 看接口与压测结果 |
| 不强制先学 Kubernetes / Prometheus 查询；用到再查 | 本仓库主路径是 **Docker Compose** |

---

## 学习路线总览（建议 3～4 周业余节奏）

| 阶段 | 目标 | 主要读/做的文件与事 |
|------|------|----------------------|
| **1 建立体感** | 本机能跑起来，能打开健康检查与压测表 | 见 **§1** |
| **2 建心智模型** | 知道服务做什么、限流/熔断/幂等/订单在哪 | 见 **§2** |
| **3 测开三板斧** | 单测、契约、报告与门禁**各摸一遍** | 见 **§3** |
| **4 全链路** | 模拟 CI：`bench → scan → gate`（+ 可选 `chaos_compare`） | 见 **§4** |
| **5 深挖与表达** | 能口述「一条请求怎么过韧性」+ 会看 Grafana | 见 **§5** |

每阶段末有**自测题**，过不了就**重复本阶段**再往下。

---

## §1 阶段 1：先跑通（第 1～3 天）

**1.1 按顺序做（不要跳）**

1. 读**半页**即可：根目录 [`README.md`](../README.md)（服务地址、快速命令）。  
2. 精读**操作篇**：[`run/GUIDE.md`](run/GUIDE.md) —— 从「开 Docker」到「能打开 `healthz`」。  
3. 启动：`docker compose up -d`（若本机镜像拉取有问题，以 GUIDE 排查为准；或已起过栈则 `docker compose ps` 确认）。  
4. 浏览器打开：`http://127.0.0.1:5000/healthz`、`/live`、`/ready`（能区分三者更好，细节在阶段 2 补）。  
5. 安装开发依赖后跑单测：  
   `python -m pip install -r requirements-dev.txt`  
   `python -m pytest -q`  
   预期：**全绿**（你本地应与其他环境一致；若红，先按报错修环境或提 issue 自查）。

**1.2 本阶段只读 1 份「地图」**（5 分钟）

- [`intro/PROJECT_INTRO_FOR_READERS.md`](intro/PROJECT_INTRO_FOR_READERS.md)：知道根目录**哪个文件是干啥的**，不要深挖实现。

**1.3 自测（全满足再进 §2）**

- [ ] 能说出：`5000` 与 `5001` 在项目上**各代表什么**（治理 vs 基线，名字记不清没关系，**能指对 compose 里两个服务**即可）。  
- [ ] 能自己敲出一条：`pytest` 全绿。  
- [ ] 知道 **`reports/`** 里会落哪些**典型产物**（先知道名字即可：benchmark、security_scan）。

---

## §2 阶段 2：吃透「事实源」——只读 `AI_PROJECT_CONTEXT`（分块读）

**2.1 读法**（重要）

- 打开 [`AI_PROJECT_CONTEXT.md`](AI_PROJECT_CONTEXT.md)，**不要**第一天从第 1 行一口气读到最后一行。  
- 按下面**顺序**每次只读 1～2 节，读时在纸上画「请求从进来到出去」的箭头。

**2.2 建议阅读顺序与用时**

| 顺序 | 章节（约） | 你应能回答的问题（读完自测） |
|------|------------|------------------------------|
| ① | **§1 目标、§2 根目录表** | 项目两条线：服务侧 vs `agent-eval` 各解决什么？**`chaos_service/`** 与 `app.py` 各负责什么？ |
| ② | **§5 韧性**（限流/熔断/超时/幂等/订单） | 什么情况下会 **202 / 429 / 503**？限流、熔断、超时**谁先来**？（幂等 **processing/等待** 与 **`IDEM_*`** 可在 §6 查表） |
| ③ | **§6 环境变量表** + **§3 compose 里两个 app** | `BUSINESS_TIMEOUT_MS` 在 compose 里大约多少、和代码默认为何可能不同？ |
| ④ | **§4 API 表** | `POST /order` 要记哪些**头**、典型状态码？ |
| ⑤ | **§7 CI** + **根目录** `.github/workflows/qa.yml`（浏览顺序即可） | CI 里**先 smoke 再全量** pytest 的意图？后面几步顺序？ |
| ⑥ | **§8 agent-eval**（先浏览） | `TOOLS_BASE_URL`、`AGENT_MODE=rule` 在 CI 里为什么合理？ |
| ⑦ | **§9 测试** | `smoke` 和 `contract` 大致分工？ |
| ⑧ | 有余力再读 **§2.1 各文件实现方法** | 为「面试深挖」和「以后看源码」打底 |

**2.3 自测**

- [ ] 能用自己的话**2 分钟**讲：一次 `POST /order` 在**开韧性**时可能经过**哪些检查**（不必背变量名，逻辑对即可）。  
- [ ] 能指出：**订单正文**、**幂等**、**熔断状态** 大致在 **Redis 哪类 key 思路** 上（见 §5，能复述关键词即可）。  
- [ ] 打开 `docker-compose.yml`：能**指认** `app` 和 `app_baseline` 与端口的对应关系。

---

## §3 阶段 3：用「测开武器」读仓库——测试与脚本

**3.1 单测与契约**（先读再跑，按顺序打开文件）

| 顺序 | 文件 | 学什么 |
|------|------|--------|
| 1 | [`tests/conftest.py`](../tests/conftest.py) | `FakeRedis`、fixture 怎么替换真实 Redis；为何单测不依赖 Docker。 |
| 2 | [`tests/test_app.py`](../tests/test_app.py) | 与 `app.py` 同路径的**功能行为**；带 `@pytest.mark.smoke` 的用例=最小回归。 |
| 3 | [`tests/test_api_contract.py`](../tests/test_api_contract.py) | **契约测开**：状态码 + JSON 形状，与接口文档对齐。 |
| 4 | [`pytest.ini`](../pytest.ini) | 标记 `smoke` / `contract` 怎么用。 |

**命令**（建议亲手各跑一遍，体会分层）：

```text
python -m pytest tests/ -m smoke -q
python -m pytest tests/ -m contract -q
python -m pytest -q
```

**3.2 压测、扫描、门禁**（读**文档级**说明即可，再对着脚本看主函数）

| 顺序 | 文件/文档 | 学什么 |
|------|-----------|--------|
| 1 | [`AI_PROJECT_CONTEXT.md`](AI_PROJECT_CONTEXT.md) **§2.1 里 B/C/D 小节** | `benchmark_compare` / `security_scan` / `quality_gate` **做什么**、产物文件名。 |
| 2 | [`benchmark_compare.py`](../benchmark_compare.py) 的 `main` 与参数 | `-n`、`-c`、`--seed`、`--warmup` 与 `BENCHMARK_*`。 |
| 3 | 扫一眼 [`quality_gate.py`](../quality_gate.py) 的入口 | 读哪些 json、什么情况下 `exit(1)`。 |

**3.3 自测**

- [ ] 能说明：**为什么**要有「契约」测试，和「业务」测试区别在哪（一句人话即可）。  
- [ ] 能打开 `reports/benchmark_latest.json`，指出 **baseline / protected** 与 **params** 各是什么。  
- [ ] 知道 **`quality_gate`** 失败时，常见是**读旧报告**还是**超阈值**（见 `AI_PROJECT_CONTEXT` §10）。

---

## §4 阶段 4：全链路像 CI 一样跑（第 2～3 周）

**4.1 在 Docker 已启动、5000 可访问的前提下**

- Windows：优先用 `.\run.ps1 -Task qa`（或要对齐含 Agent 的 CI 用 `.\run.ps1 -Task qafull`，以你机器为准，见 `run.ps1` help）。  
- 或手动按 [`AI_PROJECT_CONTEXT.md`](AI_PROJECT_CONTEXT.md) **§7** 顺序执行等价命令。

**4.2 自测**

- [ ] 能走通：**bench →（必要时等 healthz）→ scan → gate** 且**退出码 0**（或理解为何失败并会修/会认）。  
- [ ] 能打开 `reports/security_scan_latest.md`，知道 **findings=0 与 `fail_on` 的层级** 关系。  
- [ ] 可选：跑完 `agent-eval` 的 `chaos_compare` 后，能打开 `agent-eval/reports/chaos_compare_latest.md`，**看懂表格里 baseline vs chaos** 在比什么（见 [`agent-eval/README.md`](../agent-eval/README.md) + 全景 §8）。

---

## §5 阶段 5：深挖、监控与「能讲出来」

**5.1 阅读顺序**

1. [`intro/DEEP_DIVE.md`](intro/DEEP_DIVE.md) — 按章节选读：与 §2 已学内容对照，**补「为什么/边界/面试问法」**。  
2. [`interview/INTERVIEW_PREP.md`](interview/INTERVIEW_PREP.md) — 把简历 bullet、讲稿、压测样例**换成你自己的数**（本地重跑后填）。  
3. 浏览器看 **Grafana** 大盘（见根 `README` 里地址与看板名）：把 **PromQL 与 §5 韧性** 上的概念对上号（不强制全会写查询）。

**5.2 自测：什么叫「吃透本仓库」**（可对外说）

- [ ] **白板级**：3 分钟讲清项目目标、双实例对照、三件套（pytest / 压测+门禁 / 可选 agent）。  
- [ ] **路径级**：能跟随 **一条请求** 说清限流、熔断、超时、建单、Redis 键**大致顺序**（允许看笔记）。  
- [ ] **测开级**：能解释**为何**要有新鲜度/重试、契约测试、安全扫描的 **context_aware**（用项目里原词即可）。  
- [ ] **诚实边界**（加分会）：能说一句 [`plan/AGENT_EVAL_PLAN.md`](plan/AGENT_EVAL_PLAN.md) **§2.1** 里「demo 不做什么」。

---

## 日常建议：怎么记、怎么练

- 用 [`personal/MY_LEARNING_LOG.md`](personal/MY_LEARNING_LOG.md) **复制一份**到自己笔记里，**每天只记**：今天跑的命令、一个报错、一句理解。  
- **不要**在多处维护「自己版本的 API 全表」；有疑问只改「问题清单」，**答案只信** `AI_PROJECT_CONTEXT` + 源码。  
- 卡住了：先 [`run/GUIDE.md`](run/GUIDE.md) 排查节，再对照全景文 §12 **诚实边界**。

---

## 文档索引速查

| 需求 | 打开 |
|------|------|
| 全仓库 md 地图 | [`README.md`](README.md)（本 `docs` 下索引） |
| 技术事实唯一源 | [`AI_PROJECT_CONTEXT.md`](AI_PROJECT_CONTEXT.md) |
| 运行与排错 | [`run/GUIDE.md`](run/GUIDE.md) |
| 文件路径速查 | [`intro/PROJECT_INTRO_FOR_READERS.md`](intro/PROJECT_INTRO_FOR_READERS.md) |

*版本：与仓库主分支同路径；学习节奏因人而异，**宁可阶段少跳步**。*
