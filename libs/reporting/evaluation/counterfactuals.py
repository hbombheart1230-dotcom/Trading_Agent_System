from __future__ import annotations

from typing import Any

from .contracts import EvidenceClass


def build_selection_attribution(trade_model: dict[str, Any]) -> dict[str, Any]:
    selection = trade_model.get("selection") if isinstance(trade_model.get("selection"), dict) else {}
    raw_top1 = selection.get("raw_scanner_top1") if isinstance(selection.get("raw_scanner_top1"), dict) else {}
    biased_top1 = selection.get("scanner_top1") if isinstance(selection.get("scanner_top1"), dict) else {}
    top1_symbol = str(raw_top1.get("symbol") or "")
    selected_symbol = str(selection.get("selected_symbol") or "")
    same_symbol = bool(top1_symbol and selected_symbol and top1_symbol == selected_symbol)
    raw_baseline_available = bool(top1_symbol)
    return {
        "schema_version": "q9_selection_attribution.v1",
        "scanner_baseline": {
            "symbol": top1_symbol,
            "rank": raw_top1.get("rank") or 1 if top1_symbol else None,
            "forward_return_pct": None,
            "evidence_class": EvidenceClass.UNAVAILABLE.value,
            "available": raw_baseline_available,
        },
        "strategist_selected": {
            "symbol": selected_symbol,
            "post_strategist_scanner_top1": str(biased_top1.get("symbol") or ""),
            "changed_scanner_top1": bool(raw_baseline_available and selected_symbol and not same_symbol),
            "forward_return_pct": None,
            "evidence_class": EvidenceClass.UNAVAILABLE.value,
        },
        "commander_final": {
            "symbol": selected_symbol,
            "changed_strategist_selection": False,
            "forward_return_pct": None,
            "evidence_class": EvidenceClass.UNAVAILABLE.value,
        },
        "deltas": {
            "strategist_delta_pct": None,
            "commander_delta_pct": None,
            "system_delta_pct": None,
        },
        "limitations": [
            "pre-Strategist raw Scanner Top-1 snapshot is unavailable"
            if not raw_baseline_available
            else "alternate forward outcomes require matching Q8 decision-window evidence",
            "Commander alternative selection or veto outcome is unavailable",
        ],
    }
