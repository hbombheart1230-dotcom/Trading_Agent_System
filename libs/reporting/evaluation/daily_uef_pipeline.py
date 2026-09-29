"""Scheduler-agnostic daily UEF EOD evaluation orchestrator (P1.2 gap fix).

P1.2 Day-1 observation (2026-09-29) found that the Alpha Board -> UEF-7 ->
UEF-8 -> UEF-9 chain had no automatic daily trigger and no single
orchestration entry point: the UEF-7/UEF-8 CLIs each independently rebuild
the Alpha Board from scratch (libs.reporting.alpha_research_board.
build_alpha_research_board), UEF-9's CLI requires the caller to pass
already-written UEF-7/UEF-8 file paths by hand, and
write_alpha_research_board() advances reports/evaluation/
alpha_research_board/latest.json unconditionally the moment it is called,
with no gate on whether the board (or a downstream UEF stage) is actually
valid. Separately, the Windows scheduled task
(deploy/m28_launch_templates/windows/scheduler_task.xml) only ever invokes
the live commander runtime loop -- nothing in this repository automatically
triggers Alpha Board / UEF-7/8/9 on any schedule.

This module is the ONE orchestration entry point both the current Windows
scheduling and any future Docker/Linux scheduling must call (via
scripts/run_daily_uef_evaluation.py) -- never duplicate Alpha Board / UEF
semantics inside a scheduler file itself. It does not reimplement any
Alpha Board or UEF-7/8/9 semantics; it only sequences the existing, frozen
library functions and adds the missing fail-closed gating around them.

Evaluation/reporting only: nothing in this call graph imports
libs.execution.*, libs.runtime.live_loop_runner, or any Kiwoom transport
module. No broker/runtime/execution state is ever touched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from libs.reporting.alpha_research_board import build_alpha_research_board, write_alpha_research_board
from libs.reporting.evaluation.uef7.alpha_board_normalization import normalize_alpha_board
from libs.reporting.evaluation.uef7.reporter import write_uef7_normalization_outputs
from libs.reporting.evaluation.uef7.run_identity import normalizer_implementation_digest
from libs.reporting.evaluation.uef8.fair_comparison import analyze_fair_comparisons
from libs.reporting.evaluation.uef8.reporter import write_uef8_fair_comparison_outputs
from libs.reporting.evaluation.uef8.run_identity import uef8_implementation_digest
from libs.reporting.evaluation.uef9.authority import verify_formal_evaluation_authority
from libs.reporting.evaluation.uef9.reporter import write_formal_evaluation_authority
from libs.reporting.evaluation.uef9.run_identity import uef9_implementation_digest


# The Alpha Board's own candidate schema is fixed (always exactly 14 named
# slots, confirmed directly: build_alpha_research_board(reports_root=
# <a directory that does not even exist>, ...) still returns
# candidate_count=14, integrity.status="PASS_WITH_MISSING_SOURCES") -- an
# empty/near-empty input never shows up as a low candidate_count, so that
# cannot be the "board is missing" signal. These two are the sources that
# feed the board's own live, same-day-generated feature/scanner shadow
# candidates (as opposed to the more specialized BTC/large-cap/opening
# sources, which legitimately do not fire every single day and which the
# board's own contract already tolerates being absent via
# PASS_WITH_MISSING_SOURCES) -- their absence means no real per-day
# candidate evidence exists at all, not just that one specialized track is
# quiet today.
_REQUIRED_SOURCE_KEYS = ("feature_candidates", "prospective_candidates")


def check_board_source_freshness(board: Dict[str, Any], through_day: str) -> List[str]:
    """Return blocking findings for `board`; empty means clear to proceed.

    Two independent kinds of finding, both fail-closed:

    1. A required source (_REQUIRED_SOURCE_KEYS) that is missing or
       unreadable -- the board's own tolerance for missing sources
       (PASS_WITH_MISSING_SOURCES) is appropriate for its own read-only
       reporting use, but not for gating a daily evaluation authority run.

    2. Any source, required or optional, that IS available but whose own
       `through_day` field does not match the requested day. This matters
       because board["through_day"] is an ECHO of whatever the caller
       requested -- build_alpha_research_board always assigns it directly
       from its own `through_day` argument (libs/reporting/
       alpha_research_board/builder.py), never derives it from the
       underlying source data. Trusting that top-level field alone as a
       freshness signal is vacuous: it always matches by construction, for
       any requested day, even when every underlying source is weeks
       stale. Confirmed directly against this repository's own state:
       tmp/p1_1_acceptance/REAL_RUN_CAPTURE_A.json claims through_day=
       "2026-09-29" at its top level while several of its own per-source
       entries (fresh_change, latent_reactivation, opening_cumulative,
       prospective_candidates) carry through_day="2026-09-25" -- the
       underlying cumulative shadow-evaluation pipelines had not advanced
       past that Friday. This checks each individual dated SOURCE's own
       `through_day` field instead (populated by
       libs.reporting.alpha_research_board.loaders.load_json from that
       source file's own payload, independently of the board's top-level
       field).
    """
    findings: List[str] = []
    sources = board.get("sources") or {}

    for key in _REQUIRED_SOURCE_KEYS:
        info = sources.get(key)
        if not isinstance(info, dict) or not info.get("available", False):
            findings.append(f"{key}: MISSING_ARTIFACT (required source)")
        elif info.get("error"):
            findings.append(f"{key}: {info['error']} (required source)")

    for name, info in sources.items():
        if not isinstance(info, dict):
            continue
        if not info.get("available", True) or info.get("error"):
            continue  # optional/missing sources tolerated, matches the board's own PASS_WITH_MISSING_SOURCES contract
        source_day = info.get("through_day")
        if source_day and source_day != through_day:
            findings.append(f"{name}: stale through_day={source_day!r} (target={through_day!r})")
    return findings


@dataclass
class DailyUefEvaluationResult:
    ok: bool
    through_day: str
    stage_failed: Optional[str] = None
    reason: str = ""
    stale_sources: List[str] = field(default_factory=list)
    board_path: Optional[str] = None
    board_candidate_count: Optional[int] = None
    uef7_run_id: Optional[str] = None
    uef8_run_id: Optional[str] = None
    uef9_run_id: Optional[str] = None
    uef8_pair_count: Optional[int] = None
    uef8_comparable: Optional[int] = None
    uef8_conditional: Optional[int] = None
    uef8_not_comparable: Optional[int] = None
    authority_status: Optional[str] = None
    output_dirs: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "through_day": self.through_day,
            "stage_failed": self.stage_failed,
            "reason": self.reason,
            "stale_sources": self.stale_sources,
            "board_path": self.board_path,
            "board_candidate_count": self.board_candidate_count,
            "uef7_run_id": self.uef7_run_id,
            "uef8_run_id": self.uef8_run_id,
            "uef9_run_id": self.uef9_run_id,
            "uef8_pair_count": self.uef8_pair_count,
            "uef8_comparable": self.uef8_comparable,
            "uef8_conditional": self.uef8_conditional,
            "uef8_not_comparable": self.uef8_not_comparable,
            "authority_status": self.authority_status,
            "output_dirs": self.output_dirs,
        }


def run_daily_uef_evaluation(
    *,
    repo_root: Path,
    through_day: str,
    require_fresh_sources: bool = True,
) -> DailyUefEvaluationResult:
    """The one scheduler-agnostic daily post-market evaluation entry point.

    Fail-closed, in this exact order:
      1. Build the Alpha Board in-memory (read-only; nothing persisted yet;
         libs.reporting.alpha_research_board.build_alpha_research_board is
         never mutated or reimplemented here).
      2. Freshness guard (see check_board_source_freshness): a stale or
         missing source rejects here, before any UEF stage runs and before
         any file is written or latest.json/.md touched.
      3. UEF-7 normalizes that EXACT in-memory board object -- not a fresh
         rebuild, so this is genuinely "feed the exact captured board to
         UEF-7", not two independent computations that happen to agree.
      4. UEF-8 runs against that EXACT UEF-7 result object.
      5. UEF-9 verifies that EXACT UEF-7 + UEF-8 pair. VALID is the only
         non-raising outcome verify_formal_evaluation_authority's own
         contract ever returns; any contradiction raises UEF9AuthorityError,
         treated here as a failed stage. The authority_status=="VALID"
         check below is kept anyway as a second, independent, defensive
         gate rather than trusting that upstream contract blindly.
      6. Only once every stage above has succeeded are the UEF-7/8/9
         outputs persisted to their own canonical, content-keyed (and
         therefore idempotent) paths, and only THEN is the dated Alpha
         Board written and latest.json/latest.md advanced (via the
         existing, unmodified write_alpha_research_board). A failure at
         any earlier stage leaves latest.json/.md completely untouched --
         no misleading "success" pointer is ever written on a failed run.

    Re-running with the same through_day against unchanged on-disk source
    state is idempotent: every UEF run_id here is a deterministic digest of
    its own semantic input (never a wall-clock timestamp -- see each
    stage's own run_identity module), so a repeat run reproduces the exact
    same run_ids and overwrites the exact same output paths with the exact
    same content. No duplicate trading action, broker interaction, or
    runtime-state mutation is possible from this path at all: it calls
    nothing outside libs.reporting.*.
    """

    through_day = str(through_day)[:10]
    repo_root = Path(repo_root)
    reports_root = repo_root / "reports"

    try:
        board = build_alpha_research_board(reports_root=reports_root, through_day=through_day)
    except Exception as exc:  # noqa: BLE001 - fail closed on any board-build defect, not just named ones
        return DailyUefEvaluationResult(
            ok=False, through_day=through_day, stage_failed="board_build",
            reason=f"{type(exc).__name__}: {exc}",
        )

    if board.get("through_day") != through_day:
        return DailyUefEvaluationResult(
            ok=False, through_day=through_day, stage_failed="board_build",
            reason=f"board.through_day={board.get('through_day')!r} != requested {through_day!r}",
        )

    stale = check_board_source_freshness(board, through_day)
    if stale and require_fresh_sources:
        return DailyUefEvaluationResult(
            ok=False, through_day=through_day, stage_failed="freshness_guard",
            reason="one or more underlying sources are not dated for the requested day -- refusing to "
                   "materialize a board that would silently mix a fresh through_day label with stale content",
            stale_sources=stale,
            board_candidate_count=int(board.get("candidate_count") or 0),
        )

    try:
        uef7 = normalize_alpha_board(board, normalizer_implementation_digest_value=normalizer_implementation_digest())
    except Exception as exc:  # noqa: BLE001
        return DailyUefEvaluationResult(
            ok=False, through_day=through_day, stage_failed="uef7",
            reason=f"{type(exc).__name__}: {exc}", stale_sources=stale,
        )
    uef7_dict = uef7.to_dict()

    try:
        uef8 = analyze_fair_comparisons(uef7_dict, uef8_implementation_digest_value=uef8_implementation_digest())
    except Exception as exc:  # noqa: BLE001
        return DailyUefEvaluationResult(
            ok=False, through_day=through_day, stage_failed="uef8",
            reason=f"{type(exc).__name__}: {exc}", uef7_run_id=uef7.uef7_run_id, stale_sources=stale,
        )
    uef8_dict = uef8.to_dict()

    try:
        uef9 = verify_formal_evaluation_authority(
            uef7_dict, uef8=uef8_dict, uef9_implementation_digest_value=uef9_implementation_digest()
        )
    except Exception as exc:  # noqa: BLE001
        return DailyUefEvaluationResult(
            ok=False, through_day=through_day, stage_failed="uef9",
            reason=f"{type(exc).__name__}: {exc}",
            uef7_run_id=uef7.uef7_run_id, uef8_run_id=uef8.uef8_run_id, stale_sources=stale,
        )

    if uef9.authority_status != "VALID":
        return DailyUefEvaluationResult(
            ok=False, through_day=through_day, stage_failed="uef9",
            reason=f"authority_status={uef9.authority_status!r} (expected VALID)",
            uef7_run_id=uef7.uef7_run_id, uef8_run_id=uef8.uef8_run_id, uef9_run_id=uef9.uef9_run_id,
            authority_status=uef9.authority_status, stale_sources=stale,
        )

    uef7_dir = write_uef7_normalization_outputs(uef7, repo_root=repo_root)
    uef8_dir = write_uef8_fair_comparison_outputs(uef8, repo_root=repo_root)
    uef9_dir = write_formal_evaluation_authority(uef9, repo_root=repo_root)

    board_output_dir = reports_root / "evaluation" / "alpha_research_board" / through_day
    board_write = write_alpha_research_board(
        reports_root=reports_root, through_day=through_day, output_dir=board_output_dir
    )

    return DailyUefEvaluationResult(
        ok=True, through_day=through_day,
        board_path=board_write.get("json_path"),
        board_candidate_count=int(board.get("candidate_count") or 0),
        uef7_run_id=uef7.uef7_run_id, uef8_run_id=uef8.uef8_run_id, uef9_run_id=uef9.uef9_run_id,
        uef8_pair_count=uef8.summary.pair_count,
        uef8_comparable=uef8.summary.comparable_count,
        uef8_conditional=uef8.summary.conditional_count,
        uef8_not_comparable=uef8.summary.not_comparable_count,
        authority_status=uef9.authority_status,
        output_dirs={
            "uef7": str(uef7_dir), "uef8": str(uef8_dir), "uef9": str(uef9_dir),
            "board": str(board_output_dir),
        },
    )


__all__ = [
    "DailyUefEvaluationResult",
    "check_board_source_freshness",
    "run_daily_uef_evaluation",
]
