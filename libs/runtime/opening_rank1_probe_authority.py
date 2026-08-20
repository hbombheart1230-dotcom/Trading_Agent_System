from __future__ import annotations

from typing import Any, Mapping


SCHEMA_VERSION = "opening_rank1_probe_authority.v1"


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in list(value or []) if isinstance(row, Mapping)]


def _symbol(value: Any) -> str:
    raw = str(value or "").strip().upper()
    for suffix in (".KS", ".KQ"):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
    digits = "".join(ch for ch in raw if ch.isdigit())
    return digits[-6:].zfill(6) if digits else raw


def _rank(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 999


def resolve_opening_rank1_probe_authority(
    *,
    state: Mapping[str, Any] | None,
    selected: Mapping[str, Any] | None,
) -> dict[str, Any]:
    runtime_state = _mapping(state)
    scanner = _mapping(runtime_state.get("scanner_output"))
    snapshot = _mapping(scanner.get("pre_strategist_full_universe_snapshot"))
    candidates = _rows(snapshot.get("intrinsic_ranked_top20"))
    source = "scanner_output.pre_strategist_full_universe_snapshot.intrinsic_ranked_top20"
    if not candidates:
        candidates = _rows(scanner.get("scanner_intrinsic_control_top20"))
        source = "scanner_output.scanner_intrinsic_control_top20"
    if not candidates:
        candidates = _rows(scanner.get("scanner_intrinsic_control_top10"))
        source = "scanner_output.scanner_intrinsic_control_top10"

    rank1 = min(candidates, key=lambda row: (_rank(row.get("rank")), _symbol(row.get("symbol"))), default={})
    intrinsic_symbol = _symbol(rank1.get("symbol"))
    selected_symbol = _symbol(_mapping(selected).get("symbol"))
    evidence_available = bool(intrinsic_symbol and _rank(rank1.get("rank")) == 1)
    aligned = bool(evidence_available and selected_symbol and intrinsic_symbol == selected_symbol)
    if not evidence_available:
        status = "MISSING_INTRINSIC_RANK1"
    elif aligned:
        status = "ALIGNED"
    else:
        status = "SYMBOL_MISMATCH"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "evidence_available": evidence_available,
        "aligned": aligned,
        "selected_symbol": selected_symbol,
        "intrinsic_rank1_symbol": intrinsic_symbol,
        "intrinsic_rank1_rank": _rank(rank1.get("rank")) if rank1 else None,
        "source": source,
        "evidence_role": "P_SCANNER_PRE_STRATEGIST_UNIVERSE_INTRINSIC_RANK1",
        "behavior_effect": "controlled_probe_eligibility_only",
    }


__all__ = ["SCHEMA_VERSION", "resolve_opening_rank1_probe_authority"]
