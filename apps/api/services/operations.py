from __future__ import annotations

from datetime import UTC, date, datetime

from ..adapters.runtime_status_artifacts import (
    discover_scheduled_intelligence_days,
    load_scheduled_intelligence_artifacts,
)
from ..config import ApiSettings
from ..domain.scheduled_intelligence_projection import build_scheduled_intelligence_projection
from ..models.common import AvailabilityStatus, Provenance
from ..models.operations import (
    OperationsAlert,
    OperationsComparisonRow,
    OperationsDashboardResponse,
    OperationsTimelineItem,
)
from .anomalies import build_anomalies
from .runtime_status import build_runtime_status
from .trades import build_trade_list


def build_operations_dashboard(settings: ApiSettings) -> OperationsDashboardResponse:
    generated_at = datetime.now(UTC)
    days = discover_scheduled_intelligence_days(settings.reports_root)
    if not days:
        return OperationsDashboardResponse(
            status=AvailabilityStatus.NO_DATA,
            day=generated_at.date(),
            previous_day=None,
            generated_at=generated_at,
            timeline=[],
            alerts=[],
            comparison=[],
            trade_count=0,
            issues=["SCHEDULED_INTELLIGENCE_NOT_FOUND"],
            provenance=Provenance(source="operations.read_model", sample_count=0),
        )

    current_day = date.fromisoformat(days[0])
    previous_day = date.fromisoformat(days[1]) if len(days) > 1 else None
    current = _scheduled_projection(settings, days[0], generated_at)
    previous = _scheduled_projection(settings, days[1], generated_at) if previous_day else None
    trades = build_trade_list(
        settings,
        current_day,
        current_day,
        symbol=None,
        result=None,
        offset=0,
        limit=min(settings.max_trade_bundles, 100),
    )
    runtime = build_runtime_status(settings)
    anomalies = build_anomalies(settings, current_day, now=generated_at)

    timeline = _timeline(current, trades.items)
    alerts = _alerts(current, runtime, anomalies)
    issues = sorted(set([*current.issues, *trades.issues, *anomalies.issues]))
    status = AvailabilityStatus.AVAILABLE
    if issues or alerts:
        status = AvailabilityStatus.PARTIAL
    return OperationsDashboardResponse(
        status=status,
        day=current_day,
        previous_day=previous_day,
        generated_at=generated_at,
        timeline=timeline,
        alerts=alerts,
        comparison=_comparison(current, previous),
        trade_count=trades.total_count,
        issues=issues,
        provenance=Provenance(
            source="operations.read_model",
            as_of=generated_at,
            sample_count=len(timeline) + len(alerts),
        ),
    )


def _scheduled_projection(settings: ApiSettings, day: str, now: datetime):
    artifacts = load_scheduled_intelligence_artifacts(
        settings.reports_root,
        max_bytes=settings.max_report_bytes,
        day=day,
    )
    return build_scheduled_intelligence_projection(artifacts, now=now)


def _timeline(current, trades) -> list[OperationsTimelineItem]:
    rows: list[tuple[tuple[int, str], OperationsTimelineItem]] = []
    phase_order = {"preopen": 10, "entry": 20, "exit": 30, "closeout": 40}
    for job in current.jobs:
        detail = job.summary
        if job.steps:
            success = sum(step.status == "SUCCESS" for step in job.steps)
            detail = f"{success}/{len(job.steps)} steps; {detail or ''}".strip("; ")
        item = OperationsTimelineItem(
            event_id=f"scheduled:{job.job}:{job.day or 'unknown'}",
            phase=job.job,
            title="장전 브리핑" if job.job == "preopen" else "장후 통합 정리",
            expected_time_kst=job.expected_time_kst,
            actual_time=job.generated_at,
            status=job.status,
            detail=detail,
            source="scheduled_job_manifest",
        )
        rows.append(((phase_order.get(job.job, 50), str(job.generated_at or "")), item))
    for trade in trades:
        display = f"{trade.symbol} {trade.symbol_name or ''}".strip()
        if trade.entry_time:
            rows.append(((phase_order["entry"], trade.entry_time.isoformat()), OperationsTimelineItem(
                event_id=f"trade:{trade.trade_id}:entry",
                phase="entry",
                title=f"매수 {display}",
                expected_time_kst=None,
                actual_time=trade.entry_time,
                status="FILLED",
                detail=f"rank {trade.scanner_rank or '-'} · {trade.playbook or trade.tactic_id or 'strategy unavailable'}",
                source="trade_bundle",
                trade_id=trade.trade_id,
            )))
        if trade.exit_time:
            result = trade.result or "unresolved"
            return_text = "-" if trade.realized_return_pct is None else f"{trade.realized_return_pct:+.3f}%"
            rows.append(((phase_order["exit"], trade.exit_time.isoformat()), OperationsTimelineItem(
                event_id=f"trade:{trade.trade_id}:exit",
                phase="exit",
                title=f"매도 {display}",
                expected_time_kst=None,
                actual_time=trade.exit_time,
                status=result.upper(),
                detail=f"{return_text} · hold {int(trade.hold_seconds or 0)}s",
                source="trade_bundle",
                trade_id=trade.trade_id,
            )))
    return [item for _, item in sorted(rows, key=lambda row: row[0])]


