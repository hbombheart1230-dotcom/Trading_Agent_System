from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from libs.runtime.market_hours import KST
from libs.runtime.runtime_output_helpers import to_epoch


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_int(v: Any, default: int) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def to_bool(v: Any, default: bool = False) -> bool:
    raw = str(v if v is not None else "").strip().lower()
    if not raw:
        return bool(default)
    return raw in ("1", "true", "yes", "y", "on")


def resolve_path(raw: str, default_rel: str, *, root: Path) -> Path:
    s = str(raw or "").strip() or str(default_rel)
    p = Path(s)
    if not p.is_absolute():
        p = root / p
    return p


def read_env_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    out: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = str(k).strip()
        val = str(v).strip()
        if val and val[0] not in ("'", '"') and "#" in val:
            val = val.split("#", 1)[0].rstrip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        if key:
            out[key] = val
    return out


def parse_kst_datetime(value: str) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    s = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(KST)


def utc_day(ts: Any) -> Optional[str]:
    e = to_epoch(ts)
    if e is None:
        return None
    return datetime.fromtimestamp(e, tz=timezone.utc).strftime("%Y-%m-%d")


def iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                yield obj


def latest_event_day(event_log_path: Path, *, before_day: Optional[str] = None) -> Optional[str]:
    best: Optional[str] = None
    for row in iter_jsonl(event_log_path) or []:
        d = utc_day(row.get("ts"))
        if not d:
            continue
        if before_day and d >= before_day:
            continue
        if best is None or d > best:
            best = d
    return best
