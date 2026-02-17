from __future__ import annotations

from typing import Any, Dict


RUNTIME_RESILIENCE_CONTRACT_VERSION = "m23.resilience.v1"
_CIRCUIT_ALLOWED_STATES = {"unknown", "closed", "open", "half_open"}


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


def _normalize_circuit_state(value: Any) -> str:
    v = str(value or "").strip().lower()
    if v in _CIRCUIT_ALLOWED_STATES:
        return v
    return "unknown"


def _first_non_none(*values: Any) -> Any:
    for v in values:
        if v is not None:
            return v
    return None


def ensure_runtime_resilience_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure canonical runtime resilience contract keys exist in state.

    Canonical keys:
      - state["resilience"]
      - state["circuit"]["strategist"]
    """
    resilience_in = state.get("resilience") if isinstance(state.get("resilience"), dict) else {}
    circuit_in = state.get("circuit") if isinstance(state.get("circuit"), dict) else {}
    strategist_in = (
        circuit_in.get("strategist")
        if isinstance(circuit_in.get("strategist"), dict)
        else {}
    )

    # Legacy/top-level compatibility (used by strategist telemetry fields).
    legacy_circuit_state = state.get("circuit_state")
    legacy_circuit_fail_count = state.get("circuit_fail_count")
    legacy_circuit_open_until = state.get("circuit_open_until_epoch")

    normalized_resilience = dict(resilience_in)
    normalized_resilience["contract_version"] = RUNTIME_RESILIENCE_CONTRACT_VERSION
    normalized_resilience["degrade_mode"] = _coerce_bool(
        resilience_in.get("degrade_mode"),
        default=False,
    )
    normalized_resilience["degrade_reason"] = str(resilience_in.get("degrade_reason") or "")
    normalized_resilience["incident_count"] = _coerce_int(
        resilience_in.get("incident_count"),
        default=0,
    )
    normalized_resilience["cooldown_until_epoch"] = _coerce_int(
        resilience_in.get("cooldown_until_epoch"),
        default=0,
    )
    normalized_resilience["last_error_type"] = str(resilience_in.get("last_error_type") or "")

    strategist_state_raw = _first_non_none(
        strategist_in.get("state"),
        strategist_in.get("circuit_state"),
        legacy_circuit_state,
    )
    strategist_fail_count_raw = _first_non_none(
        strategist_in.get("fail_count"),
        strategist_in.get("circuit_fail_count"),
        legacy_circuit_fail_count,
    )
    strategist_open_until_raw = _first_non_none(
        strategist_in.get("open_until_epoch"),
        strategist_in.get("circuit_open_until_epoch"),
        legacy_circuit_open_until,
    )

    normalized_strategist = dict(strategist_in)
    normalized_strategist["state"] = _normalize_circuit_state(strategist_state_raw)
    normalized_strategist["fail_count"] = _coerce_int(strategist_fail_count_raw, default=0)
    normalized_strategist["open_until_epoch"] = _coerce_int(strategist_open_until_raw, default=0)
    normalized_strategist["last_error_type"] = str(strategist_in.get("last_error_type") or "")

    normalized_circuit = dict(circuit_in)
    normalized_circuit["strategist"] = normalized_strategist

    state["resilience"] = normalized_resilience
    state["circuit"] = normalized_circuit
    return state

