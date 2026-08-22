# ADR-0003：密钥边界纵深防御 + 权限 policy-as-code

- 状态：已采纳（2026-08）
- 背景：LLM Gateway 持有真实 API key（DeepSeek/DashScope）；工具层有权限边界需求
- 决策人：仓库作者（个人项目）

## 背景

对标企业实践中「密钥与授权状态由受信层持有，不暴露给渲染层/调用方」的原则：
LLM 密钥只允许在 Gateway→Provider 一条路径上流动，任何日志、trace、
HTTP 响应不得出现明文；工具调用按角色最小授权。

## 决策

1. **持有面最小化**：`GatewayConfig.api_key` 用 `field(repr=False)` 排除出
   repr——密钥不进日志的第一现场。
2. **出口统一脱敏**：`ai_platform/security/redaction.py` 提供精确值 + 模式
   （sk-xxx / Bearer / api_key=xxx）双级脱敏；AI Platform 所有 HTTP 错误
   响应必经 `redact()`（`ai_platform_api._error`）。
3. **回归守护**：`tests/core_platform/test_secret_boundary.py` 模拟「上游
   异常消息嵌入密钥」的最坏情况，断言响应体被清洗。
4. **权限 policy-as-code**：`config/security_policy.yaml` 定义角色工具权限
   （analyst 只读 / operator 不可取消 / admin 不限），文件进 git 评审、
   加载期严格校验（未知键 fail-fast）、未知角色 **fail-closed**（宁拒勿漏）。
   显式传入的 config 优先于文件（显式配置不被静默覆盖）。

## 理由

- 纵深防御：第一道防线（不持有/不打印）失误时，第二道（出口脱敏）兜底；
  两道防线各有独立回归测试。
- 策略文件可审计：权限变更 = git diff + PR，历史可追溯，CI 校验防漂移。
- fail-closed 是权限系统的默认安全姿态：未知角色的请求被拒绝而非放行。

## 代价与权衡

- 角色体系目前只有单级（无 RBAC 继承/ABAC 条件），满足 demo 量级。
- 脱敏为文本级（正则 + 精确值），不做结构化字段感知——对错误消息场景够用。
- default_role 默认为空（行为中立）；启用全局默认角色属于 breaking change，
  需单独 ADR。
