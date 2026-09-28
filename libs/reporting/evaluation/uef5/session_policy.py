"""UEF-5.2 -- canonical evaluation SessionPolicy.

Separate authority from `MarketDataReceipt.source_window_*` (see docs/decisions/ADR-0003_*): the
receipt describes what was physically ACQUIRED; SessionPolicy describes what UEF EVALUATES. A raw
source containing rows outside the canonical session (e.g. a 15:35 bar) is not thereby invalid -- it is
simply excluded from the canonical projection handed to a frozen adapter, deterministically and
non-mutating (raw storage, and its hash, are never touched by this module).

09:00-15:30 KST is drawn from repository authority, not assumption: the frozen forward engine's own
pervasive session clocks (`FixedClockSpec(clock_label="09:00"/"15:30")`,
libs/reporting/evaluation/canonical/forward/profiles.py) and
`libs/reporting/baseline_btc_woori_tech/input_delivery.py`'s own `[09:00,15:30]` candle clamp.

`ObservationSelectionMode.LAST_AVAILABLE` (frozen UEF-2B) operates purely over whatever `observations`
sequence its caller supplies -- projecting upstream, before any adapter call, makes "last available"
mean "last available within the canonical session view" with zero frozen-engine code touched.

Offline only; deterministic; no clock, no randomness.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Mapping, Sequence

KST = timezone(timedelta(hours=9))

_FIELDS = ("schema", "timezone", "session_start", "session_end", "start_inclusive", "end_inclusive", "extended_row_behavior")


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


class ExtendedRowBehavior(str, Enum):
    EXCLUDE_FROM_CANONICAL_VIEW = "EXCLUDE_FROM_CANONICAL_VIEW"


@dataclass(frozen=True)
class SessionPolicy:
    schema: str
    timezone: str
    session_start: str  # "HH:MM", KST wall-clock, zero-padded (lexicographic order == time order)
    session_end: str
    start_inclusive: bool
    end_inclusive: bool
    extended_row_behavior: str

    def semantic_fields(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in _FIELDS}

    def digest(self) -> str:
        return hashlib.sha256(_canonical_json(self.semantic_fields()).encode("utf-8")).hexdigest()

    @property
    def policy_id(self) -> str:
        return "SESSIONPOL_" + self.digest()[:20]

    def in_session(self, hhmm: str) -> bool:
        lo_ok = hhmm >= self.session_start if self.start_inclusive else hhmm > self.session_start
        hi_ok = hhmm <= self.session_end if self.end_inclusive else hhmm < self.session_end
        return lo_ok and hi_ok


KOREAN_REGULAR_SESSION = SessionPolicy(
    schema="uef5_2_session_policy.v1", timezone="Asia/Seoul",
    session_start="09:00", session_end="15:30",
    start_inclusive=True, end_inclusive=True,
    extended_row_behavior=ExtendedRowBehavior.EXCLUDE_FROM_CANONICAL_VIEW.value,
)


def _hhmm_kst(ts: int) -> str:
    return datetime.fromtimestamp(ts, KST).strftime("%H:%M")


_DIGEST_FIELDS = ("ts", "open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class ProjectionResult:
    rows: tuple  # canonical-session rows, ts ascending -- exactly what an adapter may consume
    raw_row_count: int
    canonical_row_count: int
    excluded_before_session_count: int
    excluded_after_session_count: int
    projection_digest: str


def project_session(rows: Sequence[Mapping[str, Any]], policy: SessionPolicy = KOREAN_REGULAR_SESSION) -> ProjectionResult:
    """Deterministic, non-mutating projection. Callers pass already structurally-validated rows (no
    ambiguous duplicate timestamps); rows are sorted by ts ascending, no secondary tie-break is needed
    or defined."""
    ordered_all = sorted(rows, key=lambda r: r["ts"])
    before = after = 0
    kept: list[Mapping[str, Any]] = []
    for r in ordered_all:
        hhmm = _hhmm_kst(r["ts"])
        if policy.in_session(hhmm):
            kept.append(r)
        elif hhmm < policy.session_start:
            before += 1
        else:
            after += 1
    digest_payload = [{k: r[k] for k in _DIGEST_FIELDS} for r in kept]
    projection_digest = hashlib.sha256(_canonical_json(digest_payload).encode("utf-8")).hexdigest()
    return ProjectionResult(
        rows=tuple(kept), raw_row_count=len(ordered_all), canonical_row_count=len(kept),
        excluded_before_session_count=before, excluded_after_session_count=after,
        projection_digest=projection_digest,
    )


__all__ = [
    "ExtendedRowBehavior", "KOREAN_REGULAR_SESSION", "ProjectionResult", "SessionPolicy", "project_session",
]
