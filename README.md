# Chaos Demo — 轻量级质量工程平台

[![ci](https://github.com/Baidushu/chaos-demo/actions/workflows/ci.yml/badge.svg)](https://github.com/Baidushu/chaos-demo/actions/workflows/ci.yml)
[![qa](https://github.com/Baidushu/chaos-demo/actions/workflows/qa.yml/badge.svg)](https://github.com/Baidushu/chaos-demo/actions/workflows/qa.yml)
[![supply-chain](https://github.com/Baidushu/chaos-demo/actions/workflows/supply-chain.yml/badge.svg)](https://github.com/Baidushu/chaos-demo/actions/workflows/supply-chain.yml)

一个轻量级质量工程平台（QEP）：以**带四层韧性治理与可编程故障注入的订单服务**为被测系统，围绕它构建**测试光谱、压测对照、安全扫描、AI Agent 评估与统一质量门禁**，全部接入 CI，由门禁输出发布决策。

## 架构

```
┌─────────────────────────────┐     ┌──────────────────────────────────┐
│  Chaos Service（被测系统）    │     │  AI Platform（质量保障层，:8000） │
│  Flask :5000 · Redis        │     │  FastAPI                          │
│                             │     │                                  │
│  订单业务 + 韧性治理          │     │  Security → Agent → Workflow      │
│  限流/熔断/幂等/超时预算      │     │  → Tools → LLM → Evaluation → Gate │
│  可编程故障注入（4 类）       │     │  ──────────────────────────────── │
│  Prometheus /metrics         │     │  LLM Gateway（Mock/Ollama/OpenAI 兼容）│
└──────────────┬──────────────┘     └────────────────┬─────────────────┘
               │         Redis · Prometheus · Grafana │
               └──────────────────┬───────────────────┘
                                  ▼
              质量门禁：benchmark + security + agent_eval → PASS/FAIL
```

## 核心能力

### 被测系统：Chaos Service

- **韧性治理**：滑动/固定窗口限流（Redis ZSET + Lua 原子）、熔断器（三态 + 半开探测互斥）、幂等（`X-Idempotency-Key`，200 回放 / 202 处理中 / 409 冲突）、端到端超时预算（超时 202 降级排队）、指数退避 + jitter 重试
- **可编程故障注入**：`POST /fault/inject` 在线注册 `latency / exception / drop / slow_db` 四类故障，Redis 存储 + TTL 自动恢复
- **A/B 对照**：同镜像不同配置（5000 韧性全开 / 5001 无韧性），压测验证过载保护

### 质量保障层：AI Platform

- **Agent 执行**：Security → Agent → Workflow → Tools → LLM → Evaluation → Gate 全链路，trace_id 贯穿
- **四层安全**：输入校验 → PromptGuard（22 种注入模式）→ 工具权限（policy-as-code，未知角色 fail-closed）→ 输出检查；错误响应统一密钥脱敏
- **LLM Gateway**：Mock（确定性）/ Ollama / OpenAI 兼容（DeepSeek、DashScope）四类 Provider，类型化错误分类

### 测试光谱

| 层 | 手段 | 规模 |
|---|---|---|
| 场景测试 | pytest 分层（9 类 marker，FakeRedis 零外部依赖） | 70 文件 / 722 用例 |
| 属性测试 | hypothesis 状态机（熔断器/限流器不变量） | 全量 57s 确定性 |
| 契约测试 | OpenAPI 契约先行 + schemathesis 负向 fuzz | 曾发现 2 个真实参数校验缺陷 |
| 变异测试 | mutmut（夜间 CI） | 609 变异体 / 62.3% 得分 |

### 质量门禁与 SRE

- **统一门禁**：benchmark（error_rate / p99 / p95 回归倍数）+ security（上下文感知 SQLi 扫描）+ agent_eval（6 阈值），任一失败 exit 1
- **SLO**：可用性 99.9% / 延迟合规 99%，30 天错误预算；多窗口燃烧率告警（快烧 14.4× page / 慢烧 6× warning，双窗同越界才告警）
- **供应链安全**：pip-audit 依赖审计、CycloneDX SBOM、Trivy 漏洞/密钥扫描

## 快速开始

```powershell
# 完整栈（app + app_baseline + redis + prometheus + grafana）
docker compose up --build -d

# 被测系统验证
curl http://localhost:5000/healthz
curl -X POST http://localhost:5000/order -H "Content-Type: application/json" -d "{\"item_id\":\"sku-1\",\"quantity\":1}"

# AI 平台（本地运行）
pip install -r requirements.txt -r requirements-ai.txt
uvicorn ai_platform_api:app --port 8000
curl -X POST http://localhost:8000/api/v1/agent/run -H "Content-Type: application/json" -d "{\"request\":\"诊断 Redis 连接池耗尽问题\",\"mode\":\"rule\"}"
```

> Grafana: http://localhost:3000（admin/admin123）· Prometheus: http://localhost:9090

## 测试

```powershell
python -m pytest tests/ -q -m smoke    # 冒烟 5 个，约 3 秒
python -m pytest tests/ -q             # 全量 720 passed + 2 skipped，约 57 秒
python -m pytest tests/ -q -k idempotency
```

质量门禁（需先起服务）：

```powershell
python benchmark_compare.py            # A/B 压测对照
python security_scan.py                # SQLi 安全扫描
python unified_quality_gate.py         # 统一门禁 → reports/unified_quality_gate_latest.json
python unified_summary.py              # 一页摘要
```

Agent 评估（需 Chaos Service 运行）：

```powershell
python agent-eval/scripts/run_agent_eval.py
python agent-eval/scripts/score_agent_eval.py
python agent-eval/scripts/gate_agent_eval.py
python agent-eval/scripts/chaos_compare.py --strict   # 无故障 vs 混故障对照
```

## CI/CD

| 工作流 | 职责 |
|---|---|
| `ci.yml` | lint + 类型检查 + 测试 + Docker 构建 |
| `qa.yml` | 压测 → 安全扫描 → 混沌对照 → 统一门禁 → 摘要（覆盖率门槛 85%） |
| `ai-quality.yml` | AI 评估门禁，Quality Gate 未通过阻塞 PR |
| `supply-chain.yml` | pip-audit / SBOM / Trivy；夜间 mutmut 变异测试 |

## 技术栈

| 层 | 技术 |
|---|---|
| 语言/运行时 | Python 3.11+（本地 3.14，Docker 3.9） |
| 被测系统 | Flask + Redis + gunicorn + prometheus-client |
| 质量保障层 | FastAPI + pydantic v2 + uvicorn |
| LLM | DeepSeek / DashScope / Ollama（OpenAI 兼容协议） |
| 测试 | pytest、hypothesis、schemathesis、mutmut、locust、allure |
| 基础设施 | Docker Compose、Grafana、Prometheus、Lua |

## 目录结构

```
chaos-demo/
├── app/              # 订单业务分层（api/service/repository/infrastructure）
├── chaos_service/    # 被测系统：韧性治理 + 故障注入 + 流量录制
├── ai_platform/      # 质量保障层：agent/workflow/tools/llm/security/evaluation/observability
├── agent-eval/       # Agent 评估辅线（78 条四维数据集 + 混沌对照）
├── demo/             # 三大演示场景（故障诊断/安全测试/回归门禁）
├── tests/            # 主 pytest 树（unit/integration/contract/e2e/demo/deployment）
├── lua/              # 限流 Lua 脚本
├── k8s/              # 可选 K8s 清单
└── .github/workflows/  # 4 条 CI 流水线
```

## 边界与限制

- 单机教学量级：压测为单机短连接，无真实流量
- 故障注入为应用内协作式模拟，不等价网络层 `tc` / 杀 Pod
- 存储仅 Redis（MySQL 仅为 compose 占位）
- agent-eval 为小样本辅线（78 条），评测机制与行业 golden set 同构
