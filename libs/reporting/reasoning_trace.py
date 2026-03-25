from __future__ import annotations

from typing import Any, Dict

# Canonical reasoning snapshot source-of-truth:
# - state["reasoning_trace"]
# - persisted_state["latest_reasoning_trace"] (mirror for downstream reporting/readers)
# Reporting layers should prefer these snapshots when available and only derive
# from summaries as a fallback.

REASONING_TRACE_KEYS = (
    "commander_summary",
    "strategist_summary",
    "scanner_summary",
    "monitor_summary",
)

REASONING_PROVENANCE_KEYS = (
    "commander_context_source",
    "strategist_plan_source",
    "scanner_reason_source",
    "monitor_reason_source",
    "commander_source_ref",
    "strategist_source_ref",
    "scanner_source_ref",
    "monitor_source_ref",
    "shadow_used",
    "strategist_fallback_used",
    "source_priority",
)


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _normalize_summary(summary: Any, *, fallback_summary: str = "") -> Dict[str, Any]:
    obj = dict(summary or {}) if isinstance(summary, dict) else {}
    normalized_summary = _first_text(
        obj.get("summary"),
        obj.get("decision_summary"),
        obj.get("strategy_summary"),
        obj.get("selection_summary"),
        obj.get("entry_check_summary"),
        obj.get("reason_summary"),
        obj.get("monitor_reason"),
        fallback_summary,
    )
    if normalized_summary:
        obj["summary"] = normalized_summary
    return obj


def build_reasoning_trace_from_summaries(
    *,
    commander_summary: Dict[str, Any],
    strategist_summary: Dict[str, Any],
    scanner_summary: Dict[str, Any],
    monitor_summary: Dict[str, Any],
    market_context_human: Dict[str, Any] | None = None,
    scanner_reason_human: Dict[str, Any] | None = None,
    monitor_reason_human: Dict[str, Any] | None = None,
    operator_conclusion_human: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    market_context = dict(market_context_human or {})
    scanner_reason = dict(scanner_reason_human or {})
    monitor_reason = dict(monitor_reason_human or {})
    operator_conclusion = dict(operator_conclusion_human or {})
    return {
        "commander_summary": _normalize_summary(
            commander_summary,
            fallback_summary=_first_text(
                operator_conclusion.get("summary"),
                market_context.get("summary"),
            ),
        ),
        "strategist_summary": _normalize_summary(
            strategist_summary,
            fallback_summary=_first_text(market_context.get("summary")),
        ),
        "scanner_summary": _normalize_summary(
            scanner_summary,
            fallback_summary=_first_text(scanner_reason.get("summary")),
        ),
        "monitor_summary": _normalize_summary(
            monitor_summary,
            fallback_summary=_first_text(
                monitor_reason.get("summary"),
                operator_conclusion.get("summary"),
            ),
        ),
    }


def normalize_reasoning_trace_aliases(
    source: Dict[str, Any] | None,
    *,
    fallback: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    source_obj = dict(source or {})
    fallback_obj = dict(fallback or {})
    latest_raw = source_obj.get("latest_reasoning_trace") if isinstance(source_obj.get("latest_reasoning_trace"), dict) else {}
    legacy_raw = source_obj.get("reasoning_trace") if isinstance(source_obj.get("reasoning_trace"), dict) else {}
    out: Dict[str, Any] = {}
    for key in REASONING_TRACE_KEYS:
        fallback_summary_obj = fallback_obj.get(key) if isinstance(fallback_obj.get(key), dict) else {}
        summary_obj = (
            latest_raw.get(key)
            if isinstance(latest_raw.get(key), dict) and latest_raw.get(key)
            else legacy_raw.get(key)
            if isinstance(legacy_raw.get(key), dict)
            else {}
        )
        out[key] = _normalize_summary(summary_obj, fallback_summary=str(fallback_summary_obj.get("summary") or ""))
        for extra_key, extra_value in fallback_summary_obj.items():
            if extra_key not in out[key] or out[key].get(extra_key) in (None, "", [], {}):
                out[key][extra_key] = extra_value
    return out


def build_reasoning_provenance(
    *,
    commander_context_source: str = "",
    strategist_plan_source: str = "",
    scanner_reason_source: str = "",
    monitor_reason_source: str = "",
    commander_source_ref: str = "",
    strategist_source_ref: str = "",
    scanner_source_ref: str = "",
    monitor_source_ref: str = "",
    shadow_used: bool = False,
    strategist_fallback_used: bool = False,
    source_priority: list[Any] | None = None,
) -> Dict[str, Any]:
    return {
        "commander_context_source": str(commander_context_source or ""),
        "strategist_plan_source": str(strategist_plan_source or ""),
        "scanner_reason_source": str(scanner_reason_source or ""),
        "monitor_reason_source": str(monitor_reason_source or ""),
        "commander_source_ref": str(commander_source_ref or ""),
        "strategist_source_ref": str(strategist_source_ref or ""),
        "scanner_source_ref": str(scanner_source_ref or ""),
        "monitor_source_ref": str(monitor_source_ref or ""),
        "shadow_used": bool(shadow_used),
        "strategist_fallback_used": bool(strategist_fallback_used),
        "source_priority": [str(x or "") for x in list(source_priority or []) if str(x or "").strip()],
    }


def normalize_reasoning_provenance_aliases(
    source: Dict[str, Any] | None,
    *,
    fallback: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    source_obj = dict(source or {})
    fallback_obj = dict(fallback or {})
    latest_raw = (
        source_obj.get("latest_reasoning_trace_provenance")
        if isinstance(source_obj.get("latest_reasoning_trace_provenance"), dict)
        else {}
    )
    legacy_raw = source_obj.get("reasoning_provenance") if isinstance(source_obj.get("reasoning_provenance"), dict) else {}
    out = build_reasoning_provenance()
    for key in REASONING_PROVENANCE_KEYS:
        latest_has_value = key in latest_raw and latest_raw.get(key) not in (None, "", [], {})
        legacy_has_value = key in legacy_raw and legacy_raw.get(key) not in (None, "", [], {})
        if key in {"shadow_used", "strategist_fallback_used"}:
            if key in latest_raw:
                value = latest_raw.get(key)
            elif key in legacy_raw:
                value = legacy_raw.get(key)
            else:
                value = fallback_obj.get(key)
        elif key == "source_priority":
            latest_list = list(latest_raw.get(key) or []) if key in latest_raw else []
            legacy_list = list(legacy_raw.get(key) or []) if key in legacy_raw else []
            if latest_list:
                value = latest_list
            elif legacy_list:
                value = legacy_list
            else:
                value = fallback_obj.get(key)
        else:
            if latest_has_value:
                value = latest_raw.get(key)
            elif legacy_has_value:
                value = legacy_raw.get(key)
            else:
                value = fallback_obj.get(key)
        if key in {"shadow_used", "strategist_fallback_used"}:
            out[key] = bool(value)
        elif key == "source_priority":
            out[key] = [str(x or "") for x in list(value or []) if str(x or "").strip()]
        else:
            out[key] = str(value or "")
    return out
