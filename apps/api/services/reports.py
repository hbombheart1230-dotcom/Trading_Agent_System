from __future__ import annotations

from datetime import UTC, datetime

from ..adapters.safe_reports import (
    REPORT_SPECS,
    read_safe_report,
    report_path,
    report_spec,
)
from ..config import ApiSettings
from ..infrastructure.bounded_reader import BoundedReadError
from ..infrastructure.trade_index import locate_trade_bundle
from ..models.common import AvailabilityStatus, Provenance
from ..models.reports import (
    ReportCatalogResponse,
    ReportContentResponse,
    ReportDescriptor,
)

SOURCE = "trade_bundle.allowlisted_reports"


def build_report_catalog(
    settings: ApiSettings,
    trade_id: str,
) -> ReportCatalogResponse | None:
    ref = locate_trade_bundle(settings.reports_root, trade_id)
    if ref is None:
        return None
    if settings.public_mode:
        return ReportCatalogResponse(
            status=AvailabilityStatus.UNAVAILABLE,
            trade_id=trade_id,
            generated_at=datetime.now(UTC),
            reports=[],
            provenance=Provenance(source="public_profile.report_content_disabled"),
        )
    rows: list[ReportDescriptor] = []
    for spec in REPORT_SPECS:
        path = report_path(ref.root, spec)
        size = _safe_report_size(path, settings.max_report_bytes)
        available = size is not None
        rows.append(
            ReportDescriptor(
                report_id=spec.report_id,
                title=spec.title,
                format=spec.format,
                available=available,
                size_bytes=size,
            )
        )
    status = (
        AvailabilityStatus.AVAILABLE
        if any(row.available for row in rows)
        else AvailabilityStatus.NO_DATA
    )
    return ReportCatalogResponse(
        status=status,
        trade_id=trade_id,
        generated_at=datetime.now(UTC),
        reports=rows,
        provenance=Provenance(
            source=SOURCE,
            sample_count=sum(row.available for row in rows),
        ),
    )


def build_report_content(
    settings: ApiSettings,
    trade_id: str,
    report_id: str,
) -> ReportContentResponse | None:
    ref = locate_trade_bundle(settings.reports_root, trade_id)
    spec = report_spec(report_id)
    if ref is None or spec is None:
        return None
    if settings.public_mode:
        return ReportContentResponse(
            status=AvailabilityStatus.UNAVAILABLE,
            trade_id=trade_id,
            report_id=spec.report_id,
            title=spec.title,
            format=spec.format,
            generated_at=datetime.now(UTC),
            provenance=Provenance(source="public_profile.report_content_disabled"),
        )
    path = report_path(ref.root, spec)
    if not path.is_file():
        return _missing_content(trade_id, spec)
    try:
        content = read_safe_report(
            ref.root,
            spec,
            max_bytes=settings.max_report_bytes,
        )
    except (BoundedReadError, OSError, ValueError):
        return _error_content(trade_id, spec)
    return ReportContentResponse(
        status=AvailabilityStatus.AVAILABLE,
        trade_id=trade_id,
        report_id=spec.report_id,
        title=spec.title,
        format=spec.format,
        generated_at=datetime.now(UTC),
        markdown=content if spec.format == "markdown" else None,
        json_content=content if spec.format == "json" else None,
        provenance=Provenance(source=SOURCE),
    )


def _missing_content(trade_id, spec):
    return ReportContentResponse(
        status=AvailabilityStatus.NO_DATA,
        trade_id=trade_id,
        report_id=spec.report_id,
        title=spec.title,
        format=spec.format,
        generated_at=datetime.now(UTC),
        provenance=Provenance(source=SOURCE),
    )


def _error_content(trade_id, spec):
    row = _missing_content(trade_id, spec)
    return row.model_copy(update={"status": AvailabilityStatus.ERROR})


def _safe_report_size(path, max_bytes):
    try:
        if not path.is_file():
            return None
        size = path.stat().st_size
        return size if size <= max_bytes else None
    except OSError:
        return None
