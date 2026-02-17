from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from libs.runtime.resilience_state import ensure_runtime_resilience_state


@dataclass(frozen=True)
class RuntimeCircuitPolicy:
    fail_threshold: int = 2
    cooldown_sec: int = 60

    @property
    def enabled(self) -> bool:
        return self.fail_threshold > 0 and self.cooldown_sec > 0


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _now_epoch(now_epoch: Optional[int]) -> int:
    if now_epoch is None:
        return int(time.time())
    return _coerce_int(now_epoch, int(time.time()))


def _resolve_policy(*, scope: str = "strategist", policy: Optional[RuntimeCircuitPolicy] = None) -> RuntimeCircuitPolicy:
    if policy is not None:
        return RuntimeCircuitPolicy(
            fail_threshold=max(0, _coerce_int(policy.fail_threshold, 0)),
            cooldown_sec=max(0, _coerce_int(policy.cooldown_sec, 0)),
        )

    # Runtime-level defaults
    raw_fail = (os.getenv("RUNTIME_CB_FAIL_THRESHOLD") or "").strip()
    raw_cooldown = (os.getenv("RUNTIME_CB_COOLDOWN_SEC") or "").strip()

    # Strategist scope keeps compatibility with existing provider env keys.
    if scope == "strategist":
        if not raw_fail:
            raw_fail = (os.getenv("AI_STRATEGIST_CB_FAIL_THRESHOLD") or "").strip()
        if not raw_cooldown:
            raw_cooldown = (os.getenv("AI_STRATEGIST_CB_COOLDOWN_SEC") or "").strip()

    fail_threshold = max(0, _coerce_int(raw_fail, 2))
    cooldown_sec = max(0, _coerce_int(raw_cooldown, 60))
    return RuntimeCircuitPolicy(fail_threshold=fail_threshold, cooldown_sec=cooldown_sec)


def _scope_circuit_slot(state: Dict[str, Any], *, scope: str) -> Dict[str, Any]:
    ensure_runtime_resilience_state(state)
    circuit = state.get("circuit")
    if not isinstance(circuit, dict):
        circuit = {}
        state["circuit"] = circuit

    slot = circuit.get(scope)
    if not isinstance(slot, dict):
        slot = {}
    slot.setdefault("state", "unknown")
    slot["fail_count"] = max(0, _coerce_int(slot.get("fail_count"), 0))
    slot["open_until_epoch"] = max(0, _coerce_int(slot.get("open_until_epoch"), 0))
    slot.setdefault("last_error_type", "")
    circuit[scope] = slot
    return slot


def gate_runtime_circuit(
    state: Dict[str, Any],
    *,
    scope: str = "strategist",
    now_epoch: Optional[int] = None,
) -> Dict[str, Any]:
    """Gate one request based on circuit state.

    Returns:
      {
        "allowed": bool,
        "reason": str,
        "circuit_state": str,
        "fail_count": int,
        "open_until_epoch": int
      }
    """
    now = _now_epoch(now_epoch)
    slot = _scope_circuit_slot(state, scope=scope)

    cstate = str(slot.get("state") or "unknown").strip().lower()
    fail_count = max(0, _coerce_int(slot.get("fail_count"), 0))
    open_until = max(0, _coerce_int(slot.get("open_until_epoch"), 0))

    if cstate == "open":
        if open_until > now:
            return {
                "allowed": False,
                "reason": "circuit_open",
                "circuit_state": "open",
                "fail_count": fail_count,
                "open_until_epoch": open_until,
            }
        # cooldown complete: allow one trial in half-open
        slot["state"] = "half_open"
        return {
            "allowed": True,
            "reason": "circuit_half_open",
            "circuit_state": "half_open",
            "fail_count": fail_count,
            "open_until_epoch": open_until,
        }

    if cstate not in ("closed", "half_open", "unknown"):
        slot["state"] = "unknown"
        cstate = "unknown"

    return {
        "allowed": True,
        "reason": "allowed",
        "circuit_state": cstate,
        "fail_count": fail_count,
        "open_until_epoch": open_until,
    }


def mark_runtime_circuit_failure(
    state: Dict[str, Any],
    *,
    error_type: str,
    scope: str = "strategist",
    now_epoch: Optional[int] = None,
    policy: Optional[RuntimeCircuitPolicy] = None,
) -> Dict[str, Any]:
    """Mark one failure event and update circuit/resilience state."""
    now = _now_epoch(now_epoch)
    slot = _scope_circuit_slot(state, scope=scope)
    cfg = _resolve_policy(scope=scope, policy=policy)

    fail_count = max(0, _coerce_int(slot.get("fail_count"), 0)) + 1
    slot["fail_count"] = fail_count
    slot["last_error_type"] = str(error_type or "")

    if cfg.enabled and fail_count >= cfg.fail_threshold:
        slot["state"] = "open"
        slot["open_until_epoch"] = max(0, now + int(cfg.cooldown_sec))
    else:
        if str(slot.get("state") or "").lower() != "half_open":
            slot["state"] = "closed"
        slot["open_until_epoch"] = max(0, _coerce_int(slot.get("open_until_epoch"), 0))

    resilience = state.get("resilience")
    if not isinstance(resilience, dict):
        resilience = {}
        state["resilience"] = resilience
    resilience["incident_count"] = max(0, _coerce_int(resilience.get("incident_count"), 0)) + 1
    resilience["last_error_type"] = str(error_type or "")
    if str(slot.get("state") or "").lower() == "open":
        resilience["cooldown_until_epoch"] = max(0, _coerce_int(slot.get("open_until_epoch"), 0))

    return {
        "circuit_state": str(slot.get("state") or "unknown"),
        "fail_count": max(0, _coerce_int(slot.get("fail_count"), 0)),
        "open_until_epoch": max(0, _coerce_int(slot.get("open_until_epoch"), 0)),
        "last_error_type": str(slot.get("last_error_type") or ""),
        "policy": {"fail_threshold": cfg.fail_threshold, "cooldown_sec": cfg.cooldown_sec},
    }


def mark_runtime_circuit_success(
    state: Dict[str, Any],
    *,
    scope: str = "strategist",
) -> Dict[str, Any]:
    """Mark one success event and close/reset the circuit."""
    slot = _scope_circuit_slot(state, scope=scope)
    slot["state"] = "closed"
    slot["fail_count"] = 0
    slot["open_until_epoch"] = 0
    slot["last_error_type"] = ""

    return {
        "circuit_state": "closed",
        "fail_count": 0,
        "open_until_epoch": 0,
        "last_error_type": "",
    }

