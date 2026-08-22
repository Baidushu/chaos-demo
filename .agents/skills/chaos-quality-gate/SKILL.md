---
name: chaos-quality-gate
description: Use when running tests, benchmarks, security scans, quality gates, or demo scenarios in this chaos-demo repository — the verified command sequences, ordering, thresholds, and Windows gotchas live here.
---

# Chaos Demo 测试与质量门禁

本仓库是「轻量级质量工程平台（QEP）」：Chaos Service（Flask，:5000）是被测系统，AI Platform（FastAPI，:8000）是质量保障层。所有命令在仓库根 `D:\chaos-demo` 下、激活 `.venv` 后执行。

## 测试（无需外部服务）

```powershell
.\.venv\Scripts\Activate.ps1                    # 若禁止运行脚本：Set-ExecutionPolicy -Scope Process Bypass
python -m pytest tests/ -q -m smoke             # 冒烟，约 3 秒 —— 改动后的第一道验证
python -m pytest tests/ -q                      # 全量 656 用例，约 45 秒
python -m pytest tests/ -q -k idempotency       # 按关键字挑用例
```

- 全量跑若报 Temp `PermissionError`，加 `--basetemp=D:\chaos-demo\.pytest-tmp`。
- Redis 依赖用例标记 `redis`，无真 Redis 时自动 skip（FakeRedis 已覆盖其余）。
- 注意存在两棵 pytest 树：根 `tests/`（主工程）与 `api-automation-demo/tests/`（独立工程），别混跑。

## 质量门禁（必须先起服务）

顺序严格：起栈 → 压测 → 安全扫描 → 统一门禁 → 摘要。

```powershell
docker compose up --build -d                     # app(5000)+app_baseline(5001)+redis+prometheus+grafana
curl -s http://localhost:5000/healthz            # 确认被测系统就绪
python benchmark_compare.py                      # 压测对照 → reports/benchmark_latest.json
python security_scan.py                          # 安全扫描 → reports/security_scan_latest.json
python unified_quality_gate.py                   # 统一门禁（benchmark+security+agent_eval）
python unified_summary.py                        # 一页摘要（Gate 失败也生成）
```

要点：
- 门禁阈值：error_rate≤0.05、p99≤450ms、p95 回归倍数≤1.10、unstable≤0.35；AI 评估 6 阈值见 `ai_platform/evaluation/gate.py`。可用 `QUALITY_GATE_*` 环境变量覆盖。
- `unified_quality_gate.py` 失败即 exit 1，输出 `reports/unified_quality_gate_latest.json`（含 final_decision/reasons/checks）——定位问题先读它。
- 只关心 agent 评估时：先起 Chaos Service（`python app.py` 或 compose），`$env:AGENT_MODE="rule"`，再跑 `agent-eval/scripts/run_agent_eval.py` → `score_agent_eval.py` → `gate_agent_eval.py`；CI 用 `chaos_compare.py --strict`（无故障 vs 混故障对照）。
- 快速一键复现 CI 主链：`.\run.ps1 -Task qafull`（必须带 `-Task`，耗时数分钟，需 Docker）。

## 演示场景（不起服务可跑）

```powershell
python demo/run_demo.py all                       # 三大场景：故障诊断/安全测试/回归门禁
python demo/scenarios/incident_analysis/runner.py --llm   # 根因分析走真 LLM（需 .env 配好网关）
```

## 收尾检查

- 跑完 `docker compose down` 释放端口；`reports/*` 是生成物，不要手改。
- 改动涉及架构/新环境变量/新 CI 步骤时，同步更新根 `AGENTS.md` 与 `docs/archive/reference/AI_PROJECT_CONTEXT.md`。
- 严禁把 `.env` / `local_llm_env.ps1` 的密钥内容写进报告或发往公网模型。
