"""轻量 LLM 客户端 — 支持 Ollama 本地模型和 OpenAI 兼容 API（通义千问/DeepSeek 等免费额度）。

用法：
    from llm_client import LLMClient

    client = LLMClient()  # 自动选择可用的后端
    response = client.chat("生成测试用例")

环境变量：
    LLM_BACKEND: ollama | openai（默认 auto：优先 ollama，其次 openai）
    LLM_API_KEY: 云端 API Key（openai 后端必填）
    LLM_BASE_URL: 云端 API 地址（默认 https://dashscope.aliyuncs.com/compatible-mode/v1）
    LLM_MODEL: 模型名（ollama 默认 qwen2.5:7b，openai 默认 qwen-plus）
    LLM_TIMEOUT_SEC: 请求超时（默认 30）
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class LLMClient:
    """统一的 LLM 调用接口。"""

    def __init__(
        self,
        backend: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_sec: int | None = None,
    ):
        self._timeout = timeout_sec or int(os.getenv("LLM_TIMEOUT_SEC", "30"))
        self._backend = backend or os.getenv("LLM_BACKEND", "auto")
        self._api_key = api_key or os.getenv("LLM_API_KEY", "")
        self._base_url = base_url or os.getenv("LLM_BASE_URL", "")
        self._model = model or ""

        if self._backend == "auto":
            self._backend = self._detect_backend()

        if self._backend == "ollama":
            self._model = self._model or os.getenv("LLM_MODEL", "qwen2.5:7b")
            self._base_url = self._base_url or os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434")
        else:
            self._model = self._model or os.getenv("LLM_MODEL", "qwen-plus")
            if not self._base_url:
                self._base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            if not self._api_key:
                raise ValueError(
                    "LLM_API_KEY is required for cloud backend. "
                    "Get a free key from https://dashscope.console.aliyun.com/ "
                    "or set LLM_BACKEND=ollama for local model."
                )

    def _detect_backend(self) -> str:
        """自动检测可用后端：优先 Ollama，其次云端。"""
        if self._check_ollama():
            return "ollama"
        if self._api_key:
            return "openai"
        raise ValueError(
            "No LLM backend available. Either:\n"
            "  1. Start Ollama: ollama serve && ollama pull qwen2.5:7b\n"
            "  2. Set LLM_API_KEY for cloud API (Qwen/DeepSeek)"
        )

    def _check_ollama(self) -> bool:
        """检查 Ollama 是否在运行。"""
        try:
            url = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434")
            req = urllib.request.Request(f"{url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.getcode() == 200
        except Exception:
            return False

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def model(self) -> str:
        return self._model

    def chat(self, prompt: str, system: str = "", max_tokens: int = 2000) -> str:
        """发送对话请求，返回文本响应。"""
        if self._backend == "ollama":
            return self._chat_ollama(prompt, system)
        return self._chat_openai(prompt, system, max_tokens)

    def chat_json(self, prompt: str, system: str = "", max_tokens: int = 2000) -> dict | list:
        """发送对话请求，解析 JSON 响应。"""
        text = self.chat(prompt, system, max_tokens)
        # 提取 JSON 块
        import re
        m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
        else:
            m = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
            if m:
                text = m.group(1)
        return json.loads(text)

    def _chat_ollama(self, prompt: str, system: str) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = json.dumps({
            "model": self._model,
            "messages": messages,
            "stream": False,
        }).encode("utf-8")

        url = f"{self._base_url}/api/chat"
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("message", {}).get("content", "")

    def _chat_openai(self, prompt: str, system: str, max_tokens: int) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = json.dumps({
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
        }).encode("utf-8")

        url = f"{self._base_url}/chat/completions"
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self._api_key}")

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"LLM API error {e.code}: {body}") from e
