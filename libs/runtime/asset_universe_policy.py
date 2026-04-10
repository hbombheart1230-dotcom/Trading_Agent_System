from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from libs.core.symbols import normalize_symbol


COMMON_STOCK_ONLY_ASSET_TYPE = "common_stock_only"
ETF_ETN_EXCLUSION_REASON = "etf_or_etn_not_allowed"

_NAME_FIELDS = (
    "name",
    "display_name",
    "issue_name",
    "symbol_name",
    "stock_name",
    "item_name",
    "security_name",
    "instrument_name",
    "kor_name",
    "hts_kor_isnm",
    "stk_nm",
    "isu_nm",
)
_CLASS_FIELDS = (
    "asset_class_detected",
    "asset_class",
    "asset_type",
    "instrument_type",
    "security_type",
    "product_type",
    "product_category",
    "instrument_category",
    "market_category",
    "issue_type",
)
_SYMBOL_METADATA_MAP_KEYS = (
    "symbol_metadata",
    "symbol_meta",
    "asset_metadata",
    "instrument_metadata",
    "security_master",
    "market_metadata",
)
_BLOCKED_ASSET_CLASSES = {
    "etf",
    "etn",
    "leveraged_etf",
    "inverse_etf",
    "active_etf",
    "futures_etf",
    "covered_call_etf",
    "tr_index_product",
}

_KR_LEVERAGED = "\ub808\ubc84\ub9ac\uc9c0"
_KR_INVERSE = "\uc778\ubc84\uc2a4"
_KR_ACTIVE = "\uc561\ud2f0\ube0c"
_KR_FUTURES = "\uc120\ubb3c"
_KR_COVERED_CALL = "\ucee4\ubc84\ub4dc\ucf5c"
_KR_COMMON_STOCK = "\ubcf4\ud1b5\uc8fc"
_KR_STOCK = "\uc8fc\uc2dd"
_ETF_BRAND_PREFIXES = (
    "TIGER ",
    "KODEX ",
    "KOSEF ",
    "KBSTAR ",
    "HANARO ",
    "ARIRANG ",
    "TIMEFOLIO ",
    "ACE ",
    "PLUS ",
    "RISE ",
    "SOL ",
)
_REMOTE_SYMBOL_PROFILE_CACHE: Dict[str, Dict[str, Any]] = {}


def _is_trueish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")



def _read_nested(root: Dict[str, Any], *path: str) -> Any:
    cursor: Any = root
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    return cursor



def _pick_value(*pairs: Tuple[str, Any]) -> Tuple[Any, str]:
    for source, value in pairs:
        if value not in (None, ""):
            return value, source
    return None, "default"



def _normalize_text(value: Any) -> str:
    return str(value or "").strip()



def _normalize_symbol(value: Any) -> str:
    return normalize_symbol(value)


def _lookup_remote_symbol_profile(symbol: str) -> Dict[str, Any]:
    normalized_symbol = _normalize_symbol(symbol)
    if not normalized_symbol:
        return {}
    cached = _REMOTE_SYMBOL_PROFILE_CACHE.get(normalized_symbol)
    if isinstance(cached, dict) and cached:
        return dict(cached)
    try:
        from libs.read.kiwoom_price_reader import KiwoomPriceReader

        payload = KiwoomPriceReader.from_env().get_stock_info_payload(normalized_symbol)
    except Exception:
        payload = {}
    if isinstance(payload, dict) and payload:
        _REMOTE_SYMBOL_PROFILE_CACHE[normalized_symbol] = dict(payload)
        return dict(payload)
    return {}



def _find_value_recursive(obj: Any, keys: Sequence[str], *, max_depth: int = 3) -> Any:
    if max_depth < 0:
        return None
    if isinstance(obj, dict):
        for key in keys:
            value = obj.get(key)
            if value not in (None, ""):
                return value
        for value in obj.values():
            nested = _find_value_recursive(value, keys, max_depth=max_depth - 1)
            if nested not in (None, ""):
                return nested
    elif isinstance(obj, list):
        for value in obj[:6]:
            nested = _find_value_recursive(value, keys, max_depth=max_depth - 1)
            if nested not in (None, ""):
                return nested
    return None



