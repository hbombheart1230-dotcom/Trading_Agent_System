from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp_score(value: float) -> float:
    try:
        return float(max(0.0, min(1.0, float(value))))
    except Exception:
        return 0.0


@dataclass(frozen=True)
class VolumeConfirmation:
    current_volume: float
    average_volume: float
    median_volume: float
    max_reference_volume: float
    raw_ratio: float
    effective_ratio: float
    threshold: float
    passed: bool
    adjusted: bool
    adjustment_reason: str
    spike_skew_ratio: float
    minutes_since_session_open: float | None

    def score(self) -> float:
        if self.threshold <= 0.0:
            return 1.0 if self.effective_ratio > 0.0 else 0.0
        return _clamp_score(self.effective_ratio / self.threshold)

    def distance_to_ready(self) -> float:
        return float(self.effective_ratio) - float(self.threshold)

    def to_metrics(self) -> dict[str, Any]:
        return {
            "current_volume": float(self.current_volume),
            "average_volume": float(self.average_volume),
            "median_volume": float(self.median_volume),
            "max_reference_volume": float(self.max_reference_volume),
            "volume_ratio_raw": float(self.raw_ratio),
            "volume_ratio_effective": float(self.effective_ratio),
            "volume_ratio_min": float(self.threshold),
            "volume_ok": bool(self.passed),
            "volume_adjusted": bool(self.adjusted),
            "volume_adjustment_reason": str(self.adjustment_reason),
            "volume_spike_skew_ratio": float(self.spike_skew_ratio),
            "minutes_since_session_open": self.minutes_since_session_open,
        }


def evaluate_intraday_volume_confirmation(
    *,
    current_volume: Any,
    reference_candles: Sequence[Mapping[str, Any]],
    threshold: Any,
    minutes_since_session_open: Any = None,
) -> VolumeConfirmation:
    """Evaluate entry volume without letting one opening spike distort pullbacks.

    The raw ratio remains the primary signal: current 1m volume divided by the
    previous N-bar average. During the opening window, if that average is
    materially skewed by a single spike, a median-based ratio can be used as a
    secondary confirmation. A minimum raw-ratio floor keeps genuinely dead
    pullbacks blocked.
    """

    current = max(0.0, _to_float(current_volume))
    vols = [max(0.0, _to_float(row.get("volume"))) for row in reference_candles]
    vols = [v for v in vols if v > 0.0]
    avg = sum(vols) / float(len(vols)) if vols else 0.0
    median = float(statistics.median(vols)) if vols else 0.0
    max_ref = max(vols) if vols else 0.0
    raw_ratio = (current / avg) if avg > 0.0 else 0.0
    median_ratio = (current / median) if median > 0.0 else 0.0
    min_ratio = max(0.0, _to_float(threshold))

    minutes: float | None
    if minutes_since_session_open in (None, ""):
        minutes = None
    else:
        minutes = _to_float(minutes_since_session_open)

    opening_window = minutes is not None and 0.0 <= float(minutes) <= 45.0
    spike_skew_ratio = (max_ref / median) if median > 0.0 else 0.0
    average_skewed = bool(median > 0.0 and avg >= median * 1.4 and spike_skew_ratio >= 2.5)
    raw_floor_ok = raw_ratio >= max(0.30, min_ratio * 0.50)
    adjusted = bool(
        raw_ratio < min_ratio
        and opening_window
        and average_skewed
        and raw_floor_ok
        and median_ratio >= min_ratio
    )

    effective_ratio = raw_ratio
    reason = ""
    if adjusted:
        effective_ratio = max(raw_ratio, min(median_ratio, min_ratio + 0.20))
        reason = "opening_spike_adjusted_median_volume"

    return VolumeConfirmation(
        current_volume=current,
        average_volume=avg,
        median_volume=median,
        max_reference_volume=max_ref,
        raw_ratio=raw_ratio,
        effective_ratio=effective_ratio,
        threshold=min_ratio,
        passed=effective_ratio >= min_ratio,
        adjusted=adjusted,
        adjustment_reason=reason,
        spike_skew_ratio=spike_skew_ratio,
        minutes_since_session_open=minutes,
    )
