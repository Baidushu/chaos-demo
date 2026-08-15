"""InputValidator — validates user input before agent processing.

Checks: empty input, length limits, illegal characters, blocked keywords.
"""

from __future__ import annotations

import re
from typing import Any

from ai_platform.security.policy import SecurityPolicy
from ai_platform.security.security_result import SecurityResult


class InputValidator:
    def __init__(self, policy: SecurityPolicy) -> None:
        self._policy = policy

    def validate(self, request: Any) -> SecurityResult:
        if not self._policy.security_enabled:
            return SecurityResult.pass_(check_name="input_validator")

        text = self._extract_text(request)
        violations: list[str] = []

        # 1. Empty input check
        if self._policy.min_input_length > 0 and (not text or len(text.strip()) == 0):
            violations.append("input_empty")
            return SecurityResult.block(
                risk_level="high",
                violations=violations,
                check_name="input_validator",
                metadata={"input_length": 0},
            )

        # 2. Length check
        if len(text) > self._policy.max_input_length:
            violations.append(f"input_too_long: {len(text)} > {self._policy.max_input_length}")

        if len(text) < self._policy.min_input_length:
            violations.append(f"input_too_short: {len(text)} < {self._policy.min_input_length}")

        # 3. Blocked keywords
        for kw in self._policy.blocked_keywords:
            if kw.lower() in text.lower():
                violations.append(f"blocked_keyword: {kw}")

        # 4. Blocked patterns (regex)
        for pattern in self._policy.blocked_patterns:
            try:
                if re.search(pattern, text, re.IGNORECASE):
                    violations.append(f"blocked_pattern: {pattern}")
            except re.error:
                pass

        if violations:
            risk = "high" if self._policy.block_on_input_violation else "medium"
            return SecurityResult.block(
                risk_level=risk,
                violations=violations,
                check_name="input_validator",
                metadata={"input_length": len(text)},
            )

        return SecurityResult.pass_(
            check_name="input_validator",
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
