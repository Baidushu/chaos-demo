import json
from unittest.mock import MagicMock, patch

import pytest

from llm_client import LLMClient


def test_detect_backend_no_ollama_no_key():
    """没有 Ollama 也没有 API key 时报错。"""
    with patch.object(LLMClient, "_check_ollama", return_value=False):
        with pytest.raises(ValueError, match="No LLM backend available"):
            LLMClient(backend="auto")


def test_detect_backend_ollama_available():
    """Ollama 可用时自动选择 ollama。"""
    with patch.object(LLMClient, "_check_ollama", return_value=True):
        client = LLMClient(backend="auto")
        assert client.backend == "ollama"
        assert client.model == "qwen2.5:7b"


def test_detect_backend_cloud_with_key():
    """有 API key 时选择 openai 兼容后端。"""
    with patch.object(LLMClient, "_check_ollama", return_value=False):
        client = LLMClient(backend="auto", api_key="test-key")
        assert client.backend == "openai"


def test_explicit_ollama_backend():
    """显式指定 ollama 后端。"""
    client = LLMClient(backend="ollama")
    assert client.backend == "ollama"


def test_explicit_openai_backend_needs_key():
    """显式 openai 后端但没有 key 时报错。"""
    with pytest.raises(ValueError, match="LLM_API_KEY is required"):
        LLMClient(backend="openai", api_key="")


def test_explicit_openai_backend_with_key():
    """显式 openai 后端有 key 时正常初始化。"""
    client = LLMClient(backend="openai", api_key="sk-test")
    assert client.backend == "openai"


def test_custom_model():
    """自定义模型名。"""
    client = LLMClient(backend="ollama", model="llama3:8b")
    assert client.model == "llama3:8b"


def test_chat_ollama_mock():
    """mock Ollama 调用。"""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "message": {"content": "hello from ollama"}
    }).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    client = LLMClient(backend="ollama")
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = client.chat("test prompt")
    assert result == "hello from ollama"


def test_chat_openai_mock():
    """mock OpenAI 兼容 API 调用。"""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "choices": [{"message": {"content": "hello from cloud"}}]
    }).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    client = LLMClient(backend="openai", api_key="sk-test")
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = client.chat("test prompt")
    assert result == "hello from cloud"


def test_chat_json_extracts_json_block():
    """从 markdown 代码块中提取 JSON。"""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "message": {"content": '```json\n{"key": "value"}\n```'}
    }).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    client = LLMClient(backend="ollama")
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = client.chat_json("test")
    assert result == {"key": "value"}


def test_chat_json_extracts_raw_json():
    """从纯文本中提取 JSON。"""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "message": {"content": 'Here is the result: [{"id": 1}] done.'}
    }).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    client = LLMClient(backend="ollama")
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = client.chat_json("test")
    assert result == [{"id": 1}]


def test_chat_with_system_prompt():
    """验证 system prompt 传递。"""
    captured = {}

    def mock_urlopen(req, timeout=30):
        body = json.loads(req.data.decode())
        captured["messages"] = body["messages"]
        resp = MagicMock()
        resp.read.return_value = json.dumps({
            "message": {"content": "ok"}
        }).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    client = LLMClient(backend="ollama")
    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        client.chat("user msg", system="system msg")

    assert captured["messages"][0]["role"] == "system"
    assert captured["messages"][0]["content"] == "system msg"
    assert captured["messages"][1]["role"] == "user"
