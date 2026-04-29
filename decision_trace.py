# decision_trace.py
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
import hashlib
import json
import uuid


def utcnow_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def stable_hash(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload or {}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_trace_id(ticker: str = "UNKNOWN", source: str = "unknown") -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"trace_{stamp}_{ticker.upper()}_{source}_{suffix}"


@dataclass
class TraceSectionResult:
    stage: str
    approved: Optional[bool] = None
    decision: str = ""
    reasons: List[Dict[str, Any]] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    started_at: str = field(default_factory=utcnow_iso)
    completed_at: str = ""
    latency_ms: Optional[float] = None

    def complete(self) -> "TraceSectionResult":
        self.completed_at = utcnow_iso()
        return self

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DecisionTrace:
    trace_id: str
    created_at: str
    updated_at: str
    status: str = "OPEN"

    candidate: Dict[str, Any] = field(default_factory=dict)
    data_freshness: Dict[str, Any] = field(default_factory=dict)
    engine_state: Dict[str, Any] = field(default_factory=dict)

    pre_trade_validation: Dict[str, Any] = field(default_factory=dict)
    regime_evaluation: Dict[str, Any] = field(default_factory=dict)
    risk_policy: Dict[str, Any] = field(default_factory=dict)
    portfolio_risk: Dict[str, Any] = field(default_factory=dict)
    adaptive_learning: Dict[str, Any] = field(default_factory=dict)
    execution_scoring: Dict[str, Any] = field(default_factory=dict)
    portfolio_allocator: Dict[str, Any] = field(default_factory=dict)

    final_decision: Dict[str, Any] = field(default_factory=dict)
    execution_plan: Dict[str, Any] = field(default_factory=dict)
    broker_order_events: List[Dict[str, Any]] = field(default_factory=list)
    execution_quality: Dict[str, Any] = field(default_factory=dict)
    reconciliation: Dict[str, Any] = field(default_factory=dict)
    exit: Dict[str, Any] = field(default_factory=dict)
    post_trade: Dict[str, Any] = field(default_factory=dict)

    misc_events: List[Dict[str, Any]] = field(default_factory=list)

    def touch(self) -> None:
        self.updated_at = utcnow_iso()

    def set_section(self, section: str, value: Dict[str, Any]) -> None:
        setattr(self, section, value or {})
        self.touch()

    def append_broker_event(self, event: Dict[str, Any]) -> None:
        payload = dict(event or {})
        payload.setdefault("timestamp", utcnow_iso())
        self.broker_order_events.append(payload)
        self.touch()

    def append_misc_event(self, event: Dict[str, Any]) -> None:
        payload = dict(event or {})
        payload.setdefault("timestamp", utcnow_iso())
        self.misc_events.append(payload)
        self.touch()

    def close(self, status: str = "CLOSED") -> None:
        self.status = status
        self.touch()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def create_decision_trace(
    raw_signal: Dict[str, Any],
    normalized_signal: Optional[Dict[str, Any]] = None,
    source: str = "unknown",
) -> DecisionTrace:
    normalized = normalized_signal or raw_signal or {}
    ticker = str(normalized.get("ticker") or raw_signal.get("ticker") or "UNKNOWN")
    trace_id = new_trace_id(ticker=ticker, source=source)

    return DecisionTrace(
        trace_id=trace_id,
        created_at=utcnow_iso(),
        updated_at=utcnow_iso(),
        candidate={
            "source": source,
            "raw_signal_snapshot": raw_signal or {},
            "normalized_signal": normalized,
            "signal_hash": stable_hash(normalized),
            "signal_id": normalized.get("signal_id") or normalized.get("id") or "",
            "ticker": ticker.upper(),
        },
    )


def section_result(
    stage: str,
    approved: Optional[bool] = None,
    decision: str = "",
    reasons: Optional[List[Dict[str, Any]]] = None,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return TraceSectionResult(
        stage=stage,
        approved=approved,
        decision=decision,
        reasons=reasons or [],
        data=data or {},
    ).complete().to_dict()
