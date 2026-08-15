# Chaos-Demo 深度掌握计划 V2（秋招大厂测试开发版）

> **导师定位**：Senior Software Engineer Mentor
> **总目标**：把 chaos-demo 从"AI 辅助完成的项目"，转化为**秋招大厂测试开发的核心项目**。
> **目标岗位**：大厂测试开发 / AI 测试工程师 / 质量工程师 / 测开兼后端。
> **周期**：8 周（56 天），每天**保底 2 小时（必做）+ 进阶（选做）**两档。
> **生成依据**：`D:\chaos-demo` 当前真实代码，不是通用路线。

---

## V2 相对 V1 改了什么（为什么）

| 你的反馈 | V2 的处理 |
|---|---|
| ① AI 比例过高 | 重排权重：**Testing 升为第一大块（11 天）**；AI 拆成两块——Phase 7(AI 平台内部)压到 3 天只理解设计，Phase 6(AI 评估)保留 7 天 |
| ② 缺测试核心训练 | Phase 3 扩成最详尽的章节，含 **50 道测开题**、flaky 治理、测试数据管理、Mini 测试框架 |
| ③ 缺企业代码阅读训练 | 新增 **Code Reading Task**：每天 4 问（这文件干嘛？谁调用？为什么这么设计？改需求动哪里？）贯穿全程 |
| ④ 缺从零小项目 | 每个 Mini 升级为**可独立运行 + 自带 pytest** 的小项目，可当第二个作品讲 |
| ⑤ 8 周过重 | 每天分**保底(必做)/进阶(选做)**两档；周复盘可顺延不删减 |

> **导师两条红线（必须读）**
> 1. **AI 别砍错地方**：你的岗位含"AI测试工程师"，**AI 评估是你的护城河**（普通测开讲不清 LLM 怎么测，你能）。砍的是"算法深度"（transformer/注意力，本就不该学），不是"评估深度"。
> 2. **MySQL 是八股不是项目**：本项目存储**只用 Redis，没有 MySQL**。所以 MySQL 面试题归"补充八股"，别当成"结合项目"讲，否则被追问"MySQL 在你项目里怎么用"就露馅。

---

## 每天怎么学（保底 / 进阶 两档）

**保底档（必做，约 2 小时，雷打不动）**
1. **读（40 min）**：只读当天指定源码，带"Code Reading 4 问"读，**禁止复制**。
2. **做（50 min）**：当天的重写 / 实验保底项。卡 20 分钟再对答案，对完关掉再写。
3. **答（20 min）**：当天面试题**出声**作答并录音/记录，答不出标记薄弱。
4. **记（10 min）**：3 行笔记——搞懂了什么 / 哪里含糊 / 明天第一件事。

**进阶档（选做，状态好时加 1–1.5 小时）**：当天标记为「进阶」的实验、额外练习、额外面试题。

> **执行军规**：当天没做完**顺延**，不删减；连续 3 天只能完成保底，说明排太满，主动砍掉进阶。周末默认复盘 + 补漏 + 重做本周薄弱点。

---

# Phase 0 — 项目地图建立（Day 1–3）

> **定位**：先不深入任何模块，只用 3 天把"这个项目到底怎么跑起来、一个请求怎么走、一个测试怎么跑"看清。地图不建好，后面越学越乱。
> **核心方法（Code Reading 4 问，全程通用）**：读任何文件都问——**① 这文件是干嘛的？② 谁调用它？③ 为什么这么设计？④ 要改需求该动哪里？**

## 0.1 学习目标
- 不看文档，能从代码反推出整个项目的运行链路。
- 产出三张图/表：项目架构图、请求调用链图、模块职责表。

## 0.2 项目目录分析（先建立这张真实地图）

```
chaos-demo/
├── ai_platform_api.py        # AI Platform 入口 (FastAPI :8000)
├── app.py                    # Chaos Service 入口 (Flask :5000)
├── ai_platform/              # 【质量保障层】60 文件
│   ├── core/                 # 编排核心 config/factory/service/lifecycle/context/exceptions
│   ├── agent/                # AgentRuntime / AgentState / AgentContext
│   ├── workflow/             # WorkflowEngine / Node / Router / nodes/
│   ├── tools/                # BaseTool / Registry / Executor / legacy_tool
│   ├── llm/                  # LLMGateway + providers/(mock,ollama,openai)
│   ├── security/             # SecurityGuard 4层(input/prompt/permission/output)
│   ├── evaluation/           # 评估引擎 evaluator/engine/gate/result + 子包
│   └── observability/        # Collector / Event / Trace / Metrics / Logger
├── chaos_service/            # 【被测系统-混沌】30 文件
│   ├── chaos/injector/       # 4种故障注入 latency/exception/drop/slow_db
│   ├── resilience/breaker/   # 熔断器(状态机)
│   ├── rate_limiter.py       # 限流(Redis+Lua)
│   └── retry.py              # 重试(指数退避+jitter)
├── app/                      # 【被测系统-业务】37 文件
│   ├── api/                  # order_controller 等 HTTP 层
│   ├── service/              # OrderService 业务层
│   ├── repository/           # idempotency_store 等存储层
│   ├── infrastructure/       # redis_client.py
│   └── config/ exceptions/ observability/
├── tests/                    # 61 测试文件 / 574 用例
│   ├── conftest.py           # ★ 内含 FakeRedis / FailingRedis
│   ├── core_platform/        # 平台单测(test_sec_/test_eval_/test_obs_...)
│   └── unit/ integration/ e2e/ demo/ deployment/
├── scripts/                  # generate_evaluation_report.py / run_quality_gate.py
├── .github/workflows/        # ci.yml / ai-quality.yml / qa.yml
├── lua/                      # fixed_window.lua / sliding_window.lua
└── pytest.ini                # 9 个 marker: unit/smoke/contract/integration/e2e/chaos/slow/redis/resilience
```

## 0.3 一次请求的完整链路（Day 2 要脱稿画出）

```
HTTP POST /api/v1/agent/run            ai_platform_api.py
 → AIPlatformService.run()             ai_platform/core/service.py
   → AgentRuntime.run()/run_state()    agent/runtime.py
     → SecurityGuard.check_input()     security/guard.py
     → WorkflowEngine.run()            workflow/engine.py
       → ToolNode→ToolExecutor.execute()  tools/executor.py
       → JudgeNode→LLMGateway.generate()  llm/gateway.py
   → EvaluationEngine.evaluate()       evaluation/engine/__init__.py
   → QualityGate.assert_pass()         evaluation/gate.py
 ← PlatformResult                      (success/answer/score/trace_id/gate)
全程 Collector 记录                    observability/collector.py
```

## 0.4 一次测试的执行链路（Day 3 要脱稿画出）

```
pytest -m smoke
 → pytest.ini 注册 marker / pythonpath
 → tests/conftest.py 装配 fixture
     → FakeRedis（内存版 Redis，支持 Lua、可注入故障）
     → FailingRedis（包装器，_maybe_fail 注入失败）
     → MockProvider（确定性 LLM）
 → 被测对象（如 AIPlatformService / RateLimiter）
 → 注入 fake（替换真实 Redis / LLM）
 → 执行 → assert 断言
```

> **关键洞察（面试能讲）**：这个项目测试之所以又快又稳，是因为 `conftest.py` 里手写了 **FakeRedis**——一个内存版 Redis，连 Lua 脚本都用 `register_script` 模拟了，还能用 `FailingRedis` 注入失败。这让"依赖 Redis 的测试"变成**确定、无需真实 Redis、可模拟故障**。这就是企业级测试工程的精髓。

## 0.5 需要阅读的源码文件
1. `ai_platform_api.py`、`app.py` —— 两个入口怎么启动（启动流程）。
2. `ai_platform/core/service.py` —— 只看 `run()` 主链，不抠细节。
3. `tests/conftest.py` —— 重点看 FakeRedis / FailingRedis / session fixture。
4. `pytest.ini` —— 9 个 marker 各自含义。

## 0.6 需要完成的产出（Day 3 结束交付）
- **项目架构图**：双引擎 + 各层，标注真实目录/类名。
- **请求调用链图**：上面 0.3，脱稿重画。
- **模块职责表**：一张表，每行 = `目录 | 职责 | 关键类 | 谁调用它`。

## 0.7 面试可能问题
1. 用 1 分钟讲清这个项目是干嘛的、两大块各是什么？
2. 一个请求进来，经过哪些层？哪一层挂了会怎样？
3. 你的测试为什么不用真实 Redis 也能跑？（引出 FakeRedis，高分答案）

## 0.8 验收标准
- [ ] 三张产出（架构图/调用链/职责表）完成且脱稿。
- [ ] 能口述启动流程（两个服务、各自端口、入口文件）。
- [ ] 能讲清 FakeRedis 解决了什么测试痛点。

---

# Phase 1 — Python 企业工程能力（Day 4–8）

> **定位**：能维护大型 Python 测试项目的语法与工程地基。**本周引入全程习惯：Code Reading 4 问。**

## 1. 学习目标
- 熟练项目用到的全部 Python 高级语法，能讲"解决了什么问题、有什么坑"。
- 掌握工程四件套：package/import、虚拟环境、config、logging、依赖管理。

## 2. 学习内容
- **Python 语法**：class 设计、inheritance（含 MRO/super）、abstract class（`ABC`/`@abstractmethod`）、dataclass（`field`/`slots`/frozen）、typing（`X|None`、`list[str]`、`Protocol`、`Literal`）、decorator（带参/不带参/`functools.wraps`）、context manager（`__enter__/__exit__`）、exception（异常树、`raise...from`）、iterator/generator（`yield`、惰性）。
- **工程能力**：package 结构与 `__init__.py` 导出、import 机制（循环 import 及解法）、虚拟环境（venv 隔离 + 为什么要）、config 管理、logging、`requirements*.txt` 依赖管理（区分 `requirements.txt` / `requirements-ai.txt` / `requirements-dev.txt`）。

## 3. 结合项目：源码阅读（每天带 4 问读）
> 注：项目无独立 `utils/` 包，config/logging/exception 分布在下列真实位置，按此读：
1. `ai_platform/core/exceptions.py`（`PlatformError` 树）+ `ai_platform/tools/executor.py`（`ToolExecutionError` 树）+ `app/exceptions/__init__.py`（`BusinessException` 树）→ **三棵异常树对比**。
2. `ai_platform/llm/types.py` → dataclass 与 `LLMError` 的 slots 坑（**招牌故事**）。
3. `ai_platform/core/config.py`（`PlatformConfig` + `to_dict/from_dict`）+ `app/config/`（`base/redis/resilience/chaos` 多配置）。
4. `ai_platform/observability/logger.py` + `app/observability/logging/formatter.py`（JSON 结构化日志）。
5. ABC 四处：`tools/base.py`、`llm/base.py`、`evaluation/evaluator.py`、`chaos/injector/base.py`；Protocol 三处：`workflow/node.py`、`rate_limiter.py`、`breaker/storage.py`。

