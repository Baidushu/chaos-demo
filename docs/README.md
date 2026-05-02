# 文档地图（人类读者入口）

> **技术事实（接口、环境变量、韧性、CI、实现细节）**  
> 只读 **[`AI_PROJECT_CONTEXT.md`](AI_PROJECT_CONTEXT.md)** 即可，**不要求**为日常开发再通读本页下列全部文件。

本页回答：**还有别的 md 时该打开哪篇**，以及**如何避免和全景文重复维护**。

---

## 文档分层（维护规则）

| 层 | 文件 | 职责 |
|----|--------|------|
| **0. 事实源** | [`AI_PROJECT_CONTEXT.md`](AI_PROJECT_CONTEXT.md) | 与代码/compose/CI 一致时**以本篇为准**；改主干行为、变量、流水线步骤时**必须更新本篇** |
| **0b. 面试口径** | [`TEST_STRATEGY.md`](TEST_STRATEGY.md)、[`PERFORMANCE_ANALYSIS.md`](PERFORMANCE_ANALYSIS.md) | 测试分层、failure model、压测结论表述；**不**替代 §0 的技术事实 |
| **1. 跑通** | 根目录 [`README.md`](../README.md)、[`run/GUIDE.md`](run/GUIDE.md) | 命令、端口、排障；**不**重复技术细节表 |
| **2. 子模块** | [`agent-eval/README.md`](../agent-eval/README.md) | **辅线**：工具调用稳定性评估与 `CHAOS_*`；**勿**当作「AI 主项目」讲 |
| **2b. 接口自动化样例** | [`api-automation-demo/README.md`](../api-automation-demo/README.md) | pytest + httpx + YAML + Allure + CI，与主服务解耦 |
| **3. 可选** | 面试/深挖/待办/个人，见下表 | 叙述与模板，**不**复制 §0 的变量表与 API 全表 |

**禁止**：在多篇 md 里重复维护「全量环境变量表」「全量 API 表」；应写「见 `AI_PROJECT_CONTEXT` §x」。

---

## 按需求跳转（一屏内）

| 需求 | 文档 |
|------|------|
| **零基础测开**：按天/周可执行的学习计划 | [`LEARNING_PLAN_0BASIS_SDET.md`](LEARNING_PLAN_0BASIS_SDET.md) |
| **从 0 吃透本项目**：读码顺序、学习方法、合格标准 | [`PROJECT_MASTERY_FROM_ZERO.md`](PROJECT_MASTERY_FROM_ZERO.md) |
| **吃透打卡版**：每天看什么、做多少、怎么验收 | [`PROJECT_MASTERY_DAILY_CHECKLIST.md`](PROJECT_MASTERY_DAILY_CHECKLIST.md) |
| **同一项目的三种讲法**：测开版 / 后端版 / BIOS-CI版 | [`PROJECT_POSITIONING_THREE_VERSIONS.md`](PROJECT_POSITIONING_THREE_VERSIONS.md) |
| **测试分层 / failure model（面试）** | [`TEST_STRATEGY.md`](TEST_STRATEGY.md) |
| **压测行为与 trade-off（面试）** | [`PERFORMANCE_ANALYSIS.md`](PERFORMANCE_ANALYSIS.md) |
| **HTTP 故障注入、LLM 辅助** | [`AI_PROJECT_CONTEXT.md`](AI_PROJECT_CONTEXT.md) §4～§6、`fault_demo.py`、`llm_assist.py` |
| **接口自动化框架样例** | [`api-automation-demo/README.md`](../api-automation-demo/README.md) |
| **文件/目录** 速查表（不展开语义） | [`intro/PROJECT_INTRO_FOR_READERS.md`](intro/PROJECT_INTRO_FOR_READERS.md) |
| **面试/答辩** 简历、讲稿、压测样例 | [`interview/INTERVIEW_PREP.md`](interview/INTERVIEW_PREP.md) |
| **原理与题库**（长文） | [`intro/DEEP_DIVE.md`](intro/DEEP_DIVE.md) |
| **Agent 诚实边界、理想路线图** | [`plan/AGENT_EVAL_PLAN.md`](plan/AGENT_EVAL_PLAN.md) §2 为主；脚本入口见 `agent-eval/README` |
| **工程债/已解决** 表格 | [`plan/OPTIMIZATION_BACKLOG.md`](plan/OPTIMIZATION_BACKLOG.md) |
| **个人练习** 空白模板 | [`personal/MY_LEARNING_LOG.md`](personal/MY_LEARNING_LOG.md) |
| **可选 K8s** | [`k8s/CHAOS_LITE.md`](../k8s/CHAOS_LITE.md) |

**推荐阅读顺序（省时间）**：根 `README` → `run/GUIDE` 跑通 → 需要时只读 `AI_PROJECT_CONTEXT` 对应章节 → 面试前再打开 `INTERVIEW_PREP` / `DEEP_DIVE`。

---

## 仓库内所有 Markdown 清单

| 路径 | 说明 |
|------|------|
| `README.md` | 根入口：快速命令与链接 |
| `docs/AI_PROJECT_CONTEXT.md` | **SSOT 技术全景** |
| `docs/README.md` | 本页：导航与分层规则 |
| `docs/LEARNING_PLAN_0BASIS_SDET.md` | 零基础测开学习路线（阶段 + 自测） |
| `docs/PROJECT_MASTERY_FROM_ZERO.md` | 从 0 吃透本项目的学习路线与合格标准 |
| `docs/PROJECT_MASTERY_DAILY_CHECKLIST.md` | 每日打卡版学习计划（量化工作量） |
| `docs/PROJECT_POSITIONING_THREE_VERSIONS.md` | 同一个项目面对不同岗位的叙事版本 |
| `docs/run/GUIDE.md` | 运行与排查 |
| `docs/intro/PROJECT_INTRO_FOR_READERS.md` | 结构速查（短） |
| `docs/intro/DEEP_DIVE.md` | 深挖与面试题库 |
| `docs/interview/INTERVIEW_PREP.md` | 简历与样例 |
| `docs/plan/AGENT_EVAL_PLAN.md` | Agent 规划与边界 |
| `docs/plan/OPTIMIZATION_BACKLOG.md` | 优化待办/已解决 |
| `docs/personal/MY_LEARNING_LOG.md` | 个人日志模板 |
| `docs/TEST_STRATEGY.md` | 测试分层、覆盖模型、failure model、覆盖率方法论 |
| `docs/PERFORMANCE_ANALYSIS.md` | 熔断 / 限流算法 / 超时保护的面试口径 |
| `agent-eval/README.md` | 辅线：工具调用稳定性评测脚本 |
| `api-automation-demo/README.md` | pytest + httpx + YAML + Allure 样例与 CI |
| `k8s/CHAOS_LITE.md` | 可选 K8s 与混沌说明 |

*若新增长文，先判断能否只扩写 `AI_PROJECT_CONTEXT` 或只加链接行，避免再拆一本「第三套事实」。*
