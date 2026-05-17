from __future__ import annotations

from typing import Any, Dict, List, Tuple

from libs.core.symbols import normalize_symbol


def to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def candidate_theme_match(row: Dict[str, Any]) -> Any:
    candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else {}
    components = row.get("components") if isinstance(row.get("components"), dict) else {}
    sources = [str(x or "").strip() for x in list(candidate.get("sources") or []) if str(x or "").strip()]
    if "sector_theme" in sources:
        return True
    return bool(to_float(components.get("theme_boost_component")) > 0.0)


def extract_themes(state: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    seen = set()

    def add_many(values: Any) -> None:
        if not isinstance(values, list):
            return
        for row in values:
            t = str(row or "").strip().lower()
            if not t or t in seen:
                continue
            seen.add(t)
            out.append(t)

    scanner_guidance = state.get("scanner_guidance")
    if isinstance(scanner_guidance, dict):
        add_many(scanner_guidance.get("selected_themes"))
    add_many(state.get("selected_themes"))
    add_many(state.get("themes"))
    add_many(state.get("top_themes"))
    strategist_output = state.get("strategist_output")
    if isinstance(strategist_output, dict):
        add_many(strategist_output.get("selected_themes"))
        add_many(strategist_output.get("themes"))
    return out


def extract_selected_themes(state: Dict[str, Any]) -> Tuple[List[str], str]:
    out: List[str] = []
    seen = set()

    def add_many(values: Any, source: str) -> str:
        if not isinstance(values, list):
            return ""
        added_source = ""
        for row in values:
            if isinstance(row, dict):
                raw = row.get("theme") or row.get("theme_name") or row.get("name")
            else:
                raw = row
            t = str(raw or "").strip().lower()
            if not t or t in seen:
                continue
            seen.add(t)
            out.append(t)
            added_source = added_source or source
        return added_source

    source = ""
    scanner_guidance = state.get("scanner_guidance")
    if isinstance(scanner_guidance, dict):
        source = add_many(scanner_guidance.get("selected_themes"), "scanner_guidance.selected_themes") or source
        strategy = scanner_guidance.get("theme_strategy") if isinstance(scanner_guidance.get("theme_strategy"), dict) else {}
        source = add_many(strategy.get("selected_themes"), "scanner_guidance.theme_strategy") or source
    source = add_many(state.get("selected_themes"), "state.selected_themes") or source
    strategist_output = state.get("strategist_output")
    if isinstance(strategist_output, dict):
        source = add_many(strategist_output.get("selected_themes"), "strategist_output.selected_themes") or source
        strategy = strategist_output.get("theme_strategy") if isinstance(strategist_output.get("theme_strategy"), dict) else {}
        source = add_many(strategy.get("selected_themes"), "strategist_output.theme_strategy") or source
    return out, source


def extract_avoid_themes(state: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    seen = set()

    def add_many(values: Any) -> None:
        if not isinstance(values, list):
            return
        for row in values:
            t = str(row or "").strip().lower()
            if not t or t in seen:
                continue
            seen.add(t)
            out.append(t)

    add_many(state.get("avoid_themes"))
    strategist_output = state.get("strategist_output")
    if isinstance(strategist_output, dict):
        add_many(strategist_output.get("avoid_themes"))
    scanner_guidance = state.get("scanner_guidance")
    if isinstance(scanner_guidance, dict):
        add_many(scanner_guidance.get("avoid_themes"))
    return out


def extract_theme_symbol_index(state: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, set[str]]:
    idx: Dict[str, set[str]] = {}

    def add_map(raw: Any) -> None:
        if not isinstance(raw, dict):
            return
        for theme_name, symbols in raw.items():
            key = str(theme_name or "").strip().lower()
            if not key:
                continue
            bucket = idx.setdefault(key, set())
            if isinstance(symbols, list):
                for sym in symbols:
                    s = normalize_symbol(sym)
                    if s:
                        bucket.add(s)

    add_map(state.get("theme_map"))
    add_map(policy.get("theme_map"))
    add_map(state.get("sector_map"))
    add_map(policy.get("sector_map"))
    return idx


def apply_theme_filter(
    rows: List[Dict[str, Any]],
    *,
    themes: List[str],
    theme_symbol_index: Dict[str, set[str]],
    enable_theme_filter: bool,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not rows:
        return rows, {"theme_filter_applied": False, "theme_filter_reason": "no_rows", "matched_theme_count": 0}
    if not themes:
        return rows, {"theme_filter_applied": False, "theme_filter_reason": "no_themes", "matched_theme_count": 0}
    if not theme_symbol_index:
        return rows, {"theme_filter_applied": False, "theme_filter_reason": "theme_index_missing", "matched_theme_count": 0}

    matched_theme_count = 0
    allowed: set[str] = set()
    for theme in themes:
        syms = theme_symbol_index.get(str(theme or "").strip().lower()) or set()
        if syms:
            matched_theme_count += 1
            allowed.update(set(syms))

    if not allowed:
        return rows, {
            "theme_filter_applied": False,
            "theme_filter_reason": "theme_not_mapped",
            "matched_theme_count": int(matched_theme_count),
            "theme_matched_symbols": [],
        }

    if not bool(enable_theme_filter):
        return rows, {
            "theme_filter_applied": False,
            "theme_filter_reason": "disabled",
            "matched_theme_count": int(matched_theme_count),
            "theme_matched_symbols": sorted(list(allowed)),
        }

    filtered = [r for r in rows if normalize_symbol(r.get("symbol")) in allowed]
    if not filtered:
        return rows, {
            "theme_filter_applied": False,
            "theme_filter_reason": "empty_after_filter_fallback",
            "matched_theme_count": int(matched_theme_count),
            "theme_matched_symbols": sorted(list(allowed)),
        }

    return filtered, {
        "theme_filter_applied": True,
        "theme_filter_reason": "",
        "matched_theme_count": int(matched_theme_count),
        "theme_matched_symbols": sorted(list(allowed)),
    }


def apply_avoid_theme_filter(
    rows: List[Dict[str, Any]],
    *,
    avoid_themes: List[str],
    theme_symbol_index: Dict[str, set[str]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not rows:
        return rows, {"avoid_filter_applied": False, "avoid_filter_reason": "no_rows", "avoid_theme_count": 0}
    if not avoid_themes:
        return rows, {"avoid_filter_applied": False, "avoid_filter_reason": "no_avoid_themes", "avoid_theme_count": 0}
    if not theme_symbol_index:
        return rows, {"avoid_filter_applied": False, "avoid_filter_reason": "theme_index_missing", "avoid_theme_count": 0}

    excluded_symbols: set[str] = set()
    matched = 0
    for t in avoid_themes:
        key = str(t or "").strip().lower()
        syms = theme_symbol_index.get(key) or set()
        if syms:
            matched += 1
            excluded_symbols.update(set(syms))

    if not excluded_symbols:
        return rows, {
            "avoid_filter_applied": False,
            "avoid_filter_reason": "avoid_theme_not_mapped",
            "avoid_theme_count": int(matched),
            "avoid_matched_symbols": [],
        }

    filtered = [r for r in rows if normalize_symbol(r.get("symbol")) not in excluded_symbols]
    if not filtered:
        return filtered, {
            "avoid_filter_applied": True,
            "avoid_filter_reason": "empty_after_filter",
            "avoid_theme_count": int(matched),
            "avoid_matched_symbols": sorted(list(excluded_symbols)),
            "avoid_filtered_out_count": int(len(rows)),
        }
    return filtered, {
        "avoid_filter_applied": True,
        "avoid_filter_reason": "",
        "avoid_theme_count": int(matched),
        "avoid_matched_symbols": sorted(list(excluded_symbols)),
        "avoid_filtered_out_count": int(max(0, len(rows) - len(filtered))),
    }

