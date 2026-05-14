from __future__ import annotations

from typing import Any, Iterable, Mapping


ETF_ASSET_CLASSES = {
    "etf",
    "etn",
    "leveraged_etf",
    "inverse_etf",
    "active_etf",
    "futures_etf",
    "covered_call_etf",
    "tr_index_product",
}

DEFAULT_DISCOUNT_TRIGGER_PCT = -0.30
DEFAULT_DISCOUNT_STRONG_PCT = -1.00
DEFAULT_PREMIUM_TRIGGER_PCT = 0.30
DEFAULT_PREMIUM_STRONG_PCT = 1.00

_DEVIATION_KEYS = (
    "etf_deviation_pct",
    "nav_deviation_pct",
    "deviation_pct",
    "premium_discount_pct",
    "premium_discount_rate",
    "discount_premium_pct",
    "dstr_rt",
    "dstr_rate",
    "disparity_rate",
    "tracking_deviation_pct",
)
_ASSET_CLASS_KEYS = (
    "asset_class_detected",
    "asset_class",
    "asset_type",
    "instrument_type",
    "product_type",
)
_AMBIGUOUS_RAW_DEVIATION_SOURCES = {
    "dstr_rt",
    "dstr_rate",
    "raw.dstr_rt",
    "raw.dstr_rate",
}


def _to_float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        text = str(value).strip().replace(",", "").replace("%", "")
        if not text:
            return None
        if text.startswith("+"):
            text = text[1:]
        return float(text)
    except Exception:
        return None


def _norm_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if value < lo else hi if value > hi else value


def is_etf_asset_class(value: Any) -> bool:
    return _norm_text(value) in ETF_ASSET_CLASSES


def normalize_deviation_pct(value: Any) -> float | None:
    return _to_float_or_none(value)


def _iter_raw_rows(mapping: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    raw = mapping.get("raw")
    if isinstance(raw, Mapping):
        yield raw
        rows = raw.get("cntr_infr")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, Mapping):
                    yield row
    rows = mapping.get("cntr_infr")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, Mapping):
                yield row


def _pick_first(mapping: Mapping[str, Any], keys: Iterable[str]) -> tuple[Any, str]:
    for key in keys:
        if key in mapping and mapping.get(key) not in (None, ""):
            return mapping.get(key), key
    return None, ""


def _extract_from_mapping(mapping: Mapping[str, Any] | None) -> tuple[float | None, str]:
    if not isinstance(mapping, Mapping):
        return None, ""
    value, key = _pick_first(mapping, _DEVIATION_KEYS)
    pct = normalize_deviation_pct(value)
    if pct is not None:
        return pct, key
    for raw_row in _iter_raw_rows(mapping):
        value, key = _pick_first(raw_row, _DEVIATION_KEYS)
        pct = normalize_deviation_pct(value)
        if pct is not None:
            return pct, f"raw.{key}"
    return None, ""


def _extract_asset_class(contexts: Iterable[Mapping[str, Any]]) -> str:
    for context in contexts:
        value, _key = _pick_first(context, _ASSET_CLASS_KEYS)
        text = _norm_text(value)
        if text:
            return text
        candidate = context.get("candidate")
        if isinstance(candidate, Mapping):
            value, _key = _pick_first(candidate, _ASSET_CLASS_KEYS)
            text = _norm_text(value)
            if text:
                return text
    return ""


def score_etf_deviation_for_entry(
    deviation_pct: Any,
    *,
    discount_trigger_pct: float = DEFAULT_DISCOUNT_TRIGGER_PCT,
    discount_strong_pct: float = DEFAULT_DISCOUNT_STRONG_PCT,
) -> float:
    pct = normalize_deviation_pct(deviation_pct)
    if pct is None:
        return 0.0
    trigger = abs(float(discount_trigger_pct))
    strong = max(trigger + 1e-9, abs(float(discount_strong_pct)))
    discount = max(0.0, -float(pct))
    if discount < trigger:
        return 0.0
    return _clamp((discount - trigger) / (strong - trigger))


def score_etf_deviation_for_exit(
    deviation_pct: Any,
    *,
    premium_trigger_pct: float = DEFAULT_PREMIUM_TRIGGER_PCT,
    premium_strong_pct: float = DEFAULT_PREMIUM_STRONG_PCT,
) -> float:
    pct = normalize_deviation_pct(deviation_pct)
    if pct is None:
        return 0.0
    trigger = max(0.0, float(premium_trigger_pct))
    strong = max(trigger + 1e-9, float(premium_strong_pct))
    premium = max(0.0, float(pct))
    if premium < trigger:
        return 0.0
    return _clamp((premium - trigger) / (strong - trigger))


def extract_etf_deviation_signal(
    *,
    symbol: Any = "",
    candidate: Mapping[str, Any] | None = None,
    features: Mapping[str, Any] | None = None,
    quote: Mapping[str, Any] | None = None,
    state: Mapping[str, Any] | None = None,
    asset_class_detected: Any = "",
) -> dict[str, Any]:
    contexts: list[Mapping[str, Any]] = []
    for context in (features, candidate, quote):
        if isinstance(context, Mapping):
            contexts.append(context)
    sym = str(symbol or "").strip()
    if isinstance(state, Mapping) and sym:
        for map_key in ("symbol_metadata", "symbol_meta", "asset_metadata", "security_master"):
            meta_map = state.get(map_key)
            if isinstance(meta_map, Mapping) and isinstance(meta_map.get(sym), Mapping):
                contexts.append(meta_map.get(sym))  # type: ignore[arg-type]
    asset_class = _norm_text(asset_class_detected) or _extract_asset_class(contexts)
    pct: float | None = None
    source = ""
    for context in contexts:
        pct, source = _extract_from_mapping(context)
        if pct is not None:
            break
    is_etf_family = bool(is_etf_asset_class(asset_class))
    source_key = str(source or "").strip().lower()
    if pct is not None and not is_etf_family and source_key in _AMBIGUOUS_RAW_DEVIATION_SOURCES:
        pct = None
        source = ""
    available = pct is not None
    entry_score = score_etf_deviation_for_entry(pct)
    exit_score = score_etf_deviation_for_exit(pct)
    return {
        "symbol": sym,
        "available": available,
        "etf_deviation_pct": pct,
        "etf_deviation_source": source,
        "asset_class_detected": asset_class,
        "is_etf_family": is_etf_family,
        "entry_discount_score": float(entry_score),
        "exit_premium_score": float(exit_score),
        "discount_trigger_pct": float(DEFAULT_DISCOUNT_TRIGGER_PCT),
        "premium_trigger_pct": float(DEFAULT_PREMIUM_TRIGGER_PCT),
    }
