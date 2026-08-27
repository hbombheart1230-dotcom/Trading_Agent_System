from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.short_alpha_discriminator.cohorts import (
    build_cohort_review,
    join_opening_to_feature_mart,
)
from libs.reporting.short_alpha_discriminator.pipeline import (
    build_short_alpha_discriminator,
    write_short_alpha_discriminator,
)
from libs.reporting.short_alpha_discriminator.profit_lock import (
    build_profit_fade_review,
)
from libs.reporting.short_alpha_discriminator.strategist_roi import (
    build_strategist_stage2_review,
)
from libs.reporting.short_alpha_discriminator.opening_casebook import (
    build_opening_overshoot_casebook,
    classify_opening_case,
)


def _opening(
    decision_id: str,
    *,
    day: str,
    symbol: str,
    asset_class: str,
    epoch: int,
    returns: tuple[float, float, float, float, float],
    mfe: float = 4.0,
) -> dict:
    horizons = ("+5m", "+15m", "+30m", "+60m", "EOD")
    return {
        "episode_id": f"episode:{decision_id}",
        "decision_id": decision_id,
        "decision_epoch": epoch,
        "day": day,
        "symbol": symbol,
        "opening_observability": {
            "decision_from_open_sec": 30,
            "asset_observation": {"asset_class": asset_class},
        },
        "checkpoints": {
            horizon: {"live_net_return_pct": value, "mfe_pct": mfe}
            for horizon, value in zip(horizons, returns)
        },
    }


def _feature(
    decision_id: str,
    *,
    day: str,
    symbol: str,
    risk_band: str,
    setup: str = "DIRECTIONAL_BREADTH",
    generation_mode: str = "CACHED_OR_SKIPPED_FRAME",
) -> dict:
    checkpoints = {
        horizon: {"status": "OBSERVED", "net_return_pct": value}
        for horizon, value in {
            "+5m": 1.0,
            "+15m": 1.2,
            "+30m": 1.5,
            "+60m": 1.0,
            "EOD": -0.5,
        }.items()
    }
    return {
        "identity": {
            "decision_id": decision_id,
            "decision_epoch": int(decision_id.rsplit("-", 1)[-1]),
            "day": day,
            "symbol": symbol,
        },
        "scanner": {
            "risk_band": risk_band,
            "candidate_setup": setup,
            "sources": ["sector_theme"],
            "score_total": 1.2,
        },
        "strategy": {
            "entry_horizon": "scalp",
            "tactic_id": "vwap_reclaim_pullback",
            "canonical_evidence_status": "OBSERVED",
        },
        "strategy_choice_observation": {
            "playbook_choice": {"changed_from_pre_llm": False},
            "tactic_choice": {"selected_is_playbook_default": True},
            "generation": {"mode": generation_mode},
        },
        "outcomes": {"checkpoints": checkpoints},
    }


def _fixture_payloads() -> tuple[list[dict], list[dict]]:
    opening = [
        _opening(
            "decision-1",
            day="2026-08-24",
            symbol="005930",
            asset_class="common_stock",
            epoch=1,
            returns=(3.0, 2.0, 1.0, 0.5, -1.0),
        ),
        _opening(
            "decision-2",
            day="2026-08-24",
            symbol="005930",
            asset_class="common_stock",
            epoch=2,
            returns=(9.0, 9.0, 9.0, 9.0, 9.0),
        ),
        _opening(
            "decision-3",
            day="2026-08-25",
            symbol="000660",
            asset_class="common_stock",
            epoch=3,
            returns=(2.0, 1.0, 0.5, 0.0, -0.5),
        ),
        _opening(
            "decision-4",
            day="2026-08-25",
            symbol="233740",
            asset_class="leveraged_etf",
            epoch=4,
            returns=(-1.0, -1.0, -1.0, 0.0, 1.0),
        ),
    ]
    features = [
        _feature("decision-1", day="2026-08-24", symbol="005930", risk_band="HIGH"),
        _feature("decision-2", day="2026-08-24", symbol="005930", risk_band="HIGH"),
        _feature(
            "decision-3",
            day="2026-08-25",
            symbol="000660",
            risk_band="HIGH",
            generation_mode="TACTICAL_REFRESH_INHERITED_MARKET_FRAME",
        ),
        _feature("decision-4", day="2026-08-25", symbol="233740", risk_band="HIGH"),
    ]
    return opening, features


def test_high_common_cohort_is_day_symbol_deduped_and_prospective_is_separate() -> None:
    opening, features = _fixture_payloads()
    joined, integrity = join_opening_to_feature_mart(opening, features)
    review = build_cohort_review(joined)
    primary = next(
        row
        for row in review["cohorts"]
        if row["cohort_id"] == "HIGH_COMMON_SHORT_ALPHA_V1"
    )

    assert integrity["missing_join_count"] == 0
    assert primary["episode_count"] == 3
    assert primary["independent_day_symbol_count"] == 2
    assert primary["horizons"]["+5m"]["sample_count"] == 2
    assert review["historical_reference"]["independent_day_symbol_count"] == 1
    assert review["prospective"]["independent_day_symbol_count"] == 1
    assert review["historical_sensitivity"]["without_best_observation"][
        "excluded_symbol"
    ] == "005930"


