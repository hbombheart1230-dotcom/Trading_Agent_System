from __future__ import annotations

from ..adapters.trade_bundle import TradeBundleSource
from ..models.common import AvailabilityStatus
from ..models.trades import ArtifactIntegrity
from .trade_values import mapping, number, text_value


def project_integrity(
    source: TradeBundleSource,
    extra_issues: list[str],
) -> ArtifactIntegrity:
    health = source.health or {}
    provenance = source.provenance or {}
    exclusion = source.exclusion or {}
    issues = sorted(set(source.issues).union(extra_issues))
    completeness = text_value(health.get("lifecycle_completeness"))
    if completeness and completeness != "complete":
        issues.append("LIFECYCLE_NOT_COMPLETE")
    active_exclusion = exclusion.get("active") is True
    status = AvailabilityStatus.PARTIAL if issues else AvailabilityStatus.AVAILABLE
    if source.source_status in {"MISSING", "INVALID"}:
        status = AvailabilityStatus.ERROR
    reconciliation = mapping(health.get("broker_reconciliation"))
    return ArtifactIntegrity(
        status=status,
        lifecycle_status=text_value(health.get("lifecycle_status")),
        lifecycle_completeness=completeness,
        completeness_score=number(health.get("completeness_score")),
        broker_reconciliation_status=text_value(reconciliation.get("status")),
        agent_sources={
            str(key): str(value)
            for key, value in mapping(provenance.get("agent_sources")).items()
        },
        evaluation_eligible=not active_exclusion,
        exclusion_reason=(
            text_value(exclusion.get("reason_code")) if active_exclusion else None
        ),
        issues=sorted(set(issues)),
    )
