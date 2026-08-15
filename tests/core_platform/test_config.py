"""Tests for platform configuration."""

import pytest

from ai_platform.core.config import (
    EvaluationConfig,
    ModelConfig,
    PlatformConfig,
)
from ai_platform.security.policy import SecurityPolicy


class TestModelConfig:
    def test_defaults(self):
        c = ModelConfig()
        assert c.provider == "mock"
        assert c.model == "default"
        assert c.temperature == 0.1
        assert c.max_tokens == 2048
        assert c.timeout_seconds == 30.0

    def test_custom(self):
        c = ModelConfig(
            provider="ollama", model="llama3", temperature=0.7,
            max_tokens=1024, timeout_seconds=15.0,
        )
        assert c.provider == "ollama"
        assert c.model == "llama3"
        assert c.timeout_seconds == 15.0

    def test_to_dict(self):
        c = ModelConfig(provider="ollama")
        d = c.to_dict()
        assert d["provider"] == "ollama"
        assert "model" in d

    def test_from_dict(self):
        c = ModelConfig.from_dict({"provider": "openai", "model": "gpt-4", "timeout_seconds": 45.0})
        assert c.provider == "openai"
        assert c.timeout_seconds == 45.0

    def test_from_dict_missing_keys(self):
        c = ModelConfig.from_dict({})
        assert c.provider == "mock"


class TestEvaluationConfig:
    def test_defaults(self):
        c = EvaluationConfig()
        assert c.tool_selection_accuracy_min == 0.7
        assert c.arg_accuracy_min == 0.7
        assert c.retry_rate_max == 0.3

    def test_to_dict_roundtrip(self):
        c = EvaluationConfig(tool_selection_accuracy_min=0.85)
        d = c.to_dict()
        restored = EvaluationConfig.from_dict(d)
        assert restored.tool_selection_accuracy_min == 0.85

    def test_from_dict_missing_keys(self):
        c = EvaluationConfig.from_dict({})
        assert c.arg_accuracy_min == 0.7


class TestPlatformConfig:
    def test_defaults(self):
        c = PlatformConfig.default()
        assert c.mode == "rule"
        assert c.observability_enabled is True
        assert c.timeout_seconds == 60.0

    def test_custom_security(self):
        policy = SecurityPolicy(max_input_length=500)
        c = PlatformConfig(security=policy)
        assert c.security.max_input_length == 500

    def test_to_dict(self):
        c = PlatformConfig(mode="ollama")
        d = c.to_dict()
        assert d["mode"] == "ollama"
        assert "model" in d

    def test_from_dict(self):
        d = {"mode": "ollama", "model": {"provider": "ollama"}, "timeout_seconds": 120.0}
        c = PlatformConfig.from_dict(d)
        assert c.mode == "ollama"
        assert c.timeout_seconds == 120.0

    def test_from_dict_missing_keys(self):
        c = PlatformConfig.from_dict({})
        assert c.mode == "rule"
