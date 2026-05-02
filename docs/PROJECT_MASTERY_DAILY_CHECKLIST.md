# 项目吃透打卡版：每日学习清单、工作量、验收标准

> 这篇是 **执行版**。  
> 如果 `PROJECT_MASTERY_FROM_ZERO.md` 是“总路线图”，这篇就是“每天具体干什么、干多少、怎么验收”。

**与 [`AI_PROJECT_CONTEXT.md`](AI_PROJECT_CONTEXT.md) 的同一口径**（打卡前先读 1 分钟）  
- 参数、CI、路径、**`app.py` + `chaos_service/`** 职责以 **AI_PROJECT_CONTEXT** 为准。  
- **门禁**：`quality_gate` 以 **`reports/benchmark_latest.json`** 等为输入；**`benchmark_trend_latest.*`** 是**辅助理解/对比历史**，与 FROM_ZERO 总文档说明一致。  
- 与「零基础阶段表」更短可执行版互参：[`LEARNING_PLAN_0BASIS_SDET.md`](LEARNING_PLAN_0BASIS_SDET.md)。

---

## 0. 使用方法

每天按下面 5 件事执行：

1. **看代码/文档**
2. **动手跑命令**
3. **做笔记**
4. **回答自测题**
5. **完成当天验收**

建议每天投入：

- **工作日版本**：2 ~ 3 小时
- **高强度版本**：4 ~ 6 小时

建议节奏：

- 先按 **10 天版** 走完一轮
- 再按你薄弱点补 2~3 天复盘

---

## 1. 总体量化目标

走完整个计划后，你至少要完成：

### 代码阅读量
- `app.py`
- `chaos_service/http_api.py`
- `chaos_service/store.py`
- `chaos_service/resilience.py`
- `chaos_service/traffic.py`
- `benchmark_compare.py`
- `quality_gate.py`
- `replay_traffic.py`

### 测试阅读量
- `tests/test_app.py`
- `tests/test_api_contract.py`
- `tests/test_benchmark_compare.py`
- `tests/test_quality_gate.py`
- `tests/test_replay_traffic.py`
- `tests/test_redis_integration.py`

### 命令实践量
至少亲手跑：
- `.\run.ps1 -Task test`
- `.\run.ps1 -Task bench`
- `.\run.ps1 -Task gate`
- `.\run.ps1 -Task replay`

### 输出物
你要留下：
- 1 份你自己画的服务主链路图
- 1 份 `/order` 状态码解释表
- 1 份 benchmark 报告解读
- 1 份 gate 判定逻辑笔记
- 1 份岗位叙事笔记（**BIOS/CI 角度**：读 [`PROJECT_POSITIONING_THREE_VERSIONS.md`](PROJECT_POSITIONING_THREE_VERSIONS.md)；仓库内技术对照可写 **`/fault/*` + `fault_demo.py` + `quality_gate`**）

---

## 2. 每日打卡总表

| Day | 主题 | 建议时长 | 主要产出 |
|---|---|---:|---|
| 1 | 跑通项目 + 认识目录 | 2h | 项目地图 |
| 2 | 测试先行：理解对外行为 | 2.5h | 接口行为表 |
| 3 | 主链路 1：`/order` | 3h | 请求流程图 |
| 4 | 主链路 2：幂等 + Redis | 3h | 幂等流程图 |
| 5 | 主链路 3：限流 + 熔断 + 超时 | 3h | 韧性策略表 |
| 6 | 质量链路：benchmark | 2.5h | benchmark 解读笔记 |
| 7 | 质量链路：gate + security + replay | 3h | QA 闭环图 |
| 8 | 工程化：CI / run.ps1 / docker-compose | 2.5h | 工程化总结 |
| 9 | 岗位叙事（BIOS/CI）+ Agent 粗读 | 2.5h | 岗位绑定笔记 |
| 10 | 脱稿讲项目 + 查漏补缺 | 3h | 面试讲稿草稿 |

---

## 3. Day 1：跑通项目 + 认识目录

