"""The comparison-unit identity and record shape for the UEF-5.3 dual run."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Optional

from .taxonomy import ComparisonResult, DivergenceReason, SourceAlignment

# Legacy metric fields that the frozen canonical UEF-3A/3B metric contract
# does not persist in any directly comparable form. Corrected in Core
# Correction 1: `win_count`/`loss_count`/`flat_count` were WRONGLY listed
# here in the first delivery -- canonical DOES persist them, on
# `profit_factor.population` (a `WinLossFlatPopulation`). Only the
# per-sample AVERAGE figures remain legacy-only: canonical persists totals
# (`gross_profit`, `gross_loss_abs`), not means, and legacy's own
# "average_gain_pct"/"average_loss_pct"/"expectancy_pct" definitions are not
# independently re-derived here (doing so would require assuming a formula
# equivalence this delivery has not verified against real evidence).
LEGACY_ONLY_METRIC_FIELDS = (
    "win_rate",  # derivable from canonical (win_count/evaluated_count) and now compared -- kept here only
    "average_return_pct",
    "average_gain_pct",
    "average_loss_pct",
    "expectancy_pct",
)


@dataclass(frozen=True)
class ComparisonUnitIdentity:
    family: str
    trading_date: str
    source_path: str
    legacy_content_hash: str = ""
    canonical_run_id: str = ""
    canonical_aggregate_id: str = ""
    view: Optional[str] = None
    horizon_label: Optional[str] = None
    cost_treatment: Optional[str] = None
    canonical_content_digest: str = ""
    reader_profile_identity: str = ""

    def key(self) -> tuple:
        return (
            self.family,
            self.trading_date,
            self.source_path,
            self.legacy_content_hash,
            self.canonical_run_id,
            self.canonical_aggregate_id,
            self.view,
            self.horizon_label,
            self.cost_treatment,
            self.canonical_content_digest,
            self.reader_profile_identity,
        )

    def unit_id(self) -> str:
        """Two different legacy artifacts must never collide here merely
        because their logical labels (day/view/horizon) are equal -- the
        content hash prefix and canonical run id make the identity
        content-bound, not just label-bound."""

        return "UEF53UNIT_" + hashlib.sha256(
            json.dumps(self.key(), ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


@dataclass
class ComparisonRecord:
    """One row of ``dual_run_records.jsonl``.

    Answers: what / which-legacy / which-canonical / same-source /
    same-population / same-horizon / same-cost-semantics / what-differs /
    why. Carries full output lineage (item 21 of Core Correction 1): legacy
    path + content hash, canonical run id + aggregate id, unit id,
    population/view, horizon, metric statuses, classification, reason.
    """

    unit: ComparisonUnitIdentity
    source_alignment: SourceAlignment
    result: ComparisonResult
    reason: Optional[DivergenceReason]
    detail: str
    legacy: Optional[dict] = None
    canonical: Optional[dict] = None
    non_comparable_legacy_fields: list = field(default_factory=list)
    hash_match: Optional[str] = None  # "HASH_MATCH" | "HASH_MISMATCH" | "NO_RECORDED_HASH"
    metric_comparisons: Optional[dict] = None  # per-metric {comparable, status, legacy_value, canonical_value, reason}

    def to_json(self) -> dict:
        return {
            "unit_id": self.unit.unit_id(),
            "family": self.unit.family,
            "trading_date": self.unit.trading_date,
            "source_path": self.unit.source_path,
            "legacy_content_hash": self.unit.legacy_content_hash,
            "canonical_run_id": self.unit.canonical_run_id,
            "canonical_aggregate_id": self.unit.canonical_aggregate_id,
            "canonical_content_digest": self.unit.canonical_content_digest,
            "reader_profile_identity": self.unit.reader_profile_identity,
            "hash_match": self.hash_match,
            "view": self.unit.view,
            "horizon_label": self.unit.horizon_label,
            "cost_treatment": self.unit.cost_treatment,
            "source_alignment": self.source_alignment.value,
            "result": self.result.value,
            "reason": self.reason.value if self.reason is not None else None,
            "detail": self.detail,
            "legacy": self.legacy,
            "canonical": self.canonical,
            "non_comparable_legacy_fields": self.non_comparable_legacy_fields,
            "metric_comparisons": self.metric_comparisons,
        }
