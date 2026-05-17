from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, Dict, List, Tuple

from graphs.nodes.skill_contracts import norm_symbol
from libs.runtime.scanner.theme_filter import (
    apply_avoid_theme_filter,
    apply_theme_filter,
    extract_avoid_themes,
    extract_selected_themes,
    extract_theme_symbol_index,
    extract_themes,
)
from libs.runtime.scanner_policy import resolve_scanner_runtime_policy
from libs.strategies.candidates.fallback_pool import is_static_fallback_pool
from libs.strategies.candidates.kiwoom_candidate_provider import build_kiwoom_candidate_rows


def to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def to_int(v: Any, default: int) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def extract_strategist_candidates(state: Dict[str, Any]) -> List[Any]:
    candidates = state.get("candidates")
    if isinstance(candidates, list) and candidates:
        return list(candidates)

    strategist_output = state.get("strategist_output")
    if isinstance(strategist_output, dict):
        from_output = strategist_output.get("candidates")
        if isinstance(from_output, list):
            return list(from_output)
    return []


def resolve_candidate_source(state: Dict[str, Any], policy: Dict[str, Any]) -> str:
    source_type = str((resolve_scanner_runtime_policy(state, policy) or {}).get("source_type") or "kiwoom").strip().lower()
    if source_type == "static":
        return "strategist"
    if source_type == "hybrid":
        return "auto"
    return "kiwoom"


def resolve_block_static_fallback(state: Dict[str, Any], policy: Dict[str, Any]) -> bool:
    return bool((resolve_scanner_runtime_policy(state, policy) or {}).get("block_static_when_empty"))


def resolve_strict_kiwoom_only(state: Dict[str, Any], policy: Dict[str, Any]) -> bool:
    return bool((resolve_scanner_runtime_policy(state, policy) or {}).get("strict_only"))


def resolve_scan_aggressiveness(state: Dict[str, Any]) -> float:
    commander_decision = state.get("commander_decision") if isinstance(state.get("commander_decision"), dict) else {}
    scanner_policy = commander_decision.get("scanner_policy") if isinstance(commander_decision.get("scanner_policy"), dict) else {}
    if scanner_policy.get("scan_aggressiveness") not in (None, ""):
        return max(0.0, to_float(scanner_policy.get("scan_aggressiveness")))
    adaptive_policy = commander_decision.get("adaptive_policy") if isinstance(commander_decision.get("adaptive_policy"), dict) else {}
    return max(0.0, to_float(adaptive_policy.get("scan_aggressiveness")))

def resolve_candidate_limit(state: Dict[str, Any], policy: Dict[str, Any]) -> int:
    raw = policy.get("candidate_k", policy.get("candidate_topk"))
    if raw not in (None, ""):
        return max(1, to_int(raw, 10))

    # Preserve explicit TOP_N_CANDIDATES if set by operator.
    env_topn_raw = os.getenv("TOP_N_CANDIDATES")
    if env_topn_raw not in (None, ""):
        return max(1, to_int(env_topn_raw, 10))

    # Default behavior: use full candidate pool size instead of fixed 5.
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    applied_scanner = applied_policy.get("scanner") if isinstance(applied_policy.get("scanner"), dict) else {}
    applied_candidate = applied_scanner.get("candidate") if isinstance(applied_scanner.get("candidate"), dict) else {}
    scanner_policy = policy.get("scanner") if isinstance(policy.get("scanner"), dict) else {}
    candidate_policy = scanner_policy.get("candidate") if isinstance(scanner_policy.get("candidate"), dict) else {}
    raw_pool = applied_candidate.get("top_pool")
    if raw_pool in (None, ""):
        raw_pool = candidate_policy.get("top_pool")
    if raw_pool in (None, ""):
        raw_pool = policy.get("top_candidate_pool")
    return max(1, to_int(raw_pool, 30))


