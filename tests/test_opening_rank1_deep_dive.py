from __future__ import annotations

from libs.research.opening_rank1_deep_dive.analysis import analyze
from libs.research.opening_rank1_deep_dive.read_model import build_case


def test_case_uses_next_minute_prices_and_point_in_time_context() -> None:
    episode = {
        "episode_id": "E1",
        "day": "2026-07-01",
        "symbol": "005930",
        "decision_epoch": 100,
        "baseline_epoch": 120,
        "baseline_price": 100.0,
        "sources": ["top_value"],
        "source_class": "market_native_single",
        "score_total": 1.0,
        "risk_score": 0.2,
        "checkpoints": {
            "+5m": {"live_net_return_pct": -0.1},
            "+15m": {"live_net_return_pct": 0.2},
            "+30m": {
                "observed_epoch": 1920,
                "price": 101.0,
                "gross_return_pct": 1.0,
                "live_net_return_pct": 0.72,
                "mfe_pct": 1.5,
                "mae_pct": -0.4,
            },
        },
    }
    candidate = {
        "symbol": "005930",
        "score_total": 1.2,
        "compact_feature_snapshot": {"engine_regime": "trend"},
        "quant_factor_snapshot": {
            "tactic_id": "opening_probe",
            "playbook": "momentum",
            "factors": {"volume_ratio": 2.0, "vwap_distance_pct": 0.5, "is_below_vwap": False},
        },
    }
    window = {
        "scanner_control": {"top10": [candidate]},
        "strategist_selection": {"scenario": "risk_on", "playbook": "momentum"},
        "commander_final": {"decision": "approve", "selected_symbol": "005930"},
    }
    row = build_case(
        episode,
        window=window,
        macro={"generated_at": "x", "index_moves": {"kospi_pct": 1.0}},
        metadata={"name": "삼성전자", "themes": ["반도체"]},
        actual_trades=[],
    )
    assert row["virtual_buy_price"] == 100.0
    assert row["virtual_sell_price_30m"] == 101.0
    assert row["hold_minutes"] == 30.0
    assert row["volume_ratio"] == 2.0
    assert row["macro_authority"] == "POINT_IN_TIME_AT_OR_BEFORE_DECISION"


def test_analysis_separates_winners_and_path_patterns() -> None:
    rows = [
        {
            "outcome": "WIN",
            "net_return_30m_pct": 1.0,
            "return_5m_pct": -0.2,
            "mfe_30m_pct": 1.5,
            "mae_30m_pct": -0.5,
            "decision_time_kst": "2026-07-01T09:01:00+09:00",
            "symbol": "A",
        },
        {
            "outcome": "LOSS",
            "net_return_30m_pct": -0.5,
            "return_5m_pct": 0.2,
            "mfe_30m_pct": 1.2,
            "mae_30m_pct": -0.8,
            "decision_time_kst": "2026-07-01T09:06:00+09:00",
            "symbol": "B",
        },
    ]
    result = analyze(rows)
    assert result["overall"]["count"] == 2
    assert result["path_patterns"]["negative_5m_then_30m_win"]["count"] == 1
    assert result["path_patterns"]["positive_5m_then_30m_loss"]["count"] == 1
