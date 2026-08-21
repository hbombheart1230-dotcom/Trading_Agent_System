from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from libs.runtime.broker_cost_profile import load_broker_cost_profile

from .comparison import build_comparison
from .contracts import (
    COMPARISON_SCHEMA,
    DECISIONS_SCHEMA,
    DEFAULT_SLIPPAGE_PCT,
    FORWARD_SCHEMA,
    PROGRAM_ID,
    REPORT_SCHEMA,
    TARGET_SYMBOL,
)
from .crypto_fear_greed import load_crypto_fear_greed_index, unavailable as unavailable_crypto_fear_greed
from .data_provider import load_btc_signal_rows, load_woori_candles
from .forward_returns import attach_forward_returns, summarize
from .report import render_report
from .strategy import build_decision_snapshot


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _decision_epochs(candles: list[Mapping[str, Any]]) -> list[int]:
    output: list[int] = []
    for row in candles:
        epoch = int(row.get("ts") or 0)
        if epoch <= 0:
            continue
        kst = datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(
            timezone.utc
        )
        minutes = (kst.hour * 60 + kst.minute + 9 * 60) % (24 * 60)
        if 9 * 60 + 5 <= minutes <= 15 * 60 and minutes % 5 == 0:
            output.append(epoch)
    return sorted(set(output))