## 4. Code Reading Task（从本周起，每天必做）
对每个当天读的文件，写下 4 问答案（一句话即可）：
- ① 这文件是干嘛的？
- ② 谁调用它？（用 `grep -rn "import xxx"` 或 IDE 找引用验证，不许猜）
- ③ 为什么这么设计？（至少说出一个"不这样会怎样"）
- ④ 要改某个需求，该动它哪里？

## 5. 代码重写（从零小项目，自带测试）
在 `learning/phase1/` 建一个**可运行小项目** `pykit/`，含 `pykit/` 包 + `tests/`：
- `pykit/exceptions.py`：一棵三层异常树（基类 + ≥4 子类，带结构化字段，支持 `raise...from`）。**刻意**先用 `@dataclass(slots=True)` 复现 `LLMError` 的坑再改。
- `pykit/config.py`：嵌套 Config，支持默认值、`to_dict/from_dict`、环境变量覆盖。
- `pykit/logger.py`：JSON 结构化日志器，支持 `trace_id` 透传。
- `tests/`：每个模块 ≥3 个 pytest 用例，`mypy --strict` 通过。

## 6. 需要完成的实验 / 练习
- **保底**：复现并修复 slots+super 的 TypeError；写 `@retry` 和 `@timed` 两个装饰器；制造一次循环 import 并用两种方法解。
- **进阶**：写一个把测试数据集当**生成器**逐条 `yield` 的加载器（体会惰性，为测试数据管理埋伏笔）；用 `contextlib.contextmanager` 写一个"计时块"上下文管理器。

## 7. 面试问题
1. ABC vs Protocol？你项目各用在哪？2. `LLMError` 为什么不用 `@dataclass(slots=True)`？3. 零参 `super()` 在 `__post_init__` 为何失效？4. 异常树怎么设计、粒度怎么定？5. `from __future__ import annotations` 干嘛的？6. 可变默认参数陷阱（`field(default={})`）？7. 虚拟环境解决了什么？8. 为什么要分多个 requirements 文件？

## 8. 验收标准
- [ ] `pykit/` 三件套可运行、有测试、mypy 通过。
- [ ] 能白板讲 `LLMError` slots 坑并现场复现修复。
- [ ] 每个读过的文件都写了 Code Reading 4 问。
- [ ] 8 道面试题录音达标。

---

# Phase 2 — 项目架构与代码阅读能力（Day 9–13）

> **定位**：重点**不是背架构，是能读懂企业代码**。判断标准：随便给你项目里一个文件，你能讲清它在系统中的角色。

## 1. 学习目标
- 用"分层 + DI + Factory + 接口 + 耦合度"五副眼镜读懂 `ai_platform/`。
- 产出 class diagram 和 sequence diagram（脱稿）。

## 2. 学习内容
- **分层架构**：表现层(API)/编排层(core)/领域层(agent,workflow,tools,llm)/基础设施层(providers,observability)；依赖只许向下。
- **Dependency Injection**：构造器注入；面向接口编程；DI 与可测试性的关系。
- **Factory**：集中装配、隐藏构造细节；`PlatformFactory` 的 9 个 `create_*`。
- **Interface 设计**：窄接口；面向 `ABC/Protocol` 而非具体类。
- **Coupling（耦合）**：什么是高/低耦合；如何用接口和 DI 降耦合；怎么识别"改一处牵动全身"的坏味道。

## 3. 结合项目：源码阅读（每天一个文件，读透）
1. `ai_platform/core/factory.py` —— 装配顺序：谁依赖谁。
2. `ai_platform/core/service.py` —— `__init__` 纯关键字注入 + `run()` 编排。
3. `ai_platform/core/config.py` + `core/context.py` + `core/lifecycle.py` —— 配置/上下文/生命周期。
4. `ai_platform_api.py` —— 薄控制器原则。
5. 任选一个下游模块（如 `tools/executor.py`）验证"上层不依赖其内部，只依赖其接口"。

## 4. Code Reading Task（每天 4 问，本周重点练"②谁调用"和"④改哪里"）
- 用 `grep -rn "from ai_platform.core import" --include=*.py` 这类命令，**实证**每个文件的调用方，而不是凭印象。

## 5. 代码重写 / 输出
- **class diagram**：`ai_platform/core/` 各类的关系图（`AIPlatformService` 依赖 `AgentRuntime/EvaluationEngine/QualityGate/PlatformConfig`；`PlatformFactory` 创建它们）。
- **sequence diagram**：一次 `run()` 请求的时序图（Service→Runtime→Guard→Engine→Executor→Gateway→Evaluation→Gate）。
- **一段 300 字《耦合分析》**：指出项目里一处"低耦合设计得好"（如 `CircuitBreakerStorage(Protocol)` 让熔断器可换存储）+ 一处"如果耦合高了会怎样"的反例。

## 6. 需要完成的实验 / 练习
- **保底**：实验——不用 DI 写一版 `AgentRuntime`（内部直接 new SecurityGuard），体会无法 mock；改回注入。
- **进阶**：利用 DI 把 `QualityGate` 换成"永远放行"的假实现，不改其他代码跑通；画出替换前后的依赖差异。

## 7. 面试问题
1. 项目整体架构？为什么分层？2. Service 与 Factory 分工？能合并吗？3. 为什么到处构造器注入？4. 换评估后端为外部服务要改哪？为什么只改一点？5. 怎么控制依赖方向、防下层反向依赖？6. 什么是低耦合？举个项目里的例子。

## 8. 验收标准
- [ ] class diagram + sequence diagram 脱稿完成，标注真实类名。
- [ ] 随机抽 3 个项目文件，能讲清"角色/调用方/改需求动哪"。
- [ ] 能讲清 DI 如何让"换组件不改代码"。
- [ ] 6 道题达标，第 4 题能举"换评估后端"的具体例子。

---

# Phase 3 — Testing Engineering（Day 14–24，11 天，全计划第一大块）

> **定位**：你投的是**测试开发**，这是你的专业课和面试主战场。目标：指着 574 个真实用例，讲清一套企业级测试体系是怎么设计的。
> **本阶段三件套**：pytest 机制吃透 + 测试设计分层 + 测试工程治理（数据/隔离/flaky/retry）。

## 1. 学习目标
- 精通 pytest 全机制，并能说出每个机制"解决了什么测试痛点"。
- 掌握测试金字塔在项目的落地：unit / contract / integration / e2e 各测什么、怎么隔离。
- 能独立设计并实现一个 Mini Testing Framework（fixture + runner + assertion）。
- 能治理真实测试问题：测试数据、环境隔离、flaky、重试。

## 2. 学习内容
- **pytest 机制**：fixture（function/class/module/session 四种 scope、`autouse`、setup/teardown、fixture 间依赖）、conftest.py（层级与可见性）、mock 与 `unittest.mock`、`monkeypatch`（`setattr/setitem/env`）、`@pytest.mark.parametrize`、marker（自定义 + `--strict-markers`）、`skip / skipif / xfail`、test isolation。
- **测试设计**：unit（单类/单函数）→ contract（API 状态码与 JSON 形状）→ integration（跨模块 + 真实/仿真依赖）→ e2e（进程内全栈）；每层"测什么、不测什么、怎么隔离"。
- **测试工程**：测试数据管理（黄金数据集、builder/factory、生成器惰性加载）、测试环境隔离（Fake 替代真实依赖、资源清理）、**flaky test 治理**（定位→分类→修复/隔离/quarantine）、重试策略（测试层 retry vs 生产 retry 的区别）、覆盖率（行/分支，怎么定目标）。

## 3. 结合项目：深入 `tests/`
1. `pytest.ini` —— 9 个 marker（unit/smoke/contract/integration/e2e/chaos/slow/redis/resilience）如何用标签把测试分层，`--strict-markers` 防拼写错。
2. `tests/conftest.py` —— **本周最重要**。逐段读：**FakeRedis**（内存版，连 Lua 都模拟：`register_script`、`rate_limit_sliding_allow`）、**FailingRedis**（`_maybe_fail` 注入失败）、session 级 fixture（约 line 297 起）。理解"用 Fake 换真实依赖"的完整手法。
3. `tests/core_platform/test_service.py` / `test_factory.py` / `test_api.py` —— 看 `autouse` fixture（line 22/17/10）如何自动准备平台组件；如何用 MockProvider 保证确定性。
4. `tests/core_platform/test_sec_prompt_guard.py` —— 看 parametrize 如何覆盖"应拦截/应放行"矩阵。
5. `tests/unit/test_rate_limiter.py` —— 边界参数化矩阵（`test_rate_limit_boundary_matrix`）。
6. `tests/integration/test_redis_integration.py` —— 需要真实 Redis 时怎么处理（`redis` marker + skip 条件）。
7. `tests/core_platform/test_eval_gate.py` / `test_eval_engine.py` —— 评估/门禁测试如何构造指标数据。

## 4. Code Reading Task（每天 4 问）
- 重点练"③为什么这么设计"：对每个 fixture，回答"为什么用 session 而不用 function scope？如果反过来会怎样？"

## 5. 代码重写（从零小项目）：Mini Testing Framework
在 `learning/phase3/` 实现 `minipytest/`（**不依赖 pytest，自己造轮子以理解原理**）+ 用真 pytest 写它的测试：
- **fixture 机制**：支持注册 fixture（带 scope）、按名注入到测试函数、function 级每次重建、session 级全程复用、支持 teardown。
- **test runner**：发现 `test_*` 函数 → 解析其参数名匹配 fixture → 执行 → 收集结果（pass/fail/error + 耗时）→ 汇总报告。
- **assertion**：实现 `expect_eq/expect_true/expect_raises`（后者验证"抛了指定异常"）。
- **parametrize**：支持给一个测试传多组参数逐个跑。
- 用你造的 `minipytest` 跑通 ≥8 个测试（含 1 个 parametrize、1 个 expect_raises、1 个 session fixture 复用）。
- **对比产出**：200 字——"我造的 minipytest 与真 pytest 的五点差距"（如：插件、hook、丰富的断言重写、并行、生态）。

## 6. 需要完成的实验 / 练习
- **保底**：
  - 实验 3.1（scope）：一个 fixture 分别设 function/session，`print` 观察执行次数；回答"为什么 session fixture 不能持有可变状态"。
  - 实验 3.2（隔离事故）：写两个共享全局变量的测试，连跑互相污染、单跑却过——体会隔离第一原则。
  - 实验 3.3（monkeypatch 替换时间）：把熔断器冷却时间 patch 成 0，让等待类测试瞬跑。
  - 实验 3.4（FakeRedis 实战）：用 `tests/conftest.py` 的 FakeRedis 写 3 个测试：限流放行/限流拒绝/Redis 故障（用 FailingRedis）。
