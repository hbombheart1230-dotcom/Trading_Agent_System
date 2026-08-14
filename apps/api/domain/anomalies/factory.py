from __future__ import annotations

from hashlib import sha256

from ...models.anomalies import AnomalySeverity, OperationalAnomaly


def anomaly_item(
    *,
    category,
    severity,
    identity,
    title,
    summary,
    symbols,
    evidence,
    source,
    observed_at=None,
) -> OperationalAnomaly:
    digest = sha256(f"{category.value}:{identity}".encode("utf-8")).hexdigest()[:12]
    return OperationalAnomaly(
        anomaly_id=f"ANO-{digest}",
        category=category,
        severity=severity,
        title=title,
        summary=summary,
        affected_symbols=sorted(set(symbols)),
        evidence=evidence,
        source=source,
        observed_at=observed_at,
    )


def sort_anomalies(items: list[OperationalAnomaly]) -> list[OperationalAnomaly]:
    order = {
        AnomalySeverity.CRITICAL: 0,
        AnomalySeverity.WARNING: 1,
        AnomalySeverity.WATCH: 2,
    }
    return sorted(
        items,
        key=lambda item: (order[item.severity], item.category.value, item.anomaly_id),
    )
