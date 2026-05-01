# K8s 与轻量混沌（可选学习路径）

> **Compose、端口、CI 主路径**见 [`../docs/AI_PROJECT_CONTEXT.md`](../docs/AI_PROJECT_CONTEXT.md)；本文不重复。

与 **Docker Compose 主路径、CI 默认流程** 独立；用于本地理解 Deployment/Service、探针与简单故障脚本。

## 清单与脚本

| 文件 | 说明 |
|------|------|
| `app-redis.yaml` | `app` + `redis` 的 Deployment/Service；含 **`/live` liveness、`/ready` readiness** 示例 |
| `redis-networkpolicy.yaml` / `redis-deny-all.yaml` | 网络策略示例（是否生效依赖集群 CNI） |
| `chaos-lite.ps1` | 轻量演示：删 Pod、收紧策略、CPU 限制等（需本机 `kubectl` 可用） |

## 使用前

1. 启用 Docker Desktop 内置 Kubernetes 或任意测试集群。  
2. 将 `app-redis.yaml` 中镜像名改为你可拉取的镜像（或本地 `kind load`）。  
3. 执行方式以脚本内注释为准。

## 与 Agent 侧 chaos 的关系

- **Agent**：`tools_client` 客户端注入延迟/失败（`--chaos`）。  
- **本目录**：集群侧 Pod/网络/资源扰动。两者叙事互补，非同一套实现。
