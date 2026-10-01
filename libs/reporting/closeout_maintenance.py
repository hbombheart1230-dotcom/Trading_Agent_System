from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict

from libs.agent.reporter import Reporter
from libs.performance.strategy_memory import sync_strategy_memory_artifacts
from libs.read.kiwoom_account_snapshot_collector import save_kiwoom_account_snapshot
from libs.runtime.live_loop_lock import acquire_live_loop_lock, release_live_loop_lock
from libs.reporting.closeout_completion_authority import (
    COMPLETION_ACTION_KEY,
    read_closeout_completion,
    write_closeout_completion_success,
)
from libs.reporting.broker_closed_trade_reconciler import reconcile_broker_closed_trade_reports
from libs.reporting.carryover_exit_reconciler import reconcile_carryover_exit_reports
from libs.reporting.closeout_residual_positions import reconcile_closeout_residual_positions
from libs.reporting.operator_period_summary import generate_operator_daily_summary_artifact
from libs.reporting.post_exit_shadow_recap import generate_post_exit_shadow_recap, resolve_post_exit_state_path
from libs.reporting.q8_shadow_blocker_review import generate_q8_shadow_blocker_review


def log_closeout_stage(*, run_id: str, day: str, stage: str, phase: str, detail: Dict[str, Any] | None = None) -> None:
    """Durable, immediate-flush stage-boundary diagnostic record (2026-09-30
    closeout diagnostic hardening). Uses the existing EventLogger (data/logs/
    events.jsonl, fsync'd on every write) -- NOT a new logging surface.

    Why this exists: investigating the 2026-09-29 upstream closeout gap
    found that this repository's scheduled fallback closeout
    (scripts/run_mock_exam_closeout.bat -> scripts/run_closeout_maintenance.py)
    produced ZERO captured output on a ~10m37s silent hang on 2026-09-28
    (reports/runtime/closeout_maintenance_2026-09-28_160000.log has only a
    start line and an exit line, rc=1, nothing in between) -- because this
    module's own step-level try/except blocks only ever record their
    outcome into the in-memory `out["steps"][...]` dict, which is not
    written to disk until the WHOLE function returns and the CLI's own
    print statements run. A hang or external kill mid-function leaves
    nothing durable behind to show which stage was in progress.

    Scope note: called only at the stages most relevant to the 2026-09-29
    investigation (account_snapshot -- the step most likely to block on a
    real broker/network call -- and the three steps behind the four daily
    UEF freshness sources: opening_rank1_prospective_shadow,
    rank1_fixed_candidate_shadow, rank1_fresh_change_activation_shadow),
    not all 17 steps in this function -- a deliberately bounded,
    diagnostic-only addition, not a full instrumentation framework. Never
    raises: a diagnostic-logging failure must never break closeout
    maintenance itself.
    """
    try:
        from libs.core.event_logger import EventLogger, resolve_event_log_path

        EventLogger(resolve_event_log_path()).log(
            run_id=run_id or "closeout-unknown-run",
            stage="closeout_maintenance",
            event=f"stage_{phase}",
            level="info",
            payload={"target_day": day, "closeout_stage": stage, **(detail or {})},
        )
    except Exception:  # noqa: BLE001 - diagnostics must never break closeout maintenance
        pass


def _path_exists(path: Any) -> bool:
    text = str(path or "").strip()
    return bool(text) and Path(text).exists()


def _artifact_status(path: Any) -> Dict[str, Any]:
    text = str(path or "").strip()
    if not text:
        return {"path": "", "exists": False, "size": 0}
    p = Path(text)
    return {"path": text, "exists": p.exists(), "size": p.stat().st_size if p.exists() else 0}


def _build_opening_rank1_closeout_with_offline_fallback(
    *,
    day: str,
    reports_root: Path,
    state_path: Path,
    builder: Any = None,
) -> Dict[str, Any]:
    if builder is None:
        from libs.reporting.opening_rank1_shadow import build_opening_rank1_shadow

        builder = build_opening_rank1_shadow
    try:
        result = builder(
            day=day,
            reports_root=reports_root,
            state_path=state_path,
            allow_fresh_fetch=True,
        )
        return dict(result or {})
    except Exception as fresh_exc:
        result = builder(
            day=day,
            reports_root=reports_root,
            state_path=state_path,
            allow_fresh_fetch=False,
        )
        return {
            **dict(result or {}),
            "degraded_offline_fallback": True,
            "fresh_fetch_error": str(fresh_exc),
        }


