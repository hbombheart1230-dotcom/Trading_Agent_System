from __future__ import annotations

from libs.research.opening_rank1_deep_dive.analysis import analyze
from libs.research.opening_rank1_deep_dive.read_model import build_case
from libs.research.opening_rank1_deep_dive.microstructure import microstructure_features
from libs.research.opening_rank1_deep_dive.rank_context import build_rank_index, rank_features


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


def test_microstructure_uses_only_completed_predecision_bars() -> None:
    rows = [
        {"ts": 500, "raw_ts": "20260630090000", "open": 99, "high": 100, "low": 98, "close": 99, "volume": 5},
        {"ts": 1000, "raw_ts": "20260701090000", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 10},
        {"ts": 1060, "raw_ts": "20260701090100", "open": 101, "high": 103, "low": 100, "close": 102, "volume": 20},
        {"ts": 1120, "raw_ts": "20260701090200", "open": 102, "high": 104, "low": 101, "close": 103, "volume": 30},
    ]
    from datetime import datetime, timezone

    def iso(epoch: int) -> str:
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()

    case = {
        "day": "2026-07-01",
        "decision_time_kst": iso(1070),
        "virtual_buy_time_kst": iso(1120),
        "virtual_buy_price": 102.0,
        "return_5m_pct": 0.2,
        "net_return_30m_pct": 0.5,
    }
    result = microstructure_features(case, rows)
    assert result["completed_bar_count_before_decision"] == 1
    assert result["last_completed_close"] == 101.0
    assert result["baseline_delay_sec"] == 50
    assert result["opening_observed_volume"] == 10.0
    assert result["opening_volume_reference"] == 5.0
    assert result["opening_relative_volume"] == 2.0


def test_microstructure_does_not_use_unfinished_first_minute_volume() -> None:
    rows = [
        {"ts": 500, "raw_ts": "20260630090000", "open": 99, "high": 100, "low": 98, "close": 99, "volume": 5},
        {"ts": 1000, "raw_ts": "20260701090000", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000},
        {"ts": 1060, "raw_ts": "20260701090100", "open": 101, "high": 103, "low": 100, "close": 102, "volume": 2000},
    ]
    from datetime import datetime, timezone

    def iso(epoch: int) -> str:
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()

    result = microstructure_features(
        {
            "day": "2026-07-01",
            "decision_time_kst": iso(1006),
            "virtual_buy_time_kst": iso(1060),
            "virtual_buy_price": 101.0,
            "return_5m_pct": 0.2,
            "net_return_30m_pct": 0.5,
        },
        rows,
    )

    assert result["completed_bar_count_before_decision"] == 0
    assert result["opening_observed_volume"] is None
    assert result["opening_relative_volume"] is None


def test_rank_context_calculates_gap_and_contiguous_persistence() -> None:
    def window(decision_id: str, epoch: int, top: str, score: float) -> tuple[str, dict]:
        return decision_id, {
            "decision_epoch": epoch,
            "generated_at": "2026-07-01T00:00:00+00:00",
            "scanner_control": {
                "top20": [
                    {"symbol": top, "score_total": score},
                    {"symbol": "B", "score_total": 0.8},
                ]
            },
        }

    index = build_rank_index(
        dict(
            [
                window("D0", 1000, "A", 0.9),
                window("D1", 1060, "A", 1.0),
                window("D2", 1120, "A", 1.1),
                window("D3", 1180, "C", 1.2),
            ]
        )
    )
    result = rank_features(
        {"day": "2026-07-01"},
        decision_id="D1",
        rank_index=index,
    )
    assert result["rank1_rank2_gap"] == 0.2
    assert result["rank1_age_sec"] == 60
    assert result["rank1_forward_persistence_sec"] == 60
