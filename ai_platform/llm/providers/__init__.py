"""Concrete LLM providers for the gateway."""

from ai_platform.llm.providers.mock import MockProvider
from ai_platform.llm.providers.ollama_chat import OllamaChatProvider
from ai_platform.llm.providers.ollama_generate import OllamaGenerateProvider
from ai_platform.llm.providers.openai_compatible import OpenAICompatibleProvider

__all__ = [
    "MockProvider",
    "OllamaChatProvider",
    "OllamaGenerateProvider",
    "OpenAICompatibleProvider",
]
