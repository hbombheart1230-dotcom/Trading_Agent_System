from __future__ import annotations

import hashlib
import json
from typing import Any, Final


CONTRACT_VERSION: Final = "rank1_fresh_change_activation.v1"
FROZEN_AT: Final = "2026-08-12"
FIRST_ELIGIBLE_DAY: Final = "2026-08-13"
MINIMUM_INDEPENDENT_DAY_SYMBOLS: Final = 5
MAXIMUM_VALID_DAYS: Final = 10
TARGET_HORIZON: Final = "+15m"
MINIMUM_TARGET_COVERAGE: Final = 0.90


def contract_payload() -> dict[str, Any]:
    base = {
        "schema_version": CONTRACT_VERSION,
        "behavior_effect": "NONE_OBSERVATION_ONLY",
        "frozen_at": FROZEN_AT,
        "first_eligible_day": FIRST_ELIGIBLE_DAY,
        "minimum_independent_day_symbols": MINIMUM_INDEPENDENT_DAY_SYMBOLS,
        "maximum_valid_days": MAXIMUM_VALID_DAYS,
        "target_horizon": TARGET_HORIZON,
        "minimum_target_coverage": MINIMUM_TARGET_COVERAGE,
        "candidate": {
            "candidate_id": "R1_FRESH_CHANGE_ACTIVATION_V1",
            "required_conditions": [
                "opening Rank-1",
                "scanner.source_top_change_rate == true",
            ],
            "descriptive_subgroups": [
                "scanner.theme_match",
                "scanner.directional_component_count >= 4",
                "chart.completed_return_1m_pct > 0",
                "chart.above_vwap",
                "scanner.prior_rank1_observations_5m > 0",
                "execution_evidence.quote_status",
            ],
            "future_patch_surface": "scanner lane_suitability only",
        },
    }
    canonical = json.dumps(base, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return {
        **base,
        "contract_sha256": hashlib.sha256(canonical.encode("ascii")).hexdigest(),
    }
