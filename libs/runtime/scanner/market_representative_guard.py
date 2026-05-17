from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

from libs.core.symbols import normalize_symbol


def clamp(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))


def to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def to_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def norm01(x: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return clamp((float(x) - float(lo)) / (float(hi) - float(lo)), 0.0, 1.0)


def policy_float(value: Any, default: float) -> float:
    if value in (None, ""):
        return float(default)
    return float(to_float(value))


def policy_int(value: Any, default: int) -> int:
    if value in (None, ""):
        return int(default)
    return int(to_int(value, default))


def policy_bool(value: Any, default: bool = False) -> bool:
    if value in (None, ""):
        return bool(default)
    if isinstance(value, bool):
        return bool(value)
    return is_trueish(value)


def normalize_symbol_list(value: Any) -> List[str]:
    raw_values: List[Any]
    if isinstance(value, str):
        raw_values = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = []
    out: List[str] = []
    seen = set()
    for raw in raw_values:
        symbol = normalize_symbol(raw)
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        out.append(symbol)
    return out


def default_market_representative_guard_policy() -> Dict[str, Any]:
    return {
        "enabled": True,
        "symbols": ["005930", "000660"],
        "penalty": 0.04,
        "max_penalty": 0.12,
        "near_tie_gap": 0.06,
        "top_value_dominance_min": 0.55,
        "weak_confirmation_max": 99,
        "strong_confirmation_min": 2,
        "bypass_when_strong_confirmation": False,
        "apply_when_top_value_only": True,
        "policy_source": "scanner_default",
    }


def resolve_market_representative_guard_policy(raw_policy: Any) -> Dict[str, Any]:
    raw = dict(raw_policy or {}) if isinstance(raw_policy, Mapping) else {}
    symbols = normalize_symbol_list(
        raw.get("symbols")
        or raw.get("market_representative_symbols")
        or raw.get("representative_symbols")
    )
    enabled = policy_bool(raw.get("enabled"), False) and bool(symbols)
    penalty = max(0.0, policy_float(raw.get("penalty"), 0.04))
    max_penalty = max(penalty, policy_float(raw.get("max_penalty"), 0.12))
    return {
        "enabled": bool(enabled),
        "symbols": symbols,
        "penalty": float(min(penalty, max_penalty)),
        "max_penalty": float(max_penalty),
        "near_tie_gap": max(0.0, policy_float(raw.get("near_tie_gap"), 0.06)),
        "top_value_dominance_min": clamp(
            policy_float(raw.get("top_value_dominance_min"), 0.55),
            0.0,
            1.0,
        ),
        "weak_confirmation_max": max(0, policy_int(raw.get("weak_confirmation_max"), 1)),
        "strong_confirmation_min": max(1, policy_int(raw.get("strong_confirmation_min"), 2)),
        "bypass_when_strong_confirmation": policy_bool(
            raw.get("bypass_when_strong_confirmation"),
            True,
        ),
        "apply_when_top_value_only": policy_bool(raw.get("apply_when_top_value_only"), True),
        "policy_source": str(raw.get("policy_source") or "commander"),
    }


def market_representative_confirmation_sources(row: Dict[str, Any]) -> List[str]:
    candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else {}
    score_breakdown = row.get("score_breakdown") if isinstance(row.get("score_breakdown"), dict) else {}
    components = row.get("components") if isinstance(row.get("components"), dict) else {}
    sources = {str(x or "").strip().lower() for x in list(candidate.get("sources") or []) if str(x or "").strip()}
    confirmations: List[str] = []

    def add(name: str, condition: bool) -> None:
        if condition and name not in confirmations:
            confirmations.append(name)

    add(
        "theme",
        "sector_theme" in sources
        or to_float(score_breakdown.get("theme_boost")) > 0.0
        or to_float(components.get("theme_boost_component")) > 0.0,
    )
    add(
        "momentum",
        "top_change_rate" in sources
        or to_float(score_breakdown.get("momentum")) >= 0.03
        or to_float(components.get("momentum_component")) >= 0.25,
    )
    add(
        "trend",
        to_float(score_breakdown.get("trend")) >= 0.03
        or to_float(components.get("trend_component")) >= 0.25,
    )
    add(
        "news",
        to_float(score_breakdown.get("sentiment")) >= 0.01
        or to_float(components.get("sentiment_component")) >= 0.15
        or to_float(components.get("news_sentiment")) >= 0.15,
    )
    add(
        "volume",
        "top_volume" in sources
        or to_float(score_breakdown.get("volume_surge")) >= 0.02
        or to_float(components.get("volume_surge_component")) >= 0.20,
    )
    add(
        "intraday_strength",
        to_float(score_breakdown.get("intraday_strength")) >= 0.03
        or to_float(components.get("intraday_strength_component")) >= 0.25,
    )
    return confirmations


def market_representative_top_value_dominance(row: Dict[str, Any], *, threshold: float) -> bool:
    candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else {}
    score_breakdown = row.get("score_breakdown") if isinstance(row.get("score_breakdown"), dict) else {}
    components = row.get("components") if isinstance(row.get("components"), dict) else {}
    sources = {str(x or "").strip().lower() for x in list(candidate.get("sources") or []) if str(x or "").strip()}
    source_scores = candidate.get("source_scores") if isinstance(candidate.get("source_scores"), dict) else {}
    top_value_component = to_float(components.get("trading_value_component"))
    if top_value_component <= 0.0 and source_scores.get("top_value") not in (None, ""):
        top_value_component = norm01(to_float(source_scores.get("top_value")), 0.0, 2.0)
    if sources and sources.issubset({"top_value"}):
        return top_value_component >= min(0.10, float(threshold))
    if "top_value" in sources and top_value_component >= float(threshold):
        return True
    trading_value_score = max(0.0, to_float(score_breakdown.get("trading_value")))
    positive_scores = [
        max(0.0, to_float(score_breakdown.get(key)))
        for key in (
            "momentum",
            "trend",
            "volume_surge",
            "intraday_strength",
            "theme_boost",
            "sentiment",
            "cross_section_rank",
        )
    ]
    strongest_non_value = max(positive_scores) if positive_scores else 0.0
    return bool(
        top_value_component >= float(threshold)
        and trading_value_score > 0.0
        and trading_value_score >= strongest_non_value
    )


def apply_market_representative_guard(
    rows: List[Dict[str, Any]],
    *,
    raw_policy: Any,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    policy = resolve_market_representative_guard_policy(raw_policy)
    meta: Dict[str, Any] = {
        "enabled": bool(policy.get("enabled")),
        "applied": False,
        "policy": dict(policy),
        "symbol": "",
        "penalty": 0.0,
        "score_gap": 0.0,
        "top_value_dominance": False,
        "confirmation_sources": [],
        "before_top": [],
        "after_top": [],
        "skipped_reason": "",
        "reason": "",
    }
    if not bool(policy.get("enabled")):
        meta["skipped_reason"] = "disabled"
        return rows, meta
    if len(rows or []) < 2:
        meta["skipped_reason"] = "insufficient_candidates"
        return rows, meta

    symbols = set(str(x or "").strip() for x in list(policy.get("symbols") or []) if str(x or "").strip())
    top = rows[0]
    runner_up = rows[1]
    top_symbol = normalize_symbol(top.get("symbol"))
    meta["before_top"] = [
        {"symbol": str((row or {}).get("symbol") or ""), "score_total": float(to_float((row or {}).get("score_total") or (row or {}).get("score")))}
        for row in rows[:3]
        if isinstance(row, dict)
    ]
    if top_symbol not in symbols:
        meta["symbol"] = top_symbol
        meta["skipped_reason"] = "top_not_market_representative"
        meta["after_top"] = list(meta["before_top"])
        return rows, meta

    top_score = to_float(top.get("score_total") if top.get("score_total") is not None else top.get("score"))
    runner_score = to_float(
        runner_up.get("score_total") if runner_up.get("score_total") is not None else runner_up.get("score")
    )
    score_gap = max(0.0, top_score - runner_score)
    confirmations = market_representative_confirmation_sources(top)
    top_value_dominant = market_representative_top_value_dominance(
        top,
        threshold=float(policy.get("top_value_dominance_min") or 0.55),
    )
    meta.update(
        {
            "symbol": top_symbol,
            "score_gap": float(score_gap),
            "top_value_dominance": bool(top_value_dominant),
            "confirmation_sources": list(confirmations),
        }
    )
    if bool(policy.get("bypass_when_strong_confirmation")) and len(confirmations) >= int(policy.get("strong_confirmation_min") or 2):
        meta["skipped_reason"] = "strong_confirmation"
        meta["after_top"] = list(meta["before_top"])
        return rows, meta
    if not top_value_dominant:
        meta["skipped_reason"] = "not_top_value_dominant"
        meta["after_top"] = list(meta["before_top"])
        return rows, meta
    if len(confirmations) > int(policy.get("weak_confirmation_max") or 1):
        meta["skipped_reason"] = "confirmation_not_weak"
        meta["after_top"] = list(meta["before_top"])
        return rows, meta
    if score_gap > float(policy.get("near_tie_gap") or 0.0):
        meta["skipped_reason"] = "score_gap_exceeded"
        meta["after_top"] = list(meta["before_top"])
        return rows, meta

    base_penalty = float(policy.get("penalty") or 0.0)
    prior_penalty = max(0.0, -to_float(top.get("symbol_prior_adjustment")))
    penalty = min(float(policy.get("max_penalty") or base_penalty), base_penalty + prior_penalty)
    if penalty <= 0.0:
        meta["skipped_reason"] = "zero_penalty"
        meta["after_top"] = list(meta["before_top"])
        return rows, meta

    adjusted_top = dict(top)
    adjusted_score = top_score - penalty
    adjusted_top["score_total"] = float(adjusted_score)
    adjusted_top["score"] = float(adjusted_score)
    score_breakdown = dict(adjusted_top.get("score_breakdown") or {})
    score_breakdown["market_representative_guard"] = -float(penalty)
    adjusted_top["score_breakdown"] = score_breakdown
    adjusted_top["market_representative_guard_applied"] = True
    adjusted_top["market_representative_guard_penalty"] = float(penalty)
    adjusted_top["market_representative_guard_reason"] = (
        f"{top_symbol} top_value-dominant near-tie with weak confirmation"
    )
    adjusted_top["market_representative_confirmation_sources"] = list(confirmations)
    adjusted_rows = [adjusted_top, *list(rows[1:])]
    adjusted_rows.sort(
        key=lambda r: (
            float(r.get("score_total") or 0.0),
            float(r.get("confidence") or 0.0),
            -float(r.get("risk_score") or 0.0),
        ),
        reverse=True,
    )
    meta.update(
        {
            "applied": True,
            "penalty": float(penalty),
            "reason": str(adjusted_top.get("market_representative_guard_reason") or ""),
            "after_top": [
                {
                    "symbol": str((row or {}).get("symbol") or ""),
                    "score_total": float(to_float((row or {}).get("score_total") or (row or {}).get("score"))),
                }
                for row in adjusted_rows[:3]
                if isinstance(row, dict)
            ],
        }
    )
    return adjusted_rows, meta

