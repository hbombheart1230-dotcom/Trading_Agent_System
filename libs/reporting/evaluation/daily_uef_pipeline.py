"""Scheduler-agnostic daily UEF EOD evaluation orchestrator (P1.2 gap fix).

Authority-closure revision (Codex bounded re-audit, 2026-09-29) -- see
docs/daily_patch/2026-09-29_daily_uef_authority_closure.md for the full
audit trail. This revision formally establishes:

  CANONICAL PUBLISHER IMPLEMENTATION = this module, exclusively. No other
    code path anywhere in this repository may write reports/evaluation/
    alpha_research_board/<day>/generations/, <day>/current.json, or the
    global latest.json.
  CANONICAL DAILY AUTHORITY = the single captured Alpha Board + the exact
    UEF-7 result + the exact UEF-8 result + the exact UEF-9 result +
    a COMPLETE authority manifest binding all four by digest. A directory
    full of JSON files with no verified COMPLETE manifest is NOT authority.
  MACHINE LATEST AUTHORITY = the global latest.json pointer, exclusively.
  latest.md = a derived, presentation-only view. It is never consulted by
    any authoritative reader, and its own write failure never invalidates
    machine authority (see write_latest_presentation()'s own docstring).

Findings closed in this revision (Codex bounded re-audit found these
remaining after Fix2's H1/H2/H3/M1):

  Legacy CLI bypass: scripts/run_alpha_research_board.py used to call
    write_alpha_research_board() directly -- a second, independent
    canonical-write path with no UEF-9 involvement. Fixed: that CLI now
    only ever calls build_alpha_research_board() (read-only) and prints a
    diagnostic snapshot; it cannot write any canonical file. Verified by
    repository-wide search: this module is the sole caller of
    write_generation()/advance_current_pointer()/advance_latest_pointer().

  Unknown-source permissiveness: the freshness guard used to treat any
    source key with no registered contract as automatically
    optional/tolerated. Fixed: every source key build_alpha_research_board
    can ever produce (9, enumerated below, confirmed directly against its
    source code) now has an explicit contract; a source key appearing in
    board["sources"] that is NOT in _SOURCE_FRESHNESS_CONTRACTS rejects the
    canonical run outright, rather than silently passing through.

  Bundle completion authority: a partial set of JSON/MD files used to be
    indistinguishable from a genuinely complete, verified daily result.
    Fixed: see the COMPLETE manifest / generation / pointer design below.

Generation layout (per target day):

  reports/evaluation/alpha_research_board/<day>/
    generations/
      <authority_id>/                  authority_id = the UEF-9 run_id for
        alpha_research_board.json      this exact chain (deterministic,
        alpha_research_board.md        content-derived -- never a
        COMPLETE.json                  timestamp/uuid; see uef9's own
                                        run_identity module) -- written LAST
                                        within the generation, only after
                                        every referenced artifact exists and
                                        every digest has been computed.
    current.json                       atomic pointer to the day's
                                        completed generation; a failed
                                        rerun for the same day never
                                        touches this if it does not reach a
                                        new COMPLETE manifest.
    alpha_research_board.json          legacy-compatibility VIEW, copied
    alpha_research_board.md            from the current generation after
                                        verification -- explicitly NOT
                                        authoritative (see item 11 of the
                                        closure task); human/report
                                        navigation convenience only.
  reports/evaluation/alpha_research_board/
    latest.json                        MACHINE AUTHORITY -- global pointer
                                        to the most recent day+generation
                                        that reached a verified COMPLETE
                                        manifest.
    latest.md                          presentation only, see module intro.

A generation directory that never got a COMPLETE.json (a crash/failure
mid-write) has zero effect on authority: current.json/latest.json are only
ever updated after write_generation() returns a verified manifest, so an
incomplete generation directory sitting on disk is simply inert, never
read by anything as a source of truth.

Evaluation/reporting only: nothing in this call graph imports
libs.execution.*, libs.runtime.live_loop_runner, or any Kiwoom transport
module. No broker/runtime/execution state is ever touched.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from libs.reporting.alpha_research_board import build_alpha_research_board
from libs.reporting.alpha_research_board.report import render_alpha_research_board
from libs.reporting.evaluation.uef7.alpha_board_normalization import normalize_alpha_board
from libs.reporting.evaluation.uef7.reporter import write_uef7_normalization_outputs
from libs.reporting.evaluation.uef7.run_identity import (
    alpha_board_semantic_digest,
    normalizer_implementation_digest,
)
from libs.reporting.evaluation.uef8.fair_comparison import analyze_fair_comparisons
from libs.reporting.evaluation.uef8.reporter import write_uef8_fair_comparison_outputs
from libs.reporting.evaluation.uef8.run_identity import uef8_implementation_digest
from libs.reporting.evaluation.uef9.authority import verify_formal_evaluation_authority
from libs.reporting.evaluation.uef9.reporter import write_formal_evaluation_authority
from libs.reporting.evaluation.uef9.run_identity import uef9_implementation_digest

MANIFEST_SCHEMA_VERSION = "daily_authority_manifest.v1"
CURRENT_POINTER_SCHEMA_VERSION = "alpha_research_board_current_pointer.v1"
LATEST_POINTER_SCHEMA_VERSION = "alpha_research_board_latest_pointer.v1"
OBSERVATION_REGISTRY_SCHEMA_VERSION = "p1_2_daily_observation_registry.v1"


# --- Source freshness contracts -------------------------------------------


@dataclass(frozen=True)
class SourceFreshnessContract:
    source_key: str
    required: bool
    # "UPDATED_THROUGH_TARGET_DAY": the source's own through_day/day field
    #   must equal the requested target day, including a legitimate
    #   zero-event day (VALID_NO_EPISODES / NO_OPENING_RANK1 / zero
    #   redetections is still a fresh, dated file -- freshness is judged by
    #   the date stamp, never by row/event count).
    # "PRESENT_ONLY": the source must exist and be readable (if required)
    #   but its own date (if any) is never compared to the target day,
    #   because its contract is not a daily one.
    mode: str


# Every entry's classification was verified directly against this
# repository's real source files and against build_alpha_research_board's
# and canonicalize_board's own source code (libs/reporting/
# alpha_research_board/builder.py and canonical.py) -- this is the
# COMPLETE set of 11 source keys that build_alpha_research_board's final
# (canonicalized) output can ever populate in board["sources"]: the 7 keys
# of SOURCE_PATHS in contracts.py; btc_woori_hypothesis and large_cap_daily
# (added by builder.py itself); and strategist_stage2_effectiveness and
# short_alpha_discriminator (added later, inside canonicalize_board --
# easy to miss on a first read of builder.py alone, confirmed only by
# actually running build_alpha_research_board() and inspecting its real
# output). A source key appearing in a real board that is NOT listed here
# is therefore a genuinely NEW/unreviewed source, and evaluate_source_
# freshness_contracts() rejects it outright rather than silently
# tolerating it -- adding a new source to build_alpha_research_board or
# canonicalize_board requires adding its contract here in the same change.
_SOURCE_FRESHNESS_CONTRACTS: Tuple[SourceFreshnessContract, ...] = (
    # Confirmed directly (P1.2 Day-1): these four are written by the daily
    # closeout pipeline and their own captured payload carried an explicit
    # through_day matching the day they were generated on, going stale
    # (still 2026-09-25) exactly when closeout stopped running daily.
    SourceFreshnessContract("prospective_candidates", required=True, mode="UPDATED_THROUGH_TARGET_DAY"),
    SourceFreshnessContract("fresh_change", required=True, mode="UPDATED_THROUGH_TARGET_DAY"),
    SourceFreshnessContract("opening_cumulative", required=True, mode="UPDATED_THROUGH_TARGET_DAY"),
    SourceFreshnessContract("latent_reactivation", required=True, mode="UPDATED_THROUGH_TARGET_DAY"),
    # Confirmed directly: candidate_selection.json carries no through_day/
    # day field at all. Its own payload instead carries selection_period=
    # {validation_start, selection_end_day} -- a FIXED, one-time offline
    # backtest window (schema_version=rank1_candidate_selection.v1,
    # behavior_effect=NONE_OFFLINE_RESEARCH_ONLY) -- a frozen
    # feature-eligibility artifact by design, not something that advances
    # daily. Required to be PRESENT (it feeds the core candidate pool),
    # never date-compared.
    SourceFreshnessContract("feature_candidates", required=True, mode="PRESENT_ONLY"),
    # Confirmed directly: frozen_candidate_contract.json (schema_version=
    # rank1_prospective_shadow.v1) carries frozen_at/first_eligible_day/
    # fixed_validation_days -- a frozen configuration contract, no
    # through_day/day field. build_alpha_research_board itself tolerates
    # its absence (defaults first_eligible_day to "0000-00-00"), so
    # optional here too.
    SourceFreshnessContract("prospective_contract", required=False, mode="PRESENT_ONLY"),
    # Confirmed directly: q12_v1_v2_historical_review.json (schema_version=
    # q12_v1_v2_historical_review.v1) carries source_days (a fixed
    # historical range) and no through_day/day field -- a one-time
    # historical review artifact, not a daily one. _btc_woori() degrades
    # gracefully (empty placeholder candidate row) when absent.
    SourceFreshnessContract("btc_woori_history", required=False, mode="PRESENT_ONLY"),
    # Confirmed directly: q12_btc_woori_hypothesis_cumulative.json DOES
    # carry a genuine through_day (observed fresh on the day captured).
    # build_alpha_research_board only loads it conditionally (only if the
    # file exists at all -- no MISSING_ARTIFACT is ever recorded for it),
    # so it is optional by the board's own design; when present, its date
    # is still meaningful and checked.
    SourceFreshnessContract("btc_woori_hypothesis", required=False, mode="UPDATED_THROUGH_TARGET_DAY"),
    # Confirmed directly (builder.py::_large_cap_candidate): its own
    # "through_day" field is hardcoded to the CALLER'S through_day argument
    # (the same vacuous-echo pattern as the board's own top-level field),
    # never independently derived -- so date-comparing it would check
    # nothing real. Its "available" flag, by contrast, is
    # bool(review.get("source_count")) -- a genuine same-day-artifact-
    # count signal. Required (unconditionally invoked by
    # build_alpha_research_board, feeds a core candidate), PRESENT_ONLY
    # (available already encodes real freshness; a redundant date compare
    # would be checking an untrustworthy field).
    SourceFreshnessContract("large_cap_daily", required=True, mode="PRESENT_ONLY"),
    # Confirmed directly (canonical.py::_stage2_candidate /
    # _latest_stage2_source): this deliberately prefers the LATEST
    # available cumulative rollup file at or before through_day, falling
    # back to a per-day file only if no rollup exists -- a rolling
    # look-back window by design, not "must equal today". Its own
    # through_day (via the standard load_json loader) can legitimately be
    # an earlier date than the target day. Optional (build_alpha_research_
    # board tolerates its absence) and never date-compared.
    SourceFreshnessContract("strategist_stage2_effectiveness", required=False, mode="PRESENT_ONLY"),
    # Confirmed directly (canonical.py::canonicalize_board): this entry is
    # a hardcoded sources.setdefault(..., {"available": True, "error":
    # None}) with no through_day field at all, and "available" here does
    # NOT reflect whether the underlying short_alpha_discriminator.json
    # file genuinely exists -- it is unconditionally True regardless. This
    # is an existing quirk of Alpha Board v2's own (frozen) canonicalize_
    # board, not something this closure may fix (out of scope -- Alpha
    # Board evaluation semantics are explicitly frozen). Optional,
    # PRESENT_ONLY: a REQUIRED+availability check here would be a permanent
    # no-op given the hardcoded flag, so marking it optional is the honest
    # reflection of what this source can actually tell the freshness guard.
    SourceFreshnessContract("short_alpha_discriminator", required=False, mode="PRESENT_ONLY"),
)
_KNOWN_SOURCE_KEYS = frozenset(c.source_key for c in _SOURCE_FRESHNESS_CONTRACTS)


def evaluate_source_freshness_contracts(board: Dict[str, Any], through_day: str) -> List[str]:
    """Return blocking findings for `board`; empty means clear to proceed.

    Two independent kinds of finding:
      1. UNKNOWN source: a key in board["sources"] with no registered
         contract. Fails closed -- see this module's own docstring for why
         "no contract" must never be silently treated as "optional".
      2. A registered contract violated: required-and-missing, or dated-
         and-stale (see SourceFreshnessContract.mode).
    """
    findings: List[str] = []
    sources = board.get("sources") or {}

    for name in sources:
        if name not in _KNOWN_SOURCE_KEYS:
            findings.append(f"{name}: UNKNOWN_SOURCE (no registered freshness contract -- fail closed)")

    for contract in _SOURCE_FRESHNESS_CONTRACTS:
        info = sources.get(contract.source_key)
        available = isinstance(info, dict) and bool(info.get("available")) and not info.get("error")
        if not available:
            if contract.required:
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


# --- Atomic writes -----------------------------------------------------------


def _atomic_write_text(path: Path, content: str) -> None:
    """Write `content` to `path` atomically: temp file in the same
    directory, fsync, then os.replace() -- atomic on both POSIX and NTFS
    for a same-volume rename, so a crash/interruption mid-write can never
    leave a half-written file in place.

    `newline=""` is required, not cosmetic: without it, Python's text-mode
    write translates every "\\n" in `content` to "\\r\\n" on Windows, so the
    bytes actually written to disk would differ from `content.encode(
    "utf-8")` -- silently breaking every sha256 digest this module computes
    over "the same content" (write_generation()/verify_generation_manifest()
    hash the file's bytes, not the in-memory string, specifically so a
    digest check proves nothing was altered after writing; confirmed
    directly: omitting newline="" made every freshly-written generation
    fail its own immediate self-verification with board_digest_mismatch on
    this platform).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
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