def run_closeout_maintenance(
    *,
    day: str,
    reports_root: Path = Path("reports"),
    event_log_path: Path = Path("data/logs/events.jsonl"),
    post_exit_report_dir: Path = Path("reports/dev/analysis/post_exit_shadow_recap"),
    state_path: Path | None = None,
    trigger: str = "closeout_maintenance",
    collect_account_snapshot: bool = True,
    run_id: str = "",
) -> Dict[str, Any]:
    normalized_day = str(day or "").strip()[:10]
    resolved_run_id = str(run_id or "").strip() or f"closeout-{normalized_day}-{trigger}"
    out: Dict[str, Any] = {
        "schema_version": "closeout_maintenance.v1",
        "day": normalized_day,
        "trigger": str(trigger or "closeout_maintenance"),
        "steps": {},
    }
    log_closeout_stage(run_id=resolved_run_id, day=normalized_day, stage="run_closeout_maintenance", phase="start")

    if collect_account_snapshot:
        log_closeout_stage(run_id=resolved_run_id, day=normalized_day, stage="account_snapshot", phase="start")
        try:
            snapshot = save_kiwoom_account_snapshot(day=normalized_day, trigger=str(trigger or "closeout_maintenance"))
            out["steps"]["account_snapshot"] = {
                "ok": True,
                "path": snapshot.get("path"),
                "latest_path": snapshot.get("latest_path"),
                "summary": dict(snapshot.get("summary") or {}),
            }
            try:
                carryover = reconcile_carryover_exit_reports(
                    reports_root=reports_root,
                    day=normalized_day,
                    snapshot=snapshot,
                )
                out["steps"]["carryover_exit_reconciliation"] = {
                    "ok": bool(carryover.get("ok")),
                    "patched_count": carryover.get("patched_count"),
                    "patched": list(carryover.get("patched") or [])[:20],
                    "skipped": list(carryover.get("skipped") or [])[:20],
                }
            except Exception as carryover_exc:
                out["steps"]["carryover_exit_reconciliation"] = {
                    "ok": False,
                    "error": str(carryover_exc),
                }
            try:
                residual_state_path = state_path or Path("data/state.json")
                residual = reconcile_closeout_residual_positions(
                    reports_root=reports_root,
                    day=normalized_day,
                    snapshot=snapshot,
                    state_path=residual_state_path,
                    trigger=str(trigger or "closeout_maintenance"),
                )
                out["steps"]["closeout_residual_position_reconciliation"] = {
                    "ok": bool(residual.get("ok")),
                    "position_count": residual.get("position_count"),
                    "unresolved_symbols": list(residual.get("unresolved_symbols") or []),
                    "requires_next_open_flatten": bool(residual.get("requires_next_open_flatten")),
                    "snapshot_path": residual.get("snapshot_path"),
                    "lifecycle_backfill": dict(residual.get("lifecycle_backfill") or {}),
                    "state_reconciliation": dict(residual.get("state_reconciliation") or {}),
                }
            except Exception as residual_exc:
                out["steps"]["closeout_residual_position_reconciliation"] = {
                    "ok": False,
                    "error": str(residual_exc),
                }
        except Exception as exc:
            out["steps"]["account_snapshot"] = {
                "ok": False,
                "error": str(exc),
            }
            out["steps"]["closeout_residual_position_reconciliation"] = {
                "ok": False,
                "error": "account_snapshot_failed",
            }
            out["steps"]["carryover_exit_reconciliation"] = {
                "ok": False,
                "error": "account_snapshot_failed",
            }
    else:
        out["steps"]["account_snapshot"] = {"ok": True, "skipped": True}
        out["steps"]["closeout_residual_position_reconciliation"] = {"ok": True, "skipped": True}
        out["steps"]["carryover_exit_reconciliation"] = {"ok": True, "skipped": True}

    try:
        reconciliation = reconcile_broker_closed_trade_reports(reports_root=reports_root, day=normalized_day)
        out["steps"]["broker_closed_trade_reconciliation"] = {
            "ok": bool(reconciliation.get("ok")),
            "snapshot_path": reconciliation.get("snapshot_path"),
            "patched_count": reconciliation.get("patched_count"),
            "patched": list(reconciliation.get("patched") or [])[:20],
            "skipped": list(reconciliation.get("skipped") or [])[:20],
            "reason": reconciliation.get("reason"),
        }
    except Exception as exc:
        out["steps"]["broker_closed_trade_reconciliation"] = {"ok": False, "error": str(exc)}

    try:
        q8 = generate_q8_shadow_blocker_review(reports_root=reports_root, day=normalized_day)
        out["steps"]["q8_shadow_blocker_review"] = {
            "ok": True,
            "report_md_path": q8.get("report_md_path"),
            "report_json_path": q8.get("report_json_path"),
            "candidate_count": q8.get("candidate_count"),
            "observed_review_candidate_count": q8.get("observed_review_candidate_count"),
        }
    except Exception as exc:
        out["steps"]["q8_shadow_blocker_review"] = {"ok": False, "error": str(exc)}

    try:
        resolved_state_path = resolve_post_exit_state_path(reports_root, state_path)
        recap = generate_post_exit_shadow_recap(
            reports_root=reports_root,
            report_dir=post_exit_report_dir,
            day=normalized_day,
            state_path=resolved_state_path,
        )
        out["steps"]["post_exit_shadow_recap"] = {
            "ok": True,
            "report_md_path": recap.get("report_md_path"),
            "report_json_path": recap.get("report_json_path"),
            "summary": dict(recap.get("summary") or {}),
        }
    except Exception as exc:
        out["steps"]["post_exit_shadow_recap"] = {"ok": False, "error": str(exc)}

    try:
        daily_md, daily_json, daily_payload = generate_operator_daily_summary_artifact(
            reports_root=reports_root,
            day=normalized_day,
        )
        metrics = daily_payload.get("metrics") if isinstance(daily_payload.get("metrics"), dict) else {}
        out["steps"]["operator_daily_summary_artifact"] = {
            "ok": True,
            "report_md_path": str(daily_md),
            "report_json_path": str(daily_json),
            "trade_count": metrics.get("trade_count"),
            "closed_trade_count": metrics.get("closed_trade_count"),
            "win_rate": metrics.get("win_rate"),
            "avg_return_pct": metrics.get("avg_return_pct"),
            "performance_memory_sync": dict(daily_payload.get("performance_memory_sync") or {}),
        }
    except Exception as exc:
        out["steps"]["operator_daily_summary_artifact"] = {"ok": False, "error": str(exc)}
        try:
            sync = sync_strategy_memory_artifacts(
                reports_root=reports_root,
                day=normalized_day,
                source="closeout_maintenance_fallback",
            )
            out["steps"]["performance_memory_sync_fallback"] = {"ok": True, "payload": dict(sync)}
        except Exception as sync_exc:
            out["steps"]["performance_memory_sync_fallback"] = {"ok": False, "error": str(sync_exc)}

    try:
        operator = Reporter().generate_operator_summary(
            event_log_path=event_log_path,
            report_dir=reports_root,
            day=normalized_day,
        )
        payload = operator.get("payload") if isinstance(operator.get("payload"), dict) else {}
        trading_health = payload.get("trading_health_status") if isinstance(payload.get("trading_health_status"), dict) else {}
        out["steps"]["operator_visibility_summary"] = {
            "ok": True,
            "report_md_path": operator.get("report_md_path"),
            "report_json_path": operator.get("report_json_path"),
            "system_health": (
                (payload.get("system_health_status") or {}).get("system_health_level")
                if isinstance(payload.get("system_health_status"), dict)
                else ""
            ),
            "trading_health": trading_health.get("trading_health_level"),
            "trading_health_reasoning": list(trading_health.get("reasoning") or []),
        }
    except Exception as exc:
        out["steps"]["operator_visibility_summary"] = {"ok": False, "error": str(exc)}

    try:
        from libs.reporting.evaluation.frozen_window_closeout import (
            run_frozen_window_closeout,
        )

        frozen = run_frozen_window_closeout(
            day=normalized_day,
            reports_root=reports_root,
            state_path=state_path or Path("data/state.json"),
        )
        out["steps"]["q9_baseline_frozen_window"] = {
            "ok": bool(frozen.get("ok")),
            "result_path": frozen.get("result_path"),
            "valid_day_count": frozen.get("valid_day_count"),
            "remaining_valid_days": frozen.get("remaining_valid_days"),
            "window_complete": frozen.get("window_complete"),
            "evidence_status": (
                (frozen.get("day_record") or {}).get("evidence_status")
            ),
            "forward_windows_complete": (
                (frozen.get("day_record") or {}).get("forward_windows_complete")
            ),
            "primary_alpha": dict(
                (frozen.get("day_record") or {}).get("primary_alpha") or {}
            ),
        }
    except Exception as exc:
        out["steps"]["q9_baseline_frozen_window"] = {
            "ok": False,
            "error": str(exc),
        }

    log_closeout_stage(run_id=resolved_run_id, day=normalized_day, stage="opening_rank1_prospective_shadow", phase="start")
    try:
        opening_rank1 = _build_opening_rank1_closeout_with_offline_fallback(
            day=normalized_day,
            reports_root=reports_root,
            state_path=state_path or Path("data/state.json"),
        )
        out["steps"]["opening_rank1_prospective_shadow"] = {
            "ok": bool(opening_rank1.get("ok")),
            "degraded_offline_fallback": bool(
                opening_rank1.get("degraded_offline_fallback")
            ),
            "fresh_fetch_error": opening_rank1.get("fresh_fetch_error"),
            "day_status": opening_rank1.get("day_status"),
            "episode_count": opening_rank1.get("episode_count"),
            "observed_30m_count": opening_rank1.get("observed_30m_count"),
            "promotion_status": opening_rank1.get("promotion_status"),
            "report_json_path": opening_rank1.get("daily_json_path"),
            "report_md_path": opening_rank1.get("daily_md_path"),
            "cumulative_json_path": opening_rank1.get("cumulative_json_path"),
            "cumulative_md_path": opening_rank1.get("cumulative_md_path"),
            "latent_forward_json_path": opening_rank1.get("latent_forward_json_path"),
            "latent_forward_md_path": opening_rank1.get("latent_forward_md_path"),
        }
    except Exception as exc:
        out["steps"]["opening_rank1_prospective_shadow"] = {
            "ok": False,
            "error": str(exc),
        }

    log_closeout_stage(
        run_id=resolved_run_id, day=normalized_day,
        stage="rank1_fixed_candidate_shadow+rank1_fresh_change_activation_shadow", phase="start",
    )
    try:
        from libs.research.rank1_feature_mart.pipeline import run as run_rank1_feature_mart
        from libs.research.rank1_feature_mart.prospective import build_prospective_shadow
        from libs.research.rank1_feature_mart.activation_shadow import (
            build_fresh_change_activation_shadow,
        )

        project_root = Path(reports_root).resolve().parent
        mart = run_rank1_feature_mart(project_root=project_root)
        fixed_shadow = build_prospective_shadow(
            day=normalized_day,
            reports_root=Path(reports_root),
            mart_root=Path(str(mart["output_root"])),
        )
        activation_shadow = build_fresh_change_activation_shadow(
            day=normalized_day,
            reports_root=Path(reports_root),
            mart_root=Path(str(mart["output_root"])),
        )
        out["steps"]["rank1_fixed_candidate_shadow"] = {
            "ok": bool(fixed_shadow.get("ok")),
            "day_status": fixed_shadow.get("day_status"),
            "valid_day_count": fixed_shadow.get("valid_day_count"),
            "report_json_path": fixed_shadow.get("daily_json_path"),
            "report_md_path": fixed_shadow.get("daily_md_path"),
            "cumulative_json_path": fixed_shadow.get("cumulative_json_path"),
            "cumulative_md_path": fixed_shadow.get("cumulative_md_path"),
            "strategy_alignment_json_path": (
                mart.get("strategy_alignment") or {}
            ).get("cumulative_json_path"),
            "strategy_alignment_md_path": (
                mart.get("strategy_alignment") or {}
            ).get("cumulative_md_path"),
        }
        out["steps"]["rank1_fresh_change_activation_shadow"] = {
            "ok": bool(activation_shadow.get("ok")),
            "day_status": activation_shadow.get("day_status"),
            "valid_day_count": activation_shadow.get("valid_day_count"),
            "decision_status": activation_shadow.get("decision_status"),
            "report_json_path": activation_shadow.get("daily_json_path"),
            "cumulative_json_path": activation_shadow.get("cumulative_json_path"),
            "cumulative_md_path": activation_shadow.get("cumulative_md_path"),
        }
    except Exception as exc:
        out["steps"]["rank1_fixed_candidate_shadow"] = {
            "ok": False,
            "error": str(exc),
        }

    try:
        from libs.reporting.short_alpha_discriminator import (
            write_short_alpha_discriminator,
        )

        short_alpha = write_short_alpha_discriminator(
            reports_root=Path(reports_root),
            through_day=normalized_day,
            output_dir=(
                Path(reports_root)
                / "evaluation"
                / "short_alpha_discriminator"
                / normalized_day
            ),
        )
        out["steps"]["short_alpha_discriminator"] = {
            "ok": str(short_alpha.get("integrity_status") or "").startswith("PASS"),
            "integrity_status": short_alpha.get("integrity_status"),
            "behavior_change_authorized": bool(
                short_alpha.get("behavior_change_authorized")
            ),
            **{
                key: value
                for key, value in short_alpha.items()
                if key.endswith("_path")
            },
        }
    except Exception as exc:
        out["steps"]["short_alpha_discriminator"] = {
            "ok": False,
            "behavior_change_authorized": False,
            "error": str(exc),
        }

    try:
        from libs.reporting.evaluation.same_symbol_sequences import (
            build_same_symbol_sequence_artifacts,
        )

        sequences = build_same_symbol_sequence_artifacts(
            reports_root=reports_root,
            day=normalized_day,
        )
        out["steps"]["same_symbol_sequence_provenance"] = {
            "ok": True,
            "report_json_path": sequences.get("daily_json"),
            "report_md_path": sequences.get("daily_markdown"),
            "cumulative_json_path": sequences.get("cumulative_json"),
            "cumulative_md_path": sequences.get("cumulative_markdown"),
            "summary": dict(sequences.get("summary") or {}),
        }
    except Exception as exc:
        out["steps"]["same_symbol_sequence_provenance"] = {
            "ok": False,
            "error": str(exc),
        }

    out["ok"] = all(bool(step.get("ok")) for step in out["steps"].values() if isinstance(step, dict))
    out["artifacts"] = {
        name: {
            key: _artifact_status(value)
            for key, value in step.items()
            if key.endswith("_path")
        }
        for name, step in out["steps"].items()
        if isinstance(step, dict)
    }
    log_closeout_stage(
        run_id=resolved_run_id, day=normalized_day, stage="run_closeout_maintenance", phase="end",
        detail={
            "ok": bool(out["ok"]),
            "step_results": {
                name: bool(step.get("ok")) if isinstance(step, dict) else None
                for name, step in out["steps"].items()
            },
        },
    )
    return out