def resolve_top_candidate_pool(state: Dict[str, Any], policy: Dict[str, Any], *, candidate_limit: int) -> int:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    raw = (
        (((applied_policy.get("scanner") or {}).get("candidate") or {}).get("top_pool"))
        if isinstance((applied_policy.get("scanner") or {}).get("candidate"), dict)
        else None
    )
    if raw is None and isinstance(policy.get("scanner"), dict):
        raw = (
            (((policy.get("scanner") or {}).get("candidate") or {}).get("top_pool"))
            if isinstance((policy.get("scanner") or {}).get("candidate"), dict)
            else None
        )
    if raw is None:
        raw = policy.get("top_candidate_pool")
    return max(candidate_limit, to_int(raw, 30))


def resolve_condition_limit(state: Dict[str, Any], policy: Dict[str, Any], *, top_pool: int) -> int:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    raw = (
        (((applied_policy.get("scanner") or {}).get("kiwoom") or {}).get("condition_limit"))
        if isinstance((applied_policy.get("scanner") or {}).get("kiwoom"), dict)
        else None
    )
    if raw is None and isinstance(policy.get("scanner"), dict):
        raw = (
            (((policy.get("scanner") or {}).get("kiwoom") or {}).get("condition_limit"))
            if isinstance((policy.get("scanner") or {}).get("kiwoom"), dict)
            else None
        )
    if raw is None:
        raw = policy.get("candidate_condition_limit")
    return max(top_pool, to_int(raw, 200))


def resolve_include_change_rate(state: Dict[str, Any], policy: Dict[str, Any]) -> bool:
    return bool((resolve_scanner_runtime_policy(state, policy) or {}).get("include_change_rate"))


def resolve_enable_theme_filter(policy: Dict[str, Any]) -> bool:
    if policy.get("enable_theme_filter") is not None:
        return is_trueish(policy.get("enable_theme_filter"))
    return is_trueish(os.getenv("ENABLE_THEME_FILTER", "true"))