def test_profit_lock_is_observation_only_and_records_profit_fade() -> None:
    opening, features = _fixture_payloads()
    joined, _integrity = join_opening_to_feature_mart(opening, features)
    rows = [
        row
        for row in joined
        if row["asset_class"] == "common_stock" and row["risk_band"] == "HIGH"
    ][:1]
    review = build_profit_fade_review(rows)

    assert review["positive_5m_to_negative_eod_count"] == 1
    assert review["profit_lock_proxies"][0]["triggered_count"] == 1
    assert review["behavior_change_authorized"] is False


def test_strategist_stage2_review_does_not_change_authority() -> None:
    _opening_rows, features = _fixture_payloads()
    scorecard = {
        "range": {"start": "2026-08-01", "end": "2026-08-24"},
        "components": {
            "strategist": {
                "ranking_overlay": {"state": "NEUTRAL"},
                "post_scanner_refresh": {"state": "DEGRADING"},
            }
        },
    }
    review = build_strategist_stage2_review(features, scorecard)

    assert review["official_post_scanner_refresh"]["state"] == "DEGRADING"
    assert review["authority_change_applied"] is False
    assert review["behavior_change_authorized"] is False


def test_pipeline_writes_independent_artifacts(tmp_path: Path) -> None:
    opening, features = _fixture_payloads()
    reports = tmp_path / "reports"
    opening_path = (
        reports
        / "evaluation"
        / "opening_rank1_shadow"
        / "opening_rank1_shadow_cumulative.json"
    )
    feature_path = (
        reports / "evaluation" / "feature_mart" / "opening_rank1" / "feature_mart.json"
    )
    scorecard_path = (
        reports
        / "evaluation"
        / "agent_effectiveness"
        / "cumulative_20260801_20260824"
        / "agent_effectiveness_scorecard.json"
    )
    for path, payload in (
        (opening_path, {"schema_version": "opening.v1", "episodes": opening}),
        (feature_path, {"schema_version": "feature.v1", "episodes": features}),
        (
            scorecard_path,
            {
                "schema_version": "scorecard.v1",
                "components": {"strategist": {}},
            },
        ),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    payload = build_short_alpha_discriminator(
        reports_root=reports, through_day="2026-08-25"
    )
    result = write_short_alpha_discriminator(
        reports_root=reports,
        through_day="2026-08-25",
        output_dir=tmp_path / "out",
    )

    assert payload["integrity"]["status"] == "PASS"
    assert payload["behavior_change_authorized"] is False
    assert Path(result["summary_json_path"]).exists()
    assert Path(result["cohort_json_path"]).exists()
    assert Path(result["profit_fade_json_path"]).exists()
    assert Path(result["strategist_roi_json_path"]).exists()
    assert Path(result["scanner_diagnostics_json_path"]).exists()
    assert Path(result["opening_casebook_json_path"]).exists()
    assert Path(result["opening_casebook_markdown_path"]).exists()
    markdown = Path(result["summary_markdown_path"]).read_text(encoding="utf-8")
    assert "## Historical Sensitivity" in markdown
    assert "Strategist Stage-2 authority changed: **No**" in markdown


def test_opening_case_classification_is_deterministic_and_cost_aware() -> None:
    success = _opening(
        "decision-success", day="2026-08-26", symbol="005930",
        asset_class="common_stock", epoch=10, returns=(0.2, 1.1, 0.5, 0.0, 0.0),
    )
    fade = _opening(
        "decision-fade", day="2026-08-26", symbol="000660",
        asset_class="common_stock", epoch=11, returns=(-0.2, -0.1, -0.3, 0.0, 0.0), mfe=1.5,
    )

    assert classify_opening_case(success)["label"] == "FIXED_HORIZON_SUCCESS"
    classified_fade = classify_opening_case(fade)
    assert classified_fade["label"] == "MFE_NEAR_SUCCESS_PROFIT_FADE"
    assert classified_fade["best_mfe_net_proxy_pct"] == 1.22


def test_casebook_uses_first_day_symbol_episode_only() -> None:
    opening, features = _fixture_payloads()
    joined, _ = join_opening_to_feature_mart(opening, features)
    casebook = build_opening_overshoot_casebook(joined)

    assert casebook["source_episode_count"] == 4
    assert casebook["independent_case_count"] == 3
    assert casebook["behavior_effect"] == "NONE_OBSERVATION_ONLY"