# --- Single-owner execution guard (2026-09-30 closeout safety fix) ---------
#
# Confirmed defect: both trigger paths -- the tick-loop's own
# libs/runtime/market_status_closeout.py::apply_market_status_closeout_events
# and the scheduled-fallback CLI (scripts/run_closeout_maintenance.py) --
# call run_closeout_maintenance() directly, with no coordination between
# them. Nothing prevents both from executing concurrently and writing the
# same dated report/artifact paths at the same time.
#
# Reuses this repository's EXISTING PID-based lock primitive
# (libs/runtime/live_loop_lock.py -- already used, tested, and proven for
# the m13 live loop's own single-instance guard) rather than inventing a
# second, unrelated locking mechanism. The lock file is released in a
# `finally` block, so both a normal completion and any exception free it --
# a later, separate, explicit invocation is never permanently blocked by
# an earlier failed attempt.
#
# CRITICAL CORRECTION (2026-09-30, same day): the first version of this
# guard reused the primitive's plain (non-strict) mode, whose age-based
# reclaim (a lock held past _DEFAULT_CLOSEOUT_LOCK_STALE_SEC is reclaimed
# even if its PID is still alive) meant a genuinely still-running closeout
# could lose its own lock to a second trigger purely because it ran longer
# than the staleness window -- a real runtime safety defect, given a real
# closeout run has already been observed to take ~10m37s. This now calls
# acquire/release with strict_owner_identity=True: a live, identity-
# confirmed owner (pid + real OS process-creation timestamp, not a
# self-recorded approximation) can NEVER be reclaimed on age alone. A lock
# is only ever reclaimed when its owner is conclusively dead (pid gone) or
# conclusively a different process (pid reused, creation identity
# differs); anything unverifiable fails closed (rejects) rather than
# guessing. See libs/runtime/live_loop_lock.py's own module docstring for
# the full acquire/release decision table. This strict mode is opt-in on
# the shared primitive -- the m13 live loop's own (unrelated) use of this
# same module is completely untouched.
_DEFAULT_CLOSEOUT_LOCK_PATH = Path("data/state/closeout_maintenance.lock")
# Diagnostic/dead-owner-cleanup metadata ONLY under strict mode -- age
# never authorizes reclaiming a live, identity-confirmed owner's lock (see
# above). Kept as a constant so a long-running-but-genuinely-alive owner
# can still be flagged in observability (log_closeout_stage payload
# long_running_valid_owner=True) without ever being acted on.
_DEFAULT_CLOSEOUT_LOCK_STALE_SEC = 1800

