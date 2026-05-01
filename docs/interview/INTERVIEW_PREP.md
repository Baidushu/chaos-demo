# 面试材料：简历、讲稿、模板与压测样例

合并原 `RESUME_PITCH.md`、`FAULT_BEFORE_AFTER_TEMPLATE.md`、`BENCHMARK_REPORT.md`，便于一处维护。

> **文档分层**：简历与样例数字以**你本机复跑**为准；技术事实（命令、变量、CI）以 [`../AI_PROJECT_CONTEXT.md`](../AI_PROJECT_CONTEXT.md) 为准，**勿**在本篇维护第二套「权威表」。  
> 深挖原理见 [`../intro/DEEP_DIVE.md`](../intro/DEEP_DIVE.md)。

---

## 1. 简历项目描述（可直接改写）

**服务侧（chaos-demo）**

- 设计并实现订单服务稳定性治理方案，引入限流、超时保护、熔断与降级机制，在压测场景下将系统尾延迟从 P99 `378.6ms` 优化至 `304.5ms`（见本文 **§4 样例**；面试请用自己复跑的中位数）。  
- 构建基线/治理双实例对照实验（`ENABLE_RESILIENCE` 开关），输出 QPS、P95/P99、错误率与降级率，形成可复现的性能对比报告。  
- 引入 Redis 实现幂等控制（`X-Idempotency-Key`）；健康检查区分 `/live`/`/ready`/`/healthz`；Prometheus 指标与 Grafana 看板。  
- 轻量安全扫描（`security_scan.py`），支持上下文感知分级、CI 重试与健康检查；统一门禁 `quality_gate.py`。  
- 流量录制与回放（`TRAFFIC_RECORD_ENABLED` + `replay_traffic.py`），带基础脱敏与统计报告。  
- Docker Compose 编排；`pytest` 分层标记（`smoke`/`contract`）；GitHub Actions 先 smoke 再全量 pytest，再接压测与门禁。  
- **（可选）** `k8s/` 最小清单与探针示例，与 Compose 主路径独立。

**Agent 测开（agent-eval）**

- 工具调用评测流水线：规则规划/Ollama、`chaos_compare` 对照、Token 与重试税门禁、`--strict` 接 CI。  
- `eval_variance` 多轮波动；`eval_config.yaml` 配置化 gate；详见 [`../../agent-eval/README.md`](../../agent-eval/README.md)。

---

## 2. 三分钟项目讲稿（面试版）

1. 项目分两层：下层订单服务稳定性与质量门禁，上层 Agent 工具调用与故障下行为评测。  
2. 服务侧基线/治理 A/B，限流（含滑动窗口）、熔断（含半开）、压测 JSON + 门禁。  
3. Agent 侧数据集驱动 + `--chaos` 对照 + token 门禁。  
4. 价值：可复现、可量化、可拦截；追问落到 `reports/`、`agent-eval/reports/` 与脚本路径。  
5. 故障前后填空见 **§3**；压测数字见 **§4**（务必复跑更新）。

---

## 3. 故障注入前后对比（填空模板）

跑完对照后，把 `agent-eval/reports/chaos_compare_latest.md`（或同名 JSON）里的数填到下面。

### 3.1 一句话结论（30 秒）

> 在 **混合故障**（`mixed` chaos：延迟 + 随机失败）下，本 Agent 的 **重试率从 ___% 升到 ___%**，**平均每任务 token 从 ___ 升到 ___**（增幅约 ___%），与门禁 **`CHAOS_TOKEN_SURGE_MAX`**、**`CHAOS_RETRY_TAX_MAX`**（见 `agent-eval/README.md`）对比……

（若 `--strict` 未通过，写清失败项与改进计划比硬吹更可信。）

### 3.2 实验设定

| 项目 | 填写 |
|------|------|
| 数据集 | `agent-eval/datasets/tool_eval.jsonl` |
| Agent | `AGENT_MODE=___` |
| 工具后端 | `TOOLS_BASE_URL` |
| 基线 / 故障轮 | `none` / `mixed` |
| 门禁 | `gate_agent_eval.py`；对照 `chaos_compare.py --strict` |

### 3.3 指标填空

| 指标 | 无故障 | 混合故障 | 备注 |
|------|--------|----------|------|
| Retry Rate | | | |
| Avg Token/Task | | | |
| token_surge_ratio | — | — | 见报告 Token black hole gate |
| chaos_retry_tax_ratio | — | — | 有重试样本时 |

### 3.4 多次运行波动（可选）

若已跑 `eval_variance.py` / `.\run.ps1 -Task agentvariance`，从 `eval_variance_latest.md` 摘 `mean`/`min`/`max`/`stdev` 说明非单次偶然。

### 3.5 相关产物路径

- `agent-eval/reports/chaos_compare_latest.*`  
- `agent-eval/reports/eval_variance_latest.*`  
- `reports/security_scan_latest.*`、`reports/traffic_replay_latest.*`  
- `agent-eval/README.md`

---

## 4. 压测结果样例（需自行复跑更新）

生成方式：

```bash
docker compose up --build -d
python benchmark_compare.py
```

**某次运行快照（仅作格式参考）：**

| Scenario | QPS | P95(ms) | P99(ms) | Success | Degraded | Limited | Error |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline (no resilience) | 59.0 | 356.0 | 378.6 | 98.5% | 0.0% | 0.0% | 1.5% |
| Protected (resilience on) | 76.6 | 295.5 | 304.5 | 83.5% | 13.0% | 0.0% | 3.5% |

**Raw 状态计数（同一次运行）：**

- Baseline: `{201: 197, 503: 3}`  
- Protected: `{201: 167, 202: 26, 503: 7}`

**说明**：治理版故意将部分流量降为 `202`（queued）以换尾延迟；与基线对比吞吐与 P99 改善需结合多次复跑取中位数。面试请说「我本地复跑 N 次后的典型区间」。

---

*数值与阈值以当前代码、`eval_config.yaml` 及你本机报告为准。*