- **进阶**：
  - 实验 3.5（flaky 治理）：故意写一个依赖"当前时间秒数"的 flaky 测试，复现它的偶发失败，再用三种方法治理（去时间依赖/固定种子/隔离），写治理笔记。
  - 实验 3.6（覆盖率驱动）：对 `chaos_service/rate_limiter.py` 跑 `--cov`，找未覆盖分支补测试。
  - 实验 3.7（测试数据管理）：把评估数据集改成生成器逐条加载，对比内存占用，写"大数据集为什么要惰性加载"。

## 7. 测试开发 50 问（按子主题，写答案 + 出声练）

**A. pytest 机制（12）**
1. fixture 的四种 scope 区别？各适合什么？
2. `autouse` fixture 是什么？什么时候用/不用？
3. conftest.py 的层级与可见性规则？根目录 vs 子目录各放什么？
4. fixture 之间能互相依赖吗？有什么用？
5. fixture 的 setup/teardown 怎么写？yield 形式了解吗？
6. session 级 fixture 为什么不能持有可变状态？
7. 什么是 fixture 的参数化？和 `@parametrize` 区别？
8. `monkeypatch` 和 `unittest.mock.patch` 区别？各何时用？
9. `@pytest.mark.parametrize` 怎么覆盖边界？stacked parametrize 会怎样？
10. 自定义 marker 怎么注册？`--strict-markers` 干嘛的？
11. `skip` / `skipif` / `xfail` 区别？`xfail(strict=True)` 呢？
12. pytest 怎么收集测试？命名约定是什么？

**B. mock 与依赖替换（7）**
13. 什么该 mock、什么不该 mock？过度 mock 有什么危害？
14. 怎么 mock 一个 LLM 调用，让测试确定？
15. `Mock` / `MagicMock` / `patch` / `patch.object` 区别？
16. 怎么断言"某个 mock 被以某参数调用了 N 次"？
17. `side_effect` 能干嘛？怎么模拟"第一次失败第二次成功"？
18. 怎么 mock 环境变量 / 当前时间 / 随机数？
19. 你的项目用 FakeRedis 而不是 mock，为什么？Fake vs Mock 取舍？

**C. 测试设计与分层（11）**
20. 测试金字塔是什么？为什么底层要多？
21. unit / integration / e2e 各测什么、怎么隔离？
22. 什么是 API contract test？和 unit test 区别？
23. 一个"下单"功能，你会在三层各写什么测试？
24. 怎么测试一个"依赖 Redis 的限流器"？（unit 用 Fake + integration 用真 Redis）
25. e2e 测试慢又脆，怎么控制数量和稳定性？
26. 什么是好的测试命名/结构（Arrange-Act-Assert）？
27. 测试要测私有方法吗？为什么？
28. 边界值 / 等价类怎么用于设计用例？举例。
29. 怎么为一个"评估打分函数"设计测试用例？
30. 什么是回归测试？怎么建立回归套件？

**D. 测试工程治理（10）**
31. 什么是 flaky test？常见根因有哪些？
32. 发现一个 flaky test，你的治理流程是什么？
33. 测试之间共享状态会有什么后果？怎么避免？
34. 测试数据怎么管理？黄金数据集 / builder / 工厂模式？
35. 大型数据集测试为什么要惰性加载（生成器）？
36. 怎么隔离测试环境（不污染真实 Redis / DB / 文件系统）？
37. 测试里能用 `time.sleep` 吗？替代方案？
38. 覆盖率怎么看？行覆盖 vs 分支覆盖？定多少合理？
39. 测试该不该追求 100% 覆盖？为什么？
40. CI 里怎么做快速反馈？（讲 smoke 分层 + 分阶段）

**E. 项目实战结合（10）**
41. 你项目的 574 个测试是怎么分层的？
42. 为什么测试要分 9 个 marker？解决了什么？
43. FakeRedis 怎么模拟 Lua 脚本？（讲 `register_script`）
44. FailingRedis 是干嘛的？怎么用它测"Redis 挂了"？
45. 你的安全测试怎么覆盖"应拦截/应放行"？
46. 评估门禁怎么测？（构造过/不过的指标）
47. 需要真实 Redis 的集成测试，本地/CI 没有怎么办？
48. 你怎么保证 LLM 相关测试的确定性？
49. 讲一个你项目里设计得好的测试，为什么好。
50. 如果让你给项目补测试，你最先补哪块？为什么？

## 8. 验收标准（本阶段不过，不许进 Phase 4）
- [ ] 能讲清 fixture 四种 scope + autouse + conftest 层级，并举项目实例（说出 `tests/conftest.py` 的 FakeRedis）。
- [ ] 自研 `minipytest` 能跑 fixture(scope) + runner + assertion + parametrize，≥8 测试全过。
- [ ] 能用 FakeRedis/FailingRedis 独立写"依赖 Redis"的测试。
- [ ] 能讲 flaky 治理的完整流程，并举实验 3.5 的亲身经历。
- [ ] 50 题全部作答，A/B/C 类（pytest/mock/分层）能脱口而出。
- [ ] 随机抽 5 个项目测试文件，能讲清"测什么/怎么隔离/为什么这么设计"。

---

# Phase 4 — CI/CD 与质量门禁（Day 25–29）

> **定位**：测开的高频考点。把"代码提交 → 自动测试 → 质量门禁 → 构建"这条流水线讲成你自己设计的。
> **招牌卖点**：这个项目的质量门禁是**真的能拒人**的（你亲手验证过：一份 0.42 分的烂报告会被 gate 打回）。

## 1. 学习目标
- 读懂 GitHub Actions 的分阶段 job 设计，能讲"为什么这么排"。
- 讲清质量门禁（quality gate）如何落地为可执行脚本，而非口号。
- 能独立写一个带缓存、分层、产物上传的最小 CI。

## 2. 学习内容
- GitHub Actions：`jobs / steps / needs / runs-on / strategy.matrix`、`cache`（pip）、`artifacts`（`upload/download-artifact`）、`if:` 条件、退出码语义。
- 流水线设计：快速反馈优先（先跑快的 smoke，再跑慢的 ai-quality，最后 docker-build）；"fail fast" 与"分层门禁"的取舍。
- 质量门禁：把"质量阈值"翻译成脚本退出码（0=过 / 非0=拒）；`scripts/run_quality_gate.py` 如何读报告、比阈值、非零退出。

## 3. 结合项目：源码阅读
1. `.github/workflows/ci.yml` —— job 划分、依赖（`needs`）、每步跑什么 pytest marker。
2. `scripts/run_quality_gate.py` —— 门禁逻辑：读 JSON → 比对阈值 → 打印原因 → 退出码。
3. `scripts/generate_evaluation_report.py` —— 报告怎么生成（跑 ScoreEvaluator 产出分数）。
4. `docker-compose.yml` / `Dockerfile` —— 镜像怎么构建、服务怎么编排。

## 4. Code Reading Task（4 问，重点练"④改需求动哪里"）
- 问："如果产品要求新增一个'安全评分<85 就拒'的门禁，该改哪几个文件？"——你必须答出：报告生成处 + `run_quality_gate.py` 阈值 + CI 里对应 step，三处缺一不可。

## 5. 代码重写（从零小项目）：Mini CI Pipeline
在 `learning/phase4/` 建一个最小但**真实可跑**的 CI 演示：
- 一个小 Python 包 + 几个 pytest 用例（含一个故意会失败的）。
- 一个 `.github/workflows/mini-ci.yml`：两个 job（`test` → `gate`），用 `needs` 串联；`test` 用 pip 缓存；`gate` 下载产物并校验。
- 一个本地版门禁脚本 `gate.py`：读一个 JSON 分数，低于阈值 `sys.exit(1)`。
- **实验**：先让测试全绿看 CI 过；再改坏一个测试，看 `gate` 因 `needs` 被跳过、`test` 变红——理解 `needs` 的短路语义。

## 6. 实验 / 练习
- **保底**：
  - 实验 4.1：手动跑 `python scripts/run_quality_gate.py <一份烂报告>`，亲眼看它非零退出（你已做过，这次把命令和输出记成笔记）。
  - 实验 4.2：给 mini-ci 加 pip 缓存，对比有无缓存的耗时。
- **进阶**：
  - 实验 4.3：给主项目 CI 设计"PR 只跑 smoke、合并 main 才跑全量 + 门禁"的双层策略，写成 YAML（不用真提交，能讲清即可）。
  - 实验 4.4：给门禁脚本加 `--report-json` 输出结构化结果，便于 CI 解析。

## 7. 面试问题
1. 你们的 CI 分了几个阶段？为什么先跑 smoke 再跑全量？
2. `needs` 是干嘛的？job 失败了下游会怎样？
3. 什么是质量门禁？你的项目怎么实现"不达标就拒"？
4. CI 里怎么做 pip 依赖缓存？为什么能加速？
5. 怎么理解"fail fast"？流水线顺序怎么排最合理？
6. artifact 什么时候用？上传/下载怎么配？
7. 如果 CI 里某个测试偶发失败（flaky），你怎么办？

## 8. 验收标准
- [ ] 能脱稿画出主项目 CI 的 job 依赖图，并讲每层"测什么、为什么在这层"。
- [ ] 能讲质量门禁是"可执行脚本 + 退出码"，并举 0.42 分被拒的实例。
- [ ] `learning/phase4/` 的 mini-ci 真实跑通过（绿一次、红一次）。
- [ ] 7 道题全部作答。

---

# Phase 5 — Chaos Engineering 与韧性（Day 30–35）

> **定位**：这是项目的"被测系统"半边，也是你区别于普通测开的亮点——**你不仅测正常，还主动注入故障测韧性**。

## 1. 学习目标
- 讲清混沌工程是什么、为什么测开要懂（故障注入是"反向测试"）。
- 吃透四大韧性机制：限流、熔断、重试、幂等。
- 能设计一个故障注入实验并断言系统的韧性行为。

## 2. 学习内容
- **混沌工程理念**：主动注入故障验证系统韧性；爆炸半径控制；稳态假设。
- **限流**：固定窗口 vs 滑动窗口（`lua/fixed_window.lua` / `sliding_window.lua`）；为什么用 Redis+Lua（原子性）。
- **熔断器**：状态机 CLOSED→OPEN→HALF_OPEN；失败率阈值、冷却时间、半开试探。
- **重试**：指数退避 + jitter；幂等性与重试的关系；什么错误该重试。
- **幂等**：`app/repository/idempotency_store.py`；幂等键；防重复提交。

