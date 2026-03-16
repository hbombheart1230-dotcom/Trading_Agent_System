from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from libs.llm.llm_router import LLMRouter
from libs.research.evidence_ledger import record_llm_prompt, record_llm_response, record_raw_input


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "1" if default else "0")).strip().lower()
    return raw in ("1", "true", "yes", "on")


def _strip_fenced_block(text: str) -> str:
    s = str(text or "").strip()
    if not s.startswith("```"):
        return s
    lines = s.splitlines()
    if not lines:
        return s
    lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    s = _strip_fenced_block(text)
    if not s:
        return None
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(s):
        if ch != "{":
            continue
        try:
            obj, _end = dec.raw_decode(s[i:])
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


def _clip_str(v: Any, *, max_len: int = 400) -> str:
    s = str(v or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max(0, max_len - 3)] + "..."


def _list_str(v: Any, *, max_items: int = 8, max_len: int = 240) -> List[str]:
    out: List[str] = []
    if not isinstance(v, list):
        return out
    for item in v:
        s = _clip_str(item, max_len=max_len)
        if s:
            out.append(s)
        if len(out) >= max_items:
            break
    return out


def _dict_str(v: Any, *, max_items: int = 8, max_key_len: int = 64, max_val_len: int = 120) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not isinstance(v, dict):
        return out
    for k, val in v.items():
        key = _clip_str(k, max_len=max_key_len)
        if not key:
            continue
        out[key] = _clip_str(val, max_len=max_val_len)
        if len(out) >= max_items:
            break
    return out


def _default_result(*, enabled: bool, status: str, reason: str = "", model: str = "") -> Dict[str, Any]:
    return {
        "enabled": bool(enabled),
        "status": str(status),
        "model": str(model or ""),
        "reason": _clip_str(reason, max_len=320),
        "ai_summary": "",
        "ai_findings": [],
        "ai_root_causes": [],
        "ai_improvement_suggestions": [],
        "ai_run_grade": "N/A",
        "ai_agent_evaluations": {},
        "ai_evidence_links": {"findings": [], "root_causes": [], "improvements": []},
    }


def _normalize_evidence_link_items(v: Any, *, max_items: int = 10) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(v, list):
        return out
    for item in v:
        if isinstance(item, dict):
            out.append(
                {
                    "text": _clip_str(item.get("text"), max_len=260),
                    "evidence_keys": _list_str(item.get("evidence_keys"), max_items=6, max_len=64),
                }
            )
        elif isinstance(item, str):
            key = _clip_str(item, max_len=64)
            if key:
                out.append({"text": "", "evidence_keys": [key]})
        if len(out) >= max_items:
            break
    return out


def _normalize_result(obj: Dict[str, Any], *, enabled: bool, model: str) -> Dict[str, Any]:
    evidence_links = obj.get("ai_evidence_links") if isinstance(obj.get("ai_evidence_links"), dict) else {}
    return {
        "enabled": bool(enabled),
        "status": "ok",
        "model": str(model or ""),
        "reason": "",
        "ai_summary": _clip_str(obj.get("ai_summary"), max_len=600),
        "ai_findings": _list_str(obj.get("ai_findings"), max_items=12, max_len=260),
        "ai_root_causes": _list_str(obj.get("ai_root_causes"), max_items=10, max_len=260),
        "ai_improvement_suggestions": _list_str(obj.get("ai_improvement_suggestions"), max_items=10, max_len=260),
        "ai_run_grade": _clip_str(obj.get("ai_run_grade") or "N/A", max_len=16),
        "ai_agent_evaluations": _dict_str(obj.get("ai_agent_evaluations"), max_items=10),
        "ai_evidence_links": {
            "findings": _normalize_evidence_link_items(evidence_links.get("findings")),
            "root_causes": _normalize_evidence_link_items(evidence_links.get("root_causes")),
            "improvements": _normalize_evidence_link_items(evidence_links.get("improvements")),
        },
    }


