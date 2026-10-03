from __future__ import annotations

from pathlib import Path


SCHEMA_VERSION = "alpha_research_board.v2"
CONTRACT_VERSION = "abc_fixed_2026_08_27"
LIVE_RESEARCH_COST_PCT = 0.28

SOURCE_PATHS = {
    "feature_candidates": Path(
        "evaluation/feature_mart/opening_rank1/candidate_selection.json"
    ),
    "prospective_candidates": Path(
        "evaluation/feature_mart/opening_rank1/prospective/"
        "rank1_candidate_shadow_cumulative.json"
    ),
    "prospective_contract": Path(
        "evaluation/feature_mart/opening_rank1/prospective/"
        "frozen_candidate_contract.json"
    ),
    "fresh_change": Path(
        "evaluation/feature_mart/opening_rank1/fresh_change_activation/"
        "fresh_change_activation_cumulative.json"
    ),
    "opening_cumulative": Path(
        "evaluation/opening_rank1_shadow/opening_rank1_shadow_cumulative.json"
    ),
    "latent_reactivation": Path(
        "evaluation/opening_rank1_shadow/latent_watch/"
        "latent_reactivation_forward.json"
    ),
    "btc_woori_history": Path(
        "evaluation/baseline_btc_woori_tech/historical/"
        "q12_v1_v2_historical_review.json"
    ),
}

QUESTIONS = (
    {
        "question_id": "A",
        "question": "\uc7a5\ucd08\ubc18 Rank-1 \uc131\uacf5\uacfc \uc2e4\ud328\ub97c \uac00\ub974\ub294 \uad6c\ubd84\uc790\ub294 \ubb34\uc5c7\uc778\uac00?",
        "decision_scope": "opening_rank1_discriminator",
    },
    {
        "question_id": "B",
        "question": "BTC \uac15\uc0c1\uc2b9\uc774 \uc6b0\ub9ac\uae30\uc220\ud22c\uc790 \uc0c1\uc2b9\uc73c\ub85c \uc5f0\uacb0\ub418\ub294 \uc870\uac74\uc740 \ubb34\uc5c7\uc778\uac00?",
        "decision_scope": "btc_woori_lead_lag",
    },
    {
        "question_id": "C",
        "question": "risk=HIGH\uc5d0\uc11c \ubcf4\ud1b5\uc8fc\ub294 \uc131\uacf5\ud558\uace0 ETF\ub294 \uc2e4\ud328\ud55c \uc774\uc720\ub294 \ubb34\uc5c7\uc778\uac00?",
        "decision_scope": "risk_high_asset_class_divergence",
    },
)

# Immutable candidate surface after 2026-08-27.
CANDIDATE_REGISTRY = (
    ("A", "IMMEDIATE_OPENING_PROBE", "Immediate opening response at +5m"),
    ("A", "CONFIRMED_RECURRENT_RANK", "Recurrent Rank confirmation at +30m"),
    ("A", "DISLOCATION_REBOUND", "Opening dislocation rebound at +60m"),
    ("A", "OPEN_0_20_RANK1_30M", "All 09:00-09:20 Rank-1 control"),
    ("A", "R1_FRESH_CHANGE_ACTIVATION_V1", "Fresh Top-change activation"),
    ("A", "R1_ENTRY_DAILY_MA5_20_EXTENDED_15M_V1", "Daily MA5/20 extended state"),
    ("A", "LATENT_REACTIVATION_FRESH_TRIGGER", "D+1-D+5 fresh reactivation"),
    ("A", "SAMSUNG_HYNIX_FIXED_UNIVERSE_TOP1", "Samsung/Hynix fixed control"),
    ("A", "STRATEGIST_STAGE2_REFRESH_AUTHORITY_V1", "Stage-2 pre/post Rank-1 value"),
    ("B", "BTC_WOORI_V2_ONLY_LOCAL_CONFIRMATION", "BTC lead plus Woori confirmation"),
    ("B", "BTC_STRONG_BULL_LOCAL_CONFIRMATION_V1", "Strong BTC plus Woori confirmation"),
    ("C", "R1_SCANNER_RISK_HIGH_30M_V1", "Scanner risk HIGH at +30m"),
    ("C", "HIGH_COMMON_SHORT_ALPHA_V1", "risk HIGH common-stock short alpha"),
    ("C", "TOP_VALUE_VOLUME_NEGATIVE_CONTROL_V1", "Liquidity-only negative control"),
)

CANDIDATE_IDS = tuple(row[1] for row in CANDIDATE_REGISTRY)

FEATURE_COLUMNS = (
    "market_regime",
    "asset_class",
    "rank_and_selection",
    "price_structure",
    "volume_and_flow",
    "external_signal",
    "agent_lineage",
    "horizon_and_exit",
    "cost_and_quality",
)

ROW_COLUMNS = (
    "question_id",
    "candidate_id",
    "status",
    "hypothesis",
    "feature_evidence",
    "target_horizon",
    "historical_evidence",
    "prospective_evidence",
    "sample_quality",
    "concentration",
    "net_metrics",
    "agent_attribution",
    "decision",
    "rationale",
    "next_action",
    "source_artifacts",
    "updated_through_day",
    # 2026-09-05 PRE-STEP5C cleanup (Codex audit item 4): additive fields
    # separating three previously-conflated meanings that `status` alone
    # cannot express -- see canonical.py::_operation_status /
    # _fixed_validation_status / _production_promotion_status. `status`
    # itself is unchanged; these never override or replace it.
    "operation_status",
    "fixed_validation_status",
    "production_promotion_status",
)

ALLOWED_STATUSES = (
    "DISCOVERY",
    "PROSPECTIVE",
    "REVIEW_READY",
    "PROMOTED",
    "REJECTED",
    "CLOSED",
)

TRACK_TO_QUESTION = {
    "OPENING_CONDITIONAL": "A",
    "SCANNER_REACTIVATION_HORIZON": "A",
    "LARGE_CAP_TWO_SYMBOL": "A",
    "BTC_WOORI": "B",
}

SETTLED_FINDINGS = (
    {
        "finding": "Enter every opening Rank-1",
        "status": "CLOSED",
        "reason": "The broad control failed concentration and robustness checks.",
    },
    {
        "finding": "Relax every entry guard",
        "status": "CLOSED",
        "reason": "Blocked candidates were not uniformly superior opportunities.",
    },
    {
        "finding": "Re-enter a symbol after a loss",
        "status": "CLOSED",
        "reason": "Repeated loss-condition entries degraded cumulative results.",
    },
    {
        "finding": "Extend every holding period",
        "status": "CLOSED",
        "reason": "Useful horizons differ by setup and EOD profit fade repeats.",
    },
)

TRACKS = QUESTIONS
