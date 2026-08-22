# Chaos Demo 服务级别目标（SLO）

> 状态：已采纳（v1，2026-08）
> 关联：`prometheus_alerts.yml`（burn-rate 告警）、`quality_gate.py`（单轮压测门禁）、Grafana 大盘
> 评审：本文随仓库进 git，变更需 PR（同 ADR 流程）

## 1. 为什么需要 SLO

在此之前的告警（5xx 速率 > 0.15/s 之类）是**阈值告警**：阈值拍脑袋、与业务期望无关、
要么误报要么漏报。SLO 方法论把问题倒过来：先定义「用户可感知的良好服务」，
再由错误预算（error budget）自动推导出该什么时候告警——烧得太快就报，
慢慢烧就别烦人。

## 2. SLI 定义（可测量）

| SLI | 指标来源 | 定义 |
|---|---|---|
| 可用性 | `http_request_errors_total` / `http_requests_total` | 非 5xx 请求占比（4xx 属客户端错误，不计入服务失败） |
| 延迟合规 | `http_request_duration_seconds_bucket` | 耗时 ≤ 0.5s 的请求占比（直方图为默认桶位，0.45s 门禁值落在 0.25 与 0.5 之间，取最近桶 0.5s；对齐桶位见 §6） |

## 3. 目标与错误预算（30 天滚动窗口）

| SLO | 目标 | 错误预算 | 语义 |
|---|---|---|---|
| 可用性 | 99.9% | 0.1% 的请求可为 5xx | 30 天内约 43 分钟的全量不可动 |
| 延迟合规 | 99.0% | 1% 的请求可超 0.5s | 慢请求配额 |

## 4. 燃烧速率（burn rate）与多窗口告警

错误预算的消耗速率 = 实际错误率 / 预算错误率。以可用性为例：

- 30 天烧完全部预算的平均速率 = 1×（基准）
- **快烧**：14.4× —— 约 2 天烧完一个月预算，需要立即处理（page）
- **慢烧**：6× —— 约 5 天烧完，工作时间内排查（ticket）

采用 Google SRE 多窗口/多燃烧率（multiwindow multi-burn-rate）法：**长窗与短窗
同时越界才告警**，避免单窗抖动误报。

| 告警 | 长窗 | 短窗 | 燃烧率 | 级别 |
|---|---|---|---|---|
| `SLOAvailabilityFastBurn` | 1h | 5m | > 14.4× | page |
| `SLOAvailabilitySlowBurn` | 6h | 30m | > 6× | warning |
| `SLOLatencyFastBurn` | 1h | 5m | > 14.4× | page |
| `SLOLatencySlowBurn` | 6h | 30m | > 6× | warning |

实现见 `prometheus_alerts.yml` 的 `slo-burn-rate-recording` 与 `slo-burn-rate-alerts`
规则组（recording rule 预聚合 1h/5m/6h/30m 窗口比率，告警表达式引用录制指标）。

## 5. 与 CI 门禁的关系（两层防线的分工）

| 层 | 时机 | 工具 | 回答的问题 |
|---|---|---|---|
| 门禁（gate） | 每次提交/发版前 | `quality_gate.py`（error_rate≤0.05、p99≤450ms） | **这一版能不能发** |
| SLO（运行时） | 线上持续 | Prometheus burn-rate 告警 | **线上服务质量是否偏离承诺** |

门禁阈值（单轮压测、分钟级）比 SLO（30 天统计）**严格得多**，这是有意的：
门禁挡住回归，SLO 兜住长尾与突发。

## 6. 已知限制与后续项

- [ ] 直方图桶位与 450ms 门禁值对齐（`http_request_duration_seconds` 目前用默认桶，
      需在 `app/observability/metrics` 显式配置 buckets 含 0.45）
- [ ] 多实例聚合：当前表达式按全局 sum，扩多副本后需按 job/service 维度拆分
- [ ] 错误预算剩余量看板（Grafana 增加 budget remaining 面板）
- [ ] 预算耗尽策略（freeze 发布 vs 降级演练）——当前仅告警，不做硬约束
