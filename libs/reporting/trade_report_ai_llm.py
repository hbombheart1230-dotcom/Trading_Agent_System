from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from libs.llm.json_response import parse_llm_json_response
from libs.reporting.llm_artifacts import classify_llm_exception, make_attempt


def run_trade_report_llm_attempts(
    *,
    router: Any,
    story_input: Dict[str, Any],
    messages: List[Dict[str, str]],
    current_policy: Dict[str, Any],
    retry_max: int,
    retry_token_budget: int,
    retry_backoff_sec: float,
    hard_timeout_sec: Optional[float],
    chosen_model: str,
    resolved_model: str,
    execution_observability: Dict[str, Any],
    router_chat_with_hard_timeout: Callable[..., str],
    trade_report_parse_meta: Callable[[Any, Optional[Dict[str, Any]]], Dict[str, Any]],
    trade_report_language_meta: Callable[[Dict[str, Any]], Dict[str, Any]],
    build_repair_messages: Callable[..., List[Dict[str, str]]],
) -> Dict[str, Any]:
    attempts: List[Dict[str, Any]] = []
    final_status = "error"
    final_reason = ""
    final_error = ""
    parsed: Optional[Dict[str, Any]] = None
    best_partial: Dict[str, Any] = {}
    best_partial_meta: Dict[str, Any] = {}
    raw = ""
    current_messages = list(messages)

    for attempt_index in range(retry_max + 1):
        step = "primary" if attempt_index == 0 else f"retry_{attempt_index}"
        needs_korean_repair = False
        t0 = time.perf_counter()
        try:
            raw = router_chat_with_hard_timeout(
                router,
                "trade_report",
                current_messages,
                policy=current_policy,
                hard_timeout_sec=hard_timeout_sec,
            )
        except Exception as exc:
            final_latency_ms = int((time.perf_counter() - t0) * 1000)
            final_status = classify_llm_exception(exc)
            final_reason = f"trade_report_ai_exception:{type(exc).__name__}:{exc}"
            final_error = f"{type(exc).__name__}:{exc}"
            attempts.append(
                make_attempt(
                    step=step,
                    messages=current_messages,
                    raw_response_text=f"ERROR:{final_error}",
                    parsed_output={},
                    model=chosen_model or resolved_model,
                    latency_ms=final_latency_ms,
                    status=final_status,
                    meta={"role": "ai_trade_report", "error": final_error, **execution_observability},
                )
            )
        else:
            final_latency_ms = int((time.perf_counter() - t0) * 1000)
            parse_result = parse_llm_json_response(raw)
            candidate = (
                parse_result.get("full_object")
                if isinstance(parse_result.get("full_object"), dict)
                else parse_result.get("partial_object")
            )
            candidate = dict(candidate) if isinstance(candidate, dict) else {}
            parse_meta = trade_report_parse_meta(raw, candidate)
            language_meta = (
                trade_report_language_meta(candidate)
                if candidate
                else {
                    "language_sample_count": 0,
                    "language_hangul_chars": 0,
                    "language_latin_chars": 0,
                    "language_english_like_count": 0,
                    "requires_korean_repair": False,
                }
            )
            if not bool(parse_result.get("raw_nonempty")):
                final_status = "empty_response"
                final_reason = "trade_report_ai returned an empty response"
                attempts.append(
                    make_attempt(
                        step=step,
                        messages=current_messages,
                        raw_response_text=raw,
                        parsed_output={},
                        model=chosen_model or resolved_model,
                        latency_ms=final_latency_ms,
                        status=final_status,
                        meta={"role": "ai_trade_report", "error": final_reason, **parse_meta, **language_meta, **execution_observability},
                    )
                )
            elif bool(parse_result.get("is_full")) and not parse_meta.get("required_keys_missing"):
                if bool(language_meta.get("requires_korean_repair")) and attempt_index < retry_max:
                    final_status = "partial"
                    final_reason = "trade_report_ai returned valid JSON but human-readable sections remained mostly English"
                    needs_korean_repair = True
                    attempts.append(
                        make_attempt(
                            step=step,
                            messages=current_messages,
                            raw_response_text=raw,
                            parsed_output=candidate,
                            model=chosen_model or resolved_model,
                            latency_ms=final_latency_ms,
                            status=final_status,
                            meta={"role": "ai_trade_report", "error": final_reason, **parse_meta, **language_meta, **execution_observability},
                        )
                    )
                else:
                    parsed = candidate
                    final_reason = ""
                    final_status = "ok"
                    attempts.append(
                        make_attempt(
                            step=step,
                            messages=current_messages,
                            raw_response_text=raw,
                            parsed_output=parsed,
                            model=chosen_model or resolved_model,
                            latency_ms=final_latency_ms,
                            status=final_status,
                            meta={"role": "ai_trade_report", **parse_meta, **language_meta, **execution_observability},
                        )
                    )
                    break
            elif bool(parse_result.get("is_partial")) and candidate and not parse_meta.get("required_keys_missing"):
                if attempt_index < retry_max:
                    final_status = "partial"
                    final_reason = "trade_report_ai returned a complete JSON object with extra non-JSON text; retrying strict JSON-only regeneration"
                    needs_korean_repair = bool(language_meta.get("requires_korean_repair"))
                    attempts.append(
                        make_attempt(
                            step=step,
                            messages=current_messages,
                            raw_response_text=raw,
                            parsed_output=candidate,
                            model=chosen_model or resolved_model,
                            latency_ms=final_latency_ms,
                            status=final_status,
                            meta={"role": "ai_trade_report", "error": final_reason, **parse_meta, **language_meta, **execution_observability},
                        )
                    )
                else:
                    parsed = candidate
                    final_status = "ok"
                    final_reason = ""
                    attempts.append(
                        make_attempt(
                            step=step,
                            messages=current_messages,
                            raw_response_text=raw,
                            parsed_output=parsed,
                            model=chosen_model or resolved_model,
                            latency_ms=final_latency_ms,
                            status=final_status,
                            meta={
                                "role": "ai_trade_report",
                                "finish_reason": "complete_json_extracted_after_protocol_deviation",
                                **parse_meta,
                                **language_meta,
                                **execution_observability,
                            },
                        )
                    )
                    break
            elif candidate:
                best_partial = dict(candidate)
                best_partial_meta = dict(parse_meta)
                final_status = "partial"
                missing = list(parse_meta.get("required_keys_missing") or [])
                if bool(parse_result.get("is_partial")):
                    final_reason = "trade_report_ai returned truncated or partial JSON"
                elif missing:
                    final_reason = f"trade_report_ai response is missing required keys: {', '.join(missing)}"
                else:
                    final_reason = "trade_report_ai response was incomplete"
                attempts.append(
                    make_attempt(
                        step=step,
                        messages=current_messages,
                        raw_response_text=raw,
                        parsed_output=candidate,
                        model=chosen_model or resolved_model,
                        latency_ms=final_latency_ms,
                        status=final_status,
                        meta={"role": "ai_trade_report", "error": final_reason, **parse_meta, **language_meta, **execution_observability},
                    )
                )
            else:
                final_status = "parse_error"
                final_reason = "trade_report_ai returned non-JSON response"
                attempts.append(
                    make_attempt(
                        step=step,
                        messages=current_messages,
                        raw_response_text=raw,
                        parsed_output={},
                        model=chosen_model or resolved_model,
                        latency_ms=final_latency_ms,
                        status=final_status,
                        meta={"role": "ai_trade_report", "error": final_reason, **parse_meta, **language_meta, **execution_observability},
                    )
                )
        if attempt_index < retry_max:
            if final_status in {"parse_error", "partial"}:
                current_messages = build_repair_messages(
                    story_input,
                    raw,
                    sparse=(attempt_index + 1) >= retry_max,
                    enforce_korean=needs_korean_repair,
                )
            current_policy = {
                **current_policy,
                "temperature": 0.0,
                "max_tokens": max(800, retry_token_budget),
            }
            if retry_backoff_sec > 0.0:
                time.sleep(float(retry_backoff_sec))

    return {
        "attempts": attempts,
        "parsed": parsed,
        "best_partial": best_partial,
        "best_partial_meta": best_partial_meta,
        "raw": raw,
        "final_status": final_status,
        "final_reason": final_reason,
        "final_error": final_error,
    }