## 3. 结合项目：源码阅读
1. `chaos_service/chaos/injector/` —— 4 种注入器（latency/exception/drop/slow_db）怎么挂在请求链上。
2. `chaos_service/resilience/breaker/breaker.py` + `state.py` —— 状态机转换逻辑。
3. `chaos_service/rate_limiter.py` + `lua/sliding_window.lua` —— 滑动窗口实现。
4. `chaos_service/retry.py` —— 退避与 jitter。
5. `app/repository/idempotency_store.py` —— 幂等存储。

## 4. Code Reading Task（4 问，重点练"③为什么这么设计"）
- 问："熔断器为什么要有 HALF_OPEN，而不是冷却完直接 CLOSED？"——答出"半开试探，防止雪崩式恢复"。

## 5. 代码重写（从零小项目）：Mini Resilience Kit
在 `learning/phase5/` 实现 `resilience/`，含自己的 pytest：
- `circuit_breaker.py`：一个完整三态熔断器（可配阈值/冷却），状态转换有日志。
- `retry.py`：指数退避 + 随机 jitter 的装饰器，可指定"哪些异常可重试、最多几次"。
- `rate_limiter.py`：内存版滑动窗口限流（不依赖 Redis，用列表/字典实现算法，理解原理）。
- 测试覆盖：熔断开/关/半开；重试成功/重试耗尽/不可重试异常直接抛；限流边界（第 N 个放行、第 N+1 个拒）。

## 6. 实验 / 练习
- **保底**：
  - 实验 5.1：对运行中的 Chaos Service 注入 latency，观察下游熔断器打开的过程（如果有可运行环境）。
  - 实验 5.2：用你写的 mini 熔断器包一个"会随机失败"的函数，打印状态转换序列。
  - 实验 5.3：对比 fixed vs sliding 窗口在"临界点突发流量"下的差异，写结论。
- **进阶**：
  - 实验 5.4：给一个非幂等接口加重试，制造重复提交，再加幂等键解决——亲身体会"重试必须配幂等"。
  - 实验 5.5：设计一个"慢数据库"注入实验，断言系统在 slow_db 下的响应（超时/降级）。

## 7. 面试问题
1. 什么是混沌工程？测开为什么要懂？
2. 熔断器三态怎么转？为什么要 HALF_OPEN？
3. 滑动窗口限流为什么用 Redis+Lua？（原子性）
4. 重试为什么要加 jitter？指数退避怎么算？
5. 为什么重试必须配幂等？你项目怎么保证幂等？
6. 固定窗口限流有什么临界问题？滑动窗口怎么解决？
7. 故障注入和普通的异常测试有什么区别？

## 8. 验收标准
- [ ] 能脱稿画熔断器状态机，并讲清每个转换条件。
- [ ] `learning/phase5/` 三件套可运行、测试全过。
- [ ] 能讲"重试+幂等"的配合，并举实验 5.4 的实例。
- [ ] 能讲清四大韧性机制各自解决什么故障。
- [ ] 7 道题全部作答。

---

# Phase 6 — AI 质量评估（Day 36–42，护城河阶段）

> **定位**：**这是你投"AI 测试工程师"的护城河，权重故意保留。** 普通测开讲不清"LLM 输出怎么测"，你能——这就是差距。
> **导师提醒**：砍的是"算法深度"（不用懂 transformer 内部），不是"评估深度"。你要成为"最懂 AI 怎么测的测开"。

## 1. 学习目标
- 讲清 AI 评估的三大流派：规则打分（Score）、LLM-as-Judge、回归对比（Regression）。
- 掌握一个"AI 质量门禁"从数据集 → 跑评估 → 出分 → 卡阈值的完整闭环。
- 能设计一套针对 LLM 应用的评估方案（这是面试大题）。

## 2. 学习内容
- **为什么 LLM 测试难**：输出不确定、无标准答案、语义层面正确性。→ 需要专门的评估方法论。
- **ScoreEvaluator**：规则化指标打分（关键词/结构/长度等可计算项）。
- **JudgeEvaluator（LLM-as-Judge）**：用另一个 LLM 当裁判打分；偏见与一致性风险。
- **RegressionEvaluator**：baseline vs candidate 对比，防止"改了 prompt 就变差"。
- **QualityGate 六阈值**：`tool_selection_accuracy_min(0.70)`、`arg_accuracy_min(0.70)`、`avg_tool_calls_per_task_max(10.0)`、`retry_rate_max(0.30)`、`hallucination_rate_max(0.10)`、`planner_invalid_rate_max(0.10)`——每个阈值在防什么。
- **benchmark 数据集**：黄金集怎么建、怎么避免污染。

## 3. 结合项目：源码阅读
1. `ai_platform/evaluation/evaluator.py`（ABC）→ `engine/`（Score/Judge/Regression 三个实现）。
2. `ai_platform/evaluation/gate.py` —— 六阈值如何逐一判定、不达标抛什么。
3. `ai_platform/evaluation/dataset/` —— 数据集加载（呼应 Phase 3 的"惰性加载"）。
4. `ai_platform/evaluation/judges/` —— Judge 的 prompt 与打分解析。
5. `ai_platform/evaluation/regression/` —— baseline 对比逻辑。
6. `scripts/generate_evaluation_report.py` —— 把评估结果变成 CI 可读报告。

## 4. Code Reading Task（4 问）
- 问："QualityGate 为什么是 6 个阈值而不是 1 个总分？"——答出"单一总分掩盖单维度塌方；分项阈值能精确定位退化点"。

## 5. 代码重写（从零小项目）：Mini AI Evaluator
在 `learning/phase6/` 实现 `ai_eval/`，含 pytest：
- `dataset.py`：黄金集（prompt/expected/标签），生成器惰性加载。
- `score_evaluator.py`：对"模型输出"算 ≥3 个规则指标（如关键词命中、格式合法、长度合理），输出结构化分数。
- `gate.py`：读分数，比对阈值，不达标抛 `GateError` 或 `sys.exit(1)`。
- `report.py`：输出 JSON 报告（呼应 CI 门禁）。
- 用 MockProvider 或假输出当"被测模型"，跑通"数据集→评估→门禁→报告"全闭环。
- 测试覆盖：全过、单指标塌方被门禁拦、边界阈值。

## 6. 实验 / 练习
- **保底**：
  - 实验 6.1：手动跑 `generate_evaluation_report.py`，看懂产出的每个字段。
  - 实验 6.2：改坏一个指标，看 QualityGate 拦下——把"哪个阈值触发"记下来。
  - 实验 6.3：给 ScoreEvaluator 设计一个新指标（如"答案是否包含免责声明"），写出判定逻辑。
- **进阶**：
  - 实验 6.4：写一段 Judge prompt，让"裁判 LLM"对 5 条答案打 1–5 分，人工核对一致性，写"LLM-as-Judge 的坑"。
  - 实验 6.5：构造 baseline vs candidate 两版输出，跑回归，写"回归测试防什么"。

## 7. 面试问题
1. LLM 输出不确定，怎么做自动化测试？（核心题）
2. 你们项目的 AI 评估是怎么落地的？（讲数据集→评估→门禁闭环）
3. Score vs LLM-as-Judge vs Regression 各适合什么场景？
4. LLM-as-Judge 有什么风险？怎么缓解？
5. QualityGate 的 6 个阈值各自防什么？
6. 怎么建 benchmark 黄金集？怎么防数据污染？
7. 改了 prompt 怎么保证没把模型改差？（回归）
8. 幻觉（hallucination）怎么检测/度量？

## 8. 验收标准
- [ ] 能完整讲"一个 AI 请求如何被评估并卡门禁"。
- [ ] `learning/phase6/` 的 mini evaluator 闭环跑通、有测试。
- [ ] 能现场设计一套"给某 LLM 应用"的评估方案（数据集+指标+门禁）。
- [ ] 8 道题全部作答，第 1 题能讲 3 分钟。

---

# Phase 7 — AI 平台内部（Day 43–45，只理解设计）

> **定位**：**降权到 3 天，只理解设计、不抠实现。** 你要能讲"这个 Agent 平台是怎么组织的"，而不是逐行背代码。
> **判断标准**：能画出 Agent/Workflow/Tools/LLM 的关系图即可，不用重写。

## 1. 学习目标
- 讲清 Agent 平台的编排逻辑：Runtime → Workflow → Node → Tool/LLM。
- 理解 LLM Gateway 的 Provider 抽象（mock/ollama/openai 可换）。

## 2. 学习内容（理解级，不深挖）
- **AgentRuntime**：一次任务的执行循环（规划→调工具→判断）。
- **WorkflowEngine + Node/Router**：planner/tool/judge 三类节点怎么编排流转。
- **Tools**：`BaseTool`(ABC) / `Registry` / `Executor`；工具如何被 Agent 调用。
- **LLMGateway + Provider 抽象**：面向接口，换模型不改业务。

## 3. 结合项目：源码阅读（每个只读"主干"）
1. `ai_platform/agent/runtime.py` —— 执行循环主干。
2. `ai_platform/workflow/engine.py` + `nodes/`（planner/tool/judge）—— 节点编排。
3. `ai_platform/tools/{base,registry,executor}.py` —— 工具三件套。
4. `ai_platform/llm/{gateway,base}.py` + `providers/` —— Provider 抽象。

## 4. Code Reading Task（4 问）
- 问："为什么 LLM 调用要走 Gateway 而不是业务直接调 Provider？"——答出"统一入口便于加缓存/限流/观测/换模型"。

## 5. 代码重写（最小，可选）：Mini Agent Loop
- **保底（必做）**：画三张关系图（Agent 编排图、Workflow 节点流转图、Provider 抽象图），脱稿。
- **进阶（选做）**：在 `learning/phase7/` 写一个 30 行的 Mini Agent 循环：`while 未完成: 规划→选工具→执行→记录`，工具用假实现，能跑通即可。**不要追求完整，体会循环即可。**

## 6. 实验 / 练习
- **保底**：用 MockProvider 跑通一次 `run()`，在观测数据里看清每个节点被调用的顺序。
- **进阶**：换 ollama provider（如本地有）跑同一任务，对比输出——体会 Provider 可换。

## 7. 面试问题
1. 你的 Agent 平台怎么组织一次任务的执行？
2. planner / tool / judge 三类节点各干嘛？
3. 为什么 LLM 调用要做一层 Gateway 抽象？
4. 怎么做到换底层模型（ollama→openai）不改业务代码？

## 8. 验收标准
- [ ] 三张关系图脱稿完成。
- [ ] 能讲清一次 `run()` 的节点流转顺序。
- [ ] 能讲 Provider 抽象的价值。
- [ ] 4 道题全部作答。

