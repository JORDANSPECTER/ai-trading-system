# engine_state.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime
from typing import Any, Dict, List, Optional


class EngineMode(str, Enum):
    NORMAL = "NORMAL"
    CAUTIOUS = "CAUTIOUS"
    DEGRADED = "DEGRADED"
    EXIT_ONLY = "EXIT_ONLY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    HARD_LOCK = "HARD_LOCK"


STATE_PRIORITY = {
    EngineMode.NORMAL: 0,
    EngineMode.CAUTIOUS: 1,
    EngineMode.DEGRADED: 2,
    EngineMode.EXIT_ONLY: 3,
    EngineMode.REVIEW_REQUIRED: 4,
    EngineMode.HARD_LOCK: 5,
}


@dataclass
class StateRequest:
    requested_state: EngineMode
    subsystem: str
    reason_code: str
    message: str
    severity: str = "INFO"
    manual_unlock_required: bool = False
    auto_recoverable: bool = True
    metadata: Optional[Dict[str, Any]] = None
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["requested_state"] = self.requested_state.value
        data["metadata"] = self.metadata or {}
        data["timestamp"] = self.timestamp or datetime.now().isoformat()
        return data


@dataclass
class EngineStateSnapshot:
    current_state: EngineMode
    allowed_to_trade: bool
    allow_new_entries: bool
    allow_position_management: bool
    allow_flatten: bool
    manual_unlock_required: bool
    reasons: List[Dict[str, Any]]
    downgrade_requests: List[Dict[str, Any]]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_state": self.current_state.value,
            "allowed_to_trade": self.allowed_to_trade,
            "allow_new_entries": self.allow_new_entries,
            "allow_position_management": self.allow_position_management,
            "allow_flatten": self.allow_flatten,
            "manual_unlock_required": self.manual_unlock_required,
            "reasons": self.reasons,
            "downgrade_requests": self.downgrade_requests,
            "timestamp": self.timestamp,
        }


def most_conservative_state(states: List[EngineMode]) -> EngineMode:
    if not states:
        return EngineMode.NORMAL
    return max(states, key=lambda s: STATE_PRIORITY[s])


def resolve_engine_state(requests: List[StateRequest]) -> EngineStateSnapshot:
    states = [r.requested_state for r in requests] or [EngineMode.NORMAL]
    final_state = most_conservative_state(states)

    manual_unlock = any(r.manual_unlock_required for r in requests)

    allow_new_entries = final_state in {EngineMode.NORMAL, EngineMode.CAUTIOUS}
    allowed_to_trade = allow_new_entries
    allow_position_management = final_state in {
        EngineMode.NORMAL,
        EngineMode.CAUTIOUS,
        EngineMode.DEGRADED,
        EngineMode.EXIT_ONLY,
        EngineMode.REVIEW_REQUIRED,
    }
    allow_flatten = final_state in {
        EngineMode.NORMAL,
        EngineMode.CAUTIOUS,
        EngineMode.DEGRADED,
        EngineMode.EXIT_ONLY,
        EngineMode.REVIEW_REQUIRED,
        EngineMode.HARD_LOCK,
    }

    if final_state in {EngineMode.DEGRADED, EngineMode.EXIT_ONLY, EngineMode.REVIEW_REQUIRED, EngineMode.HARD_LOCK}:
        allow_new_entries = False
        allowed_to_trade = False

    return EngineStateSnapshot(
        current_state=final_state,
        allowed_to_trade=allowed_to_trade,
        allow_new_entries=allow_new_entries,
        allow_position_management=allow_position_management,
        allow_flatten=allow_flatten,
        manual_unlock_required=manual_unlock,
        reasons=[r.to_dict() for r in requests],
        downgrade_requests=[r.to_dict() for r in requests if r.requested_state != EngineMode.NORMAL],
        timestamp=datetime.now().isoformat(),
    )


def state_policy_for_mode(mode: EngineMode) -> Dict[str, Any]:
    if mode == EngineMode.NORMAL:
        return {
            "size_multiplier": 1.0,
            "new_entries": True,
            "min_score_adjustment": 0,
            "exit_only": False,
        }

    if mode == EngineMode.CAUTIOUS:
        return {
            "size_multiplier": 0.5,
            "new_entries": True,
            "min_score_adjustment": 10,
            "exit_only": False,
        }

    if mode == EngineMode.DEGRADED:
        return {
            "size_multiplier": 0.0,
            "new_entries": False,
            "min_score_adjustment": 999,
            "exit_only": False,
        }

    if mode == EngineMode.EXIT_ONLY:
        return {
            "size_multiplier": 0.0,
            "new_entries": False,
            "min_score_adjustment": 999,
            "exit_only": True,
        }

    if mode == EngineMode.REVIEW_REQUIRED:
        return {
            "size_multiplier": 0.0,
            "new_entries": False,
            "min_score_adjustment": 999,
            "exit_only": True,
        }

    return {
        "size_multiplier": 0.0,
        "new_entries": False,
        "min_score_adjustment": 999,
        "exit_only": True,
    }
