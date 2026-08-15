from __future__ import annotations

import logging
import os

from .context import configure_default_context
from .formatter import JSONFormatter


def configure_logging(
    flask_app,
    *,
    use_json: bool,
    service_name: str | None = None,
    environment: str | None = None,
) -> None:
    configure_default_context(
        service=service_name or "chaos-demo",
        environment=environment or os.getenv("APP_ENV", "dev"),
    )
    if use_json:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        flask_app.logger.handlers = [handler]
    flask_app.logger.setLevel(logging.INFO)
