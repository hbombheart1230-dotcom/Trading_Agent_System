from __future__ import annotations

import json
import os
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable


_STRING_TS_RE = re.compile(r'"ts"\s*:\s*"(\d{4}-\d{2}-\d{2})')


def event_ts(row: Dict[str, Any]) -> Any:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    return row.get("ts") or payload.get("ts")


def to_epoch(ts: Any) -> int:
    if ts is None:
        return 0
    if isinstance(ts, (int, float)):
        return int(ts)
    text = str(ts).strip()
    if not text:
        return 0
    try:
        return int(float(text))
    except Exception:
        pass
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return 0


def utc_day(ts: Any) -> str:
    epoch = to_epoch(ts)
    if epoch <= 0:
        return ""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")


def _raw_line_can_match_day(line: str, day: str) -> bool:
    if not day:
        return True
    if day in line:
        return True
    match = _STRING_TS_RE.search(line)
    if match:
        return match.group(1) == day
    return True


def _source_signature(path: Path) -> Dict[str, Any]:
    try:
        stat = path.stat()
    except Exception:
        return {"source_size": 0, "source_mtime_ns": 0}
    return {"source_size": int(stat.st_size), "source_mtime_ns": int(stat.st_mtime_ns)}


def _cache_dir(path: Path) -> Path:
    configured = str(os.getenv("EVENT_LOG_DAY_CACHE_DIR") or "").strip()
    if configured:
        return Path(configured)
    return Path(path).parent / ".day_cache"


def _cache_paths(path: Path, day: str) -> tuple[Path, Path]:
    safe_day = re.sub(r"[^0-9-]", "_", str(day or "").strip())
    source_key = hashlib.sha1(str(Path(path).resolve()).encode("utf-8")).hexdigest()[:12]
    root = _cache_dir(path)
    return root / f"events_{safe_day}_{source_key}.jsonl", root / f"events_{safe_day}_{source_key}.meta.json"


def _cache_is_valid(path: Path, day: str, cache_path: Path, meta_path: Path) -> bool:
    if not cache_path.exists() or not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(meta, dict):
        return False
    source = _source_signature(path)
    return (
        str(meta.get("day") or "") == str(day or "")
        and str(meta.get("source_path") or "") == str(Path(path).resolve())
        and int(meta.get("source_size") or 0) == int(source.get("source_size") or 0)
        and int(meta.get("source_mtime_ns") or 0) == int(source.get("source_mtime_ns") or 0)
    )


def _iter_cached_events(cache_path: Path) -> Iterable[Dict[str, Any]]:
    def _gen() -> Iterable[Dict[str, Any]]:
        with cache_path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict):
                    yield row

    return _gen()


def _iter_source_events_with_cache(path: Path, day: str, cache_path: Path, meta_path: Path) -> Iterable[Dict[str, Any]]:
    def _gen() -> Iterable[Dict[str, Any]]:
        source_path = Path(path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
        completed = False
        try:
            with source_path.open("r", encoding="utf-8") as source, tmp_path.open("w", encoding="utf-8") as cache:
                for raw in source:
                    line = raw.strip()
                    if not line:
                        continue
                    if not _raw_line_can_match_day(line, day):
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(row, dict):
                        continue
                    row_day = utc_day(event_ts(row))
                    if row_day and row_day != day:
                        continue
                    cache.write(line + "\n")
                    yield row
            signature = _source_signature(source_path)
            meta = {
                "day": day,
                "source_path": str(source_path.resolve()),
                "source_size": int(signature.get("source_size") or 0),
                "source_mtime_ns": int(signature.get("source_mtime_ns") or 0),
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            tmp_path.replace(cache_path)
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            completed = True
        finally:
            if not completed:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    return _gen()


def iter_jsonl_events(path: Path, *, day: str | None = None) -> Iterable[Dict[str, Any]]:
    """Yield JSONL event rows, cheaply prefiltering ISO timestamp rows by UTC day."""

    if not path.exists():
        return []
    target_day = str(day or "").strip()
    if target_day:
        cache_path, meta_path = _cache_paths(path, target_day)
        if _cache_is_valid(path, target_day, cache_path, meta_path):
            return _iter_cached_events(cache_path)
        try:
            return _iter_source_events_with_cache(path, target_day, cache_path, meta_path)
        except Exception:
            pass

    def _gen() -> Iterable[Dict[str, Any]]:
        with path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                if target_day and not _raw_line_can_match_day(line, target_day):
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if not isinstance(row, dict):
                    continue
                row_day = utc_day(event_ts(row))
                if target_day and row_day and row_day != target_day:
                    continue
                yield row

    return _gen()
