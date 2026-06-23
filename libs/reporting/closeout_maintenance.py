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
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# Closeout Maintenance ({day})",
        "",
        f"- ok: **{bool(payload.get('ok'))}**",
        f"- trigger: `{payload.get('trigger')}`",
        "",
        "## Steps",
    ]
    for name, step in (payload.get("steps") or {}).items():
        if not isinstance(step, dict):
            continue
        lines.append(f"- {name}: **{'ok' if step.get('ok') else 'failed'}**")
        if step.get("error"):
            lines.append(f"  - error: `{step.get('error')}`")
        for key in ("report_md_path", "report_json_path", "latest_path", "path"):
            if step.get(key):
                lines.append(f"  - {key}: `{step.get(key)}`")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return {"report_json_path": str(json_path), "report_md_path": str(md_path)}


__all__ = ["run_closeout_maintenance", "write_closeout_maintenance_report"]
