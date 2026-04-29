# trace_writer.py
from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, Optional
from datetime import datetime


DECISION_TRACES_FILE = os.getenv("DECISION_TRACES_FILE", "decision_traces.jsonl")
ENGINE_STATE_MACHINE_FILE = os.getenv("ENGINE_STATE_MACHINE_FILE", "engine_state_machine.json")
OPERATOR_DASHBOARD_FILE = os.getenv("OPERATOR_DASHBOARD_FILE", "operator_dashboard_snapshot.json")
TRACE_WRITE_FAIL_FILE = os.getenv("TRACE_WRITE_FAIL_FILE", "trace_write_failures.jsonl")


def _json_default(obj: Any) -> str:
    return str(obj)


def append_jsonl(path: str, row: Dict[str, Any]) -> bool:
    try:
        payload = dict(row or {})
        payload.setdefault("written_at", datetime.utcnow().isoformat() + "Z")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=_json_default) + "\n")
        return True
    except Exception as e:
        try:
            with open(TRACE_WRITE_FAIL_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "target_path": path,
                    "error": str(e),
                }) + "\n")
        except Exception:
            pass
        return False


def atomic_write_json(path: str, payload: Dict[str, Any]) -> bool:
    directory = os.path.dirname(path) or "."
    try:
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload or {}, f, indent=2, default=_json_default)
        os.replace(tmp_path, path)
        return True
    except Exception as e:
        try:
            append_jsonl(TRACE_WRITE_FAIL_FILE, {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "target_path": path,
                "error": str(e),
            })
        except Exception:
            pass
        return False


def write_trace_event(trace: Any, event_type: str = "trace_update") -> bool:
    if hasattr(trace, "to_dict"):
        payload = trace.to_dict()
    else:
        payload = dict(trace or {})

    return append_jsonl(DECISION_TRACES_FILE, {
        "event_type": event_type,
        "trace_id": payload.get("trace_id", ""),
        "trace": payload,
    })


def write_engine_state_snapshot(snapshot: Any) -> bool:
    if hasattr(snapshot, "to_dict"):
        payload = snapshot.to_dict()
    else:
        payload = dict(snapshot or {})
    return atomic_write_json(ENGINE_STATE_MACHINE_FILE, payload)


def write_operator_dashboard_snapshot(payload: Dict[str, Any]) -> bool:
    return atomic_write_json(OPERATOR_DASHBOARD_FILE, payload or {})


def write_trace_section(
    trace_id: str,
    section: str,
    payload: Dict[str, Any],
    event_type: str = "trace_section",
) -> bool:
    return append_jsonl(DECISION_TRACES_FILE, {
        "event_type": event_type,
        "trace_id": trace_id,
        "section": section,
        "payload": payload or {},
    })
