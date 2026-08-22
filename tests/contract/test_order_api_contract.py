"""订单 API 契约测试（schemathesis，基于 OpenAPI 3.0 属性生成）。

契约文件：``tests/contract/openapi_order_api.yaml``（随仓库评审，契约先行）。

运行方式：进程内 WSGI——schema 通过 ``schemathesis.openapi.from_wsgi`` 加载，
用一个挂载 /openapi.json 的轻量 WSGI 包装器包住 Flask 应用；请求经
schemathesis 生成的随机/负向用例直接打到 app（不起服务、不占端口），
依赖状态用 conftest 的 FakeRedis（app_state fixture）。

验证的行为面：
- 生成的合法请求不得命中未声明状态码（status_code conformance）；
- 非法数据（缺 item_id / quantity 越界）必须被 4xx 拒绝（negative data
  rejection）——防注入面与参数校验的契约化；
- 所有 JSON 端点必须回 application/json（content type conformance）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import schemathesis
import yaml

import app as app_module

_SPEC_PATH = Path(__file__).resolve().parent / "openapi_order_api.yaml"
_SCHEMA_PATH = "/openapi.json"


class _SchemaMountingWSGI:
    """在 /openapi.json 处挂载契约文件，其余请求透传给 Flask 应用。"""

    def __init__(self, inner_app, schema_bytes: bytes, schema_path: str) -> None:
        self._inner = inner_app
        self._schema_bytes = schema_bytes
        self._schema_path = schema_path

    def __call__(self, environ, start_response):
        if environ.get("PATH_INFO") == self._schema_path:
            body = self._schema_bytes
            start_response(
                "200 OK",
                [
                    ("Content-Type", "application/json"),
                    ("Content-Length", str(len(body))),
                ],
            )
            return [body]
        return self._inner(environ, start_response)


def _build_schema():
    spec = yaml.safe_load(_SPEC_PATH.read_text(encoding="utf-8"))
    wsgi_app = _SchemaMountingWSGI(
        app_module.app,
        json.dumps(spec).encode("utf-8"),
        _SCHEMA_PATH,
    )
    return schemathesis.openapi.from_wsgi(_SCHEMA_PATH, wsgi_app)


schema = _build_schema()


@pytest.fixture(autouse=True)
def _isolated_runtime(app_state):
    """FakeRedis + 测试配置隔离（app_state 完成替换与恢复）。"""
    yield


@pytest.mark.contract
@schema.parametrize()
def test_order_api_contract(case):
    """契约属性测试：合法请求符合声明响应，非法数据被 4xx 拒绝。"""
    case.call_and_validate()
