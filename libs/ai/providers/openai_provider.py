from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

# NOTE: tests monkeypatch this symbol
def _post_json(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: float = 15.0) -> Dict[str, Any]:
    """Very small HTTP helper. Kept minimal on purpose.
    In production you can swap to requests/httpx. In tests we monkeypatch this.
    """
    import urllib.request

    req = urllib.request.Request(url, method="POST")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    data = json.dumps(payload).encode("utf-8")
    with urllib.request.urlopen(req, data=data, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


def _looks_like_chat_completions_endpoint(url: str) -> bool:
    s = str(url or "").strip().lower()
    return "/chat/completions" in s


def _strip_fenced_block(text: str) -> str:
    s = str(text or "").strip()
    if not s.startswith("```"):
        return s

    lines = s.splitlines()
    if not lines:
        return s

    # drop first fence line (` ``` ` or ` ```json `), and optional trailing fence
    lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    s = _strip_fenced_block(text)
    if not s:
        return None

    # 1) direct JSON
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # 2) best-effort: find first decodable JSON object in free text
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


def _extract_chat_content(resp: Dict[str, Any]) -> str:
    choices = resp.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    msg = choices[0] if isinstance(choices[0], dict) else {}
    msg = msg.get("message") if isinstance(msg.get("message"), dict) else msg
    content = msg.get("content") if isinstance(msg, dict) else ""

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict) and isinstance(p.get("text"), str):
                parts.append(p.get("text") or "")
        return "".join(parts)
    return ""

@dataclass
class StrategyInput:
    symbol: str
    market_snapshot: Dict[str, Any]
    portfolio_snapshot: Dict[str, Any]
    risk_context: Dict[str, Any]

@dataclass
class StrategyDecision:
    intent: Dict[str, Any]
    rationale: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