def _alerts(current, runtime, anomalies) -> list[OperationsAlert]:
    rows = [
        OperationsAlert(
            alert_id=item.anomaly_id,
            severity=item.severity.value,
            title=item.title,
            detail=item.summary,
            source=item.source,
            observed_at=item.observed_at,
        )
        for item in anomalies.items
    ]
    if runtime.market.expected_running and runtime.runtime_state.value != "RUNNING":
        rows.append(OperationsAlert(
            alert_id="runtime-state",
            severity="CRITICAL",
            title="Trading Main 상태 확인 필요",
            detail=f"장중 기대 상태와 실제 상태가 다릅니다: {runtime.runtime_state.value}",
            source="runtime_status",
            observed_at=runtime.checked_at,
        ))
    for job in current.jobs:
        for index, issue in enumerate(job.issues):
            rows.append(OperationsAlert(
                alert_id=f"scheduled:{job.job}:{index}:{issue}",
                severity="WARNING",
                title=f"{'장전' if job.job == 'preopen' else '장후'} 근거 확인 필요",
                detail=issue,
                source="scheduled_intelligence",
                observed_at=job.generated_at,
            ))
        failed = [step.name for step in job.steps if step.status not in {"SUCCESS", "DELIVERED_ADVISORY"}]
        if failed:
            rows.append(OperationsAlert(
                alert_id=f"scheduled:{job.job}:failed-steps",
                severity="WARNING",
                title=f"{'장전' if job.job == 'preopen' else '장후'} 단계 미완료",
                detail=", ".join(failed),
                source="scheduled_job_manifest",
                observed_at=job.generated_at,
            ))
    severity_order = {"CRITICAL": 0, "WARNING": 1, "WATCH": 2}
    return sorted(rows, key=lambda row: (severity_order.get(row.severity, 9), row.alert_id))


def _comparison(current, previous) -> list[OperationsComparisonRow]:
    current_values = _comparison_values(current)
    previous_values = _comparison_values(previous) if previous else {}
    return [
        OperationsComparisonRow(
            metric=metric,
            current_value=value,
            previous_value=previous_values.get(metric),
            change=("신규" if metric not in previous_values else "동일" if value == previous_values.get(metric) else "변경"),
        )
        for metric, value in current_values.items()
    ]


def _comparison_values(projection) -> dict[str, str | None]:
    if projection is None:
        return {}
    jobs = {job.job: job for job in projection.jobs}
    preopen = jobs.get("preopen")
    closeout = jobs.get("closeout")
    preopen_details = {row.label: row.value for row in (preopen.details if preopen else [])}
    closeout_details = {row.label: row.value for row in (closeout.details if closeout else [])}
    closeout_success = sum(step.status == "SUCCESS" for step in (closeout.steps if closeout else []))
    closeout_total = len(closeout.steps) if closeout else 0
    return {
        "장전 상태": preopen.status if preopen else None,
        "시장 국면": preopen_details.get("시장 국면"),
        "플레이북": preopen_details.get("플레이북"),
        "리스크": preopen_details.get("리스크"),
        "진입 권한": preopen_details.get("진입 권한"),
        "메모리 전달": preopen.memory_status if preopen else None,
        "장후 상태": closeout.status if closeout else None,
        "장후 완료 단계": f"{closeout_success}/{closeout_total}" if closeout else None,
        "거래 수": closeout_details.get("거래 수"),
    }