def _build_compact_input(day: str, out: Dict[str, Any]) -> Dict[str, Any]:
    trade_summary = out.get("trade_summary") if isinstance(out.get("trade_summary"), dict) else {}
    strategist_eval = out.get("strategist_evaluation") if isinstance(out.get("strategist_evaluation"), dict) else {}
    scanner_eval = out.get("scanner_evaluation") if isinstance(out.get("scanner_evaluation"), dict) else {}
    monitor_eval = out.get("monitor_evaluation") if isinstance(out.get("monitor_evaluation"), dict) else {}
    supervisor_activity = out.get("supervisor_activity") if isinstance(out.get("supervisor_activity"), dict) else {}
    intent_flow = out.get("intent_flow_analysis") if isinstance(out.get("intent_flow_analysis"), dict) else {}
    incidents = out.get("incident_postmortem") if isinstance(out.get("incident_postmortem"), dict) else {}
    market_context = out.get("market_context") if isinstance(out.get("market_context"), dict) else {}
    overtrading = out.get("overtrading_diagnostics") if isinstance(out.get("overtrading_diagnostics"), dict) else {}
    trace = out.get("decision_trace_chain_summary") if isinstance(out.get("decision_trace_chain_summary"), dict) else {}
    evidence_catalog = out.get("ai_evidence_catalog") if isinstance(out.get("ai_evidence_catalog"), dict) else {}

    chain_samples: List[Dict[str, Any]] = []
    for chain in (trace.get("chains") or [])[:12]:
        if not isinstance(chain, dict):
            continue
        strategist = chain.get("strategist") if isinstance(chain.get("strategist"), dict) else {}
        scanner = chain.get("scanner") if isinstance(chain.get("scanner"), dict) else {}
        monitor = chain.get("monitor") if isinstance(chain.get("monitor"), dict) else {}
        supervisor = chain.get("supervisor") if isinstance(chain.get("supervisor"), dict) else {}
        executor = chain.get("executor") if isinstance(chain.get("executor"), dict) else {}
        chain_samples.append(
            {
                "run_id": _clip_str(chain.get("run_id"), max_len=80),
                "strategist": {
                    "market_regime": _clip_str(strategist.get("market_regime"), max_len=40),
                    "themes": _list_str(strategist.get("themes"), max_items=4, max_len=40),
                    "playbook": _clip_str(strategist.get("playbook"), max_len=40),
                    "risk_tone": _clip_str(strategist.get("risk_tone"), max_len=40),
                    "monitor_guidance": _clip_str(strategist.get("monitor_guidance"), max_len=60),
                },
                "scanner": {
                    "candidate_pool_size": int(scanner.get("candidate_pool_size") or 0),
                    "selected_symbol": _clip_str(scanner.get("selected_symbol"), max_len=20),
                    "top_candidates": _list_str(scanner.get("top_candidates"), max_items=3, max_len=20),
                },
                "monitor": {
                    "monitor_reason": _clip_str(monitor.get("monitor_reason"), max_len=60),
                    "exit_reason": _clip_str(monitor.get("exit_reason"), max_len=60),
                    "min_hold_blocked": bool(monitor.get("min_hold_blocked")),
                    "sell_cooldown_blocked": bool(monitor.get("sell_cooldown_blocked")),
                },
                "supervisor": {
                    "verdict": _clip_str(supervisor.get("verdict"), max_len=32),
                    "guard_reason": _clip_str(supervisor.get("guard_reason"), max_len=80),
                },
                "executor": {
                    "fill_status_summary": _clip_str(executor.get("fill_status_summary"), max_len=40),
                },
                "complete_chain": bool(chain.get("complete_chain")),
            }
        )

    return {
        "day": str(day),
        "evidence_catalog_summary": {
            str(key): _clip_str((item or {}).get("summary"), max_len=180)
            for key, item in list(evidence_catalog.items())[:10]
            if isinstance(item, dict)
        },
        "market_context": {
            "global_sentiment_avg": market_context.get("global_sentiment_avg"),
            "symbol_sentiment_avg": market_context.get("symbol_sentiment_avg"),
            "llm_provider_top": market_context.get("llm_provider_top"),
            "llm_model_top": market_context.get("llm_model_top"),
        },
        "trade_summary": {
            "trade_count": int(trade_summary.get("trade_count") or 0),
            "symbols_traded": list(trade_summary.get("symbols_traded") or [])[:8],
        },
        "strategist_evaluation": {
            "theme_alignment_status": strategist_eval.get("theme_alignment_status"),
            "themes_proposed": list(strategist_eval.get("themes_proposed") or [])[:8],
            "assessment": _clip_str(strategist_eval.get("assessment"), max_len=220),
        },
        "scanner_evaluation": {
            "selection_status": scanner_eval.get("selection_status"),
            "no_candidate_total": int(scanner_eval.get("no_candidate_total") or 0),
            "selected_symbol_top": scanner_eval.get("selected_symbol_top") or {},
            "assessment": _clip_str(scanner_eval.get("assessment"), max_len=220),
        },
        "monitor_evaluation": {
            "monitor_status": monitor_eval.get("monitor_status"),
            "rapid_buy_sell_cycles": int(monitor_eval.get("rapid_buy_sell_cycles") or 0),
            "monitor_reason_top": monitor_eval.get("monitor_reason_top") or {},
            "assessment": _clip_str(monitor_eval.get("assessment"), max_len=220),
        },
        "supervisor_activity": {
            "blocked_rate": supervisor_activity.get("blocked_rate"),
            "blocked_total": int(supervisor_activity.get("blocked_total") or 0),
            "blocked_reason_top": supervisor_activity.get("blocked_reason_top") or {},
            "assessment": _clip_str(supervisor_activity.get("assessment"), max_len=220),
        },
        "intent_flow_analysis": {
            "intents_created": int(intent_flow.get("intents_created") or 0),
            "intents_blocked": int(intent_flow.get("intents_blocked") or 0),
            "intents_approved": int(intent_flow.get("intents_approved") or 0),
            "intents_executed": int(intent_flow.get("intents_executed") or 0),
            "reason_top": intent_flow.get("reason_top") or {},
        },
        "overtrading_diagnostics": {
            "rapid_buy_sell_cycles": int(overtrading.get("rapid_buy_sell_cycles") or 0),
            "guard_block_rate": overtrading.get("guard_block_rate"),
            "noise_exit_related_count": int(overtrading.get("noise_exit_related_count") or 0),
        },
        "incidents": incidents.get("incidents") or [],
        "improvement_suggestions": list(out.get("improvement_suggestions") or [])[:8],
        "decision_trace_chain_samples": chain_samples,
    }


