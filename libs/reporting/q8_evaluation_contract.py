from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from libs.runtime.quant.entry_lane_observation import build_entry_lane_observation


TRUSTED_FORWARD_MIN_COUNT = 100
TRUSTED_FORWARD_MIN_COVERAGE = 0.70
DUPLICATE_RATE_MAX = 0.75
PROMOTION_CANDIDATE_MIN_OBSERVED = 50
PROMOTION_CANDIDATE_MIN_DAYS = 2
FORWARD_MAX_OBSERVATION_DELAY_SEC = 180

CANONICAL_DEDUPE_KEY_FIELDS = ["day", "symbol", "baseline_epoch", "entry_lane_subtype"]

TRUST_GATE_STATUS_READY = "promotion_review_ready"
TRUST_GATE_STATUS_SAMPLE_BLOCKED = "promotion_blocked_sample_or_coverage"
TRUST_GATE_STATUS_NO_REPEATABLE_CANDIDATE = "promotion_blocked_no_repeatable_candidate"


def text_value(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"", "-", "none", "null", "unknown", "not_captured"} else text


def forward_base(row: Mapping[str, Any]) -> Dict[str, Any]:
    base = row.get("shadow_forward_base")
    return dict(base) if isinstance(base, Mapping) else {}


def candidate_day(row: Mapping[str, Any]) -> str:
    base = forward_base(row)
    raw_ts = text_value(base.get("baseline_raw_ts"))
    if len(raw_ts) >= 8 and raw_ts[:8].isdigit():
        return raw_ts[:8]
    generated = text_value(row.get("_payload_generated_at") or row.get("generated_at"))
    return generated[:10].replace("-", "") if len(generated) >= 10 else ""


def entry_lane_subtype(row: Mapping[str, Any]) -> str:
    observation = build_entry_lane_observation(row)
    lane = text_value(observation.get("primary_lane")) or "unknown"
    subtype = text_value(observation.get("subtype")) or "unknown"
    return f"{lane}:{subtype}"


def canonical_dedupe_key(row: Mapping[str, Any]) -> tuple[str, str, int, str]:
    base = forward_base(row)
    try:
        baseline_epoch = int(float(base.get("baseline_epoch") or 0))
    except Exception:
        baseline_epoch = 0
    return (
        candidate_day(row),
        text_value(row.get("symbol")).upper(),
        baseline_epoch,
        entry_lane_subtype(row),
    )


def dedupe_q8_candidates(rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, int, str]] = set()
    for row in rows:
        key = canonical_dedupe_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(row))
    return out


def promotion_candidate_is_repeatable(row: Mapping[str, Any]) -> bool:
    observed_count = int(row.get("observed_count") or 0)
    observed_day_count = int(row.get("observed_day_count") or 0)
    avg_return_5m = float(row.get("avg_return_5m_pct") or 0.0)
    avg_return_15m = float(row.get("avg_return_15m_pct") or 0.0)
    return (
        observed_count >= PROMOTION_CANDIDATE_MIN_OBSERVED
        and observed_day_count >= PROMOTION_CANDIDATE_MIN_DAYS
        and avg_return_5m > 0.0
        and avg_return_15m > 0.0
    )


def build_q8_trust_gate(
    *,
    raw_candidate_count: int,
    deduped_candidate_count: int,
    trusted_forward_count: int,
    trusted_forward_coverage: float,
    candidate_watchlist: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    duplicate_count = max(0, int(raw_candidate_count) - int(deduped_candidate_count))
    duplicate_rate = (
        round(float(duplicate_count) / float(raw_candidate_count), 4)
        if raw_candidate_count
        else 0.0
    )
    repeatable = [row for row in candidate_watchlist if promotion_candidate_is_repeatable(row)]
    reasons: List[str] = []
    if trusted_forward_count < TRUSTED_FORWARD_MIN_COUNT:
        reasons.append("trusted_forward_sample_below_100")
    if trusted_forward_coverage < TRUSTED_FORWARD_MIN_COVERAGE:
        reasons.append("trusted_forward_coverage_below_70pct")
    if duplicate_rate > DUPLICATE_RATE_MAX:
        reasons.append("duplicate_rate_above_75pct")
    if not repeatable:
        reasons.append("no_repeatable_promotion_watch_candidate")

    promotion_allowed = not reasons
    if promotion_allowed:
        status = TRUST_GATE_STATUS_READY
    elif "trusted_forward_sample_below_100" in reasons or "trusted_forward_coverage_below_70pct" in reasons:
        status = TRUST_GATE_STATUS_SAMPLE_BLOCKED
    else:
        status = TRUST_GATE_STATUS_NO_REPEATABLE_CANDIDATE

    return {
        "status": status,
        "promotion_allowed": bool(promotion_allowed),
        "block_reasons": reasons,
        "trusted_forward_count": int(trusted_forward_count),
        "trusted_forward_coverage": round(float(trusted_forward_coverage), 4),
        "duplicate_rate": duplicate_rate,
        "duplicate_count": duplicate_count,
        "minimums": {
            "trusted_forward_count": TRUSTED_FORWARD_MIN_COUNT,
            "trusted_forward_coverage": TRUSTED_FORWARD_MIN_COVERAGE,
            "duplicate_rate_max": DUPLICATE_RATE_MAX,
            "candidate_observed_count": PROMOTION_CANDIDATE_MIN_OBSERVED,
            "candidate_observed_day_count": PROMOTION_CANDIDATE_MIN_DAYS,
        },
    }


__all__ = [
    "CANONICAL_DEDUPE_KEY_FIELDS",
    "DUPLICATE_RATE_MAX",
    "FORWARD_MAX_OBSERVATION_DELAY_SEC",
    "PROMOTION_CANDIDATE_MIN_DAYS",
    "PROMOTION_CANDIDATE_MIN_OBSERVED",
    "TRUSTED_FORWARD_MIN_COUNT",
    "TRUSTED_FORWARD_MIN_COVERAGE",
    "build_q8_trust_gate",
    "candidate_day",
    "canonical_dedupe_key",
    "dedupe_q8_candidates",
    "entry_lane_subtype",
    "forward_base",
    "promotion_candidate_is_repeatable",
    "text_value",
]
