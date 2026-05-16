# 使用方式（只做一次）：
#   1. 复制本文件：  Copy-Item local_llm_env.example.ps1 local_llm_env.ps1
#   2. 编辑 local_llm_env.ps1，把下面 sk- 换成你的 DashScope API Key
#   3. local_llm_env.ps1 已在 .gitignore，不要提交到 git
#
# 生效方式：
#   - 运行 .\run.ps1 任意 Task 时会自动加载同目录下的 local_llm_env.ps1（若存在）
#   - 若直接运行 python llm_assist.py，请先执行：  . .\local_llm_env.ps1

$env:LLM_BACKEND = "openai"
$env:LLM_API_KEY = "sk-请替换"
# 可选：轻量模型（以控制台实际可用名为准）
# $env:LLM_MODEL = "qwen-turbo"
# 可选：网络慢或长 prompt（如 contract-audit）时加大（秒），默认脚本内为 120
# $env:LLM_TIMEOUT_SEC = "180"
