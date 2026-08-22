"""Guard — unified security orchestrator.

Runs all security checks in order:
  InputValidator → PromptGuard → [Workflow] → OutputChecker

Also integrates with PermissionChecker for tool-level checks.
"""

from __future__ import annotations

from typing import Any

from ai_platform.security.input_validator import InputValidator
from ai_platform.security.output_checker import OutputChecker
from ai_platform.security.permission import PermissionChecker
from ai_platform.security.policy import SecurityPolicy
from ai_platform.security.prompt_guard import PromptGuard
from ai_platform.security.security_result import SecurityResult


class SecurityGuard:
    def __init__(self, policy: SecurityPolicy | None = None) -> None:
        self._policy = policy or SecurityPolicy()
        self.input_validator = InputValidator(self._policy)
        self.prompt_guard = PromptGuard(self._policy)
        self.permission = PermissionChecker(self._policy)
        self.output_checker = OutputChecker(self._policy)

    @property
    def policy(self) -> SecurityPolicy:
        return self._policy

    def check_input(self, request: Any) -> SecurityResult:
        """Full input check: validation + injection guard."""
        if not self._policy.security_enabled:
            return SecurityResult.pass_(check_name="security_guard")

        # 1. Input validation
        result = self.input_validator.validate(request)
        if not result.passed and self._policy.block_on_input_violation:
            return result

        # 2. Prompt injection guard
        injection_result = self.prompt_guard.check(request)
        if not injection_result.passed and self._policy.block_on_injection:
            return injection_result

        return SecurityResult.worst(result, injection_result)

    def check_tool(self, tool_name: str, role: str | None = None) -> SecurityResult:
        """Check tool permission (optionally role-scoped, policy-as-code)."""
        return self.permission.check(tool_name, role)

    def check_output(self, answer: Any) -> SecurityResult:
        """Check output safety."""
        return self.output_checker.check(answer)

    def full_check(self, request: Any, answer: Any) -> SecurityResult:
        """Run complete security pipeline: input + output."""
        input_result = self.check_input(request)
        if not input_result.passed:
            return input_result
        return self.check_output(answer)
