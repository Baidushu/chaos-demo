"""Compatibility facade for Flask hook and route registration."""

from __future__ import annotations

from app.api import (
    register_chaos_routes,
    register_hooks as register_runtime_hooks,
    register_order_routes,
)


def register_hooks(app, ctx) -> None:
    register_runtime_hooks(app, ctx)


def register_routes(app, ctx) -> None:
    register_order_routes(app, ctx)
    register_chaos_routes(app, ctx)
