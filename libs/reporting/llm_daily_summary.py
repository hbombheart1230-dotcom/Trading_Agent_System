"""LLM-based daily report summary (M19-6).

This is intentionally best-effort and safely disabled unless explicitly enabled.

Usage:
  - state['policy']['use_llm_daily_report']=True

Safety:
  - DRY_RUN=1 => returns mock or empty (never calls network)
  - If OPENROUTER_API_KEY is missing => returns empty
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from libs.llm.llm_router import LLMRouter


def _is_dry_run() -> bool:
    return str(os.getenv("DRY_RUN", "0")).strip() in ("1", "true", "True")


def _build_messages(state: Dict[str, Any], policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    day = str(state.get("eod_day") or policy.get("day") or "")
    report = dict(state.get("daily_report") or {})
    approvals = report.get("approvals")
    denials = report.get("denials")
    runs = report.get("runs")

    # Keep prompt compact; we only need a short manager-friendly summary.
    sys = {
        "role": "system",
        "content": (
            "You are a trading system reporter. "
            "Summarize the day's automated decisions succinctly in Korean. "
            "No financial advice. Use bullet points." 
        ),
    }
    user = {
        "role": "user",
        "content": (
            f"Day: {day}\n"
            f"approvals: {approvals}\n"
            f"denials: {denials}\n"
            f"runs: {runs}\n\n"
            "Write a short summary (max 6 bullets) and a one-line takeaway."
        ),
    }
    return [sys, user]


def summarize_daily_report(*, state: Dict[str, Any], policy: Dict[str, Any]) -> str:
    """Return summary text or empty string.

    Test hooks:
      - state['mock_llm_daily_summary'] => returned as-is
    """
    mock = state.get("mock_llm_daily_summary")
    if isinstance(mock, str):
        return mock

    if _is_dry_run():
        return ""

    router = LLMRouter.from_env()
    if router.client is None:
        return ""

    messages = _build_messages(state, policy)
    llm_policy = dict(policy.get("llm") or {})
    # allow role specific overrides (optional)
    llm_policy.setdefault("max_tokens", 256)
    llm_policy.setdefault("temperature", 0.2)
    return router.chat("reporter", messages, policy=llm_policy).strip()
