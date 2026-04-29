# state_evaluator.py
from __future__ import annotations

import os
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from engine_state import EngineMode, StateRequest, EngineStateSnapshot, resolve_engine_state
from reason_codes import ReasonCode, Severity


def _load_json(path: str, default: Any) -> Any:
    try:
        if not path or not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _file_age_seconds(path: str) -> Optional[float]:
    try:
        if not path or not os.path.exists(path):
            return None
        return max(0.0, time.time() - os.path.getmtime(path))
    except Exception:
        return None


def request(
    state: EngineMode,
    subsystem: str,
    reason_code: ReasonCode | str,
    message: str,
    severity: Severity | str = Severity.INFO,
    manual_unlock_required: bool = False,
    auto_recoverable: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
) -> StateRequest:
    return StateRequest(
        requested_state=state,
        subsystem=subsystem,
        reason_code=str(reason_code.value if isinstance(reason_code, ReasonCode) else reason_code),
        message=message,
        severity=str(severity.value if isinstance(severity, Severity) else severity),
        manual_unlock_required=manual_unlock_required,
        auto_recoverable=auto_recoverable,
        metadata=metadata or {},
        timestamp=datetime.now().isoformat(),
    )


def evaluate_manual_controls(env: Optional[Dict[str, str]] = None) -> List[StateRequest]:
    env = env or os.environ
    requests: List[StateRequest] = []

    if str(env.get("KILL_SWITCH", "false")).lower() == "true":
        requests.append(request(
            EngineMode.HARD_LOCK,
            "manual_controls",
            ReasonCode.KILL_SWITCH_ACTIVE,
            "KILL_SWITCH=true",
            Severity.CRITICAL,
            manual_unlock_required=True,
            auto_recoverable=False,
        ))

    if str(env.get("BOT_PAUSED", "false")).lower() == "true":
        requests.append(request(
            EngineMode.DEGRADED,
            "manual_controls",
            ReasonCode.BOT_PAUSED,
            "BOT_PAUSED=true",
            Severity.BLOCK,
        ))

    return requests


def evaluate_safety_files(
    degraded_file: str = "degraded_mode.json",
    review_file: str = "review_required.json",
    hard_lock_file: str = "global_hard_lock.json",
) -> List[StateRequest]:
    requests: List[StateRequest] = []

    degraded = _load_json(degraded_file, {})
    if isinstance(degraded, dict) and degraded.get("active"):
        requests.append(request(
            EngineMode.DEGRADED,
            "safety_files",
            "DEGRADED_FILE_ACTIVE",
            "degraded_mode.json active",
            Severity.BLOCK,
            metadata=degraded,
        ))

    review = _load_json(review_file, {})
    if isinstance(review, dict) and review.get("active"):
        requests.append(request(
            EngineMode.REVIEW_REQUIRED,
            "safety_files",
            "REVIEW_REQUIRED_FILE_ACTIVE",
            "review_required.json active",
            Severity.CRITICAL,
            manual_unlock_required=True,
            auto_recoverable=False,
            metadata=review,
        ))

    hard = _load_json(hard_lock_file, {})
    if isinstance(hard, dict) and hard.get("active"):
        requests.append(request(
            EngineMode.HARD_LOCK,
            "safety_files",
            "GLOBAL_HARD_LOCK_FILE_ACTIVE",
            "global_hard_lock.json active",
            Severity.CRITICAL,
            manual_unlock_required=True,
            auto_recoverable=False,
            metadata=hard,
        ))

    return requests


def evaluate_market_data_freshness(
    market_data_file: str = "market_prices.json",
    max_age_seconds: int = 30,
) -> List[StateRequest]:
    requests: List[StateRequest] = []
    age = _file_age_seconds(market_data_file)

    if age is None:
        requests.append(request(
            EngineMode.DEGRADED,
            "market_data",
            ReasonCode.MARKET_DATA_MISSING,
            f"{market_data_file} missing",
            Severity.BLOCK,
            metadata={"file": market_data_file},
        ))
        return requests

    if age > max_age_seconds:
        requests.append(request(
            EngineMode.DEGRADED,
            "market_data",
            ReasonCode.MARKET_DATA_STALE,
            f"{market_data_file} stale: {round(age, 2)}s > {max_age_seconds}s",
            Severity.BLOCK,
            metadata={"file": market_data_file, "age_seconds": age, "max_age_seconds": max_age_seconds},
        ))

    return requests


def evaluate_reconciliation_status(
    recon_file: str = "reconciliation.json",
) -> List[StateRequest]:
    requests: List[StateRequest] = []
    recon = _load_json(recon_file, {})

    if not isinstance(recon, dict) or not recon:
        return requests

    mismatch = bool(
        recon.get("mismatch")
        or recon.get("has_mismatch")
        or recon.get("broker_local_mismatch")
        or recon.get("foreign_positions")
        or recon.get("foreign_orders")
    )

    if mismatch:
        requests.append(request(
            EngineMode.REVIEW_REQUIRED,
            "reconciliation",
            ReasonCode.BROKER_POSITION_MISMATCH,
            "Reconciliation mismatch detected",
            Severity.CRITICAL,
            manual_unlock_required=True,
            auto_recoverable=False,
            metadata=recon,
        ))

    return requests


def evaluate_engine_state_visibility(
    env: Optional[Dict[str, str]] = None,
    market_data_file: str = "market_prices.json",
    market_data_max_age_seconds: int = 30,
    recon_file: str = "reconciliation.json",
    degraded_file: str = "degraded_mode.json",
    review_file: str = "review_required.json",
    hard_lock_file: str = "global_hard_lock.json",
) -> EngineStateSnapshot:
    requests: List[StateRequest] = []

    requests.extend(evaluate_manual_controls(env))
    requests.extend(evaluate_safety_files(
        degraded_file=degraded_file,
        review_file=review_file,
        hard_lock_file=hard_lock_file,
    ))
    requests.extend(evaluate_market_data_freshness(
        market_data_file=market_data_file,
        max_age_seconds=market_data_max_age_seconds,
    ))
    requests.extend(evaluate_reconciliation_status(recon_file=recon_file))

    if not requests:
        requests.append(request(
            EngineMode.NORMAL,
            "state_evaluator",
            ReasonCode.ENGINE_OK,
            "No blocking state requests detected",
            Severity.INFO,
        ))

    return resolve_engine_state(requests)