## 今日目标
- 能把项目跑起来
- 知道仓库分成哪几块
- 知道主入口文件在哪

## 今日工作量

### 阅读
- `README.md`
- `docs/README.md`
- `docs/intro/PROJECT_INTRO_FOR_READERS.md`
- （**强烈建议**）浏览 `docs/AI_PROJECT_CONTEXT.md` **§1～§2 与 §5 小标题**（20～30 分钟，建立与文档一致的心智，避免后面读码跑偏）

建议阅读时间：
- 50 ~ 80 分钟

### 动手
运行：
```powershell
.\run.ps1 -Task test
```

如果本机环境允许，再看：
```powershell
.\run.ps1 -Task help
```

建议动手时间：
- 20 ~ 40 分钟

### 笔记
写一页：

1. 项目分几块  
2. 服务主项目文件在哪  
3. 测试在哪  
4. benchmark/gate 在哪  
5. BIOS/CI **叙事**对应哪篇文档；仓库里用什么**可运行**演示（如 **`fault_demo`、gate**）  
建议笔记时间：
- 20 分钟

## 今日验收
你要能脱口而出：

- 主服务入口：`app.py`
- 服务模块：`chaos_service/`
- 测试目录：`tests/`
- Agent 目录：`agent-eval/`

## 今日打卡标准
- [ ] 跑过 `test`
- [ ] 看完 3 个文档
- [ ] 写出项目目录分层
- [ ] 不看仓库也能说出 5 个关键目录

---

## 4. Day 2：测试先行，理解系统对外行为

## 今日目标
- 不先啃实现，先明白项目“承诺了什么行为”

## 今日工作量

### 阅读
按顺序看：
1. `tests/test_app.py`
2. `tests/test_api_contract.py`
3. `tests/test_fault_injection.py`（`/fault/*` 与注入语义）
4. `tests/conftest.py`

建议时间：
- 90 分钟

### 输出
自己整理一个表：

| 场景 | 接口 | 期望状态码 | 含义 |
|---|---|---:|---|
| 正常下单 | `/order` | 201 | 创建成功 |
| 重复幂等请求 | `/order` | 200 | 返回旧订单 |
| 幂等冲突 | `/order` | 409 | 同 key 不同 payload |
| 限流 | `/order` | 429 | 请求被保护 |
| 熔断/超时保护 | `/order` | 202 | 降级/排队 |
| 库存忙/存储异常 | `/order` | 503 | 服务端失败 |

建议时间：
- 30 分钟

### 自测
写出 8 个测试名字和对应意图。

例如：
- `test_idempotency_returns_same_order`
- `test_concurrent_same_idempotency_key_does_not_duplicate_order`

建议时间：
- 20 分钟

## 今日验收
你要能回答：

1. 为什么要先看测试  
2. `201` / `200` / `409` 分别表示什么  
3. 并发幂等测试在测什么  

## 今日打卡标准
- [ ] 看完 4 个测试文件
- [ ] 整理完状态码行为表
- [ ] 能说出 8 个测试名的目的

---

## 5. Day 3：主链路 1 —— 吃透 `/order`

## 今日目标
- 把一次下单请求从进入到返回讲清楚

## 今日工作量

### 阅读
1. `app.py`
2. `chaos_service/http_api.py`

重点只看：
- `before_request`
- `after_request`
- `create_order`

建议时间：
- 90 分钟

### 输出
手画流程图，至少包含：

1. 进入请求  
2. 生成/透传 request id  
3. 限流检查  
4. 熔断检查  
5. payload 校验  
6. 幂等检查  
7. 超时预算检查  
8. 锁内业务逻辑  
9. 存 Redis  
10. after_request 指标记录  

建议时间：
- 30 ~ 40 分钟

### 动手
打开相关测试，边看边对应代码：
- `test_create_order_success`
- `test_idempotency_returns_same_order`
- `test_idempotency_key_conflict_returns_409`

建议时间：
- 20 分钟

