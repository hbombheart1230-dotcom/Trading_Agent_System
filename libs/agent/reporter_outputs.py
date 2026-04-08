from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional


@dataclass(frozen=True)
class ReporterOutput(Mapping[str, Any]):
    report_type: str
    output_paths: Dict[str, str] = field(default_factory=dict)
    generated_at: str = ""
    data_freshness: Dict[str, Any] = field(default_factory=dict)
    route_provenance: Dict[str, Any] = field(default_factory=dict)
    narrative_axis_policy: Optional[Dict[str, Any]] = None
    summary_metadata: Dict[str, Any] = field(default_factory=dict)
    strategist_feedback_packet: Optional[Dict[str, Any]] = None
    operator_packet: Optional[Dict[str, Any]] = None
    success: bool = True
    warnings: List[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def mode(self) -> str:
        return self.report_type

    @property
    def report_md_path(self) -> str:
        return str(self.output_paths.get("md") or self.payload.get("report_md_path") or "")

    @property
    def report_json_path(self) -> str:
        return str(self.output_paths.get("json") or self.payload.get("report_json_path") or "")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.report_type,
            "report_type": self.report_type,
            "day": str(self.payload.get("day") or self.summary_metadata.get("day") or ""),
            "report_md_path": self.report_md_path,
            "report_json_path": self.report_json_path,
            "output_paths": dict(self.output_paths),
            "generated_at": self.generated_at,
            "data_freshness": dict(self.data_freshness),
            "route_provenance": dict(self.route_provenance),
            "narrative_axis_policy": dict(self.narrative_axis_policy or {}) if self.narrative_axis_policy else None,
            "summary_metadata": dict(self.summary_metadata),
            "strategist_feedback_packet": dict(self.strategist_feedback_packet or {}) if self.strategist_feedback_packet else None,
            "operator_packet": dict(self.operator_packet or {}) if self.operator_packet else None,
            "success": bool(self.success),
            "warnings": list(self.warnings),
            "payload": dict(self.payload),
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())
