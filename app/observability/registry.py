from prometheus_client import REGISTRY, CollectorRegistry


def get_metrics_registry() -> CollectorRegistry:
    return REGISTRY
