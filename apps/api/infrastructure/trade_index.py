from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .dates import inclusive_days, latest_iso_day

TRADE_ID_PATTERN = re.compile(r"^TRD_(\d{8})_[0-9A-Z]+_[0-9]+$")


@dataclass(frozen=True, slots=True)
class TradeBundleRef:
    day: date
    trade_id: str
    root: Path


def discover_trade_bundles(
    reports_root: Path,
    start: date,
    end: date,
    *,
    max_days: int,
    max_bundles: int,
) -> tuple[list[TradeBundleRef], list[str]]:
    trades_root = (reports_root / "trades").resolve()
    refs: list[TradeBundleRef] = []
    issues: list[str] = []
    seen: set[str] = set()
    for day in inclusive_days(start, end, max_days=max_days):
        for ref in _day_bundles(trades_root, day):
            if ref.trade_id in seen:
                issues.append(f"DUPLICATE_TRADE_ID:{ref.trade_id}")
                continue
            seen.add(ref.trade_id)
            refs.append(ref)
            if len(refs) >= max_bundles:
                issues.append("TRADE_DISCOVERY_LIMIT_REACHED")
                refs.sort(key=lambda item: (item.day, item.trade_id), reverse=True)
                return refs, issues
    refs.sort(key=lambda ref: (ref.day, ref.trade_id), reverse=True)
    return refs, issues


def locate_trade_bundle(reports_root: Path, trade_id: str) -> TradeBundleRef | None:
    day = trade_day_from_id(trade_id)
    if day is None:
        return None
    trades_root = (reports_root / "trades").resolve()
    matches = [ref for ref in _day_bundles(trades_root, day) if ref.trade_id == trade_id]
    return matches[0] if len(matches) == 1 else None


def trade_day_from_id(trade_id: str) -> date | None:
    match = TRADE_ID_PATTERN.fullmatch(trade_id)
    if match is None:
        return None
    compact = match.group(1)
    try:
        return date.fromisoformat(
            f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"
        )
    except ValueError:
        return None


def latest_trade_day(reports_root: Path) -> date | None:
    return latest_iso_day(reports_root / "trades")


def _day_bundles(trades_root: Path, day: date) -> list[TradeBundleRef]:
    day_root = trades_root / day.isoformat()
    if not day_root.is_dir():
        return []
    refs: list[TradeBundleRef] = []
    try:
        buckets = sorted(day_root.iterdir())
    except OSError:
        return []
    for bucket in buckets:
        if not _is_safe_directory(bucket, trades_root):
            continue
        try:
            candidates = sorted(bucket.iterdir())
        except OSError:
            continue
        for candidate in candidates:
            if not _is_safe_directory(candidate, trades_root):
                continue
            if TRADE_ID_PATTERN.fullmatch(candidate.name):
                refs.append(TradeBundleRef(day, candidate.name, candidate))
    return refs


def _is_safe_directory(path: Path, root: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return False
    return True
