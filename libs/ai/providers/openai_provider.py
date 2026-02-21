from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

DEFAULT_PROMPT_VERSION = "m20-6"
DEFAULT_SCHEMA_VERSION = "intent.v1"
DEFAULT_CB_FAIL_THRESHOLD = 0
DEFAULT_CB_COOLDOWN_SEC = 60.0

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


def _extract_chat_message(resp: Dict[str, Any]) -> Dict[str, Any]:
    choices = resp.get("choices")
    if not isinstance(choices, list) or not choices:
        return {}
    first = choices[0] if isinstance(choices[0], dict) else {}
    msg = first.get("message") if isinstance(first.get("message"), dict) else first
    return msg if isinstance(msg, dict) else {}


def _extract_chat_finish_reason(resp: Dict[str, Any]) -> str:
    choices = resp.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0] if isinstance(choices[0], dict) else {}
    return str(first.get("finish_reason") or first.get("native_finish_reason") or "").strip().lower()


def _chat_output_truncated_without_final_answer(resp: Dict[str, Any]) -> bool:
    reason = _extract_chat_finish_reason(resp)
    if reason != "length":
        return False
    msg = _extract_chat_message(resp)
    content = msg.get("content")
    content_text = str(content or "").strip() if isinstance(content, str) else ""
    reasoning_text = str(msg.get("reasoning") or "").strip()
    return (not content_text) and bool(reasoning_text)


