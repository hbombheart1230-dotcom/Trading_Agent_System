from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from libs.reporting.evaluation.trade_read_model import build_q9_trade_read_model


_SYMBOL_RE = re.compile(r"^\d{6}$")


def mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return mapping(payload)


def normalized_symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return text if _SYMBOL_RE.fullmatch(text) else ""


def _is_stage2_record(payload: Mapping[str, Any]) -> bool:
    parsed = mapping(payload.get("parsed_output"))
    review = mapping(parsed.get("selected_symbol_tactical_review"))
    return bool(review and normalized_symbol(review.get("target_symbol") or parsed.get("target_symbol")))


def load_stage2_records(
    evidence_path: Path,
    *,
    start_day: str,
    end_day: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    if not evidence_path.exists():
        return rows
    with evidence_path.open("rb", buffering=16 * 1024 * 1024) as handle:
        for raw_line in handle:
            if b"selected_symbol_tactical_review" not in raw_line:
                continue
            try:
                payload = json.loads(raw_line)
            except (UnicodeError, json.JSONDecodeError):
                continue
            if str(payload.get("agent") or "") != "strategist" or not _is_stage2_record(payload):
                continue
            timestamp = str(payload.get("timestamp") or "")
            day = timestamp[:10]
            if not (start_day <= day <= end_day):
                continue
            parsed = mapping(payload.get("parsed_output"))
            review = mapping(parsed.get("selected_symbol_tactical_review"))
            target_symbol = normalized_symbol(review.get("target_symbol") or parsed.get("target_symbol"))
            run_id = str(payload.get("run_id") or "").strip()
            if not run_id or run_id == "strategist-unknown":
                continue
            dedupe_key = (run_id, target_symbol, timestamp)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            memory_usage = mapping(review.get("memory_usage") or parsed.get("memory_usage"))
            entry_delta = mapping(review.get("entry_policy_delta") or parsed.get("entry_policy_delta"))
            rows.append(
                {
                    "run_id": run_id,
                    "timestamp": timestamp,
                    "day": day,
                    "target_symbol": target_symbol,
                    "target_rank": review.get("target_rank") or parsed.get("target_rank"),
                    "selected_symbol_decision": str(
                        review.get("selected_symbol_decision")
                        or parsed.get("selected_symbol_decision")
                        or ""
                    ),
                    "memory_usage": memory_usage,
                    "entry_policy_delta": entry_delta,
                    "commander_actionability": str(
                        review.get("commander_actionability")
                        or parsed.get("commander_actionability")
                        or ""
                    ),
                }
            )
    return rows


def load_q9_windows_for_runs(
    reports_root: Path,
    stage2_rows: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    runs_by_day: dict[str, set[str]] = {}
    for row in stage2_rows:
        day = str(row.get("day") or "")
        run_id = str(row.get("run_id") or "")
        if day and run_id:
            runs_by_day.setdefault(day, set()).add(run_id)
    out: dict[str, dict[str, Any]] = {}
    for day, wanted in runs_by_day.items():
        payload = read_json(
            reports_root / "operator_summary" / "daily" / day / "q9_decision_windows.json"
        )
        for raw in payload.get("windows") or []:
            row = mapping(raw)
            run_id = str(row.get("run_id") or "")
            if run_id in wanted and str(row.get("window_type") or "") == "scanner_selection":
                out[run_id] = row
    return out

def load_canonical_strategist(
    reports_root: Path,
    *,
    day: str,
    run_id: str,
) -> dict[str, Any]:
    return read_json(reports_root / "canonical" / day / run_id / "strategist.json")


def load_trade_outcomes(
    reports_root: Path,
    *,
    start_day: str,
    end_day: str,
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    trades_root = reports_root / "trades"
    if not trades_root.exists():
        return out
    for bundle_path in trades_root.glob("20??-??-??/**/lifecycle_bundle.json"):
        day = bundle_path.parts[-4]
        if not (start_day <= day <= end_day):
            continue
        model = build_q9_trade_read_model(bundle_path.parent)
        selection = mapping(model.get("selection"))
        run_id = str(selection.get("strategist_run_id") or "").strip()
        outcome = mapping(model.get("outcome"))
        integrity = mapping(model.get("integrity"))
        exclusion = mapping(integrity.get("evaluation_exclusion"))
        net_return = outcome.get("net_return_pct")
        if not run_id or str(model.get("status") or "") != "closed" or net_return is None:
            continue
        out.setdefault(run_id, []).append(
            {
                "trade_id": str(model.get("trade_id") or bundle_path.parent.name),
                "day": str(model.get("day") or day),
                "symbol": normalized_symbol(model.get("symbol")),
                "net_return_pct": float(net_return),
                "realized_pnl": outcome.get("realized_pnl"),
                "trusted_for_behavior": not bool(exclusion.get("active")),
                "evaluation_exclusion_reason": str(exclusion.get("reason") or ""),
            }
        )
    return out