_CLOSEOUT_SKIP_REASON_BY_ACQUIRE_REASON = {
    "lock_active": "ALREADY_RUNNING_VALID_OWNER",
    "LOCK_METADATA_INVALID": "LOCK_METADATA_INVALID",
    "IDENTITY_UNVERIFIABLE": "IDENTITY_UNVERIFIABLE",
}


def run_closeout_maintenance_with_lock(
    *,
    day: str,
    reports_root: Path = Path("reports"),
    event_log_path: Path = Path("data/logs/events.jsonl"),
    post_exit_report_dir: Path = Path("reports/dev/analysis/post_exit_shadow_recap"),
    state_path: Path | None = None,
    trigger: str = "closeout_maintenance",
    collect_account_snapshot: bool = True,
    run_id: str = "",
    lock_path: Path | None = None,
    lock_stale_sec: int | None = None,
    completion_authority_path: Path | None = None,
) -> Dict[str, Any]:
    """Single-owner-guarded entry point for run_closeout_maintenance().

    This is the function BOTH trigger paths must call (never
    run_closeout_maintenance() directly) -- see the module-level comment
    above for why. run_closeout_maintenance() itself is completely
    unmodified; this only adds a strict-identity ownership acquire/release
    boundary around the exact same call, so its own extensively-exercised
    internal step logic carries zero additional risk from this change.

    Uses strict_owner_identity=True: a live, identity-confirmed owner can
    never lose the lock on age alone (see the module-level comment above
    for why plain/age-based reclaim was unsafe for closeout specifically).
    If ownership cannot be acquired -- another owner is genuinely still
    active, the existing lock's metadata cannot be verified, or this
    process's own identity cannot be verified -- returns a safe, clearly-
    marked skipped result WITHOUT ever calling run_closeout_maintenance().

    2026-10-01 durable-completion follow-up: BEFORE even attempting the
    lock, also consults libs/reporting/closeout_completion_authority.py
    for a prior SUCCESS record for this target_day -- a fact the lock
    itself cannot represent, since the lock is released on both success
    and crash/failure alike (see that module's docstring for the full
    rationale). If the day is already durably complete, returns a skipped
    result without ever acquiring the lock or calling
    run_closeout_maintenance() again. This is intentionally a SEPARATE
    check from lock acquisition, not folded into it -- the lock answers
    "is someone else running this right now", this answers "has this
    already successfully finished", and conflating the two would make
    either one impossible to test or reason about independently.
    """
    normalized_day = str(day or "").strip()[:10]
    resolved_run_id = str(run_id or "").strip() or f"closeout-{normalized_day}-{trigger}"
    resolved_lock_path = Path(lock_path) if lock_path is not None else _DEFAULT_CLOSEOUT_LOCK_PATH
    resolved_stale_sec = int(lock_stale_sec) if lock_stale_sec is not None else _DEFAULT_CLOSEOUT_LOCK_STALE_SEC

    prior_completion = read_closeout_completion(
        normalized_day, COMPLETION_ACTION_KEY, path=completion_authority_path
    )
    if prior_completion is not None:
        log_closeout_stage(
            run_id=resolved_run_id, day=normalized_day, stage="closeout_completion_authority", phase="skip",
            detail={
                "trigger": trigger,
                "skip_reason": "ALREADY_COMPLETE",
                "prior_run_id": prior_completion.get("run_id"),
                "prior_trigger": prior_completion.get("trigger"),
                "prior_completed_at_epoch": prior_completion.get("completed_at_epoch"),
            },
        )
        return {
            "schema_version": "closeout_maintenance.v1",
            "day": normalized_day,
            "trigger": str(trigger or "closeout_maintenance"),
            "ok": True,
            "skipped": True,
            "skip_reason": "ALREADY_COMPLETE",
            "prior_completion": dict(prior_completion),
            "steps": {},
        }

    owner_token = uuid.uuid4().hex
    requesting_pid = os.getpid()

    acquired, reason = acquire_live_loop_lock(
        resolved_lock_path,
        lock_stale_sec=resolved_stale_sec,
        strict_owner_identity=True,
        owner_token=owner_token,
        trigger=trigger,
        target_day=normalized_day,
    )
    if not acquired:
        skip_reason = _CLOSEOUT_SKIP_REASON_BY_ACQUIRE_REASON.get(reason, f"OWNERSHIP_NOT_ACQUIRED:{reason}")
        active_owner_pid = None
        lock_age_sec = None
        long_running_valid_owner = False
        try:
            existing = json.loads(resolved_lock_path.read_text(encoding="utf-8"))
            active_owner_pid = existing.get("pid")
            acquired_at = int(existing.get("acquired_at") or 0)
            if acquired_at > 0:
                lock_age_sec = max(0, int(time.time()) - acquired_at)
                long_running_valid_owner = reason == "lock_active" and lock_age_sec > resolved_stale_sec
        except Exception:
            pass
        log_closeout_stage(
            run_id=resolved_run_id, day=normalized_day, stage="closeout_ownership", phase="reject",
            detail={
                "trigger": trigger,
                "reason": reason,
                "skip_reason": skip_reason,
                "lock_path": str(resolved_lock_path),
                "requesting_pid": requesting_pid,
                "active_owner_pid": active_owner_pid,
                "lock_age_sec": lock_age_sec,
                "long_running_valid_owner": long_running_valid_owner,
            },
        )
        return {
            "schema_version": "closeout_maintenance.v1",
            "day": normalized_day,
            "trigger": str(trigger or "closeout_maintenance"),
            "ok": False,
            "skipped": True,
            "skip_reason": skip_reason,
            "steps": {},
        }

    log_closeout_stage(
        run_id=resolved_run_id, day=normalized_day, stage="closeout_ownership", phase="acquire",
        detail={
            "trigger": trigger,
            "lock_path": str(resolved_lock_path),
            "owner_pid": requesting_pid,
            "owner_token": owner_token[:12],
            "acquire_reason": reason,
        },
    )
    try:
        result = run_closeout_maintenance(
            day=day,
            reports_root=reports_root,
            event_log_path=event_log_path,
            post_exit_report_dir=post_exit_report_dir,
            state_path=state_path,
            trigger=trigger,
            collect_account_snapshot=collect_account_snapshot,
            run_id=resolved_run_id,
        )
        if bool(result.get("ok")):
            # Durable SUCCESS-only marker -- written ONLY when every step
            # succeeded, while this run still holds the lock, so no other
            # trigger can observe a window where the lock is free but the
            # day's completion is not yet recorded. A failed result (ok=
            # False, including an exception path, which never reaches this
            # line) writes nothing, leaving a later retry permitted -- see
            # closeout_completion_authority.py's own docstring.
            write_closeout_completion_success(
                normalized_day,
                COMPLETION_ACTION_KEY,
                run_id=resolved_run_id,
                trigger=trigger,
                owner_pid=requesting_pid,
                path=completion_authority_path,
            )
        return result
    finally:
        released, release_status = release_live_loop_lock(
            resolved_lock_path,
            strict_owner_identity=True,
            owner_token=owner_token,
        )
        log_closeout_stage(
            run_id=resolved_run_id, day=normalized_day, stage="closeout_ownership", phase="release",
            detail={
                "trigger": trigger,
                "lock_path": str(resolved_lock_path),
                "owner_pid": requesting_pid,
                "owner_token": owner_token[:12],
                "released": released,
                "release_status": release_status,
            },
        )