---

# Phase 8 — 安全与防护（Day 46–49）

> **定位**：AI 时代的测试新考点——**Prompt 注入是新的 SQL 注入**。你能讲清"怎么测一个 AI 应用的安全性"，又是差异化加分项。

## 1. 学习目标
- 讲清项目的四层防御体系及每层职责。
- 能设计 Prompt 注入的测试用例（应拦截 / 应放行矩阵）。
- 理解"安全测试"和普通功能测试的区别。

## 2. 学习内容
- **四层防御链**：`InputValidator`（输入校验）→ `PromptGuard`（注入检测）→ `PermissionChecker`（权限）→ `OutputChecker`（输出检查）。
- **Prompt 注入**：直接注入 / 间接注入 / 越狱（jailbreak）；~22 种注入模式的覆盖思路。
- **纵深防御**：为什么单层不够、要多层兜底。
- **安全测试方法**：负向用例（应拦截）+ 正向用例（应放行，防误伤）；误报 vs 漏报的权衡。

## 3. 结合项目：源码阅读
1. `ai_platform/security/guard.py` —— SecurityGuard 怎么串起四层。
2. `ai_platform/security/prompt_guard.py` —— 注入模式匹配逻辑。
3. `ai_platform/security/input_validator.py` / `permission.py` / `output_checker.py` —— 各层职责。
4. `tests/core_platform/test_sec_prompt_guard.py` —— 注入测试的用例矩阵怎么组织。

## 4. Code Reading Task（4 问）
- 问："为什么 Prompt 检测要用模式库而不是单一正则？"——答出"注入手法多样，需要可扩展的模式集合 + 便于持续补充"。

## 5. 代码重写（从零小项目）：Mini Prompt Guard
在 `learning/phase8/` 实现 `prompt_guard/`，含 pytest：
- `patterns.py`：≥8 条注入模式（如 "ignore previous instructions"、"system prompt 泄露"、"DAN 越狱"等），每条可独立启停。
- `guard.py`：扫描输入，命中即返回 `SecurityResult(blocked=True, reason=...)`；支持"观察模式"（只记录不拦截）。
- 测试：≥10 个应拦截用例 + ≥5 个应放行用例（防误伤），参数化组织。
- **写 200 字**："误报和漏报哪个更可怕？分场景讨论。"

## 6. 实验 / 练习
- **保底**：
  - 实验 8.1：手工构造 5 种注入，分别打向项目，看四层各自拦住了哪种。
  - 实验 8.2：故意写一条"看起来正常但触发误报"的输入，调模式让它放行——体会误报治理。
- **进阶**：
  - 实验 8.3：设计一个"间接注入"场景（恶意指令藏在工具返回的数据里），讨论防御难点。
  - 实验 8.4：把 guard 切成"观察模式"跑一批流量，统计"会拦多少误伤"，写分析。

## 7. 面试问题
1. 你的 AI 平台怎么防 Prompt 注入？（讲四层）
2. 什么是直接注入 vs 间接注入？
3. 安全测试和功能测试有什么区别？怎么设计用例？
4. 误报和漏报怎么权衡？什么场景宁误报、什么场景宁漏报？
5. 为什么要纵深防御、多层兜底？
6. 怎么测试"应放行"的用例不被误伤？

## 8. 验收标准
- [ ] 能画四层防御链并讲每层拦什么。
- [ ] `learning/phase8/` 的 mini guard 跑通，拦截/放行测试全过。
- [ ] 能现场设计 Prompt 注入的测试用例矩阵。
- [ ] 6 道题全部作答。

---

# Phase 9 — 可观测性（Day 50–51，2 天轻量）

> **定位**：理解级。"出了问题怎么定位"是测开日常，你要能讲清 Trace/Metrics/Log 三件套。

## 1. 学习目标
- 讲清可观测性三支柱：Trace（请求链路）、Metrics（指标）、Log（日志）。
- 理解 Counter/Gauge/Histogram 三种指标各测什么。

## 2. 学习内容
- **Trace/Span/Event**：一次请求的全链路追踪；`trace_id` 透传。
- **Metrics 三类型**：Counter（只增计数，如请求数）、Gauge（瞬时值，如在线数）、Histogram（分布，如延迟分位）。
- **结构化日志**：JSON 日志 vs 纯文本；为什么要带 trace_id。
- Prometheus / Grafana 的角色（拉取指标 + 可视化）。

## 3. 结合项目：源码阅读
1. `ai_platform/observability/collector.py` —— 怎么收集 Trace/Span/Event/Metrics。
2. `ai_platform/observability/{trace,metrics,event,logger}.py` —— 各数据模型。
3. `app/observability/` —— Chaos Service 侧的观测实现。

## 4. Code Reading Task（4 问）
- 问："为什么 Histogram 而不是直接记平均延迟？"——答出"平均值掩盖长尾，Histogram 能看 P95/P99"。

## 5. 代码重写 / 输出（轻量）
- 画一张"一次请求的观测数据流图"：哪里产生 Span、哪里记 Metric、哪里打日志。
- **进阶（选做）**：在 `learning/phase9/` 写一个 30 行的内存 Collector，能记录一次请求的 span 树并打印——体会结构即可。

## 6. 实验 / 练习
- **保底**：跑一次请求，在观测数据里找到它的完整 span 树和每个 span 的耗时。
- **进阶**：给某个慢操作加一个自定义 Metric，观察其 Histogram 分布。

## 7. 面试问题
1. 可观测性三支柱是什么？各解决什么？
2. Counter / Gauge / Histogram 区别？各举个例子。
3. 为什么要 trace_id 透传？怎么用它定位问题？
4. 为什么平均延迟会骗人？该看什么指标？

## 8. 验收标准
- [ ] 能讲一次请求在系统里留下的三类观测痕迹。
- [ ] 能讲清三种 Metric 类型及适用场景。
- [ ] 4 道题全部作答。

---

# Phase 10 — 面试专项冲刺（Day 52–56）

> **定位**：把前 51 天的积累，打磨成"开口就能讲、追问扛得住"的面试状态。
> **核心纪律**：项目可考题必须**结合代码讲**，补充八股题**绝不硬蹭项目**（尤其 MySQL）。

## 1. 三档自我介绍（Day 52 各写一版，之后每天出声练）

**3 分钟版**（电面/HR 初筛）：我是谁 → 做了什么项目（一句话双引擎）→ 我最硬的三个点（企业级测试体系 / 真实质量门禁 / AI 评估方法论）→ 一个数字成果（574 用例 / 6 阈值门禁 / 22 注入模式）。

**5 分钟版**（技术一面）：在 3 分钟基础上，加"一个我亲手解决的技术难题"（推荐讲 **CI 假门禁→真门禁** 或 **LLMError 的 slots 坑**），突出"我验证、我发现、我修复"。

**10 分钟版**（技术二面/深挖）：完整讲架构（双引擎）→ 重点讲 Testing 体系（分层 + FakeRedis + flaky 治理）→ AI 评估闭环 → 质量门禁 → 一个最有挑战的决策（为什么用 Fake 而不是 mock / 为什么门禁要做成真脚本）。

> **写法要求**：每版写到逐字稿，但练习时要**脱稿讲**，录音回听，砍掉一切"嗯""然后""就是"。

## 2. 项目讲解的"电梯话术"（背到条件反射）
- **一句话**：一个双引擎质量工程平台——一边是注入故障的被测系统，一边是做 AI 质量评估与门禁的保障层。
- **为什么做**：普通项目只测正常路径；这个项目主动注入故障测韧性、给 LLM 输出建评估门禁，贴近大厂真实质量实践。
- **我最强的一块**：测试体系——574 用例、9 个 marker 分层、自写 FakeRedis 换掉真实依赖、能治理 flaky。

## 3. 项目可考 50 问（必须结合代码答，分六大类）

**A. Python（10）**
1. `@dataclass(slots=True)` + 零参 `super()` 为什么炸？你怎么修的？
2. ABC 和 Protocol 你项目各用在哪？为什么？
3. 项目三棵异常树怎么设计的？
4. `from __future__ import annotations` 解决了什么？
5. 可变默认参数的坑，项目里怎么规避？
6. 生成器在项目哪用到？（数据集惰性加载）
7. 装饰器在项目里有哪些实际用途？
8. 构造器注入在项目里怎么体现？
9. `X | None` 这种写法依赖什么？
10. 讲一个你项目里 Python 用得好/踩过坑的地方。

**B. pytest / 测试（12）**—— 即 Phase 3 的 50 问，此处抽核心 12 题复练
11. 项目测试怎么分层？9 个 marker 各干嘛？
12. FakeRedis 怎么实现的？为什么不用真实 Redis？
13. FailingRedis 是干嘛的？
14. fixture 四种 scope 项目里各用在哪？
15. `autouse` fixture 项目里怎么用的？
16. 怎么保证 LLM 测试确定性？（MockProvider）
17. parametrize 在安全测试里怎么覆盖拦截/放行矩阵？
18. 需要真 Redis 的集成测试怎么处理？（redis marker + skip）
19. flaky test 你怎么治理？（讲你的亲身经历）
20. 覆盖率怎么定的？补测试先补哪？
21. 你造的 minipytest 和真 pytest 差在哪？
22. 讲一个项目里设计得最好的测试。

**C. CI/CD（7）**
23. 项目 CI 分几个阶段？为什么这么排？
24. 质量门禁怎么落地的？（讲真脚本 + 退出码）
25. 你验证过门禁真的会拒吗？（讲 0.42 分被打回）
26. `needs` 干嘛的？fail fast 怎么体现？
27. pip 缓存怎么配？加速多少？
28. 你修的 CI stale-path 是什么问题？（pytest exit 4）
29. PR 和 main 分支该不该跑同样的测试？

**D. Redis / 存储（6）**
30. 项目为什么用 Redis？用在哪几处？（限流/幂等/熔断存储）
31. 限流为什么用 Redis+Lua？（原子性）
32. 滑动窗口 Lua 怎么实现的？
33. 幂等键怎么存 Redis？防什么？
34. FakeRedis 怎么模拟 Lua 的 `register_script`？
35. Redis 挂了系统怎么兜底？（FailingRedis 测的就是这个）

**E. 架构 / 设计（8）**
36. 整体架构？为什么双引擎分离？
37. 分层怎么分的？依赖方向怎么控制？
38. Factory 和 Service 分工？
39. DI 怎么让"换组件不改代码"？举例。
40. 熔断器状态机怎么转？为什么 HALF_OPEN？
41. 重试为什么配幂等？jitter 干嘛的？
42. 四层安全防御各拦什么？
43. 可观测性三件套在项目里怎么落地？

