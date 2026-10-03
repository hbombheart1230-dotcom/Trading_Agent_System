"""2026-09-04 -- Scanner canonical rank plumbing fix.

Root cause (confirmed via 2026-09-04 EOD daily-audit forensic scan): at
09:03 KST, canonical `scanner.json` correctly recorded symbol 041190 as
`selected_symbol` with `scanner_rank=1` -- the value is computed in
graphs/nodes/scanner_node.py as `selected_rank = ranked_symbols.index(
selected_symbol) + 1`. But that value was only ever written into a
logging/event payload; `state["selected"]` (the exact same candidate dict
object read by every downstream consumer, notably
libs/runtime/opening_rank1_controlled_probe.py) never received it. Every
downstream rank lookup therefore fell through to a separate, less
reliable "intrinsic ranked top20" reconstruction, which failed to align
for 041190 on 6/6 checks that day despite Scanner's own canonical record
being correct and available the entire time.

Fix: propagate the already-computed canonical rank onto
`state["selected"]` as additive `scanner_rank`/`scanner_rank_source`
keys (scanner_node.py), and rename the (previously unreachable in
production, since state["selected"] never carried a rank key before this
fix) "selected_candidate" provenance label to "canonical" in
`effective_selected_rank()` (opening_rank1_controlled_probe.py) to match.
Resolution precedence is unchanged in shape: canonical candidate rank ->
intrinsic-ranked-top20 fallback (untouched) -> missing. This is plumbing
only: no scoring, ranking, cascade, or opening-alpha condition logic is
touched.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
from zoneinfo import ZoneInfo

from graphs.nodes.scanner_node import scanner_node
from libs.runtime.opening_rank1_controlled_probe import (
    effective_selected_rank,
    evaluate_opening_rank1_controlled_probe,
    selected_rank,
)

KST = ZoneInfo("Asia/Seoul")


def _scanner_policy() -> Dict[str, Any]:
    return {
        "universe": {"asset_type": "all_tradable"},
        "scanner": {
            "source": {"type": "strategist"},
            "kiwoom": {"strict_only": True, "condition_limit": 30, "live_fetch": False, "include_change_rate": True},
            "fallback": {"block_static_when_empty": True},
            "candidate": {"top_pool": 10},
        },
    }


def _two_candidate_state() -> Dict[str, Any]:
    return {
        "applied_policy": _scanner_policy(),
        "candidates": [
            {"symbol": "041190", "name": "Woori Technology Investment", "why": "strategist_manual", "sources": ["strategist_manual"]},
            {"symbol": "005930", "name": "Samsung Electronics", "why": "strategist_manual", "sources": ["strategist_manual"]},
        ],
        "mock_scan_results": {
            "041190": {"score": 0.95, "risk_score": 0.6, "confidence": 0.8},
            "005930": {"score": 0.40, "risk_score": 0.2, "confidence": 0.8},
        },
    }


# --- Test 1: canonical rank propagation ---------------------------------


def test_canonical_scanner_rank_propagates_to_selected_state():
    out = scanner_node(_two_candidate_state())
    selected = out.get("selected") or {}

    assert selected.get("symbol") == "041190"
    assert selected.get("scanner_rank") == 1
    assert selected.get("scanner_rank_source") == "canonical"


def test_canonical_scanner_rank_for_runner_up_symbol():
    """Sanity check the rank isn't hardcoded to 1 -- construct a state
    where a third candidate outranks 041190, and confirm its propagated
    rank reflects its actual position, not always rank 1."""
    state = _two_candidate_state()
    state["candidates"].append({"symbol": "000660", "name": "SK Hynix", "why": "strategist_manual", "sources": ["strategist_manual"]})
    state["mock_scan_results"]["000660"] = {"score": 0.99, "risk_score": 0.5, "confidence": 0.9}

    out = scanner_node(state)
    selected = out.get("selected") or {}
    assert selected.get("symbol") == "000660"
    assert selected.get("scanner_rank") == 1  # still rank 1 -- it's now the top scorer

    ranked_candidates = list(out.get("ranked_candidates") or [])
    woori_row = next((row for row in ranked_candidates if row.get("symbol") == "041190"), None)
    assert woori_row is not None  # 041190 is still in the ranked list, just not selected/rank-1


# --- Test 2: opening probe canonical precedence -------------------------


def test_effective_selected_rank_prefers_canonical_over_conflicting_fallback():
    """Canonical rank is 2, while the fallback authority would -- if ever
    consulted -- independently confirm rank 1 (aligned, intrinsic_rank1_rank
    == 1). The two disagree, so whichever value comes back proves which
    source actually won. It must be the canonical rank."""
    candidate = {"symbol": "041190", "scanner_rank": 2}
    authority = {
        "evidence_available": True,
        "aligned": True,
        "intrinsic_rank1_rank": 1,
    }

    rank, source = effective_selected_rank(candidate, authority)

    assert rank == 2
    assert source == "canonical"


# --- Test 3: fallback compatibility (unchanged) --------------------------


def test_effective_selected_rank_falls_back_when_canonical_rank_missing():
    """The intrinsic-ranked-top20 fallback (untouched by this fix) is
    narrowly scoped: it only ever confirms "is this candidate intrinsic
    rank-1", so it returns a rank at all only when intrinsic_rank1_rank==1
    and the symbols are aligned -- never an arbitrary rank value."""
    candidate = {"symbol": "041190"}  # no rank key at all -- degraded/legacy input
    authority = {
        "evidence_available": True,
        "aligned": True,
        "intrinsic_rank1_rank": 1,
    }

    rank, source = effective_selected_rank(candidate, authority)

    assert rank == 1
    assert source == "scanner_authority_intrinsic_rank1"


def test_selected_rank_reads_legacy_key_names_unchanged():
    """Backward compatibility: the existing key-priority order in
    selected_rank() (rank, priority_rank, scanner_rank, selected_rank) is
    untouched by this fix."""
    assert selected_rank({"rank": 4}) == 4
    assert selected_rank({"priority_rank": 5}) == 5
    assert selected_rank({"scanner_rank": 1}) == 1
    assert selected_rank({"selected_rank": 2}) == 2
    assert selected_rank({}) == 0


# --- Test 4: true missing (neither canonical nor fallback) ---------------


def test_effective_selected_rank_missing_when_neither_source_available():
    candidate = {"symbol": "041190"}
    authority = {"evidence_available": False, "aligned": False}

    rank, source = effective_selected_rank(candidate, authority)

    assert rank == 0
    assert source == "missing"


# --- Test 5: strategy semantics unchanged --------------------------------


# --- 2026-09-05 Codex audit: canonical-rank-authority precedence fix ----
#
# Root cause (Codex independent audit): `selected_rank()`'s key-priority
# order was `rank -> priority_rank -> scanner_rank -> selected_rank`, so a
# stale/legacy `rank` value could outrank a present canonical
# `scanner_rank`. Separately, `effective_selected_rank()` hardcoded the
# provenance label to "canonical" whenever ANY of the four keys produced a
# positive rank -- so `{"rank": 4, "scanner_rank": 1}` could resolve to
# `(4, "canonical")`: a real value/provenance mismatch, since 4 actually
# came from the legacy `rank` field, not the canonical computation. Fixed
# by (1) reordering precedence to `scanner_rank -> rank -> priority_rank ->
# selected_rank`, and (2) resolving value and provenance in the same
# decision branch, so a legacy-key value is now labeled with its own exact
# source key, never "canonical".


def test_canonical_wins_over_conflicting_legacy_rank_field():
    """T1: rank=4 (legacy), scanner_rank=1 (canonical) -> canonical wins."""
    candidate = {"symbol": "041190", "rank": 4, "scanner_rank": 1}
    authority = {"evidence_available": False, "aligned": False}

    rank, source = effective_selected_rank(candidate, authority)

    assert rank == 1
    assert source == "canonical"


def test_legacy_rank_field_used_when_canonical_missing():
    """T2: canonical absent, legacy rank=4 present -> legacy value used,
    and honestly labeled as a legacy source (never "canonical")."""
    candidate = {"symbol": "041190", "rank": 4}
    authority = {"evidence_available": False, "aligned": False}

    rank, source = effective_selected_rank(candidate, authority)

    assert rank == 4
    assert source != "canonical"
    assert source == "legacy_rank_field"


def test_canonical_wins_over_conflicting_legacy_selected_rank_field():
    """T3: canonical=1 vs. legacy selected_rank=4 -> canonical still wins."""
    candidate = {"symbol": "041190", "selected_rank": 4, "scanner_rank": 1}
    authority = {"evidence_available": False, "aligned": False}

    rank, source = effective_selected_rank(candidate, authority)

    assert rank == 1
    assert source == "canonical"


def test_rank_value_and_provenance_always_agree():
    """T4: for every combination of populated legacy keys, the returned
    source must name the exact field the returned value actually came
    from -- never a blanket/mismatched label."""
    cases = [
        ({"scanner_rank": 3, "rank": 4, "priority_rank": 5, "selected_rank": 6}, 3, "canonical"),
        ({"rank": 4, "priority_rank": 5, "selected_rank": 6}, 4, "legacy_rank_field"),
        ({"priority_rank": 5, "selected_rank": 6}, 5, "legacy_priority_rank_field"),
        ({"selected_rank": 6}, 6, "legacy_selected_rank_field"),
    ]
    authority = {"evidence_available": False, "aligned": False}
    for candidate, expected_rank, expected_source in cases:
        rank, source = effective_selected_rank(dict(candidate, symbol="041190"), authority)
        assert rank == expected_rank
        assert source == expected_source


def test_rank1_eligibility_gate_uses_canonical_rank_not_stale_legacy_rank():
    """T5: the probe's `scanner_rank1_required` gate must evaluate against
    the canonical rank, not a conflicting stale legacy `rank` field. A
    candidate with legacy rank=4 but canonical scanner_rank=1 must be
    treated as rank-1 eligible."""
    candidate = _candidate_with_rank_fields(rank=4, scanner_rank=1)
    result = evaluate_opening_rank1_controlled_probe(
        selected=candidate,
        entry_info={"triggered": False},
        original_wait_reason="pullback_below_vwap_reclaim_not_ready",
        base_entry_guard_blocked=False,
        base_entry_guard_reason="",
        entry_quality_gate={"reasons": []},
        entry_cost_filter={"enabled": True, "passed": True},
        quant_entry_enforcement={"blocked": False, "matched_blockers": []},
        risk_off_policy={"blocked": False},
        selection_authority={"evidence_available": True, "aligned": True, "intrinsic_rank1_rank": 1},
        now_epoch=int(datetime(2026, 8, 17, 9, 10, tzinfo=KST).timestamp()),
        normal_qty=8,
        prior_probe_count=0,
        is_top_pick=True,
        same_symbol_reentry_detected=False,
        broker_mode="mock",
        enabled=True,
    )

    assert result["scanner_rank"] == 1
    assert result["scanner_rank_source"] == "canonical"
    assert result["reason"] != "scanner_rank1_required"


def _candidate_with_rank_fields(*, rank: int, scanner_rank: int) -> Dict[str, Any]:
    return {
        "symbol": "041190",
        "name": "Woori Technology Investment",
        "asset_class_detected": "common_stock",
        "rank": rank,
        "scanner_rank": scanner_rank,
        "scanner_rank_source": "canonical",
        "risk_score": 0.8,
        "sources": ["top_change_rate", "top_value"],
        "score_breakdown": {
            "momentum": 0.1,
            "trend": 0.1,
            "ma_alignment": 0.1,
            "adx_trend": 0.1,
        },
    }


def test_scanner_ranking_order_and_scores_unaffected_by_rank_propagation():
    """The fix only adds new keys to the selected candidate dict -- it must
    not alter score_total, ranking order, the selected symbol, or the
    ranked_candidates list contents in any way."""
    out = scanner_node(_two_candidate_state())

    ranked = list(out.get("ranked_candidates") or [])
    symbols_in_order = [row.get("symbol") for row in ranked]
    assert symbols_in_order == ["041190", "005930"]  # unchanged ranking order

    scores = {row.get("symbol"): row.get("score_total") for row in ranked}
    assert scores["041190"] > scores["005930"]  # unchanged score ordering/values

    assert out.get("top_stock") == "041190"  # unchanged selection
