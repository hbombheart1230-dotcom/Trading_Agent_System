from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from libs.agent.reporter import Reporter
from libs.performance.strategy_memory import sync_strategy_memory_artifacts
from libs.read.kiwoom_account_snapshot_collector import save_kiwoom_account_snapshot
from libs.reporting.broker_closed_trade_reconciler import reconcile_broker_closed_trade_reports
from libs.reporting.carryover_exit_reconciler import reconcile_carryover_exit_reports
from libs.reporting.closeout_residual_positions import reconcile_closeout_residual_positions
from libs.reporting.operator_period_summary import generate_operator_daily_summary_artifact
from libs.reporting.post_exit_shadow_recap import generate_post_exit_shadow_recap, resolve_post_exit_state_path
from libs.reporting.q8_shadow_blocker_review import generate_q8_shadow_blocker_review


def _path_exists(path: Any) -> bool:
    text = str(path or "").strip()
    return bool(text) and Path(text).exists()


def _artifact_status(path: Any) -> Dict[str, Any]:
    text = str(path or "").strip()
    if not text:
        return {"path": "", "exists": False, "size": 0}
    p = Path(text)
    return {"path": text, "exists": p.exists(), "size": p.stat().st_size if p.exists() else 0}


def run_closeout_maintenance(
    *,
    day: str,
    reports_root: Path = Path("reports"),
    event_log_path: Path = Path("data/logs/events.jsonl"),
    post_exit_report_dir: Path = Path("reports/dev/analysis/post_exit_shadow_recap"),
    state_path: Path | None = None,
    trigger: str = "closeout_maintenance",
    collect_account_snapshot: bool = True,
) -> Dict[str, Any]:
    normalized_day = str(day or "").strip()[:10]
    out: Dict[str, Any] = {
        "schema_version": "closeout_maintenance.v1",
        "day": normalized_day,
        "trigger": str(trigger or "closeout_maintenance"),
        "steps": {},
    }

    if collect_account_snapshot:
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

    try:
        from libs.reporting.opening_rank1_shadow import (
            build_opening_rank1_shadow,
        )

        opening_rank1 = build_opening_rank1_shadow(
            day=normalized_day,
            reports_root=reports_root,
            state_path=state_path or Path("data/state.json"),
            allow_fresh_fetch=True,
        )
        out["steps"]["opening_rank1_prospective_shadow"] = {
            "ok": bool(opening_rank1.get("ok")),
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
    return out


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

        refreshed = build_q9_evaluation(reports_root=reports_root, day=day)
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
    return {"report_json_path": str(json_path), "report_md_path": str(md_path)}


__all__ = ["run_closeout_maintenance", "write_closeout_maintenance_report"]