**F. AI 测试（7）**
44. LLM 输出怎么自动化测试？（核心，能讲 3 分钟）
45. 评估闭环怎么跑的？（数据集→评估→门禁→报告）
46. Score / Judge / Regression 各适合什么？
47. QualityGate 6 阈值各防什么？
48. LLM-as-Judge 有什么坑？
49. 怎么防 prompt 注入？测试怎么设计？
50. 改了 prompt 怎么保证没变差？（回归）

## 4. 补充八股（Day 55–56，与项目解耦，纯背诵 + 理解）

> **纪律**：这些题**别说"我项目里用了"**——项目没有 MySQL、没碰 Linux 运维深处。被问就如实说"项目主要用 Redis，MySQL 是我补的基础"。诚实比硬蹭安全得多。

**MySQL（补充八股，约 10 个概念）**：索引（B+树、聚簇/非聚簇、最左前缀）、事务（ACID、四大隔离级别、MVCC）、锁（行锁/间隙锁/死锁）、慢查询优化（explain、覆盖索引、避免 SELECT *）、分库分表概念。**会讲概念即可，不用硬接项目。**

**Linux（补充八股，约 8 个概念）**：常用命令（`grep/awk/top/ps/netstat/tail -f`）、查进程/端口/日志、权限（chmod/chown）、`nohup`/后台运行、磁盘/内存排查（`df/free`）、`kill` 信号。**以"测开日常排查"为语境背。**

**计算机网络（高频 6 个）**：HTTP vs HTTPS、TCP 三次握手/四次挥手、状态码（2xx/4xx/5xx）、GET vs POST、Cookie/Session/Token、超时与重试的关系。

**操作系统 / 通用（高频 4 个）**：进程 vs 线程、并发 vs 并行、死锁四条件、time_wait 是什么。

## 5. Mock 面试演练（Day 56）
- 让朋友/自己随机抽：3 道项目可考题 + 2 道补充八股，全程出声作答并录音。
- **追问压力测试**：每答完一题，自己再问一句"为什么/还有呢/如果…会怎样"，练扛追问。
- 回听录音，标记：卡壳处、讲超 2 分钟没重点处、没用项目实例处——这些是最后要补的。

## 6. 验收标准（毕业线）
- [ ] 3/5/10 分钟介绍脱稿，录音无"嗯/然后"，重点前置。
- [ ] 项目可考 50 题，任意抽 5 题能结合代码讲 2 分钟以上。
- [ ] 补充八股题能讲清概念，且**不硬蹭项目**。
- [ ] Mock 面试能扛住连续 3 层追问不崩。
- [ ] 能讲 2 个"我亲手发现并解决"的故事（CI 门禁 + slots 坑），有细节有数字。

---

# 附录 A：56 天每日执行表（保底 / 进阶两档）

> 使用说明：每天对照"学习内容 / 源码阅读 / 代码实现 / 练习题 / 面试问题 / 验收标准"六项执行。**保底=必做（约2h），进阶=选做。** 面试题号引用各 Phase 题库（如 P3-A1 = Phase 3 的 A 类第 1 题）。当天没做完顺延，不删减。

---

## 第 1 周：项目地图 + Python 工程起步

**Day 1 · P0 地图（目录与启动）**
- 学习：通读 README；理解双引擎分工。
- 源码：`ai_platform_api.py`、`app.py`（两个入口怎么起）。
- 实现：无（今天只读）。
- 练习：保底=画出真实目录树（对照 P0-0.2）；进阶=标注每个目录的职责一句话。
- 面试：P0-1（1 分钟讲项目）。
- 验收：能口述两个服务、端口、入口文件。

**Day 2 · P0 请求链路**
- 学习：分层 + 一次请求怎么走。
- 源码：`ai_platform/core/service.py` 的 `run()` 主链。
- 实现：无。
- 练习：保底=脱稿画 0.3 请求调用链；进阶=标注每层挂了会怎样。
- 面试：P0-2（请求经过哪些层）。
- 验收：调用链图脱稿完成。

**Day 3 · P0 测试链路 + 三张产出**
- 学习：pytest 怎么跑、fixture 怎么装配。
- 源码：`tests/conftest.py`（FakeRedis/FailingRedis）、`pytest.ini`。
- 实现：无。
- 练习：保底=画测试执行链路 + 完成模块职责表；进阶=写 200 字"FakeRedis 解决什么痛点"。
- 面试：P0-3（为什么不用真实 Redis）。
- 验收：P0 三张产出（架构图/调用链/职责表）齐，**Phase 0 通过**。

**Day 4 · P1 异常树 + dataclass**
- 学习：异常设计、dataclass。
- 源码：`ai_platform/core/exceptions.py`、`tools/executor.py`、`app/exceptions/__init__.py`（三棵异常树）。
- 实现：`learning/phase1/pykit/exceptions.py` 起骨架。
- 练习：保底=三棵异常树对比表；进阶=`raise...from` 用一处。
- 面试：P1-4（异常树怎么设计）。
- 验收：能讲三棵树各自服务谁。

**Day 5 · P1 slots 招牌坑**
- 学习：`slots`、零参 `super()`。
- 源码：`ai_platform/llm/types.py`（LLMError）。
- 实现：在 pykit 里**先复现** TypeError 再修复。
- 练习：保底=复现+修复 slots 坑并写清原因；进阶=讲清 CPython 层原因。
- 面试：P1-2、P1-3。
- 验收：能白板复现修复 slots 坑。

**Day 6 · P1 config + logging**
- 学习：config 管理、logging。
- 源码：`ai_platform/core/config.py`、`app/config/`、`observability/logger.py`。
- 实现：`pykit/config.py`（to_dict/from_dict + 环境变量覆盖）。
- 练习：保底=config 支持 env 覆盖；进阶=JSON 结构化日志带 trace_id。
- 面试：P1-7、P1-8。
- 验收：config 模块有测试且过。

**Day 7 · P1 ABC/Protocol + 装饰器/上下文**
- 学习：ABC vs Protocol、装饰器、上下文管理器。
- 源码：ABC 四处（`tools/base.py`、`llm/base.py`、`evaluation/evaluator.py`、`chaos/injector/base.py`）、Protocol 三处。
- 实现：`@retry`、`@timed` 两个装饰器。
- 练习：保底=两个装饰器可跑；进阶=写一个计时 contextmanager。
- 面试：P1-1、P1-5、P1-6。
- 验收：装饰器有测试；能讲 ABC/Protocol 取舍。

---

## 第 2 周：Python 收尾 + 架构阅读 + 测试起步

**Day 8 · P1 收尾 + mypy**
- 学习：import 机制、依赖管理、mypy。
- 源码：项目 import 结构、`requirements*.txt`。
- 实现：补全 pykit 三件套测试，`mypy --strict` 通过。
- 练习：保底=mypy 通过；进阶=制造并解一次循环 import。
- 面试：P1 全部 8 题复练。
- 验收：**Phase 1 通过**（pykit 可跑、有测试、mypy 过）。

**Day 9 · P2 分层 + Factory**
- 学习：分层架构、Factory。
- 源码：`ai_platform/core/factory.py`（9 个 create_*）。
- 实现：无。
- 练习：保底=画 factory 装配顺序图；进阶=讲"为什么集中装配"。
- 面试：P2-1、P2-2。
- 验收：能讲 Factory 解决什么。

**Day 10 · P2 Service + DI**
- 学习：DI、构造器注入。
- 源码：`ai_platform/core/service.py`（`__init__` 注入 + `run()`）。
- 实现：无。
- 练习：保底=列 Service 注入了哪些依赖；进阶=写一版不用 DI 的体会无法 mock。
- 面试：P2-3、P2-6。
- 验收：能讲 DI 与可测试性的关系。

**Day 11 · P2 config/context/lifecycle**
- 学习：配置/上下文/生命周期。
- 源码：`core/config.py`、`core/context.py`、`core/lifecycle.py`。
- 实现：无。
- 练习：保底=4 问法读三个文件；进阶=讲 context 与 trace_id 关系。
- 面试：P2-4。
- 验收：三个文件 4 问答案齐。

**Day 12 · P2 画双图**
- 学习：耦合、依赖方向。
- 源码：`ai_platform_api.py`（薄控制器）。
- 实现：class diagram + sequence diagram（脱稿）。
- 练习：保底=两张图；进阶=300 字耦合分析（一好一反例）。
- 面试：P2-5。
- 验收：双图脱稿，标真实类名。

**Day 13 · P2 验收 + 换组件实验**
- 学习：低耦合的回报。
- 源码：抽 3 个文件验证"只依赖接口"。
- 实现：用 DI 把 QualityGate 换成"永远放行"跑通。
- 练习：保底=换组件不改码实验；进阶=画替换前后依赖差异。
- 面试：P2 全部 6 题复练。
- 验收：**Phase 2 通过**。

**Day 14 · P3 起步：fixture 基础**
- 学习：fixture 概念、四种 scope。
- 源码：`tests/conftest.py` 顶部（先看 fixture 定义）。
- 实现：无。
- 练习：保底=实验 3.1（scope 次数观察）；进阶=讲 session 为何不能持可变状态。
- 面试：P3-A1、P3-A6。
- 验收：能讲四种 scope 区别。

---

## 第 3 周：Testing Engineering 主体（上）

**Day 15 · P3 conftest 层级 + autouse**
- 学习：conftest 层级、autouse。
- 源码：`tests/core_platform/test_service.py`/`test_factory.py`/`test_api.py`（autouse fixture）。
- 实现：无。
- 练习：保底=找一个 autouse fixture 讲它干嘛；进阶=conftest 根 vs 子目录可见性实验。
- 面试：P3-A2、P3-A3。
- 验收：能讲 autouse 用/不用场景。

**Day 16 · P3 FakeRedis 深读**
- 学习：Fake vs Mock。
- 源码：`tests/conftest.py` 的 FakeRedis（含 Lua `register_script`）。
- 实现：无。
- 练习：保底=实验 3.4 之"限流放行/拒绝"两个测试；进阶=讲 FakeRedis 怎么模拟 Lua。
- 面试：P3-A19、P3-E43。
- 验收：能用 FakeRedis 写限流测试。

**Day 17 · P3 FailingRedis + 故障注入测试**
- 学习：故障注入测试。
- 源码：FailingRedis（`_maybe_fail`）、`tests/integration/test_redis_integration.py`。
- 实现：无。
- 练习：保底=实验 3.4 之"Redis 故障"测试；进阶=redis marker + skip 条件讲清楚。
- 面试：P3-E44、P3-E47。
- 验收：能用 FailingRedis 测"Redis 挂了"。

