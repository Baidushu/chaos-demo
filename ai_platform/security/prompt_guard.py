"""PromptGuard — detects prompt injection attempts.

First version: rule-based pattern matching.
Detects common injection phrases: system prompt override, jailbreak, etc.
"""

from __future__ import annotations

import re
from typing import Any

from ai_platform.security.policy import SecurityPolicy
from ai_platform.security.security_result import SecurityResult


class PromptGuard:
    def __init__(self, policy: SecurityPolicy) -> None:
        self._policy = policy

    def check(self, request: Any) -> SecurityResult:
        if not self._policy.security_enabled or not self._policy.prompt_injection_enabled:
            return SecurityResult.pass_(check_name="prompt_guard")

        text = self._extract_text(request)
        violations: list[str] = []
        matched: list[str] = []

        for pattern in self._policy.prompt_injection_patterns:
            if pattern.lower() in text.lower():
                matched.append(pattern)

        if matched:
            violations.append(f"prompt_injection_detected: {len(matched)} pattern(s) matched")
            return SecurityResult.block(
                risk_level="critical",
                violations=violations,
                check_name="prompt_guard",
                metadata={
                    "matched_patterns": matched,
                    "input_length": len(text),
                },
            )

        return SecurityResult.pass_(
            check_name="prompt_guard",
            metadata={"input_length": len(text)},
        )

    @staticmethod
    def _extract_text(request: Any) -> str:
        if isinstance(request, str):
            return request
        if isinstance(request, dict):
            return str(request.get("input", request.get("content", "")))
        if request is None:
            return ""
        return str(request)