def _build_messages(day: str, compact_input: Dict[str, Any]) -> List[Dict[str, str]]:
    system_prompt = (
        "You are an AI post-run reviewer for a trading agent system. "
        "You must remain passive and never suggest direct live execution actions. "
        "Given deterministic summaries, return concise JSON only. "
        "Prefer 2-3 short findings, 1-3 root causes, and 1-3 concrete improvement suggestions. "
        "Do not return empty arrays when evidence_catalog_summary contains meaningful evidence."
    )
    json_contract = {
        "ai_summary": "string",
        "ai_findings": ["string"],
        "ai_root_causes": ["string"],
        "ai_improvement_suggestions": ["string"],
        "ai_run_grade": "A+|A|B+|B|C|D|F",
        "ai_agent_evaluations": {
            "strategist": "good|mixed|needs_improvement",
            "scanner": "good|mixed|needs_improvement",
            "monitor": "good|mixed|needs_improvement",
            "supervisor": "good|mixed|needs_improvement",
            "executor": "good|mixed|needs_improvement",
        },
        "ai_evidence_links": {
            "findings": [{"text": "same as ai_findings[i]", "evidence_keys": ["evidence_catalog_key"]}],
            "root_causes": [{"text": "same as ai_root_causes[i]", "evidence_keys": ["evidence_catalog_key"]}],
            "improvements": [{"text": "same as ai_improvement_suggestions[i]", "evidence_keys": ["evidence_catalog_key"]}],
        },
    }
    user_prompt = (
        f"Day: {day}\n"
        "Analyze the run quality and answer these aspects: strategist reasonableness, scanner fit, "
        "monitor exit quality, overtrading risk, supervisor guard appropriateness, anomalies, and next-run improvements.\n"
        "Use only evidence keys already present in evidence_catalog_summary. "
        "ai_evidence_links rows must align by index with ai_findings / ai_root_causes / ai_improvement_suggestions.\n"
        "If the run has any meaningful deterministic evidence, each of ai_findings / ai_root_causes / "
        "ai_improvement_suggestions must contain at least one item.\n"
        "Return strict JSON matching this contract keys only:\n"
        f"{json.dumps(json_contract, ensure_ascii=False)}\n\n"
        "Input summary:\n"
        f"{json.dumps(compact_input, ensure_ascii=False)}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_ai_reporter_review(
    *,
    day: str,
    reporter_output: Dict[str, Any],
    enabled: Optional[bool] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: int = 900,
) -> Dict[str, Any]:
    """Optional passive AI review stage layered on deterministic reporter analysis."""
    run_id = f"reporter-{str(day)}"
    is_enabled = _env_bool("REPORTER_AI_REVIEW_ENABLED", False) if enabled is None else bool(enabled)
    if not is_enabled:
        return _default_result(enabled=False, status="disabled", reason="REPORTER_AI_REVIEW_ENABLED is false")
    if _env_bool("DRY_RUN", False):
        return _default_result(enabled=True, status="dry_run", reason="DRY_RUN mode")

    router = LLMRouter.from_env()
    if router.client is None:
        return _default_result(enabled=True, status="unavailable", reason="LLM client unavailable")

    env_model = str(
        os.getenv("REPORTER_AI_REVIEW_MODEL", "")
        or os.getenv("OPENROUTER_MODEL_REPORTER_FINAL", "")
        or os.getenv("OPENROUTER_MODEL_DAILY_REPORT", "")
        or ""
    ).strip()
    env_temp_raw = str(os.getenv("REPORTER_AI_REVIEW_TEMPERATURE", "")).strip()
    env_max_tokens_raw = str(os.getenv("REPORTER_AI_REVIEW_MAX_TOKENS", "")).strip()
    resolved_model = str(model or env_model or "").strip()
    if temperature is not None:
        resolved_temp = float(temperature)
    elif env_temp_raw:
        try:
            resolved_temp = float(env_temp_raw)
        except Exception:
            resolved_temp = 0.1
    else:
        resolved_temp = 0.1
    resolved_max_tokens = int(max_tokens)
    if env_max_tokens_raw and max_tokens == 900:
        try:
            resolved_max_tokens = int(float(env_max_tokens_raw))
        except Exception:
            resolved_max_tokens = int(max_tokens)

    policy: Dict[str, Any] = {
        "max_tokens": max(256, int(resolved_max_tokens)),
        "temperature": float(resolved_temp),
    }
    if resolved_model:
        policy["model"] = resolved_model
    route = router.resolve("reporter_final", policy=policy)

    compact_input = _build_compact_input(day, reporter_output)
    messages = _build_messages(day, compact_input)
    prompt_text = "\n\n".join(
        [f"[{str(m.get('role') or '').strip().lower() or 'unknown'}]\n{str(m.get('content') or '')}" for m in messages]
    ).strip()
    try:
        record_raw_input(
            run_id=run_id,
            agent="reporter",
            stage="post_run_analysis",
            raw_input={"compact_input": compact_input},
            decision_link={"stage": "ai_review_input"},
        )
        record_llm_prompt(
            run_id=run_id,
            agent="reporter",
            stage="post_run_analysis",
            llm_prompt=prompt_text,
            raw_input={"compact_input": compact_input},
            decision_link={"model": str(route.model or ""), "provider": "reporter_router"},
        )
    except Exception:
        pass
    try:
        raw = router.chat("reporter_final", messages, policy=policy)
    except Exception as e:
        try:
            record_llm_response(
                run_id=run_id,
                agent="reporter",
                stage="post_run_analysis",
                llm_response=f"ERROR:{type(e).__name__}:{e}",
                parsed_output={},
                decision_link={"status": "error"},
            )
        except Exception:
            pass
        return _default_result(enabled=True, status="error", reason=f"ai_call_failed:{e}", model=route.model)

    obj = _extract_json_object(raw)
    if not isinstance(obj, dict):
        try:
            record_llm_response(
                run_id=run_id,
                agent="reporter",
                stage="post_run_analysis",
                llm_response=str(raw or ""),
                parsed_output={},
                decision_link={"status": "parse_error"},
            )
        except Exception:
            pass
        return _default_result(
            enabled=True,
            status="parse_error",
            reason=f"ai_response_not_json:{_clip_str(raw, max_len=220)}",
            model=route.model,
        )
    try:
        record_llm_response(
            run_id=run_id,
            agent="reporter",
            stage="post_run_analysis",
            llm_response=str(raw or ""),
            parsed_output=dict(obj),
            decision_link={"status": "ok", "model": str(route.model or "")},
        )
    except Exception:
        pass
    return _normalize_result(obj, enabled=True, model=route.model)
