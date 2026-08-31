from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .contracts import ACTIVATION_DAY, EXPERIMENT_GUARDS, PROGRAM_ID, SCHEMA_VERSION, THRESHOLDS
from .cumulative import build_cumulative
from .expected_actual import build_expected_actual
from .market_inputs import LeadMarketProvider, YFinanceLeadMarketProvider, detect_samsung_specific_event, flatten_signal_inputs
from .reaction_reader import build_actual_reactions
from .report import render_forward_validation_report
from .scoring import classify_hynix_extension, score_korea_market_state, score_semiconductor_signal
from .shadow_comparison import build_shadow_comparison


KST = timezone(timedelta(hours=9))


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def _capture_window(day: str) -> tuple[datetime, datetime]:
    parsed = date.fromisoformat(day)
    return (
        datetime.combine(parsed, time(8, 50), tzinfo=KST),
        datetime.combine(parsed, time(8, 59, 59), tzinfo=KST),
    )


def _preopen_snapshot(
    *, day: str, path: Path, state_path: Path, now: datetime, provider: LeadMarketProvider
) -> dict[str, Any]:
    existing = _read(path)
    if existing:
        return existing
    start, deadline = _capture_window(day)
    if now < start:
        return {"capture_status": "WAITING", "day": day, "capture_window_kst": [start.isoformat(), deadline.isoformat()]}
    if now > deadline:
        missed = {
            "schema_version": SCHEMA_VERSION,
            "evaluation_program_id": PROGRAM_ID,
            "day": day,
            "capture_status": "MISSED",
            "reason": "08:50_preopen_capture_window_missed_no_backfill",
            "captured_at_kst": now.isoformat(),
            "guards": EXPERIMENT_GUARDS,
            "thresholds": THRESHOLDS,
        }
        _write(path, missed)
        return missed
    observations = dict(provider.capture(as_of=now))
    inputs = flatten_signal_inputs(observations)
    samsung_event = detect_samsung_specific_event(state_path, day=day)
    signals = {
        "sk_hynix": score_semiconductor_signal(inputs),
        "samsung": score_semiconductor_signal(inputs, samsung=True),
        "hynix_extension": classify_hynix_extension(inputs),
        "korea_market": score_korea_market_state(inputs),
    }
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "evaluation_program_id": PROGRAM_ID,
        "day": day,
        "capture_status": "CAPTURED",
        "captured_at_kst": now.isoformat(),
        "capture_window_kst": [start.isoformat(), deadline.isoformat()],
        "observations": observations,
        "signal_inputs": inputs,
        "signals": signals,
        "samsung_event": samsung_event,
        "thresholds": THRESHOLDS,
        "guards": EXPERIMENT_GUARDS,
    }
    _write(path, snapshot)
    return snapshot


def capture_q10_preopen_snapshot(
    *,
    day: str,
    reports_root: Path,
    state_path: Path,
    now: datetime | None = None,
    lead_market_provider: LeadMarketProvider | None = None,
) -> dict[str, Any]:
    if day < ACTIVATION_DAY:
        return {
            "q10_preopen_capture_status": "NOT_ACTIVE_PROSPECTIVE_ONLY",
            "day": day,
        }
    current = (now or datetime.now(KST)).astimezone(KST)
    path = (
        reports_root
        / "evaluation"
        / "baseline_samsung_hynix"
        / day
        / "q10_forward_validation"
        / "q10_preopen_signal_snapshot.json"
    )
    snapshot = _preopen_snapshot(
        day=day,
        path=path,
        state_path=state_path,
        now=current,
        provider=lead_market_provider or YFinanceLeadMarketProvider(),
    )
    return {
        "q10_preopen_capture_status": str(snapshot.get("capture_status") or "WAITING"),
        "day": day,
        "captured_at_kst": snapshot.get("captured_at_kst"),
        "reason": str(snapshot.get("reason") or ""),
        "path": str(path) if path.exists() else "",
    }


def build_q10_forward_validation(
    *, day: str, output_dir: Path, state_path: Path, macro_root: Path,
    candle_map: Mapping[str, list[Mapping[str, Any]]], cost_pct: float, slippage_pct: float,
    now: datetime | None = None, lead_market_provider: LeadMarketProvider | None = None,
) -> dict[str, str]:
    if day < ACTIVATION_DAY:
        return {"q10_forward_validation_status": "NOT_ACTIVE_PROSPECTIVE_ONLY"}
    current = (now or datetime.now(KST)).astimezone(KST)
    experiment_dir = output_dir / "q10_forward_validation"
    preopen_path = experiment_dir / "q10_preopen_signal_snapshot.json"
    reactions_path = experiment_dir / "q10_actual_market_reactions.json"
    expected_path = experiment_dir / "q10_expected_vs_actual.json"
    shadow_path = experiment_dir / "q10_shadow_entry_comparison.json"
    report_path = experiment_dir / "q10_forward_validation_report.md"
    cumulative_path = output_dir.parent / "q10_forward_validation_cumulative.json"

    preopen = _preopen_snapshot(
        day=day, path=preopen_path, state_path=state_path, now=current,
        provider=lead_market_provider or YFinanceLeadMarketProvider(),
    )
    inputs = preopen.get("signal_inputs") or {}
    reactions = build_actual_reactions(day=day, candle_map=candle_map, macro_root=macro_root, signal_inputs=inputs)
    reactions.update({"schema_version": SCHEMA_VERSION, "evaluation_program_id": PROGRAM_ID, "guards": EXPERIMENT_GUARDS})
    expected = build_expected_actual(
        signals=preopen.get("signals") or {}, reactions=reactions, samsung_event=preopen.get("samsung_event") or {}
    )
    expected.update({"schema_version": SCHEMA_VERSION, "evaluation_program_id": PROGRAM_ID, "day": day, "guards": EXPERIMENT_GUARDS})
    shadow = build_shadow_comparison(expected_actual=expected, reactions=reactions, cost_pct=cost_pct, slippage_pct=slippage_pct)
    shadow.update({"schema_version": SCHEMA_VERSION, "evaluation_program_id": PROGRAM_ID, "day": day, "guards": EXPERIMENT_GUARDS})
    _write(reactions_path, reactions)
    _write(expected_path, expected)
    _write(shadow_path, shadow)
    cumulative = build_cumulative(output_dir.parent)
    _write(cumulative_path, cumulative)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_forward_validation_report(
            day=day, preopen=preopen, reactions=reactions,
            expected_actual=expected, shadow=shadow, cumulative=cumulative,
        ),
        encoding="utf-8",
    )
    return {
        "q10_forward_validation_status": str(preopen.get("capture_status") or "WAITING"),
        "q10_preopen_snapshot": str(preopen_path) if preopen_path.exists() else "",
        "q10_actual_reactions": str(reactions_path),
        "q10_expected_vs_actual": str(expected_path),
        "q10_shadow_comparison": str(shadow_path),
        "q10_forward_validation_report": str(report_path),
        "q10_forward_validation_cumulative": str(cumulative_path),
    }
