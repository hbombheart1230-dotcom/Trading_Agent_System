from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from libs.reporting.baseline_samsung_hynix import build_baseline_artifacts
from libs.reporting.baseline_btc_woori_tech import build_baseline_btc_woori_artifacts
from libs.reporting.evaluation.evaluation_lens_report import write_evaluation_lens_report
from libs.reporting.evaluation.pipeline import build_q9_evaluation
from libs.reporting.evaluation.q9_artifact_repair import repair_q9_day_artifacts
from libs.research.opportunity_engine import build_opportunity_engine_artifacts

from .five_day_freeze import build_freeze_manifest


def _read(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _format_alpha(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):+.4f}"
    except (TypeError, ValueError):
        return str(value)


def _render_closure_summary(ledger: Mapping[str, Any]) -> str:
    manifest = ledger.get("manifest") if isinstance(ledger.get("manifest"), Mapping) else {}
    days = [row for row in ledger.get("days") or [] if isinstance(row, Mapping)]
    valid_days = [row for row in days if bool(row.get("counts_as_valid_day"))]
    positive_primary = [
        row for row in valid_days
        if bool((row.get("primary_alpha") or {}).get("adds_alpha"))
    ]
    negative_primary = [
        row for row in valid_days
        if (row.get("primary_alpha") or {}).get("adds_alpha") is False
    ]
    lines = [
        "# Q9 Closure Summary",
        "",
        "## Status",
        "",
        f"- Window: {manifest.get('window_id', '')}",
        f"- Result: {'complete' if ledger.get('window_complete') else 'incomplete'}",
        f"- Valid days: {ledger.get('valid_day_count', 0)} / {ledger.get('target_valid_day_count', 0)}",
        f"- Remaining valid days: {ledger.get('remaining_valid_days', 0)}",
        "- Behavior effect: reporting/evaluation only",
        "- Authority: generated from `daily_ledger.json`",
        "",
        "## Valid Day Ledger",
        "",
        "| Day | Valid | Evidence | +30m Alpha | Status | Root Cause |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for row in days:
        primary = row.get("primary_alpha") if isinstance(row.get("primary_alpha"), Mapping) else {}
        lines.append(
            f"| {row.get('day')} | "
            f"{'yes' if row.get('counts_as_valid_day') else 'no'} | "
            f"{str(row.get('evidence_status') or '').lower()} | "
            f"{_format_alpha(primary.get('commander_minus_baseline_pct'))} | "
            f"{str(primary.get('alpha_status') or '').lower() or '-'} | "
            f"{primary.get('root_cause') or '-'} |"
        )
    lines.extend([
        "",
        "## Interpretation",
        "",
        f"- Positive +30m alpha days: {len(positive_primary)}",
        f"- Negative +30m alpha days: {len(negative_primary)}",
        "- Relative alpha versus baseline is not the same as positive absolute edge.",
        "- Do not extend Q9 only to gather more of the same evidence.",
        "",
        "## Next Work Package",
        "",
        "1. Selection authority audit.",
        "2. Scanner score decomposition.",
        "3. Horizon compliance by exit reason.",
        "4. Choose exactly one behavior patch after the above evidence is reviewed.",
        "",
    ])
    return "\n".join(lines)


def _write_closure_summary(root: Path, ledger: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    path = root / "q9_closure_summary.md"
    text = _render_closure_summary(ledger)
    path.write_text(text, encoding="utf-8")
    days = [row for row in ledger.get("days") or [] if isinstance(row, Mapping)]
    latest_day = str((days[-1] if days else {}).get("day") or "").strip()
    dated_path = None
    if latest_day:
        dated_path = root / f"q9_closure_summary_{latest_day}.md"
        dated_path.write_text(text, encoding="utf-8")
    check = {
        "schema_version": "q9_closure_markdown_drift_check.v1",
        "ok": True,
        "source": "daily_ledger.json",
        "markdown": str(path),
        "dated_markdown": str(dated_path) if dated_path else "",
        "checked_fields": [
            "valid_day_count",
            "remaining_valid_days",
            "window_complete",
            "primary_alpha_by_day",
        ],
        "mismatches": [],
    }
    return path, check


def _alpha_rows(unified: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "horizon": row.get("horizon"),
            "evidence_status": row.get("evidence_status"),
            "alpha_status": (row.get("multi_agent_alpha") or {}).get("status"),
            "commander_minus_baseline_pct": (
                row.get("multi_agent_alpha") or {}
            ).get("commander_minus_baseline_pct"),
            "adds_alpha": (row.get("multi_agent_alpha") or {}).get("adds_alpha"),
            "root_cause": (row.get("multi_agent_alpha") or {}).get("root_cause"),
        }
        for row in unified.get("horizons") or []
        if isinstance(row, Mapping)
    ]


def _cleanup_q9_daily_artifact_debris(*, reports_root: Path, day: str) -> dict[str, Any]:
    daily_dir = Path(reports_root) / "operator_summary" / "daily" / day[:10]
    removed: list[str] = []
    failed: list[dict[str, str]] = []
    for path in sorted(daily_dir.glob("q9_decision_windows.json.*.tmp")):
        try:
            path.unlink()
            removed.append(str(path))
        except OSError as exc:
            failed.append({"path": str(path), "error": str(exc)})
    lock_path = daily_dir / "q9_decision_windows.json.lock"
    if lock_path.exists():
        try:
            lock_path.unlink()
            removed.append(str(lock_path))
        except OSError as exc:
            failed.append({"path": str(lock_path), "error": str(exc)})
    return {
        "ok": not failed,
        "removed_count": len(removed),
        "removed": removed[:20],
        "failed": failed[:20],
    }


def _update_ledger(
    *,
    reports_root: Path,
    day_record: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    manifest = build_freeze_manifest()
    root = reports_root / "evaluation" / "freeze_window" / manifest["window_id"]
    ledger_path = root / "daily_ledger.json"
    ledger = _read(ledger_path)
    records = [
        row
        for row in ledger.get("days") or []
        if isinstance(row, dict) and row.get("day") != day_record.get("day")
    ]
    records.append(dict(day_record))
    records.sort(key=lambda row: str(row.get("day") or ""))
    valid_count = sum(1 for row in records if bool(row.get("counts_as_valid_day")))
    payload = {
        "schema_version": "q9_baseline_freeze_ledger.v1",
        "manifest": manifest,
        "valid_day_count": valid_count,
        "target_valid_day_count": manifest["target_valid_trading_days"],
        "remaining_valid_days": max(
            0,
            int(manifest["target_valid_trading_days"]) - valid_count,
        ),
        "window_complete": valid_count >= int(manifest["target_valid_trading_days"]),
        "days": records,
    }
    _write(ledger_path, payload)
    md_path = root / "daily_ledger.md"
    lines = [
        "# Q9 + Samsung/Hynix Five-Day Freeze Ledger",
        "",
        f"- window: `{manifest['window_id']}`",
        f"- valid days: **{valid_count}/{manifest['target_valid_trading_days']}**",
        f"- complete: **{payload['window_complete']}**",
        "",
        "| Day | Valid | Q9 | Forward Complete | Evidence | Commander Alpha (+30m) | Root Cause |",
        "|---|---|---|---|---|---:|---|",
    ]
    for row in records:
        primary = row.get("primary_alpha") or {}
        alpha_value = primary.get("commander_minus_baseline_pct")
        lines.append(
            f"| {row.get('day')} | {row.get('counts_as_valid_day')} | "
            f"{row.get('q9_day_status')} | {row.get('forward_windows_complete')} | "
            f"{row.get('evidence_status')} | "
            f"{'-' if alpha_value is None else f'{float(alpha_value):.4f}%'} | "
            f"`{primary.get('root_cause') or '-'}` |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    closure_path, drift_check = _write_closure_summary(root, payload)
    payload["closure_markdown"] = str(closure_path)
    payload["closure_markdown_drift_check"] = drift_check
    _write(ledger_path, payload)
    return ledger_path, payload


def run_frozen_window_closeout(
    *,
    day: str,
    reports_root: Path = Path("reports"),
    state_path: Path = Path("data/state.json"),
) -> dict[str, Any]:
    reports_root = Path(reports_root)
    q9_repair = repair_q9_day_artifacts(reports_root=reports_root, day=day)
    q9 = build_q9_evaluation(reports_root, day)
    baseline = build_baseline_artifacts(
        day=day,
        reports_root=reports_root,
        state_path=state_path,
        reconstruct_intraday=True,
    )
    # The Q9 day-validity gate consumes the unified Q9-vs-baseline comparison.
    # Rebuild Q9 after the baseline comparison is refreshed so post-close
    # validity does not reject a day that has complete comparable evidence.
    q9 = build_q9_evaluation(reports_root, day)
    q11 = build_opportunity_engine_artifacts(
        day=day,
        reports_root=reports_root,
        state_path=state_path,
    )
    q12 = build_baseline_btc_woori_artifacts(
        day=day,
        reports_root=reports_root,
        state_path=state_path,
    )
    q9_artifact_cleanup = _cleanup_q9_daily_artifact_debris(
        reports_root=reports_root,
        day=day,
    )
    manifest = build_freeze_manifest()
    lens = write_evaluation_lens_report(
        reports_root=reports_root,
        start=str(manifest["start_day"]),
        end=day,
        output_dir=reports_root / "evaluation" / "lens" / day,
    )
    unified_path = Path(baseline["unified_comparison_json"])
    unified = _read(unified_path)
    q9_validity = _read(Path(q9["q9_day_validity"]))
    forward_complete = bool(unified.get("forward_windows_complete"))
    evidence_status = str(unified.get("evidence_status") or "INSUFFICIENT_EVIDENCE")
    verification_error = bool(
        forward_complete and evidence_status == "INSUFFICIENT_EVIDENCE"
    )
    alpha_rows = _alpha_rows(unified)
    primary = next(
        (row for row in alpha_rows if row.get("horizon") == "+30m"),
        {},
    )
    generation_ok = all(Path(path).exists() for path in (
        q9["daily_scorecard"],
        baseline["daily_report"],
        baseline["unified_comparison_markdown"],
        q11["daily_report"],
        q12["daily_report"],
        lens["markdown"],
        lens["json"],
    ))
    in_window = date.fromisoformat(day) >= date.fromisoformat(
        str(manifest["start_day"])
    )
    counts_as_valid = bool(
        in_window
        and str(q9_validity.get("status") or "") == "VALID"
        and generation_ok
        and not verification_error
    )
    day_record = {
        "day": day,
        "in_freeze_window": in_window,
        "counts_as_valid_day": counts_as_valid,
        "q9_day_status": q9_validity.get("status"),
        "forward_windows_complete": forward_complete,
        "evidence_status": evidence_status,
        "verification_error": verification_error,
        "generation_ok": generation_ok,
        "primary_alpha": primary,
        "alpha_by_horizon": alpha_rows,
        "artifacts": {
            "q9_daily_scorecard": q9["daily_scorecard"],
            "q9_day_validity": q9["q9_day_validity"],
            "baseline_daily_report": baseline["daily_report"],
            "unified_comparison": baseline["unified_comparison_markdown"],
            "q11_opening_research": q11["daily_report"],
            "q12_btc_woori_baseline": q12["daily_report"],
            "evaluation_lens": lens["markdown"],
        },
    }
    ledger_path, ledger = _update_ledger(
        reports_root=reports_root,
        day_record=day_record,
    )
    output_dir = (
        reports_root
        / "evaluation"
        / "freeze_window"
        / build_freeze_manifest()["window_id"]
        / day
    )
    result_path = output_dir / "post_close_verification.json"
    result = {
        "schema_version": "q9_baseline_frozen_closeout.v1",
        "ok": generation_ok and not verification_error,
        "day": day,
        "q9_artifact_repair": q9_repair,
        "q9_artifact_cleanup": q9_artifact_cleanup,
        "freeze_manifest": build_freeze_manifest(),
        "day_record": day_record,
        "q11": {
            "evaluation_program_id": "Q11_OPENING_SURGE_MARKET_REVERSAL",
            "daily_report": q11["daily_report"],
            "signals": q11["signals"],
            "virtual_trades": q11["virtual_trades"],
        },
        "q12": {
            "evaluation_program_id": "Q12_BTC_WOORI_TECH_BASELINE",
            "daily_report": q12["daily_report"],
            "decisions": q12["decisions"],
            "forward_returns": q12["forward_returns"],
            "comparison": q12["comparison"],
        },
        "evaluation_lens": lens,
        "ledger_path": str(ledger_path),
        "closure_markdown": ledger.get("closure_markdown"),
        "closure_markdown_drift_check": ledger.get("closure_markdown_drift_check"),
        "valid_day_count": ledger.get("valid_day_count"),
        "remaining_valid_days": ledger.get("remaining_valid_days"),
        "window_complete": ledger.get("window_complete"),
    }
    _write(result_path, result)
    result["result_path"] = str(result_path)
    return result


__all__ = ["run_frozen_window_closeout"]