def _sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- Generation write + completion manifest (single-capture, atomic) -------


def write_generation(
    board: Dict[str, Any],
    *,
    day_dir: Path,
    authority_id: str,
    uef7_run_id: str,
    uef7_output_path: Path,
    uef8_run_id: str,
    uef8_output_path: Path,
    uef9_run_id: str,
    uef9_output_path: Path,
    uef9_authority_status: str,
) -> Path:
    """Write ONE generation for a day: the exact captured `board` plus a
    COMPLETE manifest binding it to the exact UEF-7/8/9 outputs already
    written to their own canonical paths. Never rebuilds the board. The
    manifest is written LAST, after every other file in the generation
    already exists and every digest has been computed from the actual
    bytes on disk -- so a crash/interruption before this point leaves an
    incomplete generation directory with no COMPLETE.json, which
    current.json/latest.json never point at and nothing treats as
    authoritative. Returns the manifest's own path.
    """
    generation_dir = day_dir / "generations" / authority_id
    generation_dir.mkdir(parents=True, exist_ok=True)

    board_json_content = json.dumps(board, ensure_ascii=False, indent=2)
    board_markdown_content = render_alpha_research_board(board)
    board_json_path = generation_dir / "alpha_research_board.json"
    board_markdown_path = generation_dir / "alpha_research_board.md"
    _atomic_write_text(board_json_path, board_json_content)
    _atomic_write_text(board_markdown_path, board_markdown_content)

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "status": "COMPLETE",
        "target_day": board.get("through_day"),
        "authority_id": authority_id,
        "board_digest": _sha256_text(board_json_content),
        "board_path": str(board_json_path),
        "uef7_run_id": uef7_run_id,
        "uef7_digest": _sha256_file(uef7_output_path),
        "uef7_path": str(uef7_output_path),
        "uef8_run_id": uef8_run_id,
        "uef8_digest": _sha256_file(uef8_output_path),
        "uef8_path": str(uef8_output_path),
        "uef9_run_id": uef9_run_id,
        "uef9_digest": _sha256_file(uef9_output_path),
        "uef9_path": str(uef9_output_path),
        "uef9_authority_status": uef9_authority_status,
        "generated_at": time.time(),  # informational only -- never part of authority_id or any digest
    }
    manifest_path = generation_dir / "COMPLETE.json"
    _atomic_write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return manifest_path


