"""Role-based LLM router.

LLM call path summary:
- Strategist frame: `graphs/nodes/strategist_node.py` -> `LLMRouter.chat("strategist", ...)`
- AI trade report: `libs/reporting/trade_report_ai.py` -> `LLMRouter.chat("trade_report", ...)`
- Operator brief: `apps/operator_ui/data_access.py` -> `LLMRouter.chat("operator_ui", ...)`
- Daily report: `libs/reporting/llm_daily_summary.py` -> `LLMRouter.chat("daily_report", ...)`
- Reporter final review: `libs/reporting/reporter_ai_review.py` -> `LLMRouter.chat("reporter_final", ...)`

Env:
- OPENROUTER_DEFAULT_MODEL
- OPENROUTER_MODEL_<ROLE> e.g. OPENROUTER_MODEL_STRATEGIST
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from libs.llm.model_names import normalize_openrouter_model_name
from libs.llm.openrouter_client import OpenRouterClient


def _env_model_key(role: str) -> str:
    return f"OPENROUTER_MODEL_{role.upper()}"


def _role_env_model_keys(role: str) -> List[str]:
    normalized = str(role or "").strip().lower()
    keys: List[str] = [_env_model_key(normalized)]
    if normalized == "reporter_final":
        keys.extend(
            [
                "OPENROUTER_MODEL_REPORTER_FINAL",
                "OPENROUTER_MODEL_DAILY_REPORT",
                "OPENROUTER_MODEL_REPORTER",
            ]
        )
    elif normalized == "daily_report":
        keys.extend(
            [
                "OPENROUTER_MODEL_DAILY_REPORT",
                "OPENROUTER_MODEL_REPORTER_FINAL",
                "OPENROUTER_MODEL_REPORTER",
            ]
        )
    elif normalized == "operator_ui":
        keys.extend(
            [
                "OPENROUTER_MODEL_OPERATOR_UI",
                "OPENROUTER_MODEL_REPORTER_INTRADAY",
                "OPENROUTER_MODEL_REPORTER",
            ]
        )
    elif normalized == "reporter_intraday":
        keys.extend(
            [
                "OPENROUTER_MODEL_REPORTER_INTRADAY",
                "OPENROUTER_MODEL_OPERATOR_UI",
                "OPENROUTER_MODEL_REPORTER",
            ]
        )
    # preserve order but dedupe
    seen = set()
    out: List[str] = []
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out

@dataclass
class LLMRoute:
    role: str
    model: str
    temperature: float = 0.2
    max_tokens: int = 512


class LLMRouter:
    def __init__(self, client: Optional[OpenRouterClient]):
        self.client = client

    @staticmethod
    def from_env() -> "LLMRouter":
        return LLMRouter(client=OpenRouterClient.from_env())

    def resolve(self, role: str, *, policy: Optional[Dict[str, Any]] = None) -> LLMRoute:
        policy = policy or {}
        # policy overrides env
        model = normalize_openrouter_model_name(str(policy.get("openrouter_model") or policy.get("model") or "").strip())
        if not model:
            for key in _role_env_model_keys(role):
                candidate = normalize_openrouter_model_name(os.getenv(key, "") or "")
                if candidate:
                    model = candidate
                    break
        if not model:
            model = normalize_openrouter_model_name(os.getenv("OPENROUTER_DEFAULT_MODEL", "") or "")
        if not model:
            model = "openrouter/auto"

        temperature = float(policy.get("temperature") or os.getenv("OPENROUTER_DEFAULT_TEMPERATURE", "0.2"))
        max_tokens = int(policy.get("max_tokens") or os.getenv("OPENROUTER_DEFAULT_MAX_TOKENS", "512"))
        return LLMRoute(role=role, model=model, temperature=temperature, max_tokens=max_tokens)

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Optional[Dict[str, Any]] = None) -> str:
        if self.client is None:
            return ""
        route = self.resolve(role, policy=policy)
        payload: Dict[str, Any] = {
            "model": route.model,
            "messages": messages,
            "temperature": route.temperature,
            "max_tokens": route.max_tokens,
        }
        # allow advanced OpenRouter passthrough fields
        if policy:
            for k in ("top_p", "presence_penalty", "frequency_penalty", "seed", "response_format"):
                if k in policy:
                    payload[k] = policy[k]
            if "timeout_sec" in policy:
                payload["__timeout_sec"] = policy["timeout_sec"]
        resp = self.client.chat_completions(payload)
        return self.client.extract_text(resp)
