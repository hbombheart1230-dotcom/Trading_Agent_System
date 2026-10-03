"""UEF-6A-local report model.

Deliberately does NOT duplicate the frozen ``DuplicateRelation`` enum
(``libs/reporting/evaluation/canonical/identity.py``) -- relation values
are carried here only as their already-canonical ``.value`` strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

REPORT_SCHEMA_VERSION = "uef6a_dedup_report.v1"


@dataclass(frozen=True)
class EventCluster:
    """One physical-event cluster: every episode sharing one ``canonical_event_id``."""

    canonical_event_id: str
    symbols: tuple
    trading_dates: tuple
    evaluation_subject_ids: tuple
    evaluation_record_ids: tuple
    hypothesis_ids: tuple
    execution_modes: tuple
    evaluator_versions: tuple
    row_count: int
    unique_subject_count: int
    unique_record_count: int
    relation_summary: Mapping[str, int]

    def to_dict(self) -> dict:
        return {
            "canonical_event_id": self.canonical_event_id,
            "symbols": list(self.symbols),
            "trading_dates": list(self.trading_dates),
            "evaluation_subject_ids": list(self.evaluation_subject_ids),
            "evaluation_record_ids": list(self.evaluation_record_ids),
            "hypothesis_ids": list(self.hypothesis_ids),
            "execution_modes": list(self.execution_modes),
            "evaluator_versions": list(self.evaluator_versions),
            "row_count": self.row_count,
            "unique_subject_count": self.unique_subject_count,
            "unique_record_count": self.unique_record_count,
            "relation_summary": dict(sorted(self.relation_summary.items())),
        }


@dataclass(frozen=True)
class DuplicateGroup:
    """One repeated ``evaluation_record_id`` group (occurrence_count > 1)."""

    evaluation_record_id: str
    evaluation_subject_id: str
    canonical_event_id: str
    occurrence_count: int
    duplicate_excess_count: int
    content_digest: Optional[str]
    relation: str

    def to_dict(self) -> dict:
        return {
            "evaluation_record_id": self.evaluation_record_id,
            "evaluation_subject_id": self.evaluation_subject_id,
            "canonical_event_id": self.canonical_event_id,
            "occurrence_count": self.occurrence_count,
            "duplicate_excess_count": self.duplicate_excess_count,
            "content_digest": self.content_digest,
            "relation": self.relation,
        }


@dataclass(frozen=True)
class PopulationDedupReport:
    """The full result of :func:`population_dedup.analyze_episode_population`."""

    raw_row_count: int
    unique_canonical_event_count: int
    unique_evaluation_subject_count: int
    unique_evaluation_record_count: int
    duplicate_group_count: int
    duplicate_excess_row_count: int
    relation_counts: Mapping[str, int]
    event_cluster_count: int
    multi_evaluation_event_count: int  # event clusters with unique_subject_count > 1
    events_with_multiple_subjects: int  # same as multi_evaluation_event_count, named per item 19's real-run report
    events_with_multiple_records: int  # event clusters with unique_record_count > 1
    event_clusters: Sequence[EventCluster] = field(default_factory=tuple)
    duplicate_groups: Sequence[DuplicateGroup] = field(default_factory=tuple)
    report_schema_version: str = REPORT_SCHEMA_VERSION

    def summary_dict(self) -> dict:
        return {
            "report_schema_version": self.report_schema_version,
            "raw_row_count": self.raw_row_count,
            "unique_canonical_event_count": self.unique_canonical_event_count,
            "unique_evaluation_subject_count": self.unique_evaluation_subject_count,
            "unique_evaluation_record_count": self.unique_evaluation_record_count,
            "duplicate_group_count": self.duplicate_group_count,
            "duplicate_excess_row_count": self.duplicate_excess_row_count,
            "relation_counts": dict(sorted(self.relation_counts.items())),
            "event_cluster_count": self.event_cluster_count,
            "multi_evaluation_event_count": self.multi_evaluation_event_count,
            "events_with_multiple_subjects": self.events_with_multiple_subjects,
            "events_with_multiple_records": self.events_with_multiple_records,
        }