def verify_generation_manifest(manifest_path: Path) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """The one validator for a generation's COMPLETE.json: checks the
    manifest exists and is COMPLETE, every referenced artifact still
    exists, every digest still matches the bytes on disk, and
    uef9_authority_status is VALID. Only a manifest that passes this may
    ever be selected by current.json / latest.json."""
    if not manifest_path.is_file():
        return False, "manifest_missing", None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"manifest_unreadable:{type(exc).__name__}", None

    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        return False, "manifest_schema_mismatch", manifest
    if manifest.get("status") != "COMPLETE":
        return False, f"manifest_status={manifest.get('status')!r}", manifest
    if manifest.get("uef9_authority_status") != "VALID":
        return False, f"uef9_authority_status={manifest.get('uef9_authority_status')!r}", manifest

    for prefix in ("board", "uef7", "uef8", "uef9"):
        artifact_path = Path(str(manifest.get(f"{prefix}_path") or ""))
        expected_digest = manifest.get(f"{prefix}_digest")
        if not artifact_path.is_file():
            return False, f"{prefix}_artifact_missing:{artifact_path}", manifest
        try:
            actual_digest = _sha256_file(artifact_path)
        except OSError as exc:
            return False, f"{prefix}_artifact_unreadable:{type(exc).__name__}", manifest
        if actual_digest != expected_digest:
            return False, f"{prefix}_digest_mismatch", manifest

    return True, "ok", manifest


