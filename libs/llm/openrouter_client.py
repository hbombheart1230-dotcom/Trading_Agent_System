"""OpenRouter HTTP client (stdlib-only).

This module is intentionally dependency-free (uses urllib).
It provides a thin wrapper around OpenRouter's Chat Completions endpoint.

Safety:
- This client does not decide DRY_RUN; the caller must gate network calls.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT_SEC = 15

# Backward-compatible message type alias used by legacy router import paths.
ChatMessage = Dict[str, Any]


@dataclass
class OpenRouterConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    http_referer: Optional[str] = None
    x_title: Optional[str] = None
    timeout_sec: int = DEFAULT_TIMEOUT_SEC


class OpenRouterError(RuntimeError):
    pass


class OpenRouterClient:
    def __init__(self, cfg: OpenRouterConfig):
        if not cfg.api_key:
            raise ValueError("OpenRouterConfig.api_key is required")
        self.cfg = cfg

    @staticmethod
    def from_env() -> Optional["OpenRouterClient"]:
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            return None
        cfg = OpenRouterConfig(
            api_key=api_key,
            base_url=os.getenv("OPENROUTER_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL,
            http_referer=os.getenv("OPENROUTER_HTTP_REFERER") or None,
            x_title=os.getenv("OPENROUTER_X_TITLE") or None,
            timeout_sec=int(os.getenv("OPENROUTER_TIMEOUT_SEC", str(DEFAULT_TIMEOUT_SEC))),
        )
        return OpenRouterClient(cfg)

    def chat_completions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = self.cfg.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type": "application/json",
        }
        # Optional attribution headers (recommended by OpenRouter)
        if self.cfg.http_referer:
            headers["HTTP-Referer"] = self.cfg.http_referer
        if self.cfg.x_title:
            headers["X-Title"] = self.cfg.x_title

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url=url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout_sec) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")
            except Exception:
                body = ""
            raise OpenRouterError(f"HTTPError {e.code}: {body or e.reason}") from e
        except urllib.error.URLError as e:
            raise OpenRouterError(f"URLError: {e}") from e

    @staticmethod
    def extract_text(resp: Dict[str, Any]) -> str:
        """Best-effort extraction of assistant text."""
        choices = resp.get("choices") or []
        if not choices:
            return ""
        msg = (choices[0] or {}).get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            return content
        # Some providers may return content as list of parts
        if isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, dict) and isinstance(p.get("text"), str):
                    parts.append(p["text"])
            return "".join(parts)
        return ""
