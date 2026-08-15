"""Target matching for chaos experiments."""

from __future__ import annotations


def _percentage_match(target: dict, random_source) -> bool:
    percentage = target.get("percentage")
    if percentage is None:
        return True
    value = float(percentage)
    if value > 1.0:
        value = value / 100.0
    value = max(0.0, min(value, 1.0))
    source = random_source or __import__("random").random
    if hasattr(source, "random"):
        sample = float(source.random())
    else:
        sample = float(source())
    return sample < value


def match_request(experiment, request, *, random_source=None) -> bool:
    target = dict(getattr(experiment, "target", {}) or {})
    endpoint = target.get("endpoint")
    method = target.get("method")
    if endpoint and endpoint not in ("*", getattr(request, "path", None)):
        return False
    if method and str(method).upper() != str(getattr(request, "method", "")).upper():
        return False
    return _percentage_match(target, random_source)