def advance_current_pointer(day_dir: Path, *, day: str, authority_id: str, manifest_path: Path) -> Path:
    """Atomically point <day>/current.json at a generation that has ALREADY
    been written and verified by the caller. Also refreshes the legacy-
    compatibility view (<day>/alpha_research_board.json/.md, copied from
    the now-current generation) -- explicitly non-authoritative, human/
    report navigation only; see this module's own docstring."""
    generation_dir = manifest_path.parent
    pointer = {
        "schema_version": CURRENT_POINTER_SCHEMA_VERSION,
        "day": day,
        "authority_id": authority_id,
        "generation_dir": str(generation_dir),
        "manifest_path": str(manifest_path),
    }
    current_path = day_dir / "current.json"
    _atomic_write_text(current_path, json.dumps(pointer, ensure_ascii=False, indent=2))

    board_json_content = (generation_dir / "alpha_research_board.json").read_text(encoding="utf-8")
    board_markdown_content = (generation_dir / "alpha_research_board.md").read_text(encoding="utf-8")
    _atomic_write_text(day_dir / "alpha_research_board.json", board_json_content)
    _atomic_write_text(day_dir / "alpha_research_board.md", board_markdown_content)
    return current_path


def advance_latest_pointer(*, latest_dir: Path, day: str, authority_id: str, manifest_path: Path) -> Path:
    """Atomically advance the GLOBAL machine-authority pointer, latest.json,
    to point at a generation that has already been written, verified, and
    made current for its own day. This is the sole machine authority this
    module (or anything else) ever publishes -- see this module's own
    docstring. Must only be called after advance_current_pointer() for the
    same generation has already succeeded."""
    generation_dir = manifest_path.parent
    pointer = {
        "schema_version": LATEST_POINTER_SCHEMA_VERSION,
        "day": day,
        "authority_id": authority_id,
        "generation_dir": str(generation_dir),
        "manifest_path": str(manifest_path),
    }
    latest_json_path = latest_dir / "latest.json"
    _atomic_write_text(latest_json_path, json.dumps(pointer, ensure_ascii=False, indent=2))
    return latest_json_path


