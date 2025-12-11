"""Prometheus helpers with graceful fallback when the dependency is unavailable."""

try:  # pragma: no cover - exercised via runtime import
    from prometheus_client import (  # type: ignore
        CONTENT_TYPE_LATEST,
        REGISTRY,
        Counter,
        Histogram,
        generate_latest,
    )
except Exception:  # pragma: no cover - fallback when library is missing
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

    class _NoopMetric:
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, *args, **kwargs):
            return self

        def inc(self, amount: float = 1.0):
            return None

        def observe(self, value):
            return None

    class _NoopRegistry:  # Minimal placeholder for signature compatibility
        pass

    REGISTRY = _NoopRegistry()
    Counter = _NoopMetric
    Histogram = _NoopMetric

    def generate_latest(registry=None):
        return b""

__all__ = [
    "CONTENT_TYPE_LATEST",
    "REGISTRY",
    "Counter",
    "Histogram",
    "generate_latest",
]
