from __future__ import annotations

from ...models.anomalies import (
    AnomalyCategory,
    AnomalyEvidence,
    AnomalySeverity,
    OperationalAnomaly,
)
from .factory import anomaly_item


def artifact_integrity_anomaly(issue_count: int) -> list[OperationalAnomaly]:
    if issue_count <= 0:
        return []
    return [
        anomaly_item(
            category=AnomalyCategory.ARTIFACT_INTEGRITY,
            severity=AnomalySeverity.WARNING,
            identity=str(issue_count),
            title="거래 artifact 정합성 주의",
            summary=f"선택 기간 거래 read model에서 {issue_count}개의 무결성 이슈가 확인됐습니다.",
            symbols=[],
            evidence=AnomalyEvidence(
                metric="trade_artifact_issue_count",
                observed_value=issue_count,
                threshold_value=0,
                comparator=">",
                unit="count",
                sample_count=issue_count,
            ),
            source="trade_bundle.normalized_read_model",
        )
    ]
