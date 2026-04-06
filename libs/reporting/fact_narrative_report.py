from typing import Any, Dict, Optional
import json
import os
from libs.llm.llm_router import LLMRouter
from libs.llm.json_response import parse_llm_json_response

def build_fact_payload(
    trade_model: Optional[Dict[str, Any]] = None,
    daily_model: Optional[Dict[str, Any]] = None,
    symbol_model: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Phase 6-1 Task 4: Completely separated deterministic fact payload."""
    return {
        "trade": trade_model or {},
        "daily": daily_model or {},
        "symbol": symbol_model or {}
    }

def generate_narrative(fact_payload: Dict[str, Any], *, model: Optional[str] = None) -> Dict[str, Any]:
    """Phase 6-1 Task 4: Generate strictly narrative part using LLM based ONLY on fact_payload."""
    narrative = {
        "summary": "",
        "insight": "",
        "recommendation": "",
        "source": "llm",
        "based_on": "fact_payload",
        "status": "skipped"
    }

    if str(os.getenv("DRY_RUN", "0")).strip().lower() in ("1", "true", "yes", "on"):
        narrative["status"] = "dry_run"
        return narrative

    router = LLMRouter.from_env()
    if not router.client:
        narrative["status"] = "error"
        narrative["error"] = "llm_client_unavailable"
        return narrative

    sys_prompt = (
        "You are an expert trading system reporter. Your task is to analyze the provided deterministic 'fact_payload' "
        "and generate a narrative summary, insight, and recommendation.\n"
        "CRITICAL RULES:\n"
        "- Rely 100% on the provided facts. DO NOT invent or assume any facts, numbers, or events.\n"
        "- Return ONLY a JSON object matching this schema:\n"
        '{"summary": "...", "insight": "...", "recommendation": "..."}'
    )

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": json.dumps(fact_payload, ensure_ascii=False)}
    ]

    primary_model = model
    fallback_model = "minimax/minimax-m2.5"
    
    def _attempt_call(target_model: str) -> Dict[str, Any]:
        policy = {"response_format": {"type": "json_object"}}
        if target_model:
            policy["model"] = target_model
        raw = router.chat("reporter_final", messages, policy=policy)
        parsed = parse_llm_json_response(raw)
        return parsed.get("full_object") or parsed.get("partial_object") or {}

    try:
        obj = _attempt_call(primary_model)
        narrative["summary"] = str(obj.get("summary", "")).strip()
        narrative["insight"] = str(obj.get("insight", "")).strip()
        narrative["recommendation"] = str(obj.get("recommendation", "")).strip()
        narrative["status"] = "ok"
    except Exception as e:
        if primary_model != fallback_model:
            try:
                obj = _attempt_call(fallback_model)
                narrative["summary"] = str(obj.get("summary", "")).strip()
                narrative["insight"] = str(obj.get("insight", "")).strip()
                narrative["recommendation"] = str(obj.get("recommendation", "")).strip()
                narrative["status"] = "ok"
                narrative["fallback_used"] = True
                narrative["fallback_model"] = fallback_model
                narrative["primary_error"] = str(e)
                return narrative
            except Exception as e2:
                narrative["status"] = "error"
                narrative["error"] = f"Primary: {e} | Fallback: {e2}"
        else:
            narrative["status"] = "error"
            narrative["error"] = str(e)

    return narrative

def build_separated_report(
    trade_model: Optional[Dict[str, Any]] = None,
    daily_model: Optional[Dict[str, Any]] = None,
    symbol_model: Optional[Dict[str, Any]] = None,
    *,
    model: Optional[str] = None
) -> Dict[str, Any]:
    """Phase 6-1 Task 4: Build the unified report structure with separated facts and narrative."""
    fact_payload = build_fact_payload(trade_model, daily_model, symbol_model)
    narrative = generate_narrative(fact_payload, model=model)
    return {
        "fact_payload": fact_payload,
        "narrative": narrative
    }