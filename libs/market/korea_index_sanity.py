from __future__ import annotations

from typing import Any, Mapping


EXTREME_CHANGE_PCT = 6.0
VERY_EXTREME_CHANGE_PCT = 10.0


def _to_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _row(packet: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    indices = packet.get("indices") if isinstance(packet.get("indices"), Mapping) else {}
    row = indices.get(name) if isinstance(indices.get(name), Mapping) else {}
    return row


def korea_index_sanity(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Return diagnostic flags for Korean index inputs without mutating values."""

    warnings: list[dict[str, Any]] = []
    for name in ("KOSPI", "KOSDAQ", "KOSPI200"):
        row = _row(packet, name)
        if not row:
            continue
        change_pct = _to_float(row.get("change_pct"))
        current = _to_float(row.get("current"))
        previous_close = _to_float(row.get("previous_close"))
        open_price = _to_float(row.get("open"))
        high = _to_float(row.get("high"))
        low = _to_float(row.get("low"))
        if change_pct is None:
            continue
        if abs(change_pct) >= VERY_EXTREME_CHANGE_PCT:
            severity = "critical"
        elif abs(change_pct) >= EXTREME_CHANGE_PCT:
            severity = "warning"
        else:
            severity = ""
        if severity:
            warnings.append(
                {
                    "code": "extreme_index_change_pct",
                    "severity": severity,
                    "index": name,
                    "change_pct": change_pct,
                    "current": current,
                    "previous_close": previous_close,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "requires_confirmation": True,
                }
            )
        if high is not None and low is not None and high > 0 and low > 0 and high < low:
            warnings.append(
                {
                    "code": "index_high_below_low",
                    "severity": "critical",
                    "index": name,
                    "high": high,
                    "low": low,
                    "requires_confirmation": True,
                }
            )
        if current is not None and high is not None and low is not None and low > 0 and high > 0:
            if current > high * 1.001 or current < low * 0.999:
                warnings.append(
                    {
                        "code": "index_current_outside_high_low",
                        "severity": "warning",
                        "index": name,
                        "current": current,
                        "high": high,
                        "low": low,
                        "requires_confirmation": True,
                    }
                )
    return {
        "status": "warning" if warnings else "ok",
        "warning_count": len(warnings),
        "warnings": warnings,
        "extreme_move_requires_confirmation": any(
            bool(row.get("requires_confirmation")) for row in warnings
        ),
    }


__all__ = ["korea_index_sanity"]
