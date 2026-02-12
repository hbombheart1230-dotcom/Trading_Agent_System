from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

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
    meta: Dict[str, Any] = None  # type: ignore[assignment]

class OpenAIStrategist:
    """HTTP strategist wrapper.

    Env:
      - AI_STRATEGIST_API_KEY
      - AI_STRATEGIST_ENDPOINT
      - AI_STRATEGIST_MODEL (optional)
      - AI_STRATEGIST_TIMEOUT_SEC (optional)
    """

    def __init__(self, *, api_key: str, endpoint: str, model: str = "gpt-4.1-mini", timeout_sec: float = 15.0):
        self.api_key = api_key
        self.endpoint = endpoint
        self.model = model
        self.timeout_sec = timeout_sec

    @classmethod
    def from_env(cls) -> "OpenAIStrategist":
        api_key = (os.getenv("AI_STRATEGIST_API_KEY") or "").strip()
        endpoint = (os.getenv("AI_STRATEGIST_ENDPOINT") or "").strip()
        model = (os.getenv("AI_STRATEGIST_MODEL") or "gpt-4.1-mini").strip()
        timeout_sec = float(os.getenv("AI_STRATEGIST_TIMEOUT_SEC") or "15")
        return cls(api_key=api_key, endpoint=endpoint, model=model, timeout_sec=timeout_sec)

    def decide(self, x: StrategyInput) -> StrategyDecision:
        """Never raise. On any error, returns NOOP with error reason."""
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
            payload = {
                "model": self.model,
                "ts": int(time.time()),
                "input": {
                    "symbol": x.symbol,
                    "market_snapshot": x.market_snapshot,
                    "portfolio_snapshot": x.portfolio_snapshot,
                    "risk_context": x.risk_context,
                },
            }
            resp = _post_json(self.endpoint, headers, payload, timeout=self.timeout_sec) or {}
            intent = dict(resp.get("intent") or {})
            rationale = str(resp.get("rationale") or intent.get("rationale") or "")
            meta = dict(resp.get("meta") or {})
            if not intent:
                intent = {"action": "NOOP", "reason": "empty_intent"}
            return StrategyDecision(intent=intent, rationale=rationale, meta=meta)
        except Exception as e:
            return StrategyDecision(intent={"action": "NOOP", "reason": "strategist_error"}, rationale=str(e), meta={"error": str(e)})
