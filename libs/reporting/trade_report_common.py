from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def clip_text(value: Any, *, max_len: int = 220) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def report_clip(value: Any, *, max_len: int = 400) -> str:
    return clip_text(value, max_len=max_len)


def list_text(values: Any, *, limit: int = 6, max_len: int = 220) -> List[str]:
    if not isinstance(values, list):
        return []
    out: List[str] = []
    for value in values:
        text = clip_text(value, max_len=max_len)
        if not text:
            continue
        out.append(text)
        if len(out) >= max(1, int(limit)):
            break
    return out


def listify(values: Any, *, max_items: int = 6, max_len: int = 240) -> List[str]:
    out: List[str] = []
    if not isinstance(values, list):
        return out
    for value in values:
        text = report_clip(value, max_len=max_len)
        if text:
            out.append(text)
        if len(out) >= max_items:
            break
    return out


def dedupe_list(values: List[str], *, max_items: int = 12, max_len: int = 260) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = report_clip(value, max_len=max_len)
        if not text or text in seen:
            continue
        out.append(text)
        seen.add(text)
        if len(out) >= max_items:
            break
    return out


def compact_named_rows(values: Any, *, max_items: int = 3) -> List[Dict[str, Any]]:
    if not isinstance(values, list):
        return []
    out: List[Dict[str, Any]] = []
    for value in values:
        if len(out) >= max(1, int(max_items)):
            break
        if not isinstance(value, dict):
            continue
        row = {
            "rank": value.get("rank"),
            "symbol": report_clip(value.get("symbol"), max_len=24),
            "score_total": value.get("score_total"),
            "risk_score": value.get("risk_score"),
            "confidence": value.get("confidence"),
            "why": report_clip(value.get("why"), max_len=180),
        }
        row = {key: item for key, item in row.items() if item not in ("", None, [])}
        if row.get("symbol"):
            out.append(row)
    return out


def compact_scalar_dict(values: Any, *, max_items: int = 8, max_len: int = 160) -> Dict[str, Any]:
    if not isinstance(values, dict):
        return {}
    out: Dict[str, Any] = {}
    for key, value in values.items():
        if len(out) >= max(1, int(max_items)):
            break
        if isinstance(value, (int, float, bool)) or value is None:
            out[str(key)] = value
            continue
        text = report_clip(value, max_len=max_len)
        if text:
            out[str(key)] = text
    return out


def merge_missing_values(base: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base or {})
    for key, value in dict(fallback or {}).items():
        if key not in out or out.get(key) in (None, "", [], {}):
            out[key] = value
    return out


def is_empty_placeholder(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value is False
    if isinstance(value, (int, float)):
        return value == 0
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return len(value) == 0
    if isinstance(value, dict):
        if not value:
            return True
        return all(is_empty_placeholder(item) for item in value.values())
    return False


def format_pct(value: Any) -> str:
    if value in (None, ""):
        return "not_captured"
    return f"{safe_float(value, 0.0):.2f}"


def format_ratio_pct(value: Any) -> str:
    if value in (None, ""):
        return "not_captured"
    return f"{safe_float(value, 0.0) * 100.0:.2f}"


def format_exit_label(value: Any) -> str:
    text = str(value or "").strip().replace("_", " ")
    if not text:
        return "not_captured"
    return " ".join(part.capitalize() for part in text.split())


def fmt_pct(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        return "-"
    return f"{number * 100.0:.2f}%"


def fmt_price(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        return "-"
    return f"{number:.2f}"
