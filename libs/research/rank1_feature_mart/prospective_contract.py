from __future__ import annotations

import hashlib
import json
from typing import Any, Final


CONTRACT_VERSION: Final = "rank1_prospective_shadow.v1"
FROZEN_AT: Final = "2026-08-11"
FIRST_ELIGIBLE_DAY: Final = "2026-08-12"
FIXED_VALIDATION_DAYS: Final = 5
MINIMUM_DAY_SYMBOL_COUNT: Final = 10
MINIMUM_TARGET_COVERAGE: Final = 0.90
MINIMUM_PROFIT_FACTOR: Final = 1.20

CANDIDATES: Final = (
    {
        "candidate_id": "R1_SCANNER_RISK_HIGH_30M_V1",
        "responsibility": "SCANNER",
        "feature_path": "scanner.risk_band",
        "operator": "EQUALS",
        "expected_value": "HIGH",
        "target_horizon": "+30m",
        "calibration_direction": "POSITIVE",
        "future_patch_surface": "scanner lane_suitability only",
    },
    {
        "candidate_id": "R1_ENTRY_DAILY_MA5_20_EXTENDED_15M_V1",
        "responsibility": "ENTRY",
        "feature_path": "chart.daily_ma5_20_cross_state",
        "operator": "EQUALS",
        "expected_value": "POST_CROSS_EXTENDED",
        "target_horizon": "+15m",
        "calibration_direction": "POSITIVE",
        "future_patch_surface": "monitor entry timing only",
    },
)


def contract_payload() -> dict[str, Any]:
    base = {
        "schema_version": CONTRACT_VERSION,
        "behavior_effect": "NONE_OBSERVATION_ONLY",
        "frozen_at": FROZEN_AT,
        "first_eligible_day": FIRST_ELIGIBLE_DAY,
        "fixed_validation_days": FIXED_VALIDATION_DAYS,
        "minimum_day_symbol_count": MINIMUM_DAY_SYMBOL_COUNT,
        "minimum_target_coverage": MINIMUM_TARGET_COVERAGE,
        "minimum_profit_factor": MINIMUM_PROFIT_FACTOR,
        "candidates": [dict(item) for item in CANDIDATES],
    }
    canonical = json.dumps(base, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return {**base, "contract_sha256": hashlib.sha256(canonical.encode("ascii")).hexdigest()}
