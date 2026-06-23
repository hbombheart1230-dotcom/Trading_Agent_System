from libs.reporting.q8_evaluation_contract import (
    CANONICAL_DEDUPE_KEY_FIELDS,
    build_q8_trust_gate,
    dedupe_q8_candidates,
)


def _candidate(symbol: str, epoch: int, subtype: str = "confirmed_post_reclaim_pullback") -> dict:
    return {
        "symbol": symbol,
        "shadow_forward_base": {
            "baseline_epoch": epoch,
            "baseline_raw_ts": "20260616093000",
        },
        "entry_lane_observation": {
            "primary_lane": "vwap_reclaim",
            "subtype": subtype,
        },
    }


def test_q8_contract_uses_canonical_dedupe_key() -> None:
    rows = [_candidate("005930", 1000), _candidate("005930", 1000), _candidate("005930", 1060)]

    deduped = dedupe_q8_candidates(rows)

    assert CANONICAL_DEDUPE_KEY_FIELDS == ["day", "symbol", "baseline_epoch", "entry_lane_subtype"]
    assert len(deduped) == 2


def test_q8_trust_gate_blocks_single_day_promotion_watch() -> None:
    gate = build_q8_trust_gate(
        raw_candidate_count=120,
        deduped_candidate_count=100,
        trusted_forward_count=100,
        trusted_forward_coverage=1.0,
        candidate_watchlist=[
            {
                "observed_count": 60,
                "observed_day_count": 1,
                "avg_return_5m_pct": 0.3,
                "avg_return_15m_pct": 0.2,
            }
        ],
    )

    assert gate["promotion_allowed"] is False
    assert "no_repeatable_promotion_watch_candidate" in gate["block_reasons"]


def test_q8_trust_gate_allows_repeatable_candidate() -> None:
    gate = build_q8_trust_gate(
        raw_candidate_count=120,
        deduped_candidate_count=100,
        trusted_forward_count=100,
        trusted_forward_coverage=1.0,
        candidate_watchlist=[
            {
                "observed_count": 60,
                "observed_day_count": 2,
                "avg_return_5m_pct": 0.3,
                "avg_return_15m_pct": 0.2,
            }
        ],
    )

    assert gate["promotion_allowed"] is True
    assert gate["block_reasons"] == []
