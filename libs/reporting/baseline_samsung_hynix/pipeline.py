from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from libs.runtime.broker_cost_profile import load_broker_cost_profile

from .contracts import (
    DECISIONS_SCHEMA,
    DEFAULT_SLIPPAGE_PCT,
    FORWARD_SCHEMA,
    REPORT_SCHEMA,
    SYMBOL_CODES,
)
from .data_provider import common_as_of_epoch, load_existing_candles, load_market_change_pct
from .forward_returns import attach_baseline_forward_returns, summarize_forward_returns
from .q9_comparison import build_q9_role_comparison
from .report import render_daily_report
from .strategy import build_decision_snapshot
from .unified_comparison import write_unified_comparison


def _read(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _complete_fixed_universe_decision(row: Mapping[str, Any]) -> bool:
    candidates = [
        candidate
        for candidate in row.get("ranked_candidates") or []
        if isinstance(candidate, Mapping)
    ]
    symbols = {str(candidate.get("symbol") or "") for candidate in candidates}
    return bool(
        symbols == set(SYMBOL_CODES)
        and all(bool((candidate.get("features") or {}).get("available")) for candidate in candidates)
    )


def _intraday_decision_epochs(
    candles: Mapping[str, list[Mapping[str, Any]]],
) -> list[int]:
    symbol_epochs = [
        {
            int(row.get("ts") or 0)
            for row in candles.get(symbol) or []
            if int(row.get("ts") or 0) > 0
        }
        for symbol in SYMBOL_CODES
    ]
    if not symbol_epochs or any(not rows for rows in symbol_epochs):
        return []
    common = set.intersection(*symbol_epochs)
    out: list[int] = []
    for epoch in sorted(common):
        dt = datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(
            timezone.utc
        )
        kst_minutes = (dt.hour * 60 + dt.minute + 9 * 60) % (24 * 60)
        if 9 * 60 + 5 <= kst_minutes <= 15 * 60 and kst_minutes % 5 == 0:
            out.append(epoch)
    return out


def build_baseline_artifacts(
    *,
    day: str,
    reports_root: Path = Path("reports"),
    state_path: Path = Path("data/state.json"),
    cost_profile_path: Path | None = None,
    as_of_epoch: int | None = None,
    candles: Mapping[str, list[Mapping[str, Any]]] | None = None,
    market_change_pct: float | None = None,
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT,
    q9_root: Path = Path("data/logs/quant_shadow_candidates"),
    allow_fresh_fetch: bool = True,
    reconstruct_intraday: bool = False,
) -> dict[str, str]:
    candle_map = (
        {symbol: [dict(row) for row in rows] for symbol, rows in candles.items()}
        if candles is not None
        else load_existing_candles(
            state_path=state_path,
            day=day,
            symbols=SYMBOL_CODES,
            allow_fresh_fetch=allow_fresh_fetch,
        )
    )
    resolved_epoch = common_as_of_epoch(candle_map, requested_epoch=as_of_epoch)
    if market_change_pct is None:
        market_change_pct = load_market_change_pct(day=day)
    decision_epochs = (
        _intraday_decision_epochs(candle_map)
        if reconstruct_intraday
        else [resolved_epoch]
    )
    new_decisions: list[dict[str, Any]] = []
    for decision_epoch in decision_epochs:
        if decision_epoch <= 0:
            continue
        decision = build_decision_snapshot(
            day=day,
            as_of_epoch=decision_epoch,
            candles=candle_map,
            market_change_pct=market_change_pct,
        )
        decision["generated_at"] = datetime.fromtimestamp(
            decision_epoch,
            tz=timezone.utc,
        ).isoformat()
        if _complete_fixed_universe_decision(decision):
            new_decisions.append(decision)

    output_dir = Path(reports_root) / "evaluation" / "baseline_samsung_hynix" / day
    decisions_path = output_dir / "baseline_samsung_hynix_decisions.json"
    existing = _read(decisions_path)
    reconstructed_epochs = set(decision_epochs) if reconstruct_intraday else set()
    decisions = [
        row
        for row in existing.get("decisions") or []
        if (
            isinstance(row, dict)
            and _complete_fixed_universe_decision(row)
            and (
                not reconstruct_intraday
                or int(row.get("as_of_epoch") or 0) in reconstructed_epochs
            )
            and row.get("decision_id")
            not in {new.get("decision_id") for new in new_decisions}
        )
    ]
    decisions.extend(new_decisions)
    decisions.sort(key=lambda row: (int(row.get("as_of_epoch") or 0), str(row.get("decision_id") or "")))
    decisions_payload = {
        "schema_version": DECISIONS_SCHEMA,
        "evaluation_program_id": "Q10_LARGECAP_BASELINE_CONTROL",
        "behavior_effect": "shadow_only",
        "day": day,
        "fixed_universe": ["005930.KS", "000660.KS"],
        "decision_count": len(decisions),
        "decisions": decisions,
    }

    profile = load_broker_cost_profile(cost_profile_path)
    cost_pct = float(profile.get("conservative_round_trip_cost_pct") or 0.0) * 100.0
    forward_rows = attach_baseline_forward_returns(
        decisions,
        minute_rows_by_symbol=candle_map,
    )
    summary = summarize_forward_returns(
        forward_rows,
        cost_pct=cost_pct,
        slippage_pct=slippage_pct,
    )
    comparison = build_q9_role_comparison(
        day=day,
        baseline_summary=summary,
        cost_pct=cost_pct,
        slippage_pct=slippage_pct,
        q9_root=q9_root,
    )
    forward_payload = {
        "schema_version": FORWARD_SCHEMA,
        "evaluation_program_id": "Q10_LARGECAP_BASELINE_CONTROL",
        "behavior_effect": "evaluation_only",
        "day": day,
        "cost_model": {
            "source": str(profile.get("source") or "broker_cost_profile"),
            "profile_sample_count": int(profile.get("sample_count") or 0),
            "round_trip_cost_pct": round(cost_pct, 6),
            "slippage_pct": round(float(slippage_pct), 6),
        },
        "row_count": len(forward_rows),
        "rows": forward_rows,
        "summary": summary,
        "q9_comparison": comparison,
    }
    forward_path = output_dir / "baseline_samsung_hynix_forward_returns.json"
    report_path = output_dir / "baseline_samsung_hynix_daily_report.md"
    _write(decisions_path, decisions_payload)
    _write(forward_path, forward_payload)
    report_path.write_text(
        render_daily_report(day=day, decisions=decisions_payload, forward=forward_payload),
        encoding="utf-8",
    )
    metadata_path = output_dir / "baseline_samsung_hynix_daily_report.json"
    _write(
        metadata_path,
        {
            "schema_version": REPORT_SCHEMA,
            "evaluation_program_id": "Q10_LARGECAP_BASELINE_CONTROL",
            "day": day,
            "decisions_path": str(decisions_path),
            "forward_returns_path": str(forward_path),
            "markdown_path": str(report_path),
        },
    )
    unified = write_unified_comparison(
        forward_path=forward_path,
        output_dir=output_dir,
    )
    return {
        "decisions": str(decisions_path),
        "forward_returns": str(forward_path),
        "daily_report": str(report_path),
        "daily_report_metadata": str(metadata_path),
        "unified_comparison_json": unified["json"],
        "unified_comparison_markdown": unified["markdown"],
    }
