from __future__ import annotations

import re
from datetime import UTC, date, datetime

from ..adapters.market_snapshot import load_market_snapshot
from ..config import ApiSettings
from ..infrastructure.dates import inclusive_days, latest_iso_day
from ..models.common import AvailabilityStatus, Provenance
from ..models.market import (
    MarketBreadth,
    MarketMetric,
    MarketSeriesPoint,
    MarketSeriesResponse,
    MarketSnapshotResponse,
)
from .trade_values import integer, mapping, number, text_value, timestamp

SOURCE = "global_sentiment_macro_snapshot.v1"
METRIC_KEY = re.compile(r"^[a-z0-9_]{1,64}$")


def resolve_market_day(settings: ApiSettings, day: date | None) -> date | None:
    return day or latest_iso_day(settings.logs_root / "macro_indicators")


def build_market_snapshot(settings: ApiSettings, day: date) -> MarketSnapshotResponse:
    payload = load_market_snapshot(
        settings.logs_root,
        day,
        max_bytes=settings.max_report_bytes,
    )
    if payload is None:
        return MarketSnapshotResponse(
            status=AvailabilityStatus.NO_DATA,
            day=day,
            generated_at=datetime.now(UTC),
            source_generated_at=None,
            sentiment_score=None,
            sentiment_reason=None,
            breadth=None,
            metrics=[],
            warning_count=0,
            warnings=[],
            provenance=Provenance(source=SOURCE, sample_count=0),
        )
    indicators = mapping(mapping(payload.get("macro_indicators")).get("indicators"))
    metrics = [_metric(key, raw) for key, raw in indicators.items()]
    metrics.sort(key=lambda item: (item.category, item.label))
    sentiment = mapping(payload.get("global_sentiment"))
    korea = mapping(payload.get("korea_indices"))
    sanity = mapping(payload.get("korea_index_sanity"))
    warnings = [str(value) for value in sanity.get("warnings", []) if str(value).strip()]
    source_generated_at = timestamp(payload.get("generated_at"))
    ok_count = sum(metric.status.lower() == "ok" for metric in metrics)
    status = AvailabilityStatus.AVAILABLE
    if not metrics:
        status = AvailabilityStatus.NO_DATA
    elif ok_count < len(metrics) or warnings:
        status = AvailabilityStatus.PARTIAL
    return MarketSnapshotResponse(
        status=status,
        day=day,
        generated_at=datetime.now(UTC),
        source_generated_at=source_generated_at,
        sentiment_score=number(sentiment.get("score")),
        sentiment_reason=text_value(sentiment.get("reason")),
        breadth=_breadth(korea),
        metrics=metrics,
        warning_count=integer(sanity.get("warning_count")) or len(warnings),
        warnings=warnings,
        provenance=Provenance(
            source=SOURCE,
            generated_at=source_generated_at,
            sample_count=ok_count,
            coverage=ok_count / len(metrics) if metrics else None,
        ),
    )


def build_market_series(
    settings: ApiSettings,
    start: date,
    end: date,
    metric_key: str,
) -> MarketSeriesResponse:
    if not METRIC_KEY.fullmatch(metric_key):
        raise ValueError("invalid market metric key")
    days = inclusive_days(start, end, max_days=settings.max_period_days)
    points: list[MarketSeriesPoint] = []
    missing = 0
    label = unit = None
    for day in days:
        payload = load_market_snapshot(settings.logs_root, day, max_bytes=settings.max_report_bytes)
        indicator = mapping(mapping(mapping(payload).get("macro_indicators")).get("indicators")).get(metric_key)
        row = mapping(indicator)
        if not row:
            missing += 1
            continue
        label = label or text_value(row.get("label"))
        unit = unit or text_value(row.get("unit"))
        points.append(
            MarketSeriesPoint(
                day=day,
                source_generated_at=timestamp(mapping(payload).get("generated_at")),
                value=number(row.get("current")),
                change=number(row.get("delta", row.get("change"))),
                change_pct=number(row.get("change_pct")),
                status=text_value(row.get("status")) or "unknown",
            )
        )
    ok_count = sum(point.status.lower() == "ok" for point in points)
    if not points:
        status = AvailabilityStatus.NO_DATA
    elif missing or ok_count < len(points):
        status = AvailabilityStatus.PARTIAL
    else:
        status = AvailabilityStatus.AVAILABLE
    return MarketSeriesResponse(
        status=status,
        start_date=start,
        end_date=end,
        generated_at=datetime.now(UTC),
        metric_key=metric_key,
        label=label,
        unit=unit,
        points=points,
        missing_day_count=missing,
        provenance=Provenance(
            source=SOURCE,
            sample_count=ok_count,
            coverage=ok_count / len(days) if days else None,
        ),
    )


def _metric(key: str, raw) -> MarketMetric:
    row = mapping(raw)
    return MarketMetric(
        key=key,
        label=text_value(row.get("label")) or key,
        category=text_value(row.get("category")) or "other",
        value=number(row.get("current")),
        change=number(row.get("delta", row.get("change"))),
        change_pct=number(row.get("change_pct")),
        unit=text_value(row.get("unit")) or "value",
        status=text_value(row.get("status")) or "unknown",
        source=text_value(row.get("source")),
        role=text_value(row.get("role")),
    )


def _breadth(row: dict) -> MarketBreadth | None:
    rising = integer(row.get("rising"))
    falling = integer(row.get("falling"))
    unchanged = integer(row.get("unchanged"))
    if rising is None or falling is None or unchanged is None:
        return None
    return MarketBreadth(
        rising=rising,
        falling=falling,
        unchanged=unchanged,
        breadth_ratio=number(row.get("breadth")),
    )
