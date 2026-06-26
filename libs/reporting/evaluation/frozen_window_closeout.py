from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from libs.reporting.baseline_samsung_hynix import build_baseline_artifacts
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
    q11 = build_opportunity_engine_artifacts(
        day=day,
        reports_root=reports_root,
        state_path=state_path,
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
    ))
    manifest = build_freeze_manifest()
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
        "freeze_manifest": build_freeze_manifest(),
        "day_record": day_record,
        "q11": {
            "evaluation_program_id": "Q11_OPENING_SURGE_MARKET_REVERSAL",
            "daily_report": q11["daily_report"],
            "signals": q11["signals"],
            "virtual_trades": q11["virtual_trades"],
        },
        "ledger_path": str(ledger_path),
        "valid_day_count": ledger.get("valid_day_count"),
        "remaining_valid_days": ledger.get("remaining_valid_days"),
        "window_complete": ledger.get("window_complete"),
    }
    _write(result_path, result)
    result["result_path"] = str(result_path)
    return result


__all__ = ["run_frozen_window_closeout"]
