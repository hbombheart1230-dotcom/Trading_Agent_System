from libs.reporting.q8_shadow_blocker_review import build_q8_shadow_blocker_review


def test_q8_shadow_blocker_review_groups_forward_outcomes() -> None:
    payloads = [
        {
            "generated_at": "2026-06-02T00:00:00+00:00",
            "candidates": [
                {
                    "symbol": "005930",
                    "reason": "breakout_not_ready",
                    "shadow_role": "top_pick",
                    "rank": 1,
                    "quant_tactic_id": "vwap_reclaim_pullback",
                    "shadow_forward_base": {
                        "available": True,
                        "baseline_epoch": 1780358400,
                        "baseline_price": 100.0,
                    },
                },
                {
                    "symbol": "005930",
                    "reason": "breakout_not_ready",
                    "shadow_role": "top_pick",
                    "rank": 1,
                    "quant_tactic_id": "vwap_reclaim_pullback",
                    "shadow_forward_base": {
                        "available": True,
                        "baseline_epoch": 1780358400,
                        "baseline_price": 100.0,
                    },
                },
                {
                    "symbol": "000660",
                    "reason": "volume_confirmation_missing",
                    "shadow_role": "runner_up_evaluated",
                    "rank": 2,
                    "quant_tactic_id": "defensive_observe",
                    "shadow_forward_base": {
                        "available": True,
                        "baseline_epoch": 1780358400,
                        "baseline_price": 200.0,
                    },
                },
            ],
        }
    ]
    minute_rows = {
        "005930": [
            {"ts": 1780358400, "close": 100.0, "high": 100.0, "low": 100.0},
            {"ts": 1780358700, "close": 101.0, "high": 102.0, "low": 99.5},
            {"ts": 1780359300, "close": 103.0, "high": 104.0, "low": 99.0},
        ],
        "000660": [
            {"ts": 1780358400, "close": 200.0, "high": 200.0, "low": 200.0},
            {"ts": 1780358700, "close": 198.0, "high": 199.0, "low": 197.0},
            {"ts": 1780359300, "close": 196.0, "high": 198.0, "low": 195.0},
        ],
    }

    review = build_q8_shadow_blocker_review(payloads, minute_rows_by_symbol=minute_rows)
    groups = {group["reason"]: group for group in review["groups"]}

    assert review["raw_candidate_count"] == 3
    assert review["candidate_count"] == 2
    assert review["deduped_candidate_count"] == 2
    assert review["duplicate_count"] == 1
    assert groups["breakout_not_ready"]["candidate_count"] == 1
    assert groups["breakout_not_ready"]["observed_count"] == 1
    assert groups["breakout_not_ready"]["missed_opportunity_count"] == 1
    assert review["dedupe_key"] == ["day", "symbol", "baseline_epoch", "entry_lane_subtype"]
    assert review["promotion_allowed"] is False
    assert groups["breakout_not_ready"]["raw_decision"] == "adjust_and_retest"
    assert groups["breakout_not_ready"]["decision"] == "retain_under_observation"
    assert groups["breakout_not_ready"]["decision_blocked_by_trust_gate"] is True
    assert groups["volume_confirmation_missing"]["candidate_count"] == 1
    assert groups["volume_confirmation_missing"]["adverse_count"] == 1
    assert groups["volume_confirmation_missing"]["decision"] == "retain_under_observation"
