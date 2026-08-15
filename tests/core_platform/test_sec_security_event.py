"""Tests for SecurityEvent — observability integration for security checks."""

import pytest

from ai_platform.security.security_event import SecurityEvent


class TestSecurityEventCreation:
    def test_default_event_is_pass(self):
        event = SecurityEvent()
        assert event.event_type == "security"
        assert event.passed is True
        assert event.risk_level == "none"
        assert event.violations == []

    def test_block_event_factory(self):
        event = SecurityEvent.block_event(
            check_name="prompt_guard",
            risk_level="critical",
            violations=["injection_detected"],
            trace_id="trace-123",
            metadata={"pattern": "jailbreak"},
        )
        assert event.event_type == "security.block"
        assert event.passed is False
        assert event.risk_level == "critical"
        assert event.check_name == "prompt_guard"
        assert event.trace_id == "trace-123"
        assert event.violations == ["injection_detected"]
        assert event.metadata == {"pattern": "jailbreak"}

    def test_block_event_defaults(self):
        event = SecurityEvent.block_event()
        assert event.event_type == "security.block"
        assert event.passed is False
        assert event.risk_level == "high"
        assert event.violations == []

    def test_pass_event_factory(self):
        event = SecurityEvent.pass_event(
            check_name="input_validator",
            trace_id="trace-456",
            metadata={"input_length": 50},
        )
        assert event.event_type == "security.pass"
        assert event.passed is True
        assert event.risk_level == "none"
        assert event.check_name == "input_validator"
        assert event.trace_id == "trace-456"
        assert event.metadata == {"input_length": 50}

    def test_pass_event_defaults(self):
        event = SecurityEvent.pass_event()
        assert event.event_type == "security.pass"
        assert event.passed is True
        assert event.risk_level == "none"


class TestSecurityEventSerialization:
    def test_as_dict_block_event(self):
        event = SecurityEvent.block_event(
            check_name="output_checker",
            risk_level="high",
            violations=["sensitive_keyword: password"],
            trace_id="trace-789",
        )
        d = event.as_dict()
        assert d["event_type"] == "security.block"
        assert d["passed"] is False
        assert d["risk_level"] == "high"
        assert d["check_name"] == "output_checker"
        assert d["violations"] == ["sensitive_keyword: password"]
        assert "timestamp" in d

    def test_as_dict_pass_event(self):
        event = SecurityEvent.pass_event(check_name="permission_checker")
        d = event.as_dict()
        assert d["event_type"] == "security.pass"
        assert d["passed"] is True
        assert d["risk_level"] == "none"


class TestSecurityEventTraceId:
    def test_trace_id_empty_by_default(self):
        event = SecurityEvent()
        assert isinstance(event.trace_id, str)
        # Default generates a hex string, falsy check for empty
        assert len(event.trace_id) > 0

    def test_trace_id_from_block_event(self):
        event = SecurityEvent.block_event(trace_id="specific-trace")
        assert event.trace_id == "specific-trace"


class TestSecurityEventTimestamp:
    def test_timestamp_is_recent(self):
        import time
        now = time.time()
        event = SecurityEvent()
        assert abs(event.timestamp - now) < 1.0
