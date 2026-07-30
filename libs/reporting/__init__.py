from __future__ import annotations

from importlib import import_module
from typing import Any


_LAZY_EXPORTS = {
    "generate_daily_report": (".daily_report", "generate_daily_report"),
    "notify_batch_result": (".alert_notifier", "notify_batch_result"),
    "build_batch_notification_payload": (
        ".alert_notifier",
        "build_batch_notification_payload",
    ),
    "generate_operator_daily_summary": (
        ".operator_visibility",
        "generate_operator_daily_summary",
    ),
    "generate_decision_story_report": (
        ".operator_visibility",
        "generate_decision_story_report",
    ),
    "generate_run_card_report": (
        ".operator_visibility",
        "generate_run_card_report",
    ),
    "generate_operator_visibility_bundle": (
        ".operator_visibility",
        "generate_operator_visibility_bundle",
    ),
    "generate_trade_explain_report": (
        ".trade_explain",
        "generate_trade_explain_report",
    ),
    "generate_reporter_analysis_report": (
        ".reporter_analysis",
        "generate_reporter_analysis_report",
    ),
    "build_ai_reporter_review": (
        ".reporter_ai_review",
        "build_ai_reporter_review",
    ),
    "generate_agent_pipeline_trace_report": (
        ".agent_pipeline_trace",
        "generate_agent_pipeline_trace_report",
    ),
    "generate_symbol_trade_report": (
        ".symbol_trade_report",
        "generate_symbol_trade_report",
    ),
}

__all__ = sorted(_LAZY_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value
