"""Compatibility facade for the modular operational-anomaly rules."""

from .anomalies import (
    POLICY_VERSION,
    AnomalyPolicy,
    artifact_integrity_anomaly,
    evaluate_freshness,
    evaluate_missed_opportunities,
    evaluate_trade_anomalies,
    sort_anomalies,
)

__all__ = [
    "POLICY_VERSION",
    "AnomalyPolicy",
    "artifact_integrity_anomaly",
    "evaluate_freshness",
    "evaluate_missed_opportunities",
    "evaluate_trade_anomalies",
    "sort_anomalies",
]
