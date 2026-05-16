"""仓库根 conftest：让任意路径下的 pytest 文件（如 reports/ 中的 LLM 生成草稿）复用 tests 里的夹具。

tests/conftest 内含 app_state、client 等；子目录单独放 conftest 时默认不会加载 tests/conftest。
"""
pytest_plugins = ["tests.conftest"]
