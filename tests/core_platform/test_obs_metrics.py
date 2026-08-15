from __future__ import annotations

import threading

from ai_platform.observability.metrics import Histogram, MetricsRegistry, SimpleCounter, SimpleGauge


def test_counter_increment():
    c = SimpleCounter("tool_calls")
    assert c.value == 0
    c.inc()
    c.inc(5)
    assert c.value == 6


def test_counter_thread_safety():
    c = SimpleCounter("parallel")
    barrier = threading.Barrier(5)

    def worker():
        barrier.wait()
        for _ in range(100):
            c.inc()

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert c.value == 500


def test_counter_as_dict():
    c = SimpleCounter("errors", description="Error count")
    c.inc()
    d = c.as_dict()
    assert d["name"] == "errors"
    assert d["type"] == "counter"
    assert d["value"] == 1


def test_gauge_set():
    g = SimpleGauge("running", "Running agents")
    g.set(3)
    assert g.value == 3


def test_gauge_inc_dec():
    g = SimpleGauge("tasks")
    g.set(10)
    g.inc(2)
    g.dec(1)
    assert g.value == 11


def test_gauge_thread_safety():
    g = SimpleGauge("concurrent")
    results = []

    def worker(delta: float):
        for _ in range(100):
            g.inc(delta)
        results.append(g.value)

    threads = [threading.Thread(target=worker, args=(0.5,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 4 workers * 100 * 0.5 = 200
    assert g.value == 200.0


def test_histogram_record():
    h = Histogram("latency", buckets=[100, 500, 1000])
    h.record(50)
    h.record(200)
    h.record(800)
    h.record(2000)
    assert h.count == 4
    assert h.sum == 3050.0


def test_histogram_statistics():
    h = Histogram("tokens", buckets=[100, 500, 1000])
    for v in [100, 200, 300, 400, 500]:
        h.record(v)
    assert h.avg == 300.0
    assert h.p50 == 300.0
    assert h.p99 == 500.0


def test_histogram_empty():
    h = Histogram("empty")
    assert h.count == 0
    assert h.sum == 0.0
    assert h.avg is None
    assert h.p50 is None


def test_histogram_as_dict():
    h = Histogram("latency", buckets=[100])
    h.record(50)
    h.record(200)
    d = h.as_dict()
    assert d["count"] == 2
    assert "buckets" in d
    assert d["buckets"]["le_100"] == 1
    assert d["buckets"]["le_inf"] == 1


def test_metrics_registry():
    r = MetricsRegistry()
    c = r.counter("calls", "API calls")
    g = r.gauge("active", "Active requests")
    h = r.histogram("latency", "Request latency")

    c.inc()
    g.set(5)
    h.record(100)

    snap = r.snapshot()
    assert "counters" in snap
    assert "gauges" in snap
    assert "histograms" in snap
    assert snap["counters"]["calls"]["value"] == 1
    assert snap["gauges"]["active"]["value"] == 5
    assert snap["histograms"]["latency"]["count"] == 1


def test_metrics_registry_reuse():
    r = MetricsRegistry()
    c1 = r.counter("x")
    c2 = r.counter("x")
    assert c1 is c2


def test_metrics_registry_reset():
    r = MetricsRegistry()
    r.counter("a").inc(10)
    r.reset()
    assert r.counter("a").value == 0
