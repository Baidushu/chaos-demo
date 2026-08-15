"""OutputChecker — validates agent output before returning to user.

Checks: empty output, length, sensitive keywords, safety violations.
"""

from __future__ import annotations

import re
from typing import Any

from ai_platform.security.policy import SecurityPolicy
from ai_platform.security.security_result import SecurityResult


class OutputChecker:
    def __init__(self, policy: SecurityPolicy) -> None:
        self._policy = policy

    def check(self, answer: Any) -> SecurityResult:
        if not self._policy.security_enabled or not self._policy.output_check_enabled:
            return SecurityResult.pass_(check_name="output_checker")

        text = self._extract_text(answer)
        violations: list[str] = []

        # 1. Empty output
        if self._policy.output_required and (not text or len(text.strip()) == 0):
            violations.append("output_empty")

        # 2. Length limit
        if len(text) > self._policy.max_output_length:
            violations.append(f"output_too_long: {len(text)} > {self._policy.max_output_length}")

        # 3. Sensitive keywords
        for kw in self._policy.sensitive_keywords:
            if kw.lower() in text.lower():
                violations.append(f"sensitive_keyword: {kw}")

        if violations:
            risk = "high" if self._policy.block_on_output_violation else "medium"
            return SecurityResult.block(
                risk_level=risk,
                violations=violations,
                check_name="output_checker",
                metadata={"output_length": len(text)},
            )

        return SecurityResult.pass_(
            check_name="output_checker",
            metadata={"output_length": len(text)},
        )

    @staticmethod
    def _extract_text(answer: Any) -> str:
        if answer is None:
            return ""
        if isinstance(answer, str):
            return answer
        if hasattr(answer, "__str__"):
            return str(answer)
        return ""
