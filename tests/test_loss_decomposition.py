from __future__ import annotations

from libs.reporting.evaluation.loss_decomposition import _group_forward, _rank_bucket


def test_rank_bucket_contract() -> None:
    assert _rank_bucket(1) == "rank1"
    assert _rank_bucket(3) == "rank2-3"
    assert _rank_bucket(5) == "rank4-5"
    assert _rank_bucket(10) == "rank6-10"


def test_group_forward_keeps_horizons_separate() -> None:
    rows = [
        {
            "rank": 1,
            "shadow_forward_outcome": {
                "checkpoints": {
                    "+5m": {"status": "observed", "return_pct": 1.0},
                    "+15m": {"status": "observed", "return_pct": -0.5},
                }
            },
        },
        {
            "rank": 1,
            "shadow_forward_outcome": {
                "checkpoints": {
                    "+5m": {"status": "observed", "return_pct": 0.0},
                }
            },
        },
    ]
    result = _group_forward(rows, lambda row: _rank_bucket(row.get("rank")))[0]
    assert result["observed_count"] == 2
    assert result["avg_return_5m_pct"] == 0.5
    assert result["avg_return_15m_pct"] == -0.5
