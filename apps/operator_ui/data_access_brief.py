from __future__ import annotations

import re
from typing import Any, Dict, List

from libs.llm.json_response import parse_llm_json_response, required_key_metadata


OPERATOR_BRIEF_REQUIRED_KEYS = [
    "headline",
    "commander_summary",
    "strategist_summary",
    "scanner_summary",
    "monitor_summary",
    "supervisor_summary",
    "executor_summary",
    "reporter_summary",
    "operator_takeaways",
]


def clean_brief_text(v: Any) -> str:
    s = str(v or "").strip()
    if not s:
        return ""
    s = re.sub(r"^\s*From\s+[A-Za-z0-9_]+\s*-\s*", "", s)
    s = re.sub(r"^\s*[A-Za-z0-9_]+_hint\s*-\s*", "", s)
    s = re.sub(r"\s+", " ", s).strip(" -")
    return s


def clean_brief_list(v: Any, *, limit: int) -> List[str]:
    if not isinstance(v, list):
        return []
    out: List[str] = []
    for item in v:
        cleaned = clean_brief_text(item)
        if cleaned:
            out.append(cleaned)
        if len(out) >= max(1, int(limit)):
            break
    return out


def operator_brief_parse_meta(raw: Any, parsed: Dict[str, Any] | None) -> Dict[str, Any]:
    result = parse_llm_json_response(raw)
    candidate = parsed if isinstance(parsed, dict) else {}
    key_meta = required_key_metadata(candidate, OPERATOR_BRIEF_REQUIRED_KEYS)
    parse_mode = "none"
    if bool(result.get("is_full")):
        parse_mode = "full"
    elif bool(result.get("is_partial")):
        parse_mode = "partial"
    return {
        "parse_mode": parse_mode,
        **key_meta,
        "trailing_text": str(result.get("trailing_text") or ""),
        "raw_nonempty": bool(result.get("raw_nonempty")),
        "parse_error": str(result.get("error") or ""),
    }


def operator_brief_is_complete(parsed: Dict[str, Any]) -> bool:
    meta = required_key_metadata(parsed, OPERATOR_BRIEF_REQUIRED_KEYS)
    return not bool(meta.get("required_keys_missing"))


def is_retryable_brief_failure(status: str, reason: str = "") -> bool:
    status_text = str(status or "").strip().lower()
    reason_text = str(reason or "").strip().lower()
    if status_text in {"timeout", "network_error", "empty_response"}:
        return True
    return "429" in reason_text or "rate" in reason_text
