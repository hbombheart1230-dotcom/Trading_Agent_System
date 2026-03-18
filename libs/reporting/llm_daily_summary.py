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
import time
from typing import Any, Dict, List

from libs.llm.model_names import normalize_openrouter_model_name
from libs.llm.llm_router import LLMRouter
from libs.reporting.llm_artifacts import build_llm_response_artifact, classify_llm_exception, make_attempt


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
    summary, _artifact = summarize_daily_report_with_artifact(state=state, policy=policy)
    return summary


def summarize_daily_report_with_artifact(*, state: Dict[str, Any], policy: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    """Return summary text or empty string.

    Test hooks:
      - state['mock_llm_daily_summary'] => returned as-is
    """
    day = str(state.get("eod_day") or policy.get("day") or "")
    run_id = str(state.get("run_id") or "")
    trade_id = str(state.get("trade_id") or "")
    messages = _build_messages(state, policy)
    llm_policy = dict(policy.get("llm") or {})
    env_model = normalize_openrouter_model_name(
        os.getenv("DAILY_REPORT_LLM_MODEL", "")
        or os.getenv("OPENROUTER_MODEL_DAILY_REPORT", "")
        or os.getenv("OPENROUTER_MODEL_REPORTER_FINAL", "")
        or ""
    )
    llm_policy.setdefault("max_tokens", 256)
    llm_policy.setdefault("temperature", 0.2)
    if env_model and not str(llm_policy.get("model") or "").strip():
        llm_policy["model"] = env_model
    model = normalize_openrouter_model_name(llm_policy.get("model") or env_model or "openrouter/auto")
    retry_max = max(0, int(float(str(os.getenv("DAILY_REPORT_LLM_RETRY_MAX", "2")).strip() or "2")))

    mock = state.get("mock_llm_daily_summary")
    if isinstance(mock, str):
        artifact = build_llm_response_artifact(
            component="daily_report",
            run_id=run_id,
            trade_id=trade_id,
            day=day,
            status="fallback",
            attempts=[],
            parsed_output={"summary": mock},
            model_info={"provider": "OpenRouter", "model": model},
            meta={"reason": "mock_llm_daily_summary"},
        )
        return mock, artifact

    if _is_dry_run():
        artifact = build_llm_response_artifact(
            component="daily_report",
            run_id=run_id,
            trade_id=trade_id,
            day=day,
            status="fallback",
            attempts=[],
            parsed_output={},
            model_info={"provider": "OpenRouter", "model": model},
            meta={"reason": "dry_run"},
        )
        return "", artifact

    router = LLMRouter.from_env()
    if router.client is None:
        artifact = build_llm_response_artifact(
            component="daily_report",
            run_id=run_id,
            trade_id=trade_id,
            day=day,
            status="fallback",
            attempts=[],
            parsed_output={},
            model_info={"provider": "OpenRouter", "model": model},
            meta={"reason": "llm_client_unavailable"},
        )
        return "", artifact

    attempts: List[Dict[str, Any]] = []
    raw = ""
    final_status = "error"
    final_reason = ""
    for attempt_index in range(retry_max + 1):
        step = "primary" if attempt_index == 0 else f"retry_{attempt_index}"
        t0 = time.perf_counter()
        try:
            raw = router.chat("daily_report", messages, policy=llm_policy).strip()
        except Exception as exc:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            final_status = classify_llm_exception(exc)
            final_reason = f"{type(exc).__name__}:{exc}"
            attempts.append(
                make_attempt(
                    step=step,
                    messages=messages,
                    raw_response_text=f"ERROR:{final_reason}",
                    parsed_output={},
                    model=model,
                    latency_ms=latency_ms,
                    status=final_status,
                    meta={"role": "daily_report", "error": final_reason},
                )
            )
        else:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            if raw:
                final_status = "ok"
                attempts.append(
                    make_attempt(
                        step=step,
                        messages=messages,
                        raw_response_text=raw,
                        parsed_output={"summary": raw},
                        model=model,
                        latency_ms=latency_ms,
                        status="ok",
                        meta={"role": "daily_report"},
                    )
                )
                artifact = build_llm_response_artifact(
                    component="daily_report",
                    run_id=run_id,
                    trade_id=trade_id,
                    day=day,
                    status="ok",
                    attempts=attempts,
                    parsed_output={"summary": raw},
                    model_info={"provider": "OpenRouter", "model": model},
                    latency_ms=sum(int(row.get("latency_ms") or 0) for row in attempts),
                )
                return raw, artifact
            final_status = "empty_response"
            final_reason = "daily_report_llm_empty_response"
            attempts.append(
                make_attempt(
                    step=step,
                    messages=messages,
                    raw_response_text=raw,
                    parsed_output={},
                    model=model,
                    latency_ms=latency_ms,
                    status="empty_response",
                    meta={"role": "daily_report", "error": final_reason},
                )
            )
        llm_policy["temperature"] = 0.0

    artifact = build_llm_response_artifact(
        component="daily_report",
        run_id=run_id,
        trade_id=trade_id,
        day=day,
        status=final_status,
        attempts=attempts,
        parsed_output={},
        model_info={"provider": "OpenRouter", "model": model},
        latency_ms=sum(int(row.get("latency_ms") or 0) for row in attempts),
        meta={"reason": final_reason, "error": final_reason},
    )
    return "", artifact
