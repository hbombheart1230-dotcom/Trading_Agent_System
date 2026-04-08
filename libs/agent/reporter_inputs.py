from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ReporterInput:
    day: str
    reports_root: Path
    canonical_report_root: Path
    run_ids: List[str] = field(default_factory=list)
    source_run_count: int = 0
    latest_run_id: str = ""
    latest_run_ts: str = ""
    route_summary: Dict[str, Any] = field(default_factory=dict)
    data_freshness: Dict[str, Any] = field(default_factory=dict)
    available_surfaces: List[str] = field(default_factory=list)
    narrative_axis_policy: Optional[Dict[str, Any]] = None
    generation_mode: str = "deterministic"
    flags: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "day": self.day,
            "reports_root": str(self.reports_root),
            "canonical_report_root": str(self.canonical_report_root),
            "run_ids": list(self.run_ids),
            "source_run_count": int(self.source_run_count),
            "latest_run_id": self.latest_run_id,
            "latest_run_ts": self.latest_run_ts,
            "route_summary": dict(self.route_summary),
            "data_freshness": dict(self.data_freshness),
            "available_surfaces": list(self.available_surfaces),
            "narrative_axis_policy": dict(self.narrative_axis_policy or {}) if self.narrative_axis_policy else None,
            "generation_mode": self.generation_mode,
            "flags": dict(self.flags),
        }