## 今日验收
闭着文档，自己讲：

> 一个 `POST /order` 请求进来以后，代码先后做了什么？

要求：
- 至少讲满 2 分钟
- 顺序不能乱

## 今日打卡标准
- [ ] 读完 `http_api.py` 的主链路
- [ ] 画出流程图
- [ ] 能口述 2 分钟主链路

---

## 6. Day 4：主链路 2 —— 幂等 + Redis

## 今日目标
- 把项目里最值钱的点之一：**并发幂等** 吃透

## 今日工作量

### 阅读
1. `chaos_service/store.py`
2. `tests/test_app.py` 中幂等相关用例
3. `tests/test_redis_integration.py`

建议时间：
- 100 分钟

### 重点问题
必须逐个写答案：

1. 为什么不能只做 `GET -> 业务 -> SETEX`
2. `processing` 状态是干什么的
3. 为什么重复请求有时是 `200`，有时可能是 `202`
4. 为什么同 key 不同 payload 要 `409`
5. 为什么真实 Redis 集成测试比 FakeRedis 更值钱

建议时间：
- 30 分钟

### 输出
整理一个幂等状态表：

| Redis 中状态 | 当前请求怎么处理 |
|---|---|
| 无 key | 尝试抢占 owner |
| processing | 等待或返回 202 |
| succeeded | 返回 200 + order_id |
| payload 冲突 | 返回 409 |

## 今日验收
你要能脱稿讲：

> 这个项目怎么防止并发重复下单？

要求：
- 1 ~ 2 分钟
- 必须说到 `SET NX`
- 必须说到 `processing`
- 必须说到 `409`

## 今日打卡标准
- [ ] 看完 `store.py`
- [ ] 看完幂等相关测试
- [ ] 写完 5 个为什么
- [ ] 能讲清并发幂等

---

## 7. Day 5：主链路 3 —— 限流 + 熔断 + 超时

## 今日目标
- 吃透“韧性治理层”

## 今日工作量

### 阅读
1. `chaos_service/resilience.py`
2. `tests/test_app.py` 中限流/熔断/half-open 相关测试

建议时间：
- 100 分钟

### 必做笔记
整理一个表：

| 策略 | 作用 | 代码位置 | 典型状态码 |
|---|---|---|---:|
| 限流 | 防止瞬时冲击 | `allow_request_by_rate_limit` | 429 |
| 熔断 | 故障隔离 | `is_circuit_open` | 202 |
| 半开 | 故障恢复探测 | `CB_KEY_PROBE` | 202/201/503 |
| 超时保护 | 防止拖垮请求 | `order_deadline_exceeded` | 202 |

建议时间：
- 30 分钟

### 自测
写出下面问题的答案：

1. fixed 和 sliding 的区别  
2. 为什么 Redis 异常时限流是 fail-open  
3. 半开探测是怎么实现的  
4. 为什么超时保护在“进锁前”判断  

建议时间：
- 25 分钟

## 今日验收
你要能回答：

> 如果面试官问“你这个项目到底做了哪些稳定性治理”，你怎么答？

要求：
- 1.5 分钟
- 不能只背术语

## 今日打卡标准
- [ ] 读完 `resilience.py`
- [ ] 整理完韧性策略表
- [ ] 写完 4 个自测题

---

## 8. Day 6：质量链路 —— benchmark

## 今日目标
- 吃透为什么这个项目不是普通 CRUD，而是“可量化质量验证项目”

## 今日工作量

### 阅读
1. `benchmark_compare.py`
2. `tests/test_benchmark_compare.py`

建议时间：
- 80 ~ 100 分钟

### 必须理解的点
- baseline 和 protected 为什么要双实例
- 为什么要多轮运行
- 为什么看 median_of_runs
- 为什么要写 history / trend
- `session_id` 是干什么的

### 动手
运行：
```powershell
.\run.ps1 -Task bench
```

然后看：
- `reports/benchmark_latest.json`（**门禁**主依据之一）
- `reports/benchmark_trend_latest.md`（**人读/对比历史**，与 `benchmark_history/` 一起理解波动）