def write_latest_presentation(*, latest_dir: Path, board: Dict[str, Any]) -> Optional[Path]:
    """Regenerate latest.md, the PRESENTATION-ONLY derived view -- never
    machine authority (that is latest.json alone, advanced separately by
    advance_latest_pointer() above, already committed by the time this is
    called). If this write fails, machine authority remains completely
    valid; only human-readable presentation freshness degrades. Callers
    must therefore treat a failure here as non-fatal to the overall
    publication -- this function itself swallows the exception and returns
    None rather than raising, so a caller cannot accidentally let a
    presentation-only failure look like an authority failure."""
    try:
        markdown_content = render_alpha_research_board(board)
        latest_markdown_path = latest_dir / "latest.md"
        _atomic_write_text(latest_markdown_path, markdown_content)
        return latest_markdown_path
    except Exception:  # noqa: BLE001 - presentation-only, must never fail the caller
        return None


def resolve_canonical_alpha_board(
    repo_root: Path, *, day: Optional[str] = None
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[Dict[str, Any]], str]:
    """The one reader authoritative daily-EOD consumers should use: resolves
    the current machine-authority Board (global latest.json if `day` is
    None, otherwise that day's own current.json), verifies its manifest,
    and returns (ok, board, manifest, reason). `ok=False` on any
    verification failure -- callers must never fall back to reading a
    generation's files directly without going through this."""
    reports_root = Path(repo_root) / "reports"
    board_root = reports_root / "evaluation" / "alpha_research_board"
    if day:
        pointer_path = board_root / str(day)[:10] / "current.json"
    else:
        pointer_path = board_root / "latest.json"

    if not pointer_path.is_file():
        return False, None, None, "pointer_missing"
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, None, None, f"pointer_unreadable:{type(exc).__name__}"

    manifest_path = Path(str(pointer.get("manifest_path") or ""))
    ok, reason, manifest = verify_generation_manifest(manifest_path)
    if not ok or manifest is None:
        return False, None, manifest, reason

    board_path = Path(str(manifest.get("board_path") or ""))
    try:
        board = json.loads(board_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, None, manifest, f"board_unreadable:{type(exc).__name__}"

    return True, board, manifest, "ok"


def _verified_complete_generations(day_dir: Path) -> List[Tuple[Path, Dict[str, Any], str]]:
    """Return verified COMPLETE manifests and their Board semantic identities.

    This is deliberately read-only and runs before UEF-7. A malformed or
    unreadable Board behind an otherwise digest-valid manifest is treated as
    unusable authority rather than guessed at.

    2026-10-01 HOST OPS FINAL FIX integration note: this is the already
    approved P1.2 same-day idempotency/determinism correction (commit
    6b59e5a on codex/p1-2-idempotency-fix, authored 2026-09-30), applied here
    onto the canonical Host branch. It was confirmed absent from both
    committed HEAD and the on-disk working tree by direct code-semantics
    inspection (not merely commit ancestry) before this integration. Paired
    with the determinism fix in libs/reporting/alpha_research_board/builder.py
    (_largest_key) -- without that fix, two runs over identical underlying
    data could still produce different board semantic digests purely from
    Python's hash-seed-dependent set iteration order, which would make this
    preflight's own identity comparison unreliable.
    """
    complete_paths = sorted((day_dir / "generations").glob("*/COMPLETE.json"))
    verified: List[Tuple[Path, Dict[str, Any], str]] = []
    for manifest_path in complete_paths:
        ok, _reason, manifest = verify_generation_manifest(manifest_path)
        if not ok or manifest is None:
            continue
        try:
            board_path = Path(str(manifest.get("board_path") or ""))
            board = json.loads(board_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            verified.append((manifest_path, manifest, "UNVERIFIABLE_COMPLETE_BOARD"))
            continue
        if not isinstance(board, dict):
            verified.append((manifest_path, manifest, "UNVERIFIABLE_COMPLETE_BOARD"))
            continue
        verified.append((manifest_path, manifest, alpha_board_semantic_digest(board)))
    return verified


def record_daily_observation(*, board_root: Path, manifest: Dict[str, Any]) -> Path:
    """Record one derived P1.2 observation for an already verified COMPLETE
    generation.  This is an index, never authority: the manifest and pointers
    remain the canonical source of truth.  Repeating the exact authority is a
    no-op; a different authority for an already observed day is rejected so a
    scheduler retry cannot silently rewrite cross-day history.
    """
    day = str(manifest.get("target_day") or "")[:10]
    authority_id = str(manifest.get("authority_id") or "")
    if not day or not authority_id:
        raise ValueError("verified manifest missing target_day or authority_id")
    registry_path = board_root / "p1_2_daily_observation_registry.json"
    existing = None
    if registry_path.exists():
        try:
            candidate = json.loads(registry_path.read_text(encoding="utf-8"))
            existing = candidate if isinstance(candidate, dict) else None
        except (OSError, json.JSONDecodeError):
            existing = None
    registry = existing if isinstance(existing, dict) else {
        "schema_version": OBSERVATION_REGISTRY_SCHEMA_VERSION, "observations": {}
    }
    if registry.get("schema_version") != OBSERVATION_REGISTRY_SCHEMA_VERSION:
        raise ValueError("observation registry schema mismatch")
    observations = registry.get("observations")
    if not isinstance(observations, dict):
        raise ValueError("observation registry malformed")
    prior = observations.get(day)
    if isinstance(prior, dict):
        if prior.get("authority_id") != authority_id:
            raise ValueError("observation registry already has a different authority for target day")
        return registry_path
    observations[day] = {
        "authority_id": authority_id,
        "manifest_path": str(manifest.get("board_path") and Path(str(manifest.get("board_path"))).parent / "COMPLETE.json"),
        "board_digest": manifest.get("board_digest"),
        "uef7_run_id": manifest.get("uef7_run_id"),
        "uef8_run_id": manifest.get("uef8_run_id"),
        "uef9_run_id": manifest.get("uef9_run_id"),
        "uef9_authority_status": manifest.get("uef9_authority_status"),
    }
    _atomic_write_text(registry_path, json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True))
    return registry_path


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
    authority_id: Optional[str] = None
    manifest_path: Optional[str] = None
    current_pointer_path: Optional[str] = None
    latest_pointer_path: Optional[str] = None
    latest_presentation_path: Optional[str] = None
    uef7_run_id: Optional[str] = None
    uef8_run_id: Optional[str] = None
    uef9_run_id: Optional[str] = None
    uef8_pair_count: Optional[int] = None
    uef8_comparable: Optional[int] = None
    uef8_conditional: Optional[int] = None
    uef8_not_comparable: Optional[int] = None
    authority_status: Optional[str] = None
    idempotency_status: Optional[str] = None
    observation_registry_path: Optional[str] = None
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
            "authority_id": self.authority_id,
            "manifest_path": self.manifest_path,
            "current_pointer_path": self.current_pointer_path,
            "latest_pointer_path": self.latest_pointer_path,
            "latest_presentation_path": self.latest_presentation_path,
            "uef7_run_id": self.uef7_run_id,
            "uef8_run_id": self.uef8_run_id,
            "uef9_run_id": self.uef9_run_id,
            "uef8_pair_count": self.uef8_pair_count,
            "uef8_comparable": self.uef8_comparable,
            "uef8_conditional": self.uef8_conditional,
            "uef8_not_comparable": self.uef8_not_comparable,
            "authority_status": self.authority_status,
            "idempotency_status": self.idempotency_status,
            "observation_registry_path": self.observation_registry_path,
            "output_dirs": self.output_dirs,
        }