class OpenAIStrategist:
    """HTTP strategist wrapper.

    Env:
      - AI_STRATEGIST_API_KEY
      - AI_STRATEGIST_ENDPOINT
      - AI_STRATEGIST_MODEL (optional)
      - AI_STRATEGIST_TIMEOUT_SEC (optional)
    """

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str,
        model: str = "gpt-4.1-mini",
        timeout_sec: float = 15.0,
        max_tokens: Optional[int] = None,
        retry_max: int = 1,
        retry_backoff_sec: float = 0.5,
    ):
        self.api_key = api_key
        self.endpoint = endpoint
        self.model = model
        self.timeout_sec = timeout_sec
        self.max_tokens = max_tokens
        self.retry_max = max(0, int(retry_max))
        self.retry_backoff_sec = max(0.0, float(retry_backoff_sec))

    def _effective_model(self) -> str:
        model = str(self.model or "").strip()
        if _looks_like_chat_completions_endpoint(self.endpoint):
            # OpenRouter often expects provider/model style names.
            if (not model) or ("/" not in model):
                env_model = (
                    (os.getenv("OPENROUTER_MODEL_STRATEGIST") or "").strip()
                    or (os.getenv("OPENROUTER_DEFAULT_MODEL") or "").strip()
                )
                if env_model:
                    model = env_model
        return model or "gpt-4.1-mini"

    @classmethod
    def from_env(cls) -> "OpenAIStrategist":
        api_key = (os.getenv("AI_STRATEGIST_API_KEY") or "").strip()
        endpoint = (os.getenv("AI_STRATEGIST_ENDPOINT") or "").strip()
        model = (os.getenv("AI_STRATEGIST_MODEL") or "").strip()
        if not model:
            if _looks_like_chat_completions_endpoint(endpoint):
                model = (
                    (os.getenv("OPENROUTER_MODEL_STRATEGIST") or "").strip()
                    or (os.getenv("OPENROUTER_DEFAULT_MODEL") or "").strip()
                    or "openai/gpt-4o-mini"
                )
            else:
                model = "gpt-4.1-mini"
        timeout_sec = float(os.getenv("AI_STRATEGIST_TIMEOUT_SEC") or "15")
        raw_max = (os.getenv("AI_STRATEGIST_MAX_TOKENS") or "").strip()
        max_tokens: Optional[int] = None
        if raw_max:
            try:
                v = int(raw_max)
                max_tokens = v if v > 0 else None
            except Exception:
                max_tokens = None

        raw_retry_max = (os.getenv("AI_STRATEGIST_RETRY_MAX") or "1").strip()
        retry_max = 1
        try:
            retry_max = max(0, int(raw_retry_max))
        except Exception:
            retry_max = 1

        raw_backoff = (os.getenv("AI_STRATEGIST_RETRY_BACKOFF_SEC") or "0.5").strip()
        retry_backoff_sec = 0.5
        try:
            retry_backoff_sec = max(0.0, float(raw_backoff))
        except Exception:
            retry_backoff_sec = 0.5

        return cls(
            api_key=api_key,
            endpoint=endpoint,
            model=model,
            timeout_sec=timeout_sec,
            max_tokens=max_tokens,
            retry_max=retry_max,
            retry_backoff_sec=retry_backoff_sec,
        )

    @staticmethod
    def _is_retryable_error(e: Exception) -> bool:
        if isinstance(e, TimeoutError):
            return True

        try:
            import urllib.error as ue

            if isinstance(e, ue.URLError):
                return True

            if isinstance(e, ue.HTTPError):
                code = int(getattr(e, "code", 0) or 0)
                return code in (408, 409, 425, 429) or (500 <= code <= 599)
        except Exception:
            pass
        return False

    def _post_with_retry(
        self,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        timeout: float,
    ) -> Tuple[Dict[str, Any], int]:
        max_attempts = max(1, int(self.retry_max) + 1)
        attempts = 0
        while True:
            attempts += 1
            try:
                return _post_json(url, headers, payload, timeout=timeout) or {}, attempts
            except Exception as e:
                if attempts >= max_attempts or not self._is_retryable_error(e):
                    raise
                backoff = float(self.retry_backoff_sec) * (2 ** (attempts - 1))
                if backoff > 0:
                    time.sleep(backoff)

    @staticmethod
    def _normalize_intent(raw: Dict[str, Any], x: StrategyInput) -> Dict[str, Any]:
        # Canonical schema enforcement for strategist outputs.
        from libs.ai.intent_schema import normalize_intent

        default_symbol = str(x.symbol) if x.symbol is not None else None
        default_price = None
        if isinstance(x.market_snapshot, dict):
            default_price = x.market_snapshot.get("price")

        norm, _rationale = normalize_intent(
            raw,
            default_symbol=default_symbol,
            default_price=default_price,
        )
        return dict(norm)

    def decide(self, x: StrategyInput) -> StrategyDecision:
        """Never raise. On any error, returns NOOP with error reason."""
        attempts = 0
        try:
            if not self.api_key or not self.endpoint:
                return StrategyDecision(
                    intent={"action": "NOOP", "reason": "missing_config"},
                    rationale="AI strategist config missing (api_key/endpoint)",
                    meta={},
                )

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
            model = self._effective_model()

            if _looks_like_chat_completions_endpoint(self.endpoint):
                system_prompt = (
                    "You are a trading strategist. "
                    "Return JSON only. "
                    "Schema: {\"intent\": {\"action\":\"BUY|SELL|NOOP\", \"symbol\": string|null, "
                    "\"qty\": int, \"price\": number|null, \"order_type\":\"limit|market\", "
                    "\"order_api_id\":\"ORDER_SUBMIT\"}, \"rationale\": string, \"meta\": object}."
                )
                user_payload = {
                    "symbol": x.symbol,
                    "market_snapshot": x.market_snapshot,
                    "portfolio_snapshot": x.portfolio_snapshot,
                    "risk_context": x.risk_context,
                }
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                    ],
                    "temperature": 0.1,
                }
            else:
                # Legacy/custom strategist endpoint contract.
                payload = {
                    "model": model,
                    "ts": int(time.time()),
                    "input": {
                        "symbol": x.symbol,
                        "market_snapshot": x.market_snapshot,
                        "portfolio_snapshot": x.portfolio_snapshot,
                        "risk_context": x.risk_context,
                    },
                }
            if self.max_tokens is not None:
                payload["max_tokens"] = int(self.max_tokens)

            resp, attempts = self._post_with_retry(
                self.endpoint,
                headers,
                payload,
                timeout=self.timeout_sec,
            )

            intent: Dict[str, Any] = {}
            rationale = ""
            meta = dict(resp.get("meta") or {})

            # 1) Native/custom contract: {"intent": {...}, ...}
            raw_intent = resp.get("intent")
            if raw_intent is not None:
                if isinstance(raw_intent, dict):
                    intent = dict(raw_intent)
                    rationale = str(resp.get("rationale") or intent.get("rationale") or "")
                else:
                    raise ValueError("Invalid response: 'intent' must be an object")
            else:
                # 2) OpenRouter/OpenAI-style chat completions:
                #    parse JSON in assistant content and adapt to {"intent": ...}.
                content = _extract_chat_content(resp)
                obj = _extract_json_object(content)
                if obj is None:
                    raise ValueError("Invalid response: no JSON object in model content")

                if isinstance(obj.get("intent"), dict):
                    intent = dict(obj.get("intent") or {})
                    rationale = str(obj.get("rationale") or intent.get("rationale") or "")
                    if isinstance(obj.get("meta"), dict):
                        meta.update(dict(obj.get("meta") or {}))
                elif obj.get("action") is not None:
                    # Allow direct intent object response.
                    intent = dict(obj)
                    rationale = str(obj.get("rationale") or "")
                else:
                    raise ValueError("Invalid response JSON: missing intent/action")

            intent = self._normalize_intent(intent, x)
            if not intent:
                intent = {"action": "NOOP", "reason": "empty_intent"}
            meta.setdefault("model", model)
            meta.setdefault(
                "endpoint_type",
                "chat_completions" if _looks_like_chat_completions_endpoint(self.endpoint) else "custom",
            )
            meta["attempts"] = int(attempts or 1)
            return StrategyDecision(intent=intent, rationale=rationale, meta=meta)
        except Exception as e:
            return StrategyDecision(
                intent={"action": "NOOP", "reason": "strategist_error"},
                rationale=str(e),
                meta={
                    "error": str(e),
                    "error_type": e.__class__.__name__,
                    "attempts": int(attempts or 1),
                },
            )