def _iter_context_candidates(
    *,
    symbol: str,
    candidate: Optional[Mapping[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    market_quotes: Optional[Mapping[str, Dict[str, Any]]] = None,
) -> Iterable[Dict[str, Any]]:
    seen_ids: set[int] = set()

    def _yield_obj(obj: Any) -> Iterable[Dict[str, Any]]:
        if not isinstance(obj, dict):
            return []
        obj_id = id(obj)
        if obj_id in seen_ids:
            return []
        seen_ids.add(obj_id)
        return [dict(obj)]

    if isinstance(candidate, Mapping):
        for item in _yield_obj(candidate):
            yield item

    if isinstance(state, dict):
        selected = state.get("selected")
        if isinstance(selected, dict) and _normalize_symbol(selected.get("symbol")) == symbol:
            for item in _yield_obj(selected):
                yield item

        scanner_output = state.get("scanner_output")
        if isinstance(scanner_output, dict):
            selected_candidate = scanner_output.get("selected_candidate")
            if isinstance(selected_candidate, dict) and _normalize_symbol(selected_candidate.get("symbol")) == symbol:
                for item in _yield_obj(selected_candidate):
                    yield item
            for bucket_key in ("ranked_candidates", "watch_candidates"):
                rows = scanner_output.get(bucket_key)
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    if isinstance(row, dict) and _normalize_symbol(row.get("symbol")) == symbol:
                        for item in _yield_obj(row):
                            yield item

        for map_key in _SYMBOL_METADATA_MAP_KEYS:
            raw_map = state.get(map_key)
            if not isinstance(raw_map, dict):
                continue
            raw_row = raw_map.get(symbol)
            if isinstance(raw_row, dict):
                for item in _yield_obj(raw_row):
                    yield item

    if isinstance(market_quotes, Mapping):
        quote = market_quotes.get(symbol)
        if isinstance(quote, dict):
            for item in _yield_obj(quote):
                yield item



def _classify_from_explicit_metadata(contexts: Sequence[Dict[str, Any]]) -> Tuple[str, str, str]:
    explicit_pairs = (
        ("is_etn", "etn"),
        ("etn", "etn"),
        ("is_inverse", "inverse_etf"),
        ("inverse", "inverse_etf"),
        ("is_leveraged", "leveraged_etf"),
        ("leveraged", "leveraged_etf"),
        ("is_active", "active_etf"),
        ("active", "active_etf"),
        ("is_etf", "etf"),
        ("etf", "etf"),
    )
    for context in contexts:
        for field, asset_class in explicit_pairs:
            if _is_trueish(_find_value_recursive(context, (field,), max_depth=2)):
                return asset_class, "metadata", field

        value = _find_value_recursive(context, _CLASS_FIELDS, max_depth=3)
        text = _normalize_text(value).lower()
        if not text:
            continue
        if "etn" in text:
            return "etn", "metadata", "asset_type"
        if "lever" in text or _KR_LEVERAGED in text:
            return "leveraged_etf", "metadata", "asset_type"
        if "inverse" in text or _KR_INVERSE in text:
            return "inverse_etf", "metadata", "asset_type"
        if "active" in text or _KR_ACTIVE in text:
            return "active_etf", "metadata", "asset_type"
        if "covered" in text or _KR_COVERED_CALL in text:
            return "covered_call_etf", "metadata", "asset_type"
        if "future" in text or _KR_FUTURES in text:
            return "futures_etf", "metadata", "asset_type"
        if text == "tr" or "total return" in text:
            return "tr_index_product", "metadata", "asset_type"
        if "etf" in text:
            return "etf", "metadata", "asset_type"
        if any(token in text for token in ("common", "stock", "equity", _KR_COMMON_STOCK, _KR_STOCK)):
            return "common_stock", "metadata", "asset_type"
    return "", "", ""



def _classify_from_name(name: str) -> str:
    text = _normalize_text(name)
    if not text:
        return ""
    upper = text.upper()
    padded = f" {upper} "
    if any(upper.startswith(prefix) for prefix in _ETF_BRAND_PREFIXES):
        return "etf"
    if "ETN" in upper:
        return "etn"
    if _KR_COVERED_CALL in text or "COVERED CALL" in upper:
        return "covered_call_etf"
    if _KR_LEVERAGED in text or "LEVERAGE" in upper:
        return "leveraged_etf"
    if _KR_INVERSE in text or "INVERSE" in upper:
        return "inverse_etf"
    if _KR_ACTIVE in text or " ACTIVE " in padded:
        return "active_etf"
    if _KR_FUTURES in text or " FUTURES " in padded or " FUTURE " in padded:
        return "futures_etf"
    if " TR " in padded or upper.endswith(" TR") or upper.startswith("TR "):
        return "tr_index_product"
    if "ETF" in upper:
        return "etf"
    return "common_stock"



def resolve_universe_runtime_policy(
    state: Dict[str, Any],
    policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    policy = policy if isinstance(policy, dict) else {}
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    applied_universe = applied_policy.get("universe") if isinstance(applied_policy.get("universe"), dict) else {}
    universe_policy = policy.get("universe") if isinstance(policy.get("universe"), dict) else {}

    asset_type_raw, asset_type_source = _pick_value(
        ("commander_applied_policy", _read_nested(applied_universe, "asset_type")),
        ("state_fallback", state.get("asset_universe_type")),
        ("policy_universe", _read_nested(universe_policy, "asset_type")),
        ("policy_flat_fallback", policy.get("asset_type")),
    )
    asset_type = _normalize_text(asset_type_raw).lower() or COMMON_STOCK_ONLY_ASSET_TYPE
    return {
        "asset_type": asset_type,
        "common_stock_only": asset_type == COMMON_STOCK_ONLY_ASSET_TYPE,
        "policy_source": asset_type_source if asset_type_source != "default" else "default_common_stock_only",
    }



def inspect_asset_universe_candidate(
    *,
    symbol: Any,
    candidate: Optional[Mapping[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    policy: Optional[Dict[str, Any]] = None,
    market_quotes: Optional[Mapping[str, Dict[str, Any]]] = None,
    allow_remote_lookup: bool = False,
) -> Dict[str, Any]:
    candidate_symbol = candidate.get("symbol") if isinstance(candidate, Mapping) else None
    normalized_symbol = _normalize_symbol(symbol or candidate_symbol)
    runtime_policy = resolve_universe_runtime_policy(state or {}, policy if isinstance(policy, dict) else None)
    contexts = list(
        _iter_context_candidates(
            symbol=normalized_symbol,
            candidate=candidate,
            state=state if isinstance(state, dict) else None,
            market_quotes=market_quotes if isinstance(market_quotes, Mapping) else None,
        )
    )

    asset_class_detected = ""
    detection_source = ""
    detection_field = ""
    detected_name = ""

    asset_class_detected, detection_source, detection_field = _classify_from_explicit_metadata(contexts)
    if not asset_class_detected:
        for context in contexts:
            name_value = _find_value_recursive(context, _NAME_FIELDS, max_depth=3)
            detected_name = _normalize_text(name_value)
            if not detected_name:
                continue
            asset_class_detected = _classify_from_name(detected_name)
            if asset_class_detected:
                detection_source = "name_heuristic"
                detection_field = "name"
                break

    if not asset_class_detected and allow_remote_lookup and normalized_symbol:
        remote_profile = _lookup_remote_symbol_profile(normalized_symbol)
        if isinstance(remote_profile, dict) and remote_profile:
            contexts = list(contexts) + [dict(remote_profile)]
            if isinstance(state, dict):
                symbol_metadata = state.get("symbol_metadata")
                if not isinstance(symbol_metadata, dict):
                    symbol_metadata = {}
                    state["symbol_metadata"] = symbol_metadata
                if normalized_symbol not in symbol_metadata:
                    symbol_metadata[normalized_symbol] = dict(remote_profile)
            asset_class_detected, detection_source, detection_field = _classify_from_explicit_metadata(contexts)
            if not asset_class_detected:
                name_value = _find_value_recursive(remote_profile, _NAME_FIELDS, max_depth=2)
                detected_name = _normalize_text(name_value)
                if detected_name:
                    asset_class_detected = _classify_from_name(detected_name)
                    if asset_class_detected:
                        detection_source = "name_heuristic"
                        detection_field = "remote_symbol_profile"

    if not asset_class_detected:
        asset_class_detected = "unknown"
        detection_source = "fallback"
        detection_field = ""

    excluded = bool(runtime_policy.get("common_stock_only")) and asset_class_detected in _BLOCKED_ASSET_CLASSES
    return {
        "symbol": normalized_symbol,
        "asset_policy_type": str(runtime_policy.get("asset_type") or COMMON_STOCK_ONLY_ASSET_TYPE),
        "asset_policy_source": str(runtime_policy.get("policy_source") or "default_common_stock_only"),
        "asset_class_detected": str(asset_class_detected),
        "detection_source": str(detection_source or "fallback"),
        "detection_field": str(detection_field or ""),
        "detected_name": detected_name,
        "excluded_by_asset_policy": bool(excluded),
        "exclusion_reason": ETF_ETN_EXCLUSION_REASON if excluded else "",
    }



def apply_asset_universe_filter(
    candidates: Sequence[Any],
    *,
    state: Dict[str, Any],
    policy: Optional[Dict[str, Any]] = None,
    market_quotes: Optional[Mapping[str, Dict[str, Any]]] = None,
) -> Tuple[List[Any], Dict[str, Any]]:
    runtime_policy = resolve_universe_runtime_policy(state, policy if isinstance(policy, dict) else None)
    kept: List[Any] = []
    excluded_rows: List[Dict[str, Any]] = []
    evaluated = 0

    for item in list(candidates or []):
        symbol = _normalize_symbol(item.get("symbol")) if isinstance(item, dict) else _normalize_symbol(item)
        if not symbol:
            continue
        evaluated += 1
        inspection = inspect_asset_universe_candidate(
            symbol=symbol,
            candidate=item if isinstance(item, dict) else None,
            state=state,
            policy=policy,
            market_quotes=market_quotes,
        )
        if inspection.get("excluded_by_asset_policy"):
            excluded_rows.append(
                {
                    "symbol": symbol,
                    "asset_class_detected": str(inspection.get("asset_class_detected") or ""),
                    "detection_source": str(inspection.get("detection_source") or ""),
                    "exclusion_reason": str(inspection.get("exclusion_reason") or ETF_ETN_EXCLUSION_REASON),
                    "detected_name": str(inspection.get("detected_name") or ""),
                }
            )
            continue
        if isinstance(item, dict):
            enriched = dict(item)
            enriched.setdefault("asset_class_detected", str(inspection.get("asset_class_detected") or ""))
            enriched.setdefault("detection_source", str(inspection.get("detection_source") or ""))
            enriched.setdefault("excluded_by_asset_policy", False)
            enriched.setdefault("exclusion_reason", "")
            if inspection.get("detected_name") and not enriched.get("name"):
                enriched["name"] = str(inspection.get("detected_name") or "")
            kept.append(enriched)
        else:
            kept.append(item)

    meta = {
        "asset_universe_policy": str(runtime_policy.get("asset_type") or COMMON_STOCK_ONLY_ASSET_TYPE),
        "asset_universe_policy_source": str(runtime_policy.get("policy_source") or "default_common_stock_only"),
        "asset_policy_filter_applied": bool(runtime_policy.get("common_stock_only")),
        "asset_policy_candidate_evaluated_count": int(evaluated),
        "asset_policy_excluded_count": int(len(excluded_rows)),
        "asset_policy_excluded_symbols": [str(row.get("symbol") or "") for row in excluded_rows[:20]],
        "asset_policy_exclusions": list(excluded_rows[:20]),
        "asset_policy_filter_reason": ETF_ETN_EXCLUSION_REASON if excluded_rows else "",
    }
    return kept, meta
