from __future__ import annotations

from datetime import UTC, date, datetime

from ..adapters.opportunity_artifacts import load_opportunity_sources
from ..config import ApiSettings
from ..infrastructure.dates import latest_iso_day
from ..models.common import AvailabilityStatus, CostBasis, Provenance
from ..models.opportunities import (
    OpportunityFunnelResponse,
    OpportunityOutcomesResponse,
)
from .opportunity_projection import (
    blocker_coverage,
    project_blockers,
    project_latest_signals,
    project_outcomes,
)
from .trade_values import integer, list_value, mapping

SOURCE = "opportunity_shadow_artifacts"


def resolve_opportunity_day(
    settings: ApiSettings,
    day: date | None,
    *,
    outcomes: bool = False,
) -> date | None:
    if day is not None:
        return day
    folder = "opening_rank1_shadow" if outcomes else "opportunity_engine_shadow"
    return latest_iso_day(settings.reports_root / "evaluation" / folder)


def build_opportunity_funnel(
    settings: ApiSettings,
    day: date,
) -> OpportunityFunnelResponse:
    sources = load_opportunity_sources(
        settings.reports_root,
        day,
        max_bytes=settings.max_report_bytes,
    )
    signals_payload = mapping(sources.signals)
    blocker_payload = mapping(sources.blockers)
    signals = list_value(signals_payload.get("signals"))
    latest = project_latest_signals(signals_payload)
    blockers = project_blockers(blocker_payload)
    issues = [
        issue
        for issue in sources.issues
        if issue.endswith("signals") or issue.endswith("blockers")
    ]
    status = _status(bool(signals_payload), bool(blocker_payload), tuple(issues))
    return OpportunityFunnelResponse(
        status=status,
        day=day,
        generated_at=datetime.now(UTC),
        behavior_effect="SHADOW_ONLY",
        raw_candidate_count=integer(blocker_payload.get("raw_candidate_count")) or 0,
        deduplicated_candidate_count=integer(blocker_payload.get("deduped_candidate_count")) or 0,
        duplicate_count=integer(blocker_payload.get("duplicate_count")) or 0,
        signal_count=integer(signals_payload.get("signal_count")) or len(signals),
        current_signal_count=len(latest),
        probe_candidate_count=sum(item.probe_candidate for item in latest),
        probe_near_miss_count=sum(item.probe_near_miss for item in latest),
        blockers=blockers,
        current_signals=latest,
        issues=issues,
        provenance=Provenance(
            source=SOURCE,
            sample_count=len(signals),
            coverage=blocker_coverage(blocker_payload),
        ),
    )


def build_opportunity_outcomes(
    settings: ApiSettings,
    day: date,
) -> OpportunityOutcomesResponse:
    sources = load_opportunity_sources(
        settings.reports_root,
        day,
        max_bytes=settings.max_report_bytes,
    )
    payload = mapping(sources.opening_outcomes)
    outcomes = project_outcomes(payload)
    observed = sum(
        checkpoint.status.lower() == "observed"
        for outcome in outcomes
        for checkpoint in outcome.checkpoints
    )
    expected = sum(len(outcome.checkpoints) for outcome in outcomes)
    issues = [issue for issue in sources.issues if issue.endswith("opening_outcomes")]
    if not payload:
        status = AvailabilityStatus.ERROR if issues else AvailabilityStatus.NO_DATA
    elif not outcomes:
        status = AvailabilityStatus.NO_DATA
    elif not expected:
        status = AvailabilityStatus.PARTIAL
    elif observed < expected:
        status = AvailabilityStatus.PARTIAL
    else:
        status = AvailabilityStatus.AVAILABLE
    return OpportunityOutcomesResponse(
        status=status,
        day=day,
        generated_at=datetime.now(UTC),
        behavior_effect="OBSERVATION_ONLY",
        cost_basis=CostBasis.MOCK_BROKER_NET,
        opportunity_count=len(outcomes),
        observed_checkpoint_count=observed,
        expected_checkpoint_count=expected,
        coverage=observed / expected if expected else None,
        outcomes=outcomes,
        issues=issues,
        provenance=Provenance(
            source="opening_rank1_shadow.v1",
            sample_count=len(outcomes),
            coverage=observed / expected if expected else None,
        ),
    )
def _status(has_signals: bool, has_blockers: bool, issues: tuple[str, ...]) -> AvailabilityStatus:
    if not has_signals and not has_blockers:
        return AvailabilityStatus.ERROR if issues else AvailabilityStatus.NO_DATA
    return AvailabilityStatus.PARTIAL if issues or not (has_signals and has_blockers) else AvailabilityStatus.AVAILABLE
