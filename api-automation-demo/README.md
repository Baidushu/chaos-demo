# api-automation-demo

轻量级 **pytest + httpx + YAML 数据驱动 + Allure** 示例，与主项目 **`chaos-demo` 解耦**：用于简历上证明「接口自动化框架」基本功（fixture、数据驱动、重试、日志、CI）。

## 能力清单

| 能力 | 说明 |
|------|------|
| **Fixture** | `base_url`（session）、`http_client`（按用例选择 **MockTransport** 或真实 base） |
| **数据驱动** | `data/api_cases.yaml` → `pytest_generate_tests` 参数化 |
| **重试** | `lib/retry.py`；用例级 `retry: true`；示例 `flaky_ok_mock` 前两次 503 |
| **日志** | `lib/logging_config.py` + `LoggingHttpClient` 打印 method/path/status/耗时 |
| **Allure** | `@allure.epic/feature` + `--alluredir` 生成结果目录（**`allure-results/`** 已在仓库 `.gitignore`，勿提交） |
| **CI** | **本地/自建流水线**运行子目录 `pytest`；当前仓库默认主 CI 仅为 **`qa.yml`**，本样例不绑定发布决策主链 |

## 本地运行

在无服务（**默认 CI 模式**）下，`http_client` 使用 **mock**，不发起外网请求：

```powershell
cd api-automation-demo
python -m pip install -r requirements.txt
pytest
```

带 **Allure** 原始结果：

```powershell
pytest --alluredir=allure-results
```

对已启动的 **chaos-demo**（如 `http://127.0.0.1:5000`）做**联调**时，YAML 中 `path`/`json_body` 需与服务真实行为一致；可先把 `healthz` 案例改成不依赖 mock：

```powershell
$env:API_AUTOMATION_BASE_URL="http://127.0.0.1:5000"
cd api-automation-demo
pytest -v
```

> 联调时若断言与默认 mock 用例不一致，请**复制**用例改成「真实响应」字段，或保留 `API_AUTOMATION_BASE_URL` 为空仅用 mock 跑通 CI。

## 与主仓库关系

| 项目 | 作用 |
|------|------|
| **chaos-demo**（根目录） | 质量工程主线：韧性、压测、门禁、故障注入 |
| **本目录** | **接口自动化范式**保底： pytest 工程化样板 |

测试策略叙事见 [`../docs/TEST_STRATEGY.md`](../docs/TEST_STRATEGY.md)。
