from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
POLICY_VERSION = "operational_anomaly.v1"


@dataclass(frozen=True, slots=True)
class AnomalyPolicy:
    repeated_loss_count: int = 2
    early_loss_exit_seconds: int = 60
    cost_drag_warning_pct: float = 0.50
    missed_opportunity_net_return_pct: float = 0.30
    runtime_stale_warning_seconds: int = 300
    runtime_stale_critical_seconds: int = 900
