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
DEFAULT_X_TITLE = "Trading_Agent_System"

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
        api_key = (
            os.getenv("OPENROUTER_API_KEY", "").strip()
            or os.getenv("AI_STRATEGIST_API_KEY", "").strip()
        )
        if not api_key:
            return None
        cfg = OpenRouterConfig(
            api_key=api_key,
            base_url=os.getenv("OPENROUTER_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL,
            http_referer=os.getenv("OPENROUTER_HTTP_REFERER") or None,
            x_title=DEFAULT_X_TITLE,
            timeout_sec=int(
                os.getenv(
                    "OPENROUTER_TIMEOUT_SEC",
                    os.getenv("AI_STRATEGIST_TIMEOUT_SEC", str(DEFAULT_TIMEOUT_SEC)),
                )
            ),
        )
        return OpenRouterClient(cfg)

    def chat_completions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        req_timeout = int(payload.pop("__timeout_sec", self.cfg.timeout_sec) or self.cfg.timeout_sec)
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
            with urllib.request.urlopen(req, timeout=req_timeout) as resp:
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
        first = choices[0] or {}
        if isinstance(first.get("text"), str) and str(first.get("text") or "").strip():
            return str(first.get("text") or "")

        msg = first.get("message") or {}
        if not isinstance(msg, dict):
            return ""

        parsed = msg.get("parsed")
        if isinstance(parsed, dict) and parsed:
            try:
                return json.dumps(parsed, ensure_ascii=False)
            except Exception:
                return str(parsed)

        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, dict):
            for key in ("json", "parsed", "input_json"):
                nested = content.get(key)
                if isinstance(nested, dict) and nested:
                    try:
                        return json.dumps(nested, ensure_ascii=False)
                    except Exception:
                        return str(nested)
        # Some providers may return content as list of parts
        if isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, str):
                    parts.append(p)
                    continue
                if not isinstance(p, dict):
                    continue
                if isinstance(p, dict) and isinstance(p.get("text"), str):
                    parts.append(p["text"])
                    continue
                for key in ("json", "parsed", "input_json"):
                    nested = p.get(key)
                    if isinstance(nested, dict) and nested:
                        try:
                            return json.dumps(nested, ensure_ascii=False)
                        except Exception:
                            return str(nested)
            return "".join(parts)
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list):
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function")
                if not isinstance(fn, dict):
                    continue
                args = fn.get("arguments")
                if isinstance(args, str) and args.strip():
                    return args
                if isinstance(args, dict) and args:
                    try:
                        return json.dumps(args, ensure_ascii=False)
                    except Exception:
                        return str(args)
        reasoning = msg.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning
        output_text = resp.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text
        output = resp.get("output")
        if isinstance(output, list):
            parts = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content_parts = item.get("content")
                if not isinstance(content_parts, list):
                    continue
                for part in content_parts:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        parts.append(part.get("text") or "")
            if parts:
                return "".join(parts)
        return ""