def write_closeout_maintenance_report(payload: Dict[str, Any], *, reports_root: Path = Path("reports")) -> Dict[str, str]:
    day = str(payload.get("day") or "unknown")
    out_dir = reports_root / "operator_summary" / "daily" / day
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "closeout_maintenance.json"
    md_path = out_dir / "closeout_maintenance.md"

    def _write(payload_to_write: Dict[str, Any]) -> None:
        json_path.write_text(json.dumps(payload_to_write, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = [
            f"# Closeout Maintenance ({day})",
            "",
            f"- ok: **{bool(payload_to_write.get('ok'))}**",
            f"- trigger: `{payload_to_write.get('trigger')}`",
            "",
            "## Steps",
        ]
        for name, step in (payload_to_write.get("steps") or {}).items():
            if not isinstance(step, dict):
                continue
            lines.append(f"- {name}: **{'ok' if step.get('ok') else 'failed'}**")
            if step.get("error"):
                lines.append(f"  - error: `{step.get('error')}`")
            for key in ("report_md_path", "report_json_path", "latest_path", "path"):
                if step.get(key):
                    lines.append(f"  - {key}: `{step.get(key)}`")
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    _write(payload)
    try:
        from libs.reporting.evaluation.pipeline import build_q9_evaluation

        refreshed = build_q9_evaluation(
            reports_root=reports_root,
            day=day,
            recover_forward=True,
        )
        payload.setdefault("steps", {})["q9_evaluation_post_close_refresh"] = {
            "ok": True,
            "artifact_inventory_path": str(
                Path(reports_root) / "evaluation" / "daily" / day / "artifact_inventory.json"
            ),
            "q9_day_validity_path": str(refreshed.get("q9_day_validity") or ""),
            "daily_scorecard_path": str(refreshed.get("daily_scorecard") or ""),
        }
    except Exception as exc:
        payload.setdefault("steps", {})["q9_evaluation_post_close_refresh"] = {
            "ok": False,
            "error": str(exc),
        }
    payload["ok"] = all(bool(step.get("ok")) for step in payload.get("steps", {}).values() if isinstance(step, dict))
    try:
        from libs.reporting.evaluation.artifact_inventory import build_artifact_inventory
        from libs.reporting.evaluation.day_validity import build_q9_day_validity

        daily_out = Path(reports_root) / "evaluation" / "daily" / day
        daily_out.mkdir(parents=True, exist_ok=True)
        payload.setdefault("steps", {})["post_close_inventory_final_refresh"] = {
            "ok": True,
            "artifact_inventory_path": str(daily_out / "artifact_inventory.json"),
            "q9_day_validity_path": str(daily_out / "q9_day_validity.json"),
        }
        payload["ok"] = all(bool(step.get("ok")) for step in payload.get("steps", {}).values() if isinstance(step, dict))
        _write(payload)
        inventory = build_artifact_inventory(reports_root=reports_root, day=day)
        day_validity = build_q9_day_validity(day=day, inventory=inventory)
        (daily_out / "artifact_inventory.json").write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (daily_out / "q9_day_validity.json").write_text(
            json.dumps(day_validity, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        payload.setdefault("steps", {})["post_close_inventory_final_refresh"] = {
            "ok": False,
            "error": str(exc),
        }
        payload["ok"] = all(bool(step.get("ok")) for step in payload.get("steps", {}).values() if isinstance(step, dict))
        _write(payload)
    try:
        # P1.2 Fix2 (2026-09-29): this used to call write_alpha_research_board()
        # directly, which persists the CANONICAL dated Board and unconditionally
        # advances reports/evaluation/alpha_research_board/latest.json/.md --
        # with no UEF-7/8/9 involvement at all. That made closeout a second,
        # competing canonical publisher, bypassing the fail-closed
        # UEF-9-gated publication libs.reporting.evaluation.daily_uef_pipeline
        # now owns exclusively. Closeout still gets its own same-day board
        # snapshot for this report -- via build_alpha_research_board() (read
        # -only, no persistence at all) -- but writes it to an explicitly
        # non-canonical location, never the canonical dated/latest paths.
        from libs.reporting.alpha_research_board import build_alpha_research_board
        from libs.reporting.alpha_research_board.report import render_alpha_research_board

        board = build_alpha_research_board(reports_root=Path(reports_root), through_day=day)
        snapshot_dir = Path(reports_root) / "evaluation" / "closeout_alpha_board_snapshot" / day
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_json_path = snapshot_dir / "alpha_research_board_snapshot.json"
        snapshot_md_path = snapshot_dir / "alpha_research_board_snapshot.md"
        snapshot_json_path.write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")
        snapshot_md_path.write_text(render_alpha_research_board(board), encoding="utf-8")
        integrity_status = str((board.get("integrity") or {}).get("status") or "")
        payload.setdefault("steps", {})["alpha_research_board_final"] = {
            "ok": integrity_status.startswith("PASS"),
            "integrity_status": integrity_status,
            "candidate_count": board.get("candidate_count"),
            "snapshot_json_path": str(snapshot_json_path),
            "snapshot_md_path": str(snapshot_md_path),
            "explanation_authority": "alpha_research_board_only",
            "canonical_authority": "libs.reporting.evaluation.daily_uef_pipeline (not closeout)",
        }
    except Exception as exc:
        payload.setdefault("steps", {})["alpha_research_board_final"] = {
            "ok": False,
            "error": str(exc),
            "explanation_authority": "alpha_research_board_only",
        }
    payload["ok"] = all(
        bool(step.get("ok"))
        for step in payload.get("steps", {}).values()
        if isinstance(step, dict)
    )
    _write(payload)
    return {"report_json_path": str(json_path), "report_md_path": str(md_path)}


__all__ = ["run_closeout_maintenance", "write_closeout_maintenance_report"]
