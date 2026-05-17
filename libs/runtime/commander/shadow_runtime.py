from __future__ import annotations

from typing import Any, Dict


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def mark_strategist_skipped(
    shadow_runtime: Dict[str, Any],
    *,
    used_cached: bool,
) -> Dict[str, Any]:
    shadow_runtime["strategist_executed"] = False
    shadow_runtime["strategist_called"] = False
    shadow_runtime["llm_called_by_strategist"] = False
    shadow_runtime["used_cached_strategist"] = bool(used_cached)
    return shadow_runtime


def mark_strategist_executed(
    shadow_runtime: Dict[str, Any],
    state: Dict[str, Any],
    *,
    used_cached: bool = False,
) -> Dict[str, Any]:
    shadow_runtime["strategist_executed"] = True
    shadow_runtime["strategist_called"] = True
    shadow_runtime["used_cached_strategist"] = bool(used_cached)
    strategist_llm = state.get("strategist_llm") if isinstance(state.get("strategist_llm"), dict) else {}
    llm_status = str(strategist_llm.get("status") or strategist_llm.get("llm_status") or "").strip().lower()
    shadow_runtime["llm_called_by_strategist"] = bool(
        llm_status not in {"", "disabled"}
        or str(strategist_llm.get("prompt_ref") or "").strip()
        or str(strategist_llm.get("response_ref") or "").strip()
    )
    shadow_runtime["retry_count_estimate"] = max(0, _to_int(strategist_llm.get("attempts"), 1) - 1)
    return shadow_runtime


def reset_pre_buy_refresh_shadow(shadow_runtime: Dict[str, Any]) -> Dict[str, Any]:
    shadow_runtime["pre_buy_refresh_requested"] = False
    shadow_runtime["pre_buy_refresh_reason"] = ""
    shadow_runtime["pre_buy_refresh_context"] = {}
    return shadow_runtime


def reset_post_scanner_refresh_shadow(shadow_runtime: Dict[str, Any]) -> Dict[str, Any]:
    shadow_runtime["post_scanner_refresh_requested"] = False
    shadow_runtime["post_scanner_refresh_reason"] = ""
    shadow_runtime["post_scanner_refresh_context"] = {}
    return shadow_runtime


def mark_pre_buy_refresh_shadow(
    shadow_runtime: Dict[str, Any],
    cache_payload: Dict[str, Any],
) -> Dict[str, Any]:
    shadow_runtime["pre_buy_refresh_requested"] = True
    shadow_runtime["pre_buy_refresh_reason"] = str(
        cache_payload.get("refresh_signal")
        or cache_payload.get("strategist_refresh_reason")
        or cache_payload.get("reason")
        or ""
    )
    shadow_runtime["pre_buy_refresh_context"] = dict(cache_payload)
    return shadow_runtime


def mark_post_scanner_refresh_shadow(
    shadow_runtime: Dict[str, Any],
    *,
    decision: Dict[str, Any],
    refresh_context: Dict[str, Any],
    skipped: bool = False,
    skip_reason: str = "",
) -> Dict[str, Any]:
    shadow_runtime["post_scanner_refresh_requested"] = True
    shadow_runtime["post_scanner_refresh_reason"] = str(
        decision.get("strategist_refresh_reason")
        or refresh_context.get("refresh_signal")
        or ""
    )
    context = dict(refresh_context)
    if skipped:
        context["skipped"] = True
        context["skip_reason"] = str(skip_reason)
    shadow_runtime["post_scanner_refresh_context"] = context
    return shadow_runtime