def build_baseline_btc_woori_artifacts(
    *,
    day: str,
    reports_root: Path = Path("reports"),
    state_path: Path = Path("data/state.json"),
    cost_profile_path: Path | None = None,
    q9_root: Path = Path("data/logs/quant_shadow_candidates"),
    candles: list[Mapping[str, Any]] | None = None,
    btc_signals: Mapping[str, Any] | None = None,
    crypto_fear_greed: Mapping[str, Any] | None = None,
    allow_fresh_fetch: bool = True,
    reconstruct_intraday: bool = True,
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT,
) -> dict[str, str]:
    output_dir = reports_root / "evaluation" / "baseline_btc_woori_tech" / day
    decisions_path = output_dir / "baseline_btc_woori_decisions.json"
    existing = _read(decisions_path)
    existing_fear_greed = (
        dict(existing.get("crypto_fear_greed") or {})
        if isinstance(existing.get("crypto_fear_greed"), Mapping)
        else {}
    )
    existing_decisions = [
        row for row in existing.get("decisions") or []
        if isinstance(row, dict)
    ]
    candle_rows = (
        [dict(row) for row in candles]
        if candles is not None
        else load_woori_candles(day=day, state_path=state_path, allow_fresh_fetch=allow_fresh_fetch)
    )
    signal_payload = (
        dict(btc_signals)
        if btc_signals is not None
        else load_btc_signal_rows(day=day)
        if allow_fresh_fetch
        else {
            "available": False,
            "available_sources": [],
            "sources": {},
            "fallback_reason": "fresh_fetch_disabled",
        }
    )
    if crypto_fear_greed is not None:
        fear_greed_payload = dict(crypto_fear_greed)
    elif allow_fresh_fetch:
        fetched_fear_greed = load_crypto_fear_greed_index(day=day)
        fear_greed_payload = (
            fetched_fear_greed
            if fetched_fear_greed.get("available")
            else existing_fear_greed
            if existing_fear_greed.get("available") and existing_fear_greed.get("day") == day
            else fetched_fear_greed
        )
    elif existing_fear_greed.get("available") and existing_fear_greed.get("day") == day:
        fear_greed_payload = existing_fear_greed
    else:
        fear_greed_payload = unavailable_crypto_fear_greed("fresh_fetch_disabled", day=day)
    epochs = _decision_epochs(candle_rows) if reconstruct_intraday else ([int(candle_rows[-1]["ts"])] if candle_rows else [])
    decisions: list[dict[str, Any]] = []
    if not allow_fresh_fetch and btc_signals is None and existing_decisions:
        decisions = existing_decisions
    else:
        for epoch in epochs:
            row = build_decision_snapshot(
                day=day,
                as_of_epoch=epoch,
                woori_candles=candle_rows,
                btc_signals=signal_payload,
                crypto_fear_greed=fear_greed_payload,
            )
            row["generated_at"] = datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
            decisions.append(row)
        if not decisions and existing_decisions:
            decisions = existing_decisions
    forward_path = output_dir / "baseline_btc_woori_forward_returns.json"
    report_path = output_dir / "baseline_btc_woori_daily_report.md"
    comparison_path = output_dir / "baseline_btc_woori_comparison.json"
    decisions_payload = {
        "schema_version": DECISIONS_SCHEMA,
        "evaluation_program_id": PROGRAM_ID,
        "behavior_effect": "shadow_only",
        "decision_policy_version": "q12_btc_multihorizon_leading_signal.v2",
        "day": day,
        "fixed_target": "041190.KQ",
        "btc_signal_availability": (
            existing.get("btc_signal_availability")
            if not allow_fresh_fetch and btc_signals is None and existing_decisions
            else {
                "available": signal_payload.get("available"),
                "sources": signal_payload.get("available_sources") or [],
                "fallback_reason": signal_payload.get("fallback_reason") or "",
            }
        ),
        "crypto_fear_greed": fear_greed_payload,
        "crypto_fear_greed_behavior_effect": "observation_only",
        "decision_count": len(decisions),
        "decisions": decisions,
    }
    profile = load_broker_cost_profile(cost_profile_path)
    cost_pct = float(profile.get("conservative_round_trip_cost_pct") or 0.0) * 100.0
    forward_rows = attach_forward_returns(decisions, candles=candle_rows)
    summary = summarize(forward_rows, cost_pct=cost_pct, slippage_pct=slippage_pct)
    observed = sum(
        1
        for row in forward_rows
        if any((checkpoint or {}).get("status") == "observed" for checkpoint in (row.get("returns") or {}).values())
    )
    forward_payload = {
        "schema_version": FORWARD_SCHEMA,
        "evaluation_program_id": PROGRAM_ID,
        "behavior_effect": "evaluation_only",
        "day": day,
        "evidence_status": "AVAILABLE" if observed else "INSUFFICIENT_EVIDENCE",
        "cost_model": {
            "source": str(profile.get("source") or "broker_cost_profile"),
            "round_trip_cost_pct": round(cost_pct, 6),
            "slippage_pct": round(slippage_pct, 6),
        },
        "row_count": len(forward_rows),
        "rows": forward_rows,
        "summary": summary,
    }
    comparison = build_comparison(
        day=day,
        summary=summary,
        forward_rows=forward_rows,
        decisions=decisions,
        cost_pct=cost_pct,
        slippage_pct=slippage_pct,
        reports_root=reports_root,
        q9_root=q9_root,
        state_path=state_path,
    )
    comparison["schema_version"] = COMPARISON_SCHEMA
    _write(decisions_path, decisions_payload)
    _write(forward_path, forward_payload)
    _write(comparison_path, comparison)
    report_path.write_text(
        render_report(
            day=day,
            decisions=decisions_payload,
            forward=forward_payload,
            comparison=comparison,
        ),
        encoding="utf-8",
    )
    metadata_path = output_dir / "baseline_btc_woori_daily_report.json"
    _write(
        metadata_path,
        {
            "schema_version": REPORT_SCHEMA,
            "evaluation_program_id": PROGRAM_ID,
            "behavior_effect": "shadow_only",
            "day": day,
            "target_symbol": TARGET_SYMBOL,
            "decisions_path": str(decisions_path),
            "forward_returns_path": str(forward_path),
            "comparison_path": str(comparison_path),
            "markdown_path": str(report_path),
        },
    )
    return {
        "decisions": str(decisions_path),
        "forward_returns": str(forward_path),
        "daily_report": str(report_path),
        "daily_report_metadata": str(metadata_path),
        "comparison": str(comparison_path),
    }
