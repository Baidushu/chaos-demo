"""Platform lifecycle management — initialization, shutdown, health checks.

Provides lifecycle hooks for the AI Platform service:
  - initialize(): bootstrap all platform components
  - shutdown(): clean up resources
  - health(): report component health status
"""

from __future__ import annotations

from typing import Any

from ai_platform.core.config import PlatformConfig
from ai_platform.core.factory import PlatformFactory


def initialize(config: PlatformConfig | None = None) -> PlatformFactory:
    """Bootstrap the platform with the given (or default) configuration.

    Returns a PlatformFactory ready to create wired components.
    """
    cfg = config or PlatformConfig.default()
    return PlatformFactory(cfg)


def shutdown(factory: PlatformFactory) -> None:
    """Clean up platform resources."""
    factory.reset()


def health(factory: PlatformFactory) -> dict[str, Any]:
    """Report health status of core platform components."""
    return {
        "status": "healthy",
        "mode": factory.config.mode,
        "observability_enabled": factory.config.observability_enabled,
    }