建议时间：
- 30 ~ 40 分钟

### 输出
自己写一段 benchmark 结果解读，150~250 字。

## 今日验收
你要能回答：

1. 为什么不能只看单次 benchmark  
2. 为什么 current latest 不能完全代表趋势  
3. benchmark history 对面试有什么价值  

## 今日打卡标准
- [ ] 跑过 bench
- [ ] 看过 latest + trend 报告
- [ ] 写完 benchmark 解读

---

## 9. Day 7：质量链路 —— gate + security + replay

## 今日目标
- 理解 QA 闭环

## 今日工作量

### 阅读
1. `quality_gate.py`
2. `security_scan.py`
3. `replay_traffic.py`
4. `tests/test_quality_gate.py`
5. `tests/test_replay_traffic.py`

建议时间：
- 110 分钟

### 动手
运行：
```powershell
.\run.ps1 -Task gate
.\run.ps1 -Task replay
```

建议时间：
- 30 分钟

### 输出
画一个 QA 闭环图：

`benchmark -> security_scan -> reports -> quality_gate -> pass/fail`

再补一条：

`traffic_record -> replay -> replay_report`

## 今日验收
你要能回答：

1. gate 为什么读报告，不重测  
2. replay 的意义是什么  
3. security scan 为什么说是轻量版，不是专业版  

## 今日打卡标准
- [ ] 跑过 gate
- [ ] 跑过 replay
- [ ] 画出 QA 闭环图

---

## 10. Day 8：工程化 —— CI / run.ps1 / docker-compose

## 今日目标
- 能从“脚本和流水线”角度讲项目

## 今日工作量

### 阅读
1. `run.ps1`
2. `.github/workflows/qa.yml`
3. `docker-compose.yml`
4. `Dockerfile`

建议时间：
- 90 分钟

### 输出
整理一个表：

| 文件 | 作用 |
|---|---|
| `run.ps1` | 本地一键任务入口 |
| `qa.yml` | CI 质量流水线 |
| `docker-compose.yml` | 本地服务编排 |
| `Dockerfile` | 服务镜像构建 |

### 自测
你要解释：
- 本地跑和 CI 跑有什么关系
- 为什么 `run.ps1` 值得在简历里讲
- 为什么 benchmark / gate 脚本化很重要

## 今日验收
你要能脱稿讲：

> 这个项目不仅有服务逻辑，还有完整的本地和 CI 工程化链路。

## 今日打卡标准
- [ ] 看完 4 个工程化文件
- [ ] 整理完 1 张职责表
- [ ] 能讲 CI 链路

---

## 11. Day 9：岗位叙事（BIOS/CI）+ Agent 粗读

## 今日目标
- 把项目和实习方向、秋招岗位**绑定表述**；搞清「叙事」与「仓库真实代码」的对应关系

## 今日工作量

### 阅读
1. [`PROJECT_POSITIONING_THREE_VERSIONS.md`](../PROJECT_POSITIONING_THREE_VERSIONS.md)（BIOS/CI 讲法在哪一节）
2. `agent-eval/README.md`（粗读）
3. （可选）`docs/AI_PROJECT_CONTEXT.md` **§4 `/fault/*`、§8 `agent-eval`**

建议时间：
- 100 分钟

### 动手（可选，需服务已起）
```powershell
curl http://127.0.0.1:5000/fault/status
python fault_demo.py
```

建议时间：
- 20 分钟

### 输出
写 2 段话：

#### 第一段
**BIOS/CI 岗位**你要讲的是方法论类比（日志 → 报告 → gate），本仓库里你用哪些**真实模块**支撑这句话（例如 **`quality_gate`、`/fault/*`**）？

#### 第二段
为什么主项目更适合投测开/质量平台，而 **BIOS/CI 叙事**更适合投固件自动化岗？（参照 `PROJECT_POSITIONING`）

## 今日验收
你要能讲：

