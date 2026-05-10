"""最小 Runtime Trace：HTTP 工具调用步骤落盘（与 docs/plan/PLATFORM_CONVERGENCE_ROADMAP.md P1 对齐）。"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


def new_trace_document(
    *,
    eval_kind: str,
    tools_base_url: str,
    chaos_mode: str,
    chaos_fail_rate: float,
    chaos_latency_ms: int,
) -> dict[str, Any]:
    now = int(time.time())
    return {
        "trace_id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
        "generated_at": now,
        "schema_version": 1,
        "eval_kind": eval_kind,
        "tools_base_url": tools_base_url,
        "chaos_mode": chaos_mode,
        "chaos_fail_rate": chaos_fail_rate,
        "chaos_latency_ms": chaos_latency_ms,
        "cases": [],
    }


def append_case_trace(doc: dict[str, Any], case_trace: dict[str, Any]) -> None:
    doc["cases"].append(case_trace)


def default_trace_path(report_dir: Path) -> Path:
    p = os.getenv("AGENT_TRACE_FILE", "").strip()
    if p:
        return Path(p)
    return report_dir / "agent_eval_trace_latest.json"


def write_trace_document(doc: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
