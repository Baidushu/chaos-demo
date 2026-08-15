"""AI Platform Core — unified enterprise AI platform infrastructure.

Provides:
  - PlatformConfig: centralized configuration (no hardcoding)
  - PlatformFactory: component creation and wiring
  - AIPlatformService: unified run(request) pipeline
  - PlatformResult: unified result type
  - exceptions: PlatformError, SecurityBlockedError, etc.
  - create_platform_service(): one-shot convenience factory
"""

from ai_platform.core.config import (
    EvaluationConfig,
    ModelConfig,
    PlatformConfig,
)
from ai_platform.core.factory import PlatformFactory
from ai_platform.core.exceptions import (
    AgentExecutionError,
    EvaluationError,
    PlatformError,
    SecurityBlockedError,
)
from ai_platform.core.service import (
    AIPlatformService,
    PlatformResult,
    create_platform_service,
)

__all__ = [
    "AgentExecutionError",
    "AIPlatformService",
    "EvaluationConfig",
    "EvaluationError",
    "ModelConfig",
    "PlatformConfig",
    "PlatformError",
    "PlatformFactory",
    "PlatformResult",
    "SecurityBlockedError",
    "create_platform_service",
]