def normalize_scanner_source_policy(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    out: Dict[str, Any] = {}
    for key in (
        "include_top_value",
        "include_top_volume",
        "include_change_rate",
        "include_condition_search",
        "include_sector_candidates",
        "include_watchlist",
    ):
        if value.get(key) is not None:
            out[key] = bool(value.get(key))
    for key in ("top_candidate_pool", "condition_limit"):
        if value.get(key) not in (None, ""):
            out[key] = max(0, to_int(value.get(key), 0))
    if isinstance(value.get("preferred_sources"), list):
        out["preferred_sources"] = [str(x).strip() for x in list(value.get("preferred_sources") or []) if str(x).strip()]
    if isinstance(value.get("source_weights"), dict):
        out["source_weights"] = {
            str(k).strip(): float(to_float(v))
            for k, v in dict(value.get("source_weights") or {}).items()
            if str(k).strip()
        }
    if value.get("reason") not in (None, ""):
        out["reason"] = str(value.get("reason") or "")
    return out


def build_kiwoom_candidates(
    state: Dict[str, Any],
    *,
    policy: Dict[str, Any],
    scanner_guidance_resolver: Callable[[Dict[str, Any]], Dict[str, Any]] | None = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    scanner_guidance = scanner_guidance_resolver(state) if callable(scanner_guidance_resolver) else {}
    source_policy = normalize_scanner_source_policy(scanner_guidance.get("scanner_source_policy"))
    candidate_limit = resolve_candidate_limit(state, policy)
    top_pool = resolve_top_candidate_pool(state, policy, candidate_limit=candidate_limit)
    if source_policy.get("top_candidate_pool"):
        top_pool = max(candidate_limit, int(source_policy.get("top_candidate_pool") or top_pool))
    condition_limit = resolve_condition_limit(state, policy, top_pool=top_pool)
    if source_policy.get("condition_limit") is not None:
        condition_limit = max(0, int(source_policy.get("condition_limit") or 0))
    scanner_runtime_policy = resolve_scanner_runtime_policy(state, policy)
    scan_aggressiveness = resolve_scan_aggressiveness(state)
    include_change_rate = resolve_include_change_rate(state, policy)
    if source_policy.get("include_change_rate") is not None:
        include_change_rate = bool(source_policy.get("include_change_rate"))
    enable_theme_filter = resolve_enable_theme_filter(policy)
    include_top_value = bool(source_policy.get("include_top_value", True))
    include_top_volume = bool(source_policy.get("include_top_volume", True))
    include_condition_search = bool(source_policy.get("include_condition_search", True))
    include_sector_candidates = bool(source_policy.get("include_sector_candidates", True))
    include_watchlist = bool(source_policy.get("include_watchlist", True))
    base_candidate_limit = int(candidate_limit)
    base_top_pool = int(top_pool)
    base_condition_limit = int(condition_limit)
    aggressive_source_expansion_used = False
    aggressive_source_expansion_slots = 0
    aggressive_source_expansion_sources: List[str] = []
    if scan_aggressiveness > 0.0:
        aggressive_source_expansion_used = True
        aggressive_source_expansion_slots = max(
            2,
            int(round(1.0 + min(3.0, float(scan_aggressiveness) * 40.0))),
        )
        candidate_limit = max(candidate_limit, base_candidate_limit + aggressive_source_expansion_slots)
        top_pool = max(top_pool, candidate_limit + aggressive_source_expansion_slots)
        condition_limit = max(condition_limit, top_pool + aggressive_source_expansion_slots)
        include_change_rate = True
        include_condition_search = True
        include_watchlist = True
        aggressive_source_expansion_sources = [
            "condition_search",
            "operator_watchlist",
            "top_change_rate",
            "strategist_backfill",
        ]
        expanded_weights = dict(source_policy.get("source_weights") or {})
        expanded_weights["condition_search"] = max(2.8, float(to_float(expanded_weights.get("condition_search"))))
        expanded_weights["operator_watchlist"] = max(1.4, float(to_float(expanded_weights.get("operator_watchlist"))))
        expanded_weights["top_change_rate"] = max(1.5, float(to_float(expanded_weights.get("top_change_rate"))))
        source_policy = dict(source_policy)
        source_policy.update(
            {
                "include_change_rate": True,
                "include_condition_search": True,
                "include_watchlist": True,
                "top_candidate_pool": int(top_pool),
                "condition_limit": int(condition_limit),
                "source_weights": expanded_weights,
            }
        )

    selected_themes, selected_theme_source = extract_selected_themes(state)
    themes_for_universe = list(selected_themes) if selected_themes else extract_themes(state)
    rows, meta = build_kiwoom_candidate_rows(
        state=state,
        top_pool=top_pool,
        condition_limit=condition_limit,
        include_change_rate=include_change_rate,
        include_top_value=include_top_value,
        include_top_volume=include_top_volume,
        include_condition_search=include_condition_search,
        themes=themes_for_universe,
        include_sector_candidates=include_sector_candidates,
        include_watchlist=include_watchlist,
        source_weights=dict(source_policy.get("source_weights") or {}),
    )
    raw_kiwoom_count = int(len(rows))
    themes = list(themes_for_universe)
    avoid_themes = extract_avoid_themes(state)
    theme_symbol_index = extract_theme_symbol_index(state, policy)
    rows, filter_meta = apply_theme_filter(
        rows,
        themes=themes,
        theme_symbol_index=theme_symbol_index,
        enable_theme_filter=enable_theme_filter,
    )
    rows, avoid_meta = apply_avoid_theme_filter(
        rows,
        avoid_themes=avoid_themes,
        theme_symbol_index=theme_symbol_index,
    )
    avoid_meta = dict(avoid_meta)
    avoid_meta.setdefault("avoid_filter_fallback_used", False)
    rows = rows[:candidate_limit]
    backfill_count = 0
    backfill_skipped = ""
    strict_kiwoom_only = resolve_strict_kiwoom_only(state, policy)
    relaxed_strict_mode = bool(strict_kiwoom_only and scan_aggressiveness > 0.0)
    backfill_allowed = raw_kiwoom_count > 0 and len(rows) < candidate_limit and (not strict_kiwoom_only or relaxed_strict_mode)
    if backfill_allowed:
        strategist_candidates = extract_strategist_candidates(state)
        if strategist_candidates and resolve_block_static_fallback(state, policy) and is_static_fallback_pool(strategist_candidates):
            strategist_candidates = []
            backfill_skipped = "static_fallback_blocked"
        existing = {norm_symbol(r.get("symbol")) for r in rows if isinstance(r, dict)}
        strategist_backfill_score = 0.10 + min(0.10, float(scan_aggressiveness))
        for cand in strategist_candidates:
            if isinstance(cand, dict):
                sym = norm_symbol(cand.get("symbol"))
                why = str(cand.get("why") or "strategist_backfill")
            else:
                sym = norm_symbol(cand)
                why = "strategist_backfill"
            if not sym or sym in existing:
                continue
            rows.append(
                {
                    "symbol": sym,
                    "why": why,
                    "sources": ["strategist_backfill"],
                    "source_scores": {"strategist_backfill": strategist_backfill_score},
                    "source_count": 1,
                    "rank_score": 0.0,
                    "universe_score": 0.0,
                    "trading_value_source_score": 0.0,
                    "trading_volume_source_score": 0.0,
                }
            )
            existing.add(sym)
            backfill_count += 1
            if len(rows) >= candidate_limit:
                break
    meta_out = dict(meta)
    meta_out.update(filter_meta)
    meta_out.update(avoid_meta)
    meta_out.update(
        {
            "themes": list(themes),
            "selected_themes": list(selected_themes),
            "selected_theme_source": str(selected_theme_source or ""),
            "avoid_themes": list(avoid_themes),
            "candidate_limit": int(candidate_limit),
            "candidate_count": int(len(rows)),
            "condition_limit": int(condition_limit),
            "top_candidate_pool": int(top_pool),
            "enable_theme_filter": bool(enable_theme_filter),
            "scanner_source_policy": dict(source_policy),
            "scanner_policy_source": str(scanner_runtime_policy.get("policy_source") or ""),
            "scanner_candidate_source": str(scanner_runtime_policy.get("source_type") or "kiwoom"),
            "scanner_strict_mode": bool(scanner_runtime_policy.get("strict_only")),
            "scanner_fallback_mode": str(scanner_runtime_policy.get("fallback_mode") or ""),
            "raw_kiwoom_count": int(raw_kiwoom_count),
            "backfill_used": bool(backfill_count > 0),
            "backfill_count": int(backfill_count),
            "backfill_skipped_reason": str(backfill_skipped or ""),
            "scan_aggressiveness": float(scan_aggressiveness),
            "strict_mode_relaxed_by_scan_aggressiveness": bool(relaxed_strict_mode and backfill_count > 0),
            "candidate_limit_base": int(base_candidate_limit),
            "candidate_limit_effective": int(candidate_limit),
            "top_candidate_pool_base": int(base_top_pool),
            "condition_limit_base": int(base_condition_limit),
            "aggressive_source_expansion_used": bool(aggressive_source_expansion_used),
            "aggressive_source_expansion_slots": int(aggressive_source_expansion_slots),
            "aggressive_source_expansion_sources": list(aggressive_source_expansion_sources),
        }
    )
    return rows, meta_out


def resolve_scanner_candidates(
    state: Dict[str, Any],
    policy: Dict[str, Any],
    *,
    scanner_guidance_resolver: Callable[[Dict[str, Any]], Dict[str, Any]] | None = None,
) -> Tuple[List[Any], Dict[str, Any]]:
    source = resolve_candidate_source(state, policy)
    scanner_runtime_policy = resolve_scanner_runtime_policy(state, policy)
    strategist_candidates = extract_strategist_candidates(state)

    if source == "strategist":
        return strategist_candidates, {
            "candidate_source": "strategist",
            "scanner_candidate_source": str(scanner_runtime_policy.get("source_type") or "static"),
            "scanner_policy_source": str(scanner_runtime_policy.get("policy_source") or ""),
            "scanner_strict_mode": bool(scanner_runtime_policy.get("strict_only")),
            "scanner_fallback_mode": str(scanner_runtime_policy.get("fallback_mode") or ""),
            "candidate_count": int(len(strategist_candidates)),
            "fallback_used": False,
        }

    kiwoom_rows, kiwoom_meta = build_kiwoom_candidates(
        state,
        policy=policy,
        scanner_guidance_resolver=scanner_guidance_resolver,
    )
    if kiwoom_rows:
        return kiwoom_rows, dict(kiwoom_meta)

    if source == "kiwoom" and resolve_strict_kiwoom_only(state, policy):
        strict_meta = dict(kiwoom_meta)
        strict_meta.update(
            {
                "candidate_source": "kiwoom",
                "scanner_candidate_source": str(scanner_runtime_policy.get("source_type") or "kiwoom"),
                "scanner_policy_source": str(scanner_runtime_policy.get("policy_source") or ""),
                "scanner_strict_mode": bool(scanner_runtime_policy.get("strict_only")),
                "scanner_fallback_mode": str(scanner_runtime_policy.get("fallback_mode") or ""),
                "candidate_count": 0,
                "fallback_used": False,
                "fallback_reason": "kiwoom_candidate_pool_empty_strict_mode",
                "strict_kiwoom_only": True,
            }
        )
        return [], strict_meta

    if strategist_candidates:
        if resolve_block_static_fallback(state, policy) and is_static_fallback_pool(strategist_candidates):
            blocked_meta = dict(kiwoom_meta)
            blocked_meta.update(
                {
                    "candidate_source": "kiwoom",
                    "scanner_candidate_source": str(scanner_runtime_policy.get("source_type") or "kiwoom"),
                    "scanner_policy_source": str(scanner_runtime_policy.get("policy_source") or ""),
                    "scanner_strict_mode": bool(scanner_runtime_policy.get("strict_only")),
                    "scanner_fallback_mode": str(scanner_runtime_policy.get("fallback_mode") or ""),
                    "candidate_count": 0,
                    "fallback_used": False,
                    "fallback_reason": "kiwoom_candidate_pool_empty_static_fallback_blocked",
                    "blocked_static_fallback": True,
                }
            )
            return [], blocked_meta
        fallback_meta = dict(kiwoom_meta)
        fallback_meta.update(
            {
                "candidate_source": "strategist_fallback",
                "scanner_candidate_source": str(scanner_runtime_policy.get("source_type") or "kiwoom"),
                "scanner_policy_source": str(scanner_runtime_policy.get("policy_source") or ""),
                "scanner_strict_mode": bool(scanner_runtime_policy.get("strict_only")),
                "scanner_fallback_mode": str(scanner_runtime_policy.get("fallback_mode") or ""),
                "candidate_count": int(len(strategist_candidates)),
                "fallback_used": True,
                "fallback_reason": "kiwoom_candidate_pool_empty",
            }
        )
        return strategist_candidates, fallback_meta

    if source == "auto":
        return strategist_candidates, {
            "candidate_source": "auto",
            "scanner_candidate_source": str(scanner_runtime_policy.get("source_type") or "hybrid"),
            "scanner_policy_source": str(scanner_runtime_policy.get("policy_source") or ""),
            "scanner_strict_mode": bool(scanner_runtime_policy.get("strict_only")),
            "scanner_fallback_mode": str(scanner_runtime_policy.get("fallback_mode") or ""),
            "candidate_count": int(len(strategist_candidates)),
            "fallback_used": False,
            "fallback_reason": "no_kiwoom_and_no_strategist_candidates",
        }

    empty_meta = dict(kiwoom_meta)
    empty_meta.update(
        {
            "candidate_source": "kiwoom",
            "scanner_candidate_source": str(scanner_runtime_policy.get("source_type") or "kiwoom"),
            "scanner_policy_source": str(scanner_runtime_policy.get("policy_source") or ""),
            "scanner_strict_mode": bool(scanner_runtime_policy.get("strict_only")),
            "scanner_fallback_mode": str(scanner_runtime_policy.get("fallback_mode") or ""),
            "candidate_count": 0,
            "fallback_used": False,
            "fallback_reason": "kiwoom_candidate_pool_empty",
        }
    )
    return [], empty_meta

