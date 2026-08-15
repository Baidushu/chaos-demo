from __future__ import annotations

from flask import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


def register_routes(flask_app, runtime) -> None:
    @flask_app.route("/metrics")
    def metrics():
        return Response(
            generate_latest(runtime.metrics.registry),
            mimetype=CONTENT_TYPE_LATEST,
        )
