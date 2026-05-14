from __future__ import annotations

import graphs.commander_runtime as commander_runtime


def test_post_scanner_candidate_compact_preserves_scanner_chart_fit_fields() -> None:
    compact = commander_runtime._compact_post_scanner_candidate_row(
        {
            "symbol": "005930",
            "rank": 1,
            "score_total": 1.23456789,
            "entry_compatibility_score": 0.72,
            "compatibility_bias": 0.022,
            "scanner_chart_fit_score": 0.81,
            "scanner_chart_fit_authority": "soft_rank_bias_only",
            "scanner_chart_fit_penalty": 0.03,
            "scanner_chart_fit_components": {
                "vwap_reclaim_persistence": "strong",
                "entry_chart_score": 0.76,
                "exit_risk_score": 0.12,
            },
            "scanner_macro_chart_fit_score": 0.77,
            "scanner_macro_chart_fit_bias": 0.032,
            "scanner_macro_chart_fit_authority": "soft_rank_bias_only",
            "scanner_macro_chart_fit_components": {
                "trend_alignment_score": 0.82,
                "relative_strength_score": 0.74,
                "risk_balance_score": 0.68,
            },
        },
        fallback_rank=1,
    )

    assert compact["scanner_chart_fit_score"] == 0.81
    assert compact["scanner_chart_fit_authority"] == "soft_rank_bias_only"
    assert compact["scanner_chart_fit_penalty"] == 0.03
    assert compact["scanner_chart_fit_components"]["vwap_reclaim_persistence"] == "strong"
    assert compact["scanner_chart_fit_components"]["entry_chart_score"] == 0.76
    assert compact["scanner_chart_fit_components"]["exit_risk_score"] == 0.12
    assert compact["scanner_macro_chart_fit_score"] == 0.77
    assert compact["scanner_macro_chart_fit_bias"] == 0.032
    assert compact["scanner_macro_chart_fit_authority"] == "soft_rank_bias_only"
    assert compact["scanner_macro_chart_fit_components"]["trend_alignment_score"] == 0.82
    assert compact["scanner_macro_chart_fit_components"]["relative_strength_score"] == 0.74
