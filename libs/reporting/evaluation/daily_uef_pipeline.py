"""Scheduler-agnostic daily UEF EOD evaluation orchestrator (P1.2 gap fix).

Fix2 (Codex independent audit, 2026-09-29) corrected three defects in the
first implementation and hardened one atomicity gap; see
docs/daily_patch/2026-09-29_daily_uef_eod_wiring_fix2.md for the full audit
trail. Summary of what changed and why:

H1 (single-capture authority): the first implementation called
build_alpha_research_board() twice -- once to feed UEF-7/8/9, once more
inside write_alpha_research_board() to persist -- so if an underlying
source mutated between the two calls (a live host writing concurrently is
exactly this repository's normal operating condition), the persisted
canonical Board could silently differ from the Board UEF-9 actually
verified. Fixed: build_alpha_research_board() is called EXACTLY ONCE per
run; persist_canonical_alpha_board()/advance_latest_pointer() below write
that exact in-memory object, never rebuilding.

H2 (competing canonical publisher): libs/reporting/closeout_maintenance.py
independently called write_alpha_research_board() -- which persists the
canonical dated Board and advances latest.json/.md unconditionally -- with
no UEF-9 involvement at all. Fixed by removing that call (see the closeout
module's own history); this module is now the ONLY code path anywhere in
this repository permitted to advance
reports/evaluation/alpha_research_board/<day>/ or latest.json/.md.

H3 (freshness contracts): the first implementation's freshness guard
required every dated source's own through_day to equal the target day,
with no distinction between sources whose contract is genuinely daily and
sources that are not. It also allowed --allow-stale-sources to bypass the
guard and still reach canonical publication. Fixed: _SOURCE_FRESHNESS_
CONTRACTS below encodes explicit, evidence-based per-source rules (see its
own docstring), and `canonical=False` (diagnostic mode) can never write
any canonical file, regardless of outcome -- publication and the freshness
bypass are now structurally exclusive.

M1 (atomicity): file writes previously used plain path.write_text(), which
can leave a half-written file on interruption. persist_canonical_alpha_
board() and advance_latest_pointer() now write to a temp file in the same
directory, fsync it, and os.replace() it into place -- atomic on both
POSIX and NTFS for a same-volume rename.

This module remains the ONE scheduler-agnostic orchestration entry point
(via scripts/run_daily_uef_evaluation.py) -- never duplicate Alpha Board /
UEF semantics in a scheduler file. It reimplements no Alpha Board or
UEF-7/8/9 semantics; it only sequences the existing, frozen library
functions and owns the missing fail-closed gating and atomic persistence
around them.

Evaluation/reporting only: nothing in this call graph imports
libs.execution.*, libs.runtime.live_loop_runner, or any Kiwoom transport
module. No broker/runtime/execution state is ever touched.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from libs.reporting.alpha_research_board import build_alpha_research_board
from libs.reporting.alpha_research_board.report import render_alpha_research_board
from libs.reporting.evaluation.uef7.alpha_board_normalization import normalize_alpha_board
from libs.reporting.evaluation.uef7.reporter import write_uef7_normalization_outputs
from libs.reporting.evaluation.uef7.run_identity import normalizer_implementation_digest
from libs.reporting.evaluation.uef8.fair_comparison import analyze_fair_comparisons
from libs.reporting.evaluation.uef8.reporter import write_uef8_fair_comparison_outputs
from libs.reporting.evaluation.uef8.run_identity import uef8_implementation_digest
from libs.reporting.evaluation.uef9.authority import verify_formal_evaluation_authority
from libs.reporting.evaluation.uef9.reporter import write_formal_evaluation_authority
from libs.reporting.evaluation.uef9.run_identity import uef9_implementation_digest


# --- Source freshness contracts (H3) ----------------------------------------


@dataclass(frozen=True)
class SourceFreshnessContract:
    source_key: str
    required: bool
    # "UPDATED_THROUGH_TARGET_DAY": the source's own through_day/day field
    #   must equal the requested target day, including a legitimate
    #   zero-event day (VALID_NO_EPISODES / NO_OPENING_RANK1 / zero
    #   redetections is still a fresh, dated file -- freshness is judged by
    #   the date stamp, never by row/event count).
    # "PRESENT_ONLY": the source must exist and be readable, but its own
    #   date (if any) is never compared to the target day, because its
    #   contract is not a daily one (see feature_candidates below).
    mode: str


# Evidence for every entry here was gathered directly against this
# repository's real source files, not assumed. Deliberately NOT generalized
# to every key in SOURCE_PATHS (libs/reporting/alpha_research_board/
# contracts.py) -- a source with no contract entry here is treated as
# optional/best-effort, exactly matching build_alpha_research_board's own
# PASS_WITH_MISSING_SOURCES tolerance, and is never used to reject a run.
_SOURCE_FRESHNESS_CONTRACTS: Tuple[SourceFreshnessContract, ...] = (
    # Confirmed directly (P1.2 Day-1): these four are written by the daily
    # closeout pipeline and their own captured payload carried an explicit
    # through_day matching the day they were generated on, going stale
    # (still 2026-09-25) exactly when closeout stopped running daily.
    SourceFreshnessContract("prospective_candidates", required=True, mode="UPDATED_THROUGH_TARGET_DAY"),
    SourceFreshnessContract("fresh_change", required=True, mode="UPDATED_THROUGH_TARGET_DAY"),
    SourceFreshnessContract("opening_cumulative", required=True, mode="UPDATED_THROUGH_TARGET_DAY"),
    SourceFreshnessContract("latent_reactivation", required=True, mode="UPDATED_THROUGH_TARGET_DAY"),
    # Confirmed directly (Fix2): reports/evaluation/feature_mart/
    # opening_rank1/candidate_selection.json carries no through_day/day
    # field at all. Its own payload instead carries
    # selection_period={validation_start, selection_end_day} -- a FIXED,
    # one-time offline backtest window (schema_version=
    # rank1_candidate_selection.v1, behavior_effect=
    # NONE_OFFLINE_RESEARCH_ONLY) -- this is a frozen feature-eligibility
    # artifact by design, not something that advances daily. Treating its
    # age as "staleness" would be inventing a freshness rule its own
    # contract does not have. It is still required to be PRESENT (it feeds
    # the core candidate pool), just never date-compared.
    SourceFreshnessContract("feature_candidates", required=True, mode="PRESENT_ONLY"),
)


def evaluate_source_freshness_contracts(board: Dict[str, Any], through_day: str) -> List[str]:
    """Return blocking findings for `board` against _SOURCE_FRESHNESS_CONTRACTS;
    empty means clear to proceed. See each contract's own mode docstring
    above for what "clear" means per source.
    """
    findings: List[str] = []
    sources = board.get("sources") or {}
    for contract in _SOURCE_FRESHNESS_CONTRACTS:
        info = sources.get(contract.source_key)
        available = isinstance(info, dict) and bool(info.get("available")) and not info.get("error")
        if not available:
            error = info.get("error") if isinstance(info, dict) else None
            detail = f" ({error})" if error else ""
            findings.append(
                f"{contract.source_key}: MISSING_ARTIFACT{detail} (required, mode={contract.mode})"
            )
            continue
        if contract.mode == "UPDATED_THROUGH_TARGET_DAY":
            source_day = info.get("through_day")
            if source_day != through_day:
                findings.append(
                    f"{contract.source_key}: stale through_day={source_day!r} (target={through_day!r})"
                )
        # PRESENT_ONLY: presence already confirmed above; no date comparison.
    return findings


# --- Atomic, single-capture canonical persistence (H1 + M1) -----------------


def _atomic_write_text(path: Path, content: str) -> None:
    """Write `content` to `path` atomically: temp file in the same
    directory, fsync, then os.replace() -- atomic on both POSIX and NTFS
    for a same-volume rename, so a crash/interruption mid-write can never
    leave a half-written canonical file in place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def persist_canonical_alpha_board(board: Dict[str, Any], *, output_dir: Path) -> Dict[str, str]:
    """Persist the EXACT already-built `board` object to the dated
    `output_dir` -- never rebuilds it. The only function permitted to write
    reports/evaluation/alpha_research_board/<day>/alpha_research_board.*.

    Deliberately writes only the identity-critical board file itself
    (json + markdown), not the supplementary sensitivity/remaining-review/
    runtime-validation/short-alpha diagnostic companions -- those are
    separate derived reports, not part of "the Board UEF-7 evaluated", and
    including them here would reintroduce a second, independently-rebuilt
    surface with its own single-capture question. Callers that want those
    diagnostics for a given day can still call their own builders directly
    against a non-canonical output location.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    json_content = json.dumps(board, ensure_ascii=False, indent=2)
    markdown_content = render_alpha_research_board(board)
    json_path = output_dir / "alpha_research_board.json"
    markdown_path = output_dir / "alpha_research_board.md"
    _atomic_write_text(json_path, json_content)
    _atomic_write_text(markdown_path, markdown_content)
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}


def advance_latest_pointer(board: Dict[str, Any], *, latest_dir: Path) -> Dict[str, str]:
    """Advance latest.json/.md to the EXACT `board` already persisted by
    persist_canonical_alpha_board(). Callers must only invoke this AFTER
    the dated bundle above has been fully written AND UEF-9 has returned
    authority_status=VALID for that exact board -- this function itself
    performs no such check, ordering is the orchestrator's responsibility.
    """
    latest_dir.mkdir(parents=True, exist_ok=True)
    json_content = json.dumps(board, ensure_ascii=False, indent=2)
    markdown_content = render_alpha_research_board(board)
    latest_json_path = latest_dir / "latest.json"
    latest_markdown_path = latest_dir / "latest.md"
    _atomic_write_text(latest_json_path, json_content)
    _atomic_write_text(latest_markdown_path, markdown_content)
    return {"latest_json_path": str(latest_json_path), "latest_markdown_path": str(latest_markdown_path)}


# --- Result / orchestrator ---------------------------------------------------


@dataclass
class DailyUefEvaluationResult:
    ok: bool
    through_day: str
    canonical: bool
    published: bool = False
    stage_failed: Optional[str] = None
    reason: str = ""
    freshness_findings: List[str] = field(default_factory=list)
    board_candidate_count: Optional[int] = None
    board_path: Optional[str] = None
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
            "canonical": self.canonical,
            "published": self.published,
            "stage_failed": self.stage_failed,
            "reason": self.reason,
            "freshness_findings": self.freshness_findings,
            "board_candidate_count": self.board_candidate_count,
            "board_path": self.board_path,
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
    canonical: bool = True,
) -> DailyUefEvaluationResult:
    """The one scheduler-agnostic daily post-market evaluation entry point.

    `canonical=True` (the only mode a scheduler may use): the freshness
    contracts are always enforced, and reports/evaluation/
    alpha_research_board/<day>/ + latest.json/.md are only ever written
    once the full chain succeeds with authority_status=VALID -- using the
    single board object captured at the start of this call, never rebuilt.

    `canonical=False` (diagnostic only): freshness contracts are NOT
    enforced, so a stale or incomplete source set can still be inspected
    end to end -- but this mode can NEVER write any canonical file,
    regardless of outcome. This is a hard structural guarantee, not a
    convention: the persistence branch below is only ever reached when
    `canonical` is True, so there is no code path by which a diagnostic
    run's success can advance real canonical state.

    Fail-closed, in this exact order:
      1. Build the Alpha Board in-memory EXACTLY ONCE (read-only; nothing
         persisted yet).
      2. In canonical mode: evaluate_source_freshness_contracts() -- a
         blocking finding rejects here, before any UEF stage runs and
         before any file is written.
      3. UEF-7 normalizes that EXACT in-memory board object.
      4. UEF-8 runs against that EXACT UEF-7 result object.
      5. UEF-9 verifies that EXACT UEF-7 + UEF-8 pair. authority_status
         must be VALID.
      6. Only in canonical mode, and only once every stage above has
         succeeded: UEF-7/8/9 outputs are persisted to their own
         canonical, content-keyed (idempotent) paths, then
         persist_canonical_alpha_board() writes the dated bundle from the
         SAME board object captured in step 1, and only then does
         advance_latest_pointer() move latest.json/.md. A failure at any
         earlier stage, or diagnostic mode, leaves every canonical file
         completely untouched.

    Re-running with the same through_day against unchanged on-disk source
    state is idempotent: every UEF run_id is a deterministic digest of its
    own semantic input, so a repeat run reproduces the exact same run_ids
    and overwrites the exact same output paths with the exact same
    content. Nothing in this path calls anything outside libs.reporting.*.
    """

    through_day = str(through_day)[:10]
    repo_root = Path(repo_root)
    reports_root = repo_root / "reports"

    try:
        board = build_alpha_research_board(reports_root=reports_root, through_day=through_day)
    except Exception as exc:  # noqa: BLE001 - fail closed on any board-build defect, not just named ones
        return DailyUefEvaluationResult(
            ok=False, through_day=through_day, canonical=canonical, stage_failed="board_build",
            reason=f"{type(exc).__name__}: {exc}",
        )

    if board.get("through_day") != through_day:
        return DailyUefEvaluationResult(
            ok=False, through_day=through_day, canonical=canonical, stage_failed="board_build",
            reason=f"board.through_day={board.get('through_day')!r} != requested {through_day!r}",
        )

    findings: List[str] = []
    if canonical:
        findings = evaluate_source_freshness_contracts(board, through_day)
        if findings:
            return DailyUefEvaluationResult(
                ok=False, through_day=through_day, canonical=canonical, stage_failed="freshness_guard",
                reason="one or more contractually-daily sources are not dated for the requested day -- "
                       "refusing to materialize a canonical board that would silently mix a fresh "
                       "through_day label with stale content",
                freshness_findings=findings,
                board_candidate_count=int(board.get("candidate_count") or 0),
            )

    try:
        uef7 = normalize_alpha_board(board, normalizer_implementation_digest_value=normalizer_implementation_digest())
    except Exception as exc:  # noqa: BLE001
        return DailyUefEvaluationResult(
            ok=False, through_day=through_day, canonical=canonical, stage_failed="uef7",
            reason=f"{type(exc).__name__}: {exc}", freshness_findings=findings,
        )
    uef7_dict = uef7.to_dict()

    try:
        uef8 = analyze_fair_comparisons(uef7_dict, uef8_implementation_digest_value=uef8_implementation_digest())
    except Exception as exc:  # noqa: BLE001
        return DailyUefEvaluationResult(
            ok=False, through_day=through_day, canonical=canonical, stage_failed="uef8",
            reason=f"{type(exc).__name__}: {exc}", uef7_run_id=uef7.uef7_run_id, freshness_findings=findings,
        )
    uef8_dict = uef8.to_dict()

    try:
        uef9 = verify_formal_evaluation_authority(
            uef7_dict, uef8=uef8_dict, uef9_implementation_digest_value=uef9_implementation_digest()
        )
    except Exception as exc:  # noqa: BLE001
        return DailyUefEvaluationResult(
            ok=False, through_day=through_day, canonical=canonical, stage_failed="uef9",
            reason=f"{type(exc).__name__}: {exc}",
            uef7_run_id=uef7.uef7_run_id, uef8_run_id=uef8.uef8_run_id, freshness_findings=findings,
        )

    if uef9.authority_status != "VALID":
        return DailyUefEvaluationResult(
            ok=False, through_day=through_day, canonical=canonical, stage_failed="uef9",
            reason=f"authority_status={uef9.authority_status!r} (expected VALID)",
            uef7_run_id=uef7.uef7_run_id, uef8_run_id=uef8.uef8_run_id, uef9_run_id=uef9.uef9_run_id,
            authority_status=uef9.authority_status, freshness_findings=findings,
        )

    base_result = dict(
        ok=True, through_day=through_day, canonical=canonical,
        board_candidate_count=int(board.get("candidate_count") or 0),
        uef7_run_id=uef7.uef7_run_id, uef8_run_id=uef8.uef8_run_id, uef9_run_id=uef9.uef9_run_id,
        uef8_pair_count=uef8.summary.pair_count,
        uef8_comparable=uef8.summary.comparable_count,
        uef8_conditional=uef8.summary.conditional_count,
        uef8_not_comparable=uef8.summary.not_comparable_count,
        authority_status=uef9.authority_status,
        freshness_findings=findings,
    )

    if not canonical:
        # Diagnostic mode: the chain succeeded and is safe to inspect, but
        # NOTHING is written -- not the dated board, not latest.json/.md,
        # not even the UEF-7/8/9 run directories, since those are keyed by
        # a run_id derived in part from this exact board and would
        # otherwise leave canonical-looking evidence on disk from a run
        # that explicitly bypassed the freshness contract.
        return DailyUefEvaluationResult(published=False, **base_result)

    uef7_dir = write_uef7_normalization_outputs(uef7, repo_root=repo_root)
    uef8_dir = write_uef8_fair_comparison_outputs(uef8, repo_root=repo_root)
    uef9_dir = write_formal_evaluation_authority(uef9, repo_root=repo_root)

    board_output_dir = reports_root / "evaluation" / "alpha_research_board" / through_day
    latest_dir = reports_root / "evaluation" / "alpha_research_board"
    board_write = persist_canonical_alpha_board(board, output_dir=board_output_dir)
    advance_latest_pointer(board, latest_dir=latest_dir)

    return DailyUefEvaluationResult(
        published=True,
        board_path=board_write.get("json_path"),
        output_dirs={
            "uef7": str(uef7_dir), "uef8": str(uef8_dir), "uef9": str(uef9_dir),
            "board": str(board_output_dir),
        },
        **base_result,
    )


__all__ = [
    "DailyUefEvaluationResult",
    "SourceFreshnessContract",
    "advance_latest_pointer",
    "evaluate_source_freshness_contracts",
    "persist_canonical_alpha_board",
    "run_daily_uef_evaluation",
]
