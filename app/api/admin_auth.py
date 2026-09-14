"""管理接口鉴权：保护 `/fault/*` 与 `/chaos/*` 的**写操作**。

背景
----
`POST /fault/inject`、`POST /fault/clear(-all)`、`DELETE /fault/inject/<type>`、
`POST /chaos/experiments`、`POST /chaos/experiments/<id>/stop` 能直接改变被测系统
的行为（注入延迟/异常/丢包、起停混沌实验）。它们原先**完全没有鉴权**：任何能连到
端口的人都能让服务"假装故障"——对一个演示韧性治理的服务来说，这是最不该留的口子。

策略
----
1. 令牌来自环境变量 `CHAOS_ADMIN_TOKEN`，**不在仓库里内置默认口令**；
2. 已配置令牌 → 写操作必须带请求头 `X-Chaos-Admin-Token`，用
   `hmac.compare_digest` 做常量时间比较；缺失或错误一律 401，不回显期望值；
3. **未配置令牌** → 保持放行（本地零配置演示、历史脚本不被打断），但启动时打一条
   醒目告警：把"故障注入没鉴权"显式暴露出来，而不是静默裸奔；
4. 只保护写操作：只读的 `GET /fault/status`、`GET /chaos/experiments`、
   `GET /chaos/experiments/<id>` 保持公开，供观测面板与巡检脚本读取；
5. 守卫按**路径前缀 + 非常规方法**判定，所以将来新增的写接口默认就是被保护的
   （fail-closed），而不是默认裸奔。
"""

from __future__ import annotations

import hmac
import os

from flask import jsonify, request

#: 令牌环境变量名
ADMIN_TOKEN_ENV = "CHAOS_ADMIN_TOKEN"
#: 令牌请求头名
ADMIN_TOKEN_HEADER = "X-Chaos-Admin-Token"
#: 受保护的路径前缀
PROTECTED_PREFIXES = ("/fault", "/chaos")
#: 视为只读、不校验令牌的 HTTP 方法
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def configured_admin_token() -> str | None:
    """当前配置的管理令牌（未配置或为空白 → None）。"""
    raw = os.getenv(ADMIN_TOKEN_ENV, "")
    token = raw.strip()
    return token or None


def admin_auth_enabled() -> bool:
    """管理接口是否已启用令牌鉴权。"""
    return configured_admin_token() is not None


def admin_auth_status() -> str:
    """供报告/巡检使用的鉴权状态描述：`token` 或 `open`。"""
    return "token" if admin_auth_enabled() else "open"


def token_accepted(provided: str | None) -> bool:
    """请求头里的令牌是否被接受。

    未配置令牌时一律接受（保持旧行为）；配置后必须**常量时间**相等。
    """
    expected = configured_admin_token()
    if expected is None:
        return True
    if not provided:
        return False
    return hmac.compare_digest(provided.strip(), expected)


def is_protected_request(method: str, path: str) -> bool:
    """该请求是否属于需要鉴权的管理写操作。"""
    if method.upper() in SAFE_METHODS:
        return False
    return path.startswith(PROTECTED_PREFIXES)


def register_admin_guard(flask_app, runtime=None) -> None:
    """注册管理接口守卫，并在未配置令牌时给出启动告警。"""
    logger = getattr(flask_app, "logger", None)
    if not admin_auth_enabled() and logger is not None:
        logger.warning(
            "chaos admin API is unauthenticated: %s is not set, so POST/DELETE %s "
            "are open to anyone who can reach this port. Set %s to require the %s header.",
            ADMIN_TOKEN_ENV,
            " ".join(f"{p}/*" for p in PROTECTED_PREFIXES),
            ADMIN_TOKEN_ENV,
            ADMIN_TOKEN_HEADER,
        )

    @flask_app.before_request
    def admin_guard():
        if not is_protected_request(request.method, request.path):
            return None
        if token_accepted(request.headers.get(ADMIN_TOKEN_HEADER)):
            return None
        return (
            jsonify(
                {
                    "error": "unauthorized",
                    "detail": f"管理接口需要 {ADMIN_TOKEN_HEADER} 请求头",
                    "code": "admin_auth_required",
                }
            ),
            401,
        )
