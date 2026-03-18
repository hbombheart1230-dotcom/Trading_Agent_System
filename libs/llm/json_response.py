from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List


def strip_fenced_code_block(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw.startswith("```"):
        return raw
    lines = raw.splitlines()
    if not lines:
        return raw
    lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_llm_json_response(text: Any) -> Dict[str, Any]:
    normalized = strip_fenced_code_block(text)
    raw_nonempty = bool(str(normalized or "").strip())
    out: Dict[str, Any] = {
        "full_object": None,
        "partial_object": None,
        "is_full": False,
        "is_partial": False,
        "raw_nonempty": raw_nonempty,
        "error": "",
        "trailing_text": "",
    }
    if not raw_nonempty:
        out["error"] = "empty_response"
        return out

    try:
        obj = json.loads(normalized)
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}:{exc}"
    else:
        if isinstance(obj, dict):
            out["full_object"] = obj
            out["is_full"] = True
            out["error"] = ""
            return out
        out["error"] = "json_root_not_object"

    decoder = json.JSONDecoder()
    for idx, ch in enumerate(normalized):
        if ch != "{":
            continue
        try:
            obj, end = decoder.raw_decode(normalized[idx:])
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        leading = str(normalized[:idx]).strip()
        trailing = str(normalized[idx + end :]).strip()
        extra = "\n".join(part for part in (leading, trailing) if part).strip()
        out["partial_object"] = obj
        out["is_partial"] = True
        out["trailing_text"] = extra
        return out
    return out


def extract_json_object_loose(text: Any) -> Dict[str, Any]:
    parsed = parse_llm_json_response(text)
    obj = parsed.get("full_object") if isinstance(parsed.get("full_object"), dict) else parsed.get("partial_object")
    return dict(obj) if isinstance(obj, dict) else {}


def required_key_metadata(obj: Any, required_keys: Iterable[str]) -> Dict[str, Any]:
    expected = [str(key or "").strip() for key in list(required_keys or []) if str(key or "").strip()]
    target = obj if isinstance(obj, dict) else {}
    present: List[str] = []
    missing: List[str] = []
    for key in expected:
        if target.get(key) is None:
            missing.append(key)
        else:
            present.append(key)
    score = float(len(present)) / float(len(expected)) if expected else 1.0
    return {
        "required_keys_expected": expected,
        "required_keys_present": present,
        "required_keys_missing": missing,
        "completeness_score": score,
    }