**Day 18 · P3 mock 与 monkeypatch**
- 学习：mock 全家、monkeypatch。
- 源码：项目里 mock LLM 的地方（MockProvider）。
- 实现：无。
- 练习：保底=实验 3.3（patch 时间让熔断瞬跑）；进阶=side_effect 模拟"第一次失败第二次成功"。
- 面试：P3-A8、P3-B13/15/17。
- 验收：能讲 Fake vs Mock 取舍 + monkeypatch 用法。

**Day 19 · P3 parametrize + marker**
- 学习：parametrize、自定义 marker、skip/xfail。
- 源码：`pytest.ini`、`tests/core_platform/test_sec_prompt_guard.py`（参数化矩阵）。
- 实现：无。
- 练习：保底=写一个 stacked parametrize 看组合数；进阶=`xfail(strict=True)` 实验。
- 面试：P3-A9/10/11。
- 验收：能讲 9 个 marker 解决什么。

**Day 20 · P3 测试分层设计**
- 学习：测试金字塔、unit/contract/integration/e2e。
- 源码：`tests/unit/`、`tests/integration/`、`tests/e2e/` 各抽一个。
- 实现：无。
- 练习：保底=给一个"下单"功能设计三层用例；进阶=讲每层隔离手段。
- 面试：P3-C20/21/22/23。
- 验收：能讲三层各测什么、怎么隔离。

**Day 21 · P3 边界与用例设计**
- 学习：边界值/等价类、AAA 结构。
- 源码：`tests/unit/test_rate_limiter.py`（边界矩阵）。
- 实现：为评估打分函数设计一组用例。
- 练习：保底=边界矩阵用例设计；进阶=私有方法该不该测的论述。
- 面试：P3-C26/27/28/29。
- 验收：能用边界值设计一组用例。

---

## 第 4 周：Testing 主体（下）+ CI 起步

**Day 22 · P3 测试数据管理**
- 学习：黄金集、builder/工厂、惰性加载。
- 源码：`ai_platform/evaluation/dataset/`。
- 实现：无。
- 练习：保底=实验 3.7（数据集改生成器）；进阶=对比内存占用写结论。
- 面试：P3-D34、P3-D35。
- 验收：能讲测试数据怎么管。

**Day 23 · P3 flaky 治理 + minipytest 起步**
- 学习：flaky 根因与治理流程。
- 源码：无（方法论日）。
- 实现：`learning/phase3/minipytest/` 起骨架（fixture 注册 + 注入）。
- 练习：保底=实验 3.5（造一个 flaky 并治理）；进阶=三种治理方法对比笔记。
- 面试：P3-D31、P3-D32。
- 验收：能讲 flaky 治理流程 + minipytest fixture 能注入。

**Day 24 · P3 minipytest 完成 + Phase 3 验收**
- 学习：覆盖率。
- 源码：无。
- 实现：minipytest 补 runner + assertion + parametrize，跑 ≥8 测试全过。
- 练习：保底=minipytest 全绿 + 200 字对比真 pytest；进阶=实验 3.6（覆盖率驱动补测试）。
- 面试：P3 全部 50 题抽 10 复练。
- 验收：**Phase 3 通过**（minipytest 全绿、50 题达标）。

**Day 25 · P4 GitHub Actions 基础**
- 学习：jobs/steps/needs/cache。
- 源码：`.github/workflows/ci.yml`。
- 实现：无。
- 练习：保底=画 CI job 依赖图；进阶=讲每层为什么在这层。
- 面试：P4-1、P4-2。
- 验收：能脱稿画 CI 图。

**Day 26 · P4 质量门禁**
- 学习：门禁 = 脚本 + 退出码。
- 源码：`scripts/run_quality_gate.py`、`generate_evaluation_report.py`。
- 实现：无。
- 练习：保底=实验 4.1（烂报告被门禁拒）；进阶=讲新增一个阈值要改哪三处。
- 面试：P4-3。
- 验收：能讲门禁真实可拒 + 0.42 实例。

**Day 27 · P4 Mini CI**
- 学习：artifact、if 条件。
- 源码：`docker-compose.yml`。
- 实现：`learning/phase4/` mini-ci（test→gate + needs + 缓存）。
- 练习：保底=mini-ci 绿一次；进阶=实验 4.2（缓存对比）。
- 面试：P4-4、P4-6。
- 验收：mini-ci 绿一次。

**Day 28 · P4 CI 红一次 + Phase 4 验收**
- 学习：fail fast。
- 源码：无。
- 实现：改坏 mini-ci 一个测试，看 needs 短路。
- 练习：保底=CI 红一次理解 needs；进阶=实验 4.3（PR/main 双层策略 YAML）。
- 面试：P4 全部 7 题复练。
- 验收：**Phase 4 通过**。

---

## 第 5 周：CI 收尾 + Chaos/韧性

**Day 29 · P4 补强（机动/补漏）**
- 学习：回看本周薄弱项。
- 源码：补读没读懂的 CI / 门禁细节。
- 实现：补全 mini-ci 未完成项。
- 练习：保底=把 P4 七题再过一遍；进阶=实验 4.4（门禁加 --report-json）。
- 面试：抽 P4 3 题。
- 验收：P4 无短板。

**Day 30 · P5 混沌工程理念 + 注入器**
- 学习：混沌工程、故障注入。
- 源码：`chaos_service/chaos/injector/`（4 种注入器）。
- 实现：无。
- 练习：保底=讲 4 种注入器各模拟什么；进阶=实验 5.1（注入 latency 看熔断）。
- 面试：P5-1、P5-7。
- 验收：能讲混沌工程与"反向测试"。

**Day 31 · P5 熔断器状态机**
- 学习：熔断三态。
- 源码：`resilience/breaker/breaker.py`、`state.py`。
- 实现：`learning/phase5/resilience/circuit_breaker.py` 起骨架。
- 练习：保底=画状态机 + 转换条件；进阶=讲为何 HALF_OPEN。
- 面试：P5-2。
- 验收：熔断状态机脱稿。

**Day 32 · P5 限流 + Lua**
- 学习：固定/滑动窗口、Redis+Lua 原子性。
- 源码：`chaos_service/rate_limiter.py`、`lua/sliding_window.lua`、`fixed_window.lua`。
- 实现：`resilience/rate_limiter.py`（内存滑动窗口）。
- 练习：保底=实验 5.3（fixed vs sliding 临界差异）；进阶=讲 Lua 原子性。
- 面试：P5-3、P5-6。
- 验收：能讲滑动窗口原理。

**Day 33 · P5 重试 + 幂等**
- 学习：指数退避 + jitter、幂等。
- 源码：`chaos_service/retry.py`、`app/repository/idempotency_store.py`。
- 实现：`resilience/retry.py`（退避 + jitter 装饰器）。
- 练习：保底=重试装饰器可跑；进阶=实验 5.4（重试必须配幂等）。
- 面试：P5-4、P5-5。
- 验收：能讲重试+幂等配合。

**Day 34 · P5 三件套测试补全**
- 学习：韧性机制的测试设计。
- 源码：`tests/` 里熔断/限流/重试相关测试。
- 实现：补全 phase5 测试（开/关/半开；重试成功/耗尽/不可重试；限流边界）。
- 练习：保底=phase5 测试全绿；进阶=实验 5.5（slow_db 注入实验设计）。
- 面试：P5 全部 7 题抽 4。
- 验收：phase5 三件套测试全绿。

**Day 35 · P5 Phase 验收**
- 学习：四大韧性机制串联。
- 源码：回看注入器→韧性联动。
- 实现：无（收口日）。
- 练习：保底=画"故障→韧性"对照图；进阶=讲一处可改进。
- 面试：P5 全部 7 题复练。
- 验收：**Phase 5 通过**。

---

## 第 6 周：AI 质量评估（护城河）

**Day 36 · P6 LLM 测试之难 + 三流派**
- 学习：为什么 LLM 难测、Score/Judge/Regression。
- 源码：`ai_platform/evaluation/evaluator.py`（ABC）→ `engine/`。
- 实现：无。
- 练习：保底=讲三流派各适合什么；进阶=讲 LLM 测试为什么难。
- 面试：P6-1、P6-3。
- 验收：能讲三流派区别。

**Day 37 · P6 ScoreEvaluator**
- 学习：规则化指标。
- 源码：ScoreEvaluator 实现 + `evaluation/metrics/`。
- 实现：`learning/phase6/ai_eval/score_evaluator.py`（≥3 指标）。
- 练习：保底=实验 6.3（设计一个新指标）；进阶=讲指标怎么选。
- 面试：P6-1 复练。
- 验收：score_evaluator 可跑。

**Day 38 · P6 QualityGate 六阈值**
- 学习：六阈值各防什么。
- 源码：`ai_platform/evaluation/gate.py`。
- 实现：`ai_eval/gate.py`（阈值比对 + 不达标拒）。
- 练习：保底=实验 6.2（改坏指标被拦）；进阶=讲为何分项阈值而非总分。
- 面试：P6-5。
- 验收：能背六阈值含义。

**Day 39 · P6 数据集 + 报告闭环**
- 学习：黄金集、报告生成。
- 源码：`evaluation/dataset/`、`scripts/generate_evaluation_report.py`。
- 实现：`ai_eval/dataset.py`（生成器）+ `report.py`（JSON）。
- 练习：保底=实验 6.1（跑报告懂字段）；进阶=讲黄金集怎么建。
- 面试：P6-6。
- 验收：数据集→评估→门禁→报告闭环通。

**Day 40 · P6 LLM-as-Judge**
- 学习：Judge prompt、一致性风险。
- 源码：`evaluation/judges/`。
- 实现：无（用项目 Judge 即可）。
- 练习：保底=实验 6.4（Judge 打分 + 人工核对）；进阶=写"LLM-as-Judge 的坑"。
- 面试：P6-4。
- 验收：能讲 Judge 风险与缓解。

**Day 41 · P6 回归评估**
- 学习：baseline vs candidate。
- 源码：`evaluation/regression/`。
- 实现：无。
- 练习：保底=实验 6.5（构造两版跑回归）；进阶=讲回归防什么。
- 面试：P6-7、P6-8。
- 验收：能讲回归测试价值。

**Day 42 · P6 闭环收口 + Phase 验收**
- 学习：整套评估方案设计。
- 源码：回看评估全链。
- 实现：补全 phase6 测试（全过/单指标塌方/边界）。
- 练习：保底=phase6 全绿；进阶=设计一套"给某 LLM 应用"的评估方案。
- 面试：P6 全部 8 题复练，第 1 题讲 3 分钟。
- 验收：**Phase 6 通过**。

---

## 第 7 周：AI 平台（轻）+ 安全

**Day 43 · P7 Agent 编排**
- 学习：Runtime 执行循环。
- 源码：`ai_platform/agent/runtime.py`。
- 实现：无。
- 练习：保底=画 Agent 编排图；进阶=进阶 Mini Agent Loop 起骨架。
- 面试：P7-1。
- 验收：能讲一次 run 的节点顺序。