> 我不是只有一个服务 demo：我有 **可脚本化的 benchmark + gate**，还有 **HTTP 故障注入** 做对照演示；BIOS 岗用 **`PROJECT_POSITIONING`** 里的话术衔接。

## 今日打卡标准
- [ ] 读完 `PROJECT_POSITIONING` 相关节与 `agent-eval/README`
- [ ] （可选）跑过 `fault/status` 或 `fault_demo.py`
- [ ] 写完岗位绑定两段话

---

## 12. Day 10：脱稿讲项目 + 查漏补缺

## 今日目标
- 从“会看代码”升级到“会面试表达”

## 今日工作量

### 任务 1：脱稿讲 3 遍

#### 第 1 遍：3 分钟总述
结构建议：
1. 项目是什么
2. 主服务做了什么
3. 质量验证做了什么
4. BIOS/CI **岗位叙事**你怎么讲（参照 `PROJECT_POSITIONING`，勿声称有独立 BIOS 代码树）

#### 第 2 遍：2 分钟讲 `/order`
必须讲：
- 限流
- 熔断
- 幂等
- 超时
- Redis

#### 第 3 遍：1 分钟讲 benchmark + gate

建议时间：
- 40 分钟

### 任务 2：回答 15 个问题

你至少要自己口头回答：

1. 这个项目解决什么问题  
2. 为什么不是普通 CRUD  
3. 为什么要 Redis  
4. 为什么幂等要先占位  
5. 为什么要 409  
6. 为什么有 202  
7. 限流为什么默认 sliding  
8. 熔断为什么放 Redis  
9. 半开怎么做  
10. 为什么 benchmark 跑多轮  
11. 为什么 quality gate 读报告  
12. replay 的意义是什么  
13. security scan 的边界是什么  
14. BIOS/CI **岗位叙事**为什么有价值（勿与仓库子目录混淆）  
15. 这个项目最大的边界是什么  

建议时间：
- 40 分钟

### 任务 3：查漏补缺
把答不上来的问题记下来，再回头补代码。

建议时间：
- 30 分钟

## 今日验收
满足下面 4 条就算这轮完成：

- [ ] 能 3 分钟总讲项目
- [ ] 能 2 分钟讲 `/order`
- [ ] 能 1 分钟讲 benchmark + gate
- [ ] 15 个问题里至少答对 12 个

---

## 13. 每天统一复盘模板

每天学完都填一次：

```md
## 今日日期：

### 今天看了什么
- 

### 今天跑了什么
- 

### 今天搞懂了什么
- 

### 今天还没搞懂什么
- 

### 明天优先补什么
- 

### 今日完成度（0~100）
- 
```

---

## 14. 吃透程度量化评分表

你可以给自己打分：

### A. 结构理解（20 分）
- 说清模块分层：10
- 说清目录职责：10

### B. 主链路理解（30 分）
- 讲清 `/order`：10
- 讲清幂等：10
- 讲清限流/熔断/超时：10

### C. 质量链路理解（20 分）
- 讲清 benchmark：10
- 讲清 gate/replay/security：10

### D. 工程化（15 分）
- 讲清 run.ps1 / CI / compose：15

### E. 岗位绑定（15 分）
- 讲清 **BIOS/CI 叙事 + `PROJECT_POSITIONING`** 与 **`fault`/`gate` 演示**的对应：5
- 讲清主项目适合什么岗位：10

## 评分标准
- **90+**：可以拿去打主项目面试
- **80~89**：基本合格，再补表达
- **70~79**：理解还行，但不够稳
- **70 以下**：还没有真正吃透

---

## 15. 最终合格线

你至少要达到这些：

- 能独立跑项目
- 能独立讲主链路
- 能独立解释幂等并发
- 能独立读 benchmark/gate 报告
- 能独立说明 **BIOS/CI 岗位叙事**与本仓库 **`fault`/`gate`/benchmark** 如何对齐（见 `PROJECT_POSITIONING`）

做到这些，才算这轮“吃透计划”合格。