def run_daily_uef_evaluation(
    *,
    repo_root: Path,
    through_day: str,
    canonical: bool = True,
) -> DailyUefEvaluationResult:
    """The one scheduler-agnostic daily post-market evaluation entry point,
    and the sole implementation permitted to publish canonical Alpha Board
    authority anywhere in this repository (see this module's own
    docstring for the full authority model).

    `canonical=True` (the only mode a scheduler may use): the freshness
    contracts (including the unknown-source fail-closed rule) are always
    enforced, and a new generation/manifest/pointer advance only ever
    happens once the full chain succeeds with authority_status=VALID --
    using the single board object captured at the start of this call,
    never rebuilt.

    `canonical=False` (diagnostic only): freshness contracts are NOT
    enforced, so a stale or incomplete source set can still be inspected
    end to end -- but this mode can NEVER write any canonical file,
    regardless of outcome. This is a hard structural guarantee: the
    publication branch below is only ever reached when `canonical` is
    True, so there is no code path by which a diagnostic run's success can
    advance real canonical state.

    Fail-closed, in this exact order: build the board once -> freshness
    contracts (canonical mode only) -> verified-COMPLETE idempotency preflight
    (canonical mode only) -> UEF-7 -> UEF-8 -> UEF-9
    (authority_status must be VALID) -> [canonical mode only] persist
    UEF-7/8/9 outputs -> write_generation() (single capture, COMPLETE
    manifest written last) -> verify_generation_manifest() on what was
    just written (a second, independent check before anything is allowed
    to point at it) -> advance_current_pointer() -> advance_latest_pointer()
    -> write_latest_presentation() (best-effort, non-fatal). A failure at
    any stage before the final pointer advances leaves every existing
    current.json/latest.json completely untouched -- the prior valid
    generation (if any) remains authoritative.
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
                reason="one or more sources failed their registered freshness contract, or are unknown "
                       "(no registered contract) -- refusing to materialize a canonical board that would "
                       "silently mix a fresh through_day label with stale or unreviewed content",
                freshness_findings=findings,
                board_candidate_count=int(board.get("candidate_count") or 0),
            )

        day_dir = reports_root / "evaluation" / "alpha_research_board" / through_day
        preflight_board_root = reports_root / "evaluation" / "alpha_research_board"
        board_identity = alpha_board_semantic_digest(board)
        complete_generations = _verified_complete_generations(day_dir)
        if len(complete_generations) > 1:
            return DailyUefEvaluationResult(
                ok=False, through_day=through_day, canonical=True,
                stage_failed="idempotency_preflight",
                reason="multiple verified COMPLETE generations exist for target day",
                idempotency_status="MULTIPLE_COMPLETE_CONFLICT",
                freshness_findings=findings,
                board_candidate_count=int(board.get("candidate_count") or 0),
            )
        if len(complete_generations) == 1:
            manifest_path, manifest, existing_identity = complete_generations[0]
            if existing_identity != board_identity:
                return DailyUefEvaluationResult(
                    ok=False, through_day=through_day, canonical=True,
                    stage_failed="idempotency_preflight",
                    reason="verified COMPLETE source identity differs from current Board",
                    idempotency_status="CANONICAL_SOURCE_CONFLICT",
                    freshness_findings=findings,
                    board_candidate_count=int(board.get("candidate_count") or 0),
                )
            return DailyUefEvaluationResult(
                ok=True, through_day=through_day, canonical=True, published=False,
                reason="target day already has a verified COMPLETE generation with the same source identity",
                idempotency_status="ALREADY_COMPLETE",
                freshness_findings=findings,
                board_candidate_count=int(board.get("candidate_count") or 0),
                authority_id=str(manifest.get("authority_id") or "") or None,
                manifest_path=str(manifest_path),
                uef7_run_id=str(manifest.get("uef7_run_id") or "") or None,
                uef8_run_id=str(manifest.get("uef8_run_id") or "") or None,
                uef9_run_id=str(manifest.get("uef9_run_id") or "") or None,
                authority_status=str(manifest.get("uef9_authority_status") or "") or None,
                # Not re-invoked here -- the registry was already populated by
                # whichever earlier call first published this generation, and
                # P1.2's own idempotency test
                # (test_same_complete_preflight_keeps_pointers_and_registry_unchanged)
                # requires the registry file to stay byte-for-byte unchanged on
                # an ALREADY_COMPLETE short-circuit. The path itself is still
                # reported -- same deterministic location record_daily_observation()
                # itself always writes to -- so a caller never sees a surprising
                # None here just because this particular call happened to be a
                # no-op.
                observation_registry_path=str(preflight_board_root / "p1_2_daily_observation_registry.json"),
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
        # NOTHING is written -- not a generation, not current.json, not
        # latest.json/.md, not even the UEF-7/8/9 run directories (keyed by
        # a run_id derived in part from this exact board, which would
        # otherwise leave canonical-looking evidence on disk from a run
        # that explicitly bypassed the freshness contract).
        return DailyUefEvaluationResult(published=False, **base_result)

    day_dir = reports_root / "evaluation" / "alpha_research_board" / through_day
    board_root = reports_root / "evaluation" / "alpha_research_board"

    uef7_dir = write_uef7_normalization_outputs(uef7, repo_root=repo_root)
    uef8_dir = write_uef8_fair_comparison_outputs(uef8, repo_root=repo_root)
    uef9_dir = write_formal_evaluation_authority(uef9, repo_root=repo_root)

    authority_id = uef9.uef9_run_id

    manifest_path = write_generation(
        board,
        day_dir=day_dir,
        authority_id=authority_id,
        uef7_run_id=uef7.uef7_run_id,
        uef7_output_path=uef7_dir / "normalized_alpha_board.json",
        uef8_run_id=uef8.uef8_run_id,
        uef8_output_path=uef8_dir / "fair_comparison_summary.json",
        uef9_run_id=uef9.uef9_run_id,
        uef9_output_path=uef9_dir / "formal_evaluation_authority.json",
        uef9_authority_status=uef9.authority_status,
    )

    verified, verify_reason, _manifest = verify_generation_manifest(manifest_path)
    if not verified:
        # Self-check before anything is allowed to point at this
        # generation -- if this ever trips, current.json/latest.json are
        # left completely untouched, exactly like any other failed stage.
        return DailyUefEvaluationResult(
            ok=False, through_day=through_day, canonical=canonical, stage_failed="manifest_verification",
            reason=f"newly-written generation failed self-verification: {verify_reason}",
            uef7_run_id=uef7.uef7_run_id, uef8_run_id=uef8.uef8_run_id, uef9_run_id=uef9.uef9_run_id,
            authority_status=uef9.authority_status, freshness_findings=findings,
        )

    current_path = advance_current_pointer(
        day_dir, day=through_day, authority_id=authority_id, manifest_path=manifest_path
    )
    latest_path = advance_latest_pointer(
        latest_dir=board_root, day=through_day, authority_id=authority_id, manifest_path=manifest_path
    )
    presentation_path = write_latest_presentation(latest_dir=board_root, board=board)
    registry_path = record_daily_observation(board_root=board_root, manifest=_manifest or {})

    return DailyUefEvaluationResult(
        published=True,
        authority_id=authority_id,
        manifest_path=str(manifest_path),
        current_pointer_path=str(current_path),
        latest_pointer_path=str(latest_path),
        latest_presentation_path=str(presentation_path) if presentation_path else None,
        observation_registry_path=str(registry_path),
        output_dirs={
            "uef7": str(uef7_dir), "uef8": str(uef8_dir), "uef9": str(uef9_dir),
            "generation": str(manifest_path.parent),
        },
        **base_result,
    )


__all__ = [
    "DailyUefEvaluationResult",
    "SourceFreshnessContract",
    "advance_current_pointer",
    "advance_latest_pointer",
    "evaluate_source_freshness_contracts",
    "resolve_canonical_alpha_board",
    "record_daily_observation",
    "verify_generation_manifest",
    "write_generation",
    "write_latest_presentation",
    "run_daily_uef_evaluation",
]