**Day 44 · P7 Workflow + Tools**
- 学习：节点编排、工具三件套。
- 源码：`workflow/engine.py` + `nodes/`、`tools/{base,registry,executor}.py`。
- 实现：无。
- 练习：保底=画 Workflow 节点流转图；进阶=讲 planner/tool/judge 分工。
- 面试：P7-2。
- 验收：三类节点讲清楚。

**Day 45 · P7 LLM Gateway + Phase 验收**
- 学习：Provider 抽象。
- 源码：`llm/{gateway,base}.py` + `providers/`。
- 实现：保底=画 Provider 抽象图；进阶=30 行 Mini Agent Loop 跑通。
- 练习：保底=三张关系图齐；进阶=换 provider 跑同一任务。
- 面试：P7-3、P7-4。
- 验收：**Phase 7 通过**（三张图脱稿）。

**Day 46 · P8 四层防御**
- 学习：纵深防御、四层职责。
- 源码：`security/guard.py`、`input_validator.py`、`permission.py`、`output_checker.py`。
- 实现：无。
- 练习：保底=画四层防御链；进阶=讲单层为何不够。
- 面试：P8-1、P8-5。
- 验收：四层各拦什么讲清楚。

**Day 47 · P8 Prompt 注入**
- 学习：直接/间接注入、越狱。
- 源码：`security/prompt_guard.py`。
- 实现：`learning/phase8/prompt_guard/patterns.py`（≥8 模式）。
- 练习：保底=实验 8.1（手工 5 种注入看哪层拦）；进阶=讲模式库 vs 单正则。
- 面试：P8-2。
- 验收：能讲注入类型。

**Day 48 · P8 注入测试矩阵**
- 学习：负向 + 正向用例、误报/漏报。
- 源码：`tests/core_platform/test_sec_prompt_guard.py`。
- 实现：`prompt_guard/guard.py` + 拦截/放行参数化测试。
- 练习：保底=≥10 拦截 + ≥5 放行测试过；进阶=实验 8.2（误报治理）。
- 面试：P8-3、P8-4、P8-6。
- 验收：注入测试矩阵跑通。

**Day 49 · P8 收口 + Phase 验收**
- 学习：间接注入难点。
- 源码：回看四层联动。
- 实现：补全 phase8，写"误报 vs 漏报"200 字。
- 练习：保底=phase8 全绿；进阶=实验 8.3/8.4（间接注入/观察模式）。
- 面试：P8 全部 6 题复练。
- 验收：**Phase 8 通过**。

---

## 第 8 周：可观测性（轻）+ 面试冲刺

**Day 50 · P9 Trace + Metrics**
- 学习：三支柱、三种 Metric。
- 源码：`observability/collector.py`、`trace.py`、`metrics.py`。
- 实现：无。
- 练习：保底=画一次请求的观测数据流图；进阶=进阶内存 Collector 30 行。
- 面试：P9-1、P9-2。
- 验收：三种 Metric 讲清楚。

**Day 51 · P9 日志 + Phase 验收**
- 学习：结构化日志、trace_id 透传。
- 源码：`observability/logger.py`、`event.py`、`app/observability/`。
- 实现：无。
- 练习：保底=找一次请求的完整 span 树；进阶=加自定义 Metric 看 Histogram。
- 面试：P9-3、P9-4。
- 验收：**Phase 9 通过**。

**Day 52 · P10 三档自我介绍**
- 学习：自我介绍结构。
- 源码：无。
- 实现：写 3/5/10 分钟逐字稿。
- 练习：保底=三版逐字稿 + 录音各一遍；进阶=砍掉所有口头禅。
- 面试：练 3 分钟版到条件反射。
- 验收：三版稿子 + 录音达标。

**Day 53 · P10 项目可考题（Python + pytest）**
- 学习：复练 P10-A（Python 10）+ P10-B（pytest 12）。
- 源码：按需回查代码。
- 实现：无。
- 练习：保底=22 题逐题结合代码答；进阶=每题自问一层"为什么"。
- 面试：P10-A1–22。
- 验收：抽 5 题能讲 2 分钟。

**Day 54 · P10 项目可考题（CI + Redis + 架构 + AI）**
- 学习：复练 P10-C/D/E/F。
- 源码：按需回查。
- 实现：无。
- 练习：保底=28 题逐题答；进阶=CI 门禁 + slots 两个故事打磨细节。
- 面试：P10-A23–50。
- 验收：抽 5 题能讲 2 分钟。

**Day 55 · P10 补充八股**
- 学习：MySQL 10 概念 + Linux 8 命令/概念 + 网络 6 + OS 4。
- 源码：无（纯八股）。
- 实现：无。
- 练习：保底=八股过一遍，每概念能讲 3 句；进阶=**练"诚实话术"**（项目没 MySQL，就说是补的基础）。
- 面试：补充八股全过。
- 验收：八股概念能讲清，不硬蹭项目。

**Day 56 · P10 Mock 面试 + 毕业**
- 学习：综合。
- 源码：无。
- 实现：无。
- 练习：保底=完整 Mock（3 项目题 + 2 八股，录音 + 3 层追问）；进阶=回听标记卡壳处补漏。
- 面试：随机抽题抗压。
- 验收：**Phase 10 通过 → 毕业**。见附录 B 总验收清单。

---

# 附录 B：毕业总验收清单（Final Sign-off）

> 全部勾上，才算把这个项目真正"变成你自己的"。逐项自测，敢打勾才打。

## B1. 项目理解（地基）
- [ ] 能脱稿画双引擎架构图，标真实目录/类名。
- [ ] 能脱稿画一次请求的完整调用链（API→Service→Runtime→Workflow→Tool/LLM→Evaluation→Gate）。
- [ ] 能脱稿画一次测试的执行链（pytest→fixture→FakeRedis/MockProvider→service→assert）。
- [ ] 随机抽 5 个项目文件，能讲清"角色/调用方/为什么这么设计/改需求动哪"（4 问法）。

## B2. Python 企业工程
- [ ] 能白板复现并修复 `LLMError` 的 slots+super 坑，讲清 CPython 原因。
- [ ] 能讲 ABC vs Protocol 并各举项目实例。
- [ ] 能讲三棵异常树的设计与粒度。
- [ ] `learning/phase1/pykit/` 三件套可跑、有测试、mypy 过。

## B3. Testing Engineering（主战场）
- [ ] 能讲 fixture 四种 scope + autouse + conftest 层级，举 `tests/conftest.py` 实例。
- [ ] 能讲 FakeRedis（含 Lua 模拟）为什么比真实 Redis / mock 更好。
- [ ] 能用 FakeRedis / FailingRedis 独立写"依赖 Redis"的测试。
- [ ] 自研 `minipytest` 跑通 fixture(scope)+runner+assertion+parametrize，≥8 测试全绿。
- [ ] 能讲 flaky 治理完整流程并举亲身经历。
- [ ] 测开 50 题全部作答，pytest/mock/分层类脱口而出。

## B4. CI/CD 与质量门禁
- [ ] 能脱稿画 CI 分阶段 job 图并讲每层用意。
- [ ] 能讲质量门禁是"真脚本 + 退出码"，举 0.42 分被门禁打回的实例。
- [ ] `learning/phase4/` mini-ci 真实跑过（绿一次、红一次）。

## B5. Chaos 与韧性
- [ ] 能脱稿画熔断器三态状态机并讲每个转换条件。
- [ ] 能讲限流（Redis+Lua 原子性）、重试（退避+jitter）、幂等的配合。
- [ ] `learning/phase5/` 三件套可跑、测试全绿。

## B6. AI 质量评估（护城河）
- [ ] 能完整讲"AI 请求 → 数据集 → 评估 → 门禁 → 报告"闭环。
- [ ] 能讲 Score / LLM-as-Judge / Regression 三流派及适用场景。
- [ ] 能背 QualityGate 六阈值各自防什么。
- [ ] `learning/phase6/` mini evaluator 闭环跑通、有测试。
- [ ] 能现场为某 LLM 应用设计一套评估方案。

## B7. AI 平台 / 安全 / 可观测
- [ ] 能画 Agent 编排、Workflow 节点流转、Provider 抽象三张图。
- [ ] 能画四层安全防御链并讲各层拦什么；会设计注入测试矩阵。
- [ ] 能讲可观测三支柱 + 三种 Metric 类型。

## B8. 面试就绪
- [ ] 3/5/10 分钟自我介绍脱稿，录音无口头禅、重点前置。
- [ ] 项目可考 50 题，任意抽 5 题能结合代码讲 2 分钟。
- [ ] 补充八股（MySQL/Linux/网络/OS）能讲清概念且**不硬蹭项目**。
- [ ] 能讲 2 个"我亲手发现并解决"的故事（CI 假门禁→真门禁、slots 坑），有细节有数字。
- [ ] Mock 面试能扛连续 3 层追问不崩。

---

# 附录 C：执行军规（贴在桌前）

1. **先读后写**：任何重写前，先读对应源码并完成 4 问，不许上来就敲。
2. **禁止复制**：所有 `learning/` 代码必须手敲；卡住 20 分钟再看答案，看完关掉再写。
3. **出声练**：面试题一律出声作答并录音，默读不算数。
4. **顺延不删减**：当天没做完就顺延，绝不为了赶进度跳过验收。
5. **周末复盘**：每周末回做本周标记的薄弱点 + 重听录音。
6. **诚实优先**：项目没有的（MySQL 等）就如实说是补的基础，被追问不硬编。
7. **两档弹性**：连续 3 天只能完成保底，说明排太满，主动砍进阶保保底。

---

# 导师寄语

这个项目的价值，不在于它用了多少技术，而在于它**本身就是一套质量工程思想的实体化**——而这恰好是你的岗位。普通候选人背"什么是熔断器"，你能打开 `breaker.py` 讲状态机；普通候选人说"我写过测试"，你能讲 574 个用例怎么分层、FakeRedis 怎么换掉真实依赖、flaky 怎么治理；普通测开讲不清"LLM 怎么测"，你能讲一整套评估门禁闭环。

这 56 天，你不是在"复习一个项目"，是在把别人的代码一寸寸变成你自己的判断力和手感。每天那 2 小时，是在为面试那一刻的脱口而出存钱。

记住两条红线：**AI 评估是你的护城河，别砍错地方；MySQL 是八股不是项目，别硬蹭。** 其余的，按部就班，一天一勾。

8 周后，附录 B 全部打勾——你就不是"做过这个项目的人"，而是"这个项目的主人"。

去吧。第一天，从画那张目录树开始。

—— 你的 Mentor