def _extract_chat_structured_object(resp: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract structured JSON object from non-text chat response shapes."""
    choices = resp.get("choices")
    if not isinstance(choices, list) or not choices:
        return None

    first = choices[0] if isinstance(choices[0], dict) else {}
    msg = first.get("message") if isinstance(first.get("message"), dict) else first
    if not isinstance(msg, dict):
        return None

    # OpenAI structured outputs may expose parsed object directly.
    parsed = msg.get("parsed")
    if isinstance(parsed, dict):
        return dict(parsed)

    content = msg.get("content")
    if isinstance(content, dict):
        if isinstance(content.get("json"), dict):
            return dict(content.get("json") or {})
        if isinstance(content.get("parsed"), dict):
            return dict(content.get("parsed") or {})
    elif isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            if isinstance(part.get("json"), dict):
                return dict(part.get("json") or {})
            if isinstance(part.get("parsed"), dict):
                return dict(part.get("parsed") or {})
            if isinstance(part.get("input_json"), dict):
                return dict(part.get("input_json") or {})

    # Tool-call outputs can include function arguments as JSON.
    tool_calls = msg.get("tool_calls")
    if isinstance(tool_calls, list):
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function")
            if not isinstance(fn, dict):
                continue
            args = fn.get("arguments")
            if isinstance(args, dict):
                return dict(args)
            if isinstance(args, str):
                obj = _extract_json_object(args)
                if isinstance(obj, dict):
                    return obj
    reasoning = msg.get("reasoning")
    if isinstance(reasoning, str):
        obj = _extract_json_object(reasoning)
        if isinstance(obj, dict):
            return obj
    return None


def _to_nonneg_int(v: Any) -> Optional[int]:
    try:
        x = int(float(v))
    except Exception:
        return None
    if x < 0:
        return None
    return x


def _extract_usage(resp: Dict[str, Any]) -> Dict[str, int]:
    """Extract token usage from provider response (best-effort)."""
    usage = resp.get("usage")
    if not isinstance(usage, dict):
        return {}

    prompt_tokens = _to_nonneg_int(usage.get("prompt_tokens"))
    completion_tokens = _to_nonneg_int(usage.get("completion_tokens"))
    total_tokens = _to_nonneg_int(usage.get("total_tokens"))

    if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens

    out: Dict[str, int] = {}
    if prompt_tokens is not None:
        out["prompt_tokens"] = prompt_tokens
    if completion_tokens is not None:
        out["completion_tokens"] = completion_tokens
    if total_tokens is not None:
        out["total_tokens"] = total_tokens
    return out

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
      - AI_STRATEGIST_API_KEY (or OPENROUTER_API_KEY as fallback)
      - AI_STRATEGIST_ENDPOINT
      - AI_STRATEGIST_MODEL (optional)
      - AI_STRATEGIST_TIMEOUT_SEC (optional)
    """

    _CB_STATE: Dict[str, Dict[str, float]] = {}

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
        prompt_version: str = DEFAULT_PROMPT_VERSION,
        schema_version: str = DEFAULT_SCHEMA_VERSION,
        prompt_cost_per_1k_usd: float = 0.0,
        completion_cost_per_1k_usd: float = 0.0,
        cb_fail_threshold: int = DEFAULT_CB_FAIL_THRESHOLD,
        cb_cooldown_sec: float = DEFAULT_CB_COOLDOWN_SEC,
        json_response_format: bool = True,
    ):
        self.api_key = api_key
        self.endpoint = endpoint
        self.model = model
        self.timeout_sec = timeout_sec
        self.max_tokens = max_tokens
        self.retry_max = max(0, int(retry_max))
        self.retry_backoff_sec = max(0.0, float(retry_backoff_sec))
        self.prompt_version = str(prompt_version or "").strip() or DEFAULT_PROMPT_VERSION
        self.schema_version = str(schema_version or "").strip() or DEFAULT_SCHEMA_VERSION
        self.prompt_cost_per_1k_usd = max(0.0, float(prompt_cost_per_1k_usd))
        self.completion_cost_per_1k_usd = max(0.0, float(completion_cost_per_1k_usd))
        self.cb_fail_threshold = max(0, int(cb_fail_threshold))
        self.cb_cooldown_sec = max(0.0, float(cb_cooldown_sec))
        self.json_response_format = bool(json_response_format)

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
        api_key = (
            (os.getenv("AI_STRATEGIST_API_KEY") or "").strip()
            or (os.getenv("OPENROUTER_API_KEY") or "").strip()
        )
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
        prompt_version = (os.getenv("AI_STRATEGIST_PROMPT_VERSION") or "").strip() or DEFAULT_PROMPT_VERSION
        schema_version = (os.getenv("AI_STRATEGIST_SCHEMA_VERSION") or "").strip() or DEFAULT_SCHEMA_VERSION
        raw_prompt_cost = (os.getenv("AI_STRATEGIST_PROMPT_COST_PER_1K_USD") or "0").strip()
        raw_completion_cost = (os.getenv("AI_STRATEGIST_COMPLETION_COST_PER_1K_USD") or "0").strip()
        raw_cb_fail_threshold = (os.getenv("AI_STRATEGIST_CB_FAIL_THRESHOLD") or str(DEFAULT_CB_FAIL_THRESHOLD)).strip()
        raw_cb_cooldown_sec = (os.getenv("AI_STRATEGIST_CB_COOLDOWN_SEC") or str(DEFAULT_CB_COOLDOWN_SEC)).strip()
        raw_json_response_format = (os.getenv("AI_STRATEGIST_JSON_RESPONSE_FORMAT") or "true").strip().lower()
        prompt_cost_per_1k_usd = 0.0
        completion_cost_per_1k_usd = 0.0
        cb_fail_threshold = DEFAULT_CB_FAIL_THRESHOLD
        cb_cooldown_sec = DEFAULT_CB_COOLDOWN_SEC
        json_response_format = raw_json_response_format not in ("0", "false", "no", "off")
        try:
            prompt_cost_per_1k_usd = max(0.0, float(raw_prompt_cost))
        except Exception:
            prompt_cost_per_1k_usd = 0.0
        try:
            completion_cost_per_1k_usd = max(0.0, float(raw_completion_cost))
        except Exception:
            completion_cost_per_1k_usd = 0.0
        try:
            cb_fail_threshold = max(0, int(raw_cb_fail_threshold))
        except Exception:
            cb_fail_threshold = DEFAULT_CB_FAIL_THRESHOLD
        try:
            cb_cooldown_sec = max(0.0, float(raw_cb_cooldown_sec))
        except Exception:
            cb_cooldown_sec = DEFAULT_CB_COOLDOWN_SEC

        return cls(
            api_key=api_key,
            endpoint=endpoint,
            model=model,
            timeout_sec=timeout_sec,
            max_tokens=max_tokens,
            retry_max=retry_max,
            retry_backoff_sec=retry_backoff_sec,
            prompt_version=prompt_version,
            schema_version=schema_version,
            prompt_cost_per_1k_usd=prompt_cost_per_1k_usd,
            completion_cost_per_1k_usd=completion_cost_per_1k_usd,
            cb_fail_threshold=cb_fail_threshold,
            cb_cooldown_sec=cb_cooldown_sec,
            json_response_format=json_response_format,
        )

    @staticmethod
    def _is_response_format_error(e: Exception) -> bool:
        s = str(e or "").strip().lower()
        if not s:
            return False
        markers = (
            "response_format",
            "json_object",
            "json schema",
            "json_schema",
            "unsupported parameter",
            "unknown field",
        )
        return any(m in s for m in markers)

    def _cb_enabled(self) -> bool:
        return self.cb_fail_threshold > 0 and self.cb_cooldown_sec > 0.0

    def _cb_key(self, model: str) -> str:
        return f"{self.endpoint}|{model}"

    @classmethod
    def _cb_state_for_key(cls, key: str) -> Dict[str, float]:
        st = cls._CB_STATE.get(key)
        if st is None:
            st = {"fail_count": 0.0, "open_until_epoch": 0.0}
            cls._CB_STATE[key] = st
        return st

    def _cb_maybe_reset_after_cooldown(self, key: str, now_epoch: float) -> Dict[str, float]:
        st = self._cb_state_for_key(key)
        open_until = float(st.get("open_until_epoch") or 0.0)
        if open_until > 0.0 and open_until <= now_epoch:
            st["fail_count"] = 0.0
            st["open_until_epoch"] = 0.0
        return st

    def _cb_is_open(self, key: str, now_epoch: float) -> bool:
        if not self._cb_enabled():
            return False
        st = self._cb_maybe_reset_after_cooldown(key, now_epoch)
        return float(st.get("open_until_epoch") or 0.0) > now_epoch

    def _cb_on_success(self, key: str) -> None:
        if not self._cb_enabled():
            return
        st = self._cb_state_for_key(key)
        st["fail_count"] = 0.0
        st["open_until_epoch"] = 0.0

    def _cb_on_failure(self, key: str, now_epoch: float) -> Dict[str, float]:
        if not self._cb_enabled():
            return {"fail_count": 0.0, "open_until_epoch": 0.0}
        st = self._cb_maybe_reset_after_cooldown(key, now_epoch)
        fail_count = float(st.get("fail_count") or 0.0) + 1.0
        st["fail_count"] = fail_count
        if fail_count >= float(self.cb_fail_threshold):
            st["open_until_epoch"] = max(
                float(st.get("open_until_epoch") or 0.0),
                float(now_epoch) + float(self.cb_cooldown_sec),
            )
        return st

    def _estimate_cost_usd(
        self,
        *,
        prompt_tokens: Optional[int],
        completion_tokens: Optional[int],
    ) -> Optional[float]:
        if self.prompt_cost_per_1k_usd <= 0.0 and self.completion_cost_per_1k_usd <= 0.0:
            return None
        if prompt_tokens is None and completion_tokens is None:
            return None
        pt = int(prompt_tokens or 0)
        ct = int(completion_tokens or 0)
        if pt < 0:
            pt = 0
        if ct < 0:
            ct = 0
        cost = (float(pt) / 1000.0) * self.prompt_cost_per_1k_usd
        cost += (float(ct) / 1000.0) * self.completion_cost_per_1k_usd
        return float(cost)

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
        model = self._effective_model()
        cb_key = self._cb_key(model)
        try:
            if not self.api_key or not self.endpoint:
                return StrategyDecision(
                    intent={"action": "NOOP", "reason": "missing_config"},
                    rationale="AI strategist config missing (api_key/endpoint)",
                    meta={
                        "prompt_version": self.prompt_version,
                        "schema_version": self.schema_version,
                        "attempts": 0,
                    },
                )
            now_epoch = float(time.time())
            if self._cb_is_open(cb_key, now_epoch):
                st = self._cb_state_for_key(cb_key)
                open_until = int(float(st.get("open_until_epoch") or 0.0))
                return StrategyDecision(
                    intent={"action": "NOOP", "reason": "circuit_open"},
                    rationale="Strategist circuit breaker is open",
                    meta={
                        "error": "circuit_open",
                        "error_type": "CircuitOpen",
                        "attempts": 0,
                        "prompt_version": self.prompt_version,
                        "schema_version": self.schema_version,
                        "circuit_state": "open",
                        "circuit_fail_count": int(float(st.get("fail_count") or 0.0)),
                        "circuit_open_until_epoch": open_until,
                    },
                )

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }

            if _looks_like_chat_completions_endpoint(self.endpoint):
                system_prompt = (
                    "You are a trading strategist. "
                    "Return JSON only. "
                    f"Prompt-Version: {self.prompt_version}. "
                    f"Schema-Version: {self.schema_version}. "
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
                if self.json_response_format:
                    payload["response_format"] = {"type": "json_object"}
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

            try:
                resp, attempts = self._post_with_retry(
                    self.endpoint,
                    headers,
                    payload,
                    timeout=self.timeout_sec,
                )
            except Exception as e:
                # Some providers ignore or reject response_format; retry once without it.
                if (
                    _looks_like_chat_completions_endpoint(self.endpoint)
                    and self.json_response_format
                    and self._is_response_format_error(e)
                    and "response_format" in payload
                ):
                    payload = dict(payload)
                    payload.pop("response_format", None)
                    resp, attempts = self._post_with_retry(
                        self.endpoint,
                        headers,
                        payload,
                        timeout=self.timeout_sec,
                    )
                else:
                    raise

            if _looks_like_chat_completions_endpoint(self.endpoint) and _chat_output_truncated_without_final_answer(resp):
                retry_payload = dict(payload)
                base_max = _to_nonneg_int(retry_payload.get("max_tokens"))
                if base_max is None:
                    base_max = _to_nonneg_int(self.max_tokens) or 256
                retry_payload["max_tokens"] = int(min(max(base_max * 2, 512), 2048))
                msgs = retry_payload.get("messages")
                if isinstance(msgs, list):
                    retry_payload["messages"] = list(msgs) + [
                        {
                            "role": "user",
                            "content": "Return only one JSON object for the schema. No explanation.",
                        }
                    ]
                resp2, retry_attempts = self._post_with_retry(
                    self.endpoint,
                    headers,
                    retry_payload,
                    timeout=self.timeout_sec,
                )
                resp = resp2
                attempts = int(attempts or 0) + int(retry_attempts or 0)

            intent: Dict[str, Any] = {}
            rationale = ""
            meta = dict(resp.get("meta") or {})
            usage = _extract_usage(resp)

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
                    obj = _extract_chat_structured_object(resp)
                if obj is None:
                    preview = str(content or "").strip().replace("\r", " ").replace("\n", " ")
                    if not preview:
                        try:
                            choices = resp.get("choices")
                            first_choice = choices[0] if isinstance(choices, list) and choices else {}
                            preview = json.dumps(first_choice, ensure_ascii=False)
                        except Exception:
                            preview = ""
                    if len(preview) > 240:
                        preview = preview[:240] + "..."
                    raise ValueError(
                        "Invalid response: no JSON object in model content"
                        + (f" (preview={preview})" if preview else "")
                    )

                if isinstance(obj.get("intent"), dict):
                    intent = dict(obj.get("intent") or {})
                    rationale = str(obj.get("rationale") or intent.get("rationale") or "")
                    if isinstance(obj.get("meta"), dict):
                        meta.update(dict(obj.get("meta") or {}))
                elif obj.get("action") is not None:
                    # Allow direct intent object response.
                    intent = dict(obj)
                    rationale = str(obj.get("rationale") or "")
                elif obj.get("decision") is not None:
                    # Common alias in some models.
                    intent = {
                        "action": obj.get("decision"),
                        "symbol": obj.get("symbol"),
                        "qty": obj.get("qty"),
                        "price": obj.get("price"),
                        "order_type": obj.get("order_type"),
                        "order_api_id": obj.get("order_api_id"),
                        "reason": obj.get("reason"),
                    }
                    rationale = str(obj.get("rationale") or obj.get("reason") or "")
                elif obj.get("signal") is not None:
                    # Another common alias.
                    intent = {
                        "action": obj.get("signal"),
                        "symbol": obj.get("symbol"),
                        "qty": obj.get("qty"),
                        "price": obj.get("price"),
                        "order_type": obj.get("order_type"),
                        "order_api_id": obj.get("order_api_id"),
                        "reason": obj.get("reason"),
                    }
                    rationale = str(obj.get("rationale") or obj.get("reason") or "")
                else:
                    raise ValueError("Invalid response JSON: missing intent/action")

            intent = self._normalize_intent(intent, x)
            if not intent:
                intent = {"action": "NOOP", "reason": "empty_intent"}
            if str(intent.get("action") or "").upper() == "NOOP":
                if not str(intent.get("reason") or "").strip():
                    intent["reason"] = "model_no_signal"
            meta.setdefault("model", model)
            meta.setdefault(
                "endpoint_type",
                "chat_completions" if _looks_like_chat_completions_endpoint(self.endpoint) else "custom",
            )
            meta.setdefault("prompt_version", self.prompt_version)
            meta.setdefault("schema_version", self.schema_version)
            if usage.get("prompt_tokens") is not None:
                meta.setdefault("prompt_tokens", int(usage["prompt_tokens"]))
            if usage.get("completion_tokens") is not None:
                meta.setdefault("completion_tokens", int(usage["completion_tokens"]))
            if usage.get("total_tokens") is not None:
                meta.setdefault("total_tokens", int(usage["total_tokens"]))
            estimated_cost_usd = self._estimate_cost_usd(
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
            )
            if estimated_cost_usd is not None:
                meta.setdefault("estimated_cost_usd", float(estimated_cost_usd))
            meta["attempts"] = int(attempts or 1)
            self._cb_on_success(cb_key)
            return StrategyDecision(intent=intent, rationale=rationale, meta=meta)
        except Exception as e:
            now_epoch = float(time.time())
            st = self._cb_on_failure(cb_key, now_epoch)
            open_until_epoch = float(st.get("open_until_epoch") or 0.0)
            circuit_state = "open" if open_until_epoch > now_epoch else "closed"
            return StrategyDecision(
                intent={"action": "NOOP", "reason": "strategist_error"},
                rationale=str(e),
                meta={
                    "error": str(e),
                    "error_type": e.__class__.__name__,
                    "attempts": int(attempts or 1),
                    "prompt_version": self.prompt_version,
                    "schema_version": self.schema_version,
                    "circuit_state": circuit_state,
                    "circuit_fail_count": int(float(st.get("fail_count") or 0.0)),
                    "circuit_open_until_epoch": int(open_until_epoch) if open_until_epoch > 0.0 else 0,
                },
            )
