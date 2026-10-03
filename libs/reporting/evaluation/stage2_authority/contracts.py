from __future__ import annotations

from typing import Any, Mapping


SCHEMA_VERSION = "strategist_stage2_authority_review.v3"
PRIMARY_HORIZON = "+30m"
EVALUATION_HORIZONS = ("+5m", "+15m", "+30m", "+60m", "EOD")
LIVE_ROUND_TRIP_COST_PCT = 0.28
MIN_OBSERVATIONS = 20
MIN_DAYS = 2
MIN_MATERIAL_DELTA_PCT = 0.30
MIN_POSITIVE_RATE = 0.55
MAX_DEGRADING_POSITIVE_RATE = 0.45
MIN_PROMOTION_OBSERVATIONS = 50
MIN_PROMOTION_DAYS = 5
MAX_SINGLE_DAY_SHARE = 0.40
MIN_DIRECTIONAL_DAY_RATE = 0.60


def classify_paired_effect(metrics: Mapping[str, Any]) -> dict[str, Any]:
    count = int(metrics.get("comparison_count") or 0)
    day_count = int(metrics.get("day_count") or 0)
    delta = metrics.get("average_delta_pct")
    positive_rate = metrics.get("positive_delta_rate")
    if count < MIN_OBSERVATIONS or day_count < MIN_DAYS or delta is None or positive_rate is None:
        return {
            "state": "NOT_MEASURABLE",
            "reason": (
                f"requires {MIN_OBSERVATIONS} paired observations across {MIN_DAYS} days; "
                f"current={count}/{day_count}"
            ),
        }
    if float(delta) >= MIN_MATERIAL_DELTA_PCT and float(positive_rate) >= MIN_POSITIVE_RATE:
        return {
            "state": "VALUE_ADD",
            "reason": "paired cost-adjusted effect meets the fixed positive materiality contract",
        }
    if float(delta) <= -MIN_MATERIAL_DELTA_PCT and float(positive_rate) <= MAX_DEGRADING_POSITIVE_RATE:
        return {
            "state": "DEGRADING",
            "reason": "paired cost-adjusted effect meets the fixed negative materiality contract",
        }
    return {
        "state": "NEUTRAL",
        "reason": "paired effect is measurable but does not meet positive or negative materiality",
    }


def classify_promotion_eligibility(metrics: Mapping[str, Any], *, effect_state: str) -> dict[str, Any]:
    count = int(metrics.get("comparison_count") or 0)
    day_count = int(metrics.get("day_count") or 0)
    max_day_share = float(metrics.get("max_single_day_share") or 0.0)
    median_delta = metrics.get("median_delta_pct")
    directional_day_rate = (
        float(metrics.get("negative_day_rate") or 0.0)
        if effect_state == "DEGRADING"
        else float(metrics.get("positive_day_rate") or 0.0)
    )
    failures: list[str] = []
    if effect_state not in {"DEGRADING", "VALUE_ADD"}:
        failures.append(f"effect_state={effect_state}")
    if count < MIN_PROMOTION_OBSERVATIONS:
        failures.append(f"paired_observations={count}<{MIN_PROMOTION_OBSERVATIONS}")
    if day_count < MIN_PROMOTION_DAYS:
        failures.append(f"days={day_count}<{MIN_PROMOTION_DAYS}")
    if max_day_share > MAX_SINGLE_DAY_SHARE:
        failures.append(f"max_single_day_share={max_day_share:.1%}>{MAX_SINGLE_DAY_SHARE:.0%}")
    if directional_day_rate < MIN_DIRECTIONAL_DAY_RATE:
        failures.append(
            f"directional_day_rate={directional_day_rate:.1%}<{MIN_DIRECTIONAL_DAY_RATE:.0%}"
        )
    if median_delta is None:
        failures.append("median_delta=missing")
    elif effect_state == "DEGRADING" and float(median_delta) >= 0:
        failures.append(f"median_delta={float(median_delta):+.4f}%p is not negative")
    elif effect_state == "VALUE_ADD" and float(median_delta) <= 0:
        failures.append(f"median_delta={float(median_delta):+.4f}%p is not positive")
    return {
        "eligible": not failures,
        "state": "ELIGIBLE" if not failures else "INSUFFICIENT_STABILITY",
        "reason": "promotion stability contract met" if not failures else "; ".join(failures),
    }
