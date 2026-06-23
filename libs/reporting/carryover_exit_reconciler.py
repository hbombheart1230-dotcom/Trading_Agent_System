from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from libs.reporting.broker_closed_trade_reconciler import (
    _patch_exit_payload,
    _patch_health_payload,
    _patch_lifecycle_payload,
    _patch_report_payload,
    _patch_summary_payload,
)
from libs.reporting.intraday_trade_reports import resolve_story_input_for_regeneration
from libs.reporting.llm_artifacts import (
    build_compact_input_artifact,
    build_llm_response_artifact,
    trade_artifact_paths,
    write_json,
)
from libs.reporting.trade_report_ai import (
    build_ai_trade_report_compact_input,
    build_deterministic_trade_report,
    build_trade_summary_input,
    build_trade_summary_report,
    render_trade_report_markdown,
    render_trade_summary_markdown_with_evaluation,
)

KST = timezone(timedelta(hours=9))


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _to_int(value: Any) -> int:
    try:
        return int(float(str(value or "").strip().replace(",", "")))
    except Exception:
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(str(value or "").strip().replace(",", ""))
    except Exception:
        return 0.0


def _symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("A") and len(text) == 7:
        text = text[1:]
    return text[-6:] if len(text) >= 6 else text


def _call_rows(snapshot: Mapping[str, Any], api_id: str, row_key: str) -> Iterable[Dict[str, Any]]:
    for call in list(snapshot.get("calls") or []):
        if not isinstance(call, dict) or str(call.get("api_id") or "") != api_id:
            continue
        payload = call.get("payload") if isinstance(call.get("payload"), dict) else {}
        for row in list(payload.get(row_key) or []):
            if isinstance(row, dict):
                yield dict(row)


def _order_time_to_utc(day: str, value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 4:
        digits = "090000"
    hh = int(digits[0:2])
    mm = int(digits[2:4])
    ss = int(digits[4:6]) if len(digits) >= 6 else 0
    local = datetime.strptime(day, "%Y-%m-%d").replace(hour=hh, minute=mm, second=ss, tzinfo=KST)
    return local.astimezone(timezone.utc).isoformat(timespec="seconds")


def _current_sell_orders(snapshot: Mapping[str, Any], day: str) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    rows = list(_call_rows(snapshot, "ka10076", "cntr"))
    rows.extend(_call_rows(snapshot, "kt00009", "acnt_ord_cntr_prst_array"))
    for row in rows:
        side = str(row.get("io_tp_nm") or "").lower()
        if "매도" not in side and "sell" not in side:
            continue
        symbol = _symbol(row.get("stk_cd"))
        qty = _to_int(row.get("cntr_qty") or row.get("cnfm_qty"))
        if not symbol or qty <= 0:
            continue
        current = out.get(symbol)
        if current and _to_int(current.get("qty")) >= qty:
            continue
        order_time = row.get("cntr_tm") or row.get("ord_tm")
        out[symbol] = {
            "symbol": symbol,
            "qty": qty,
            "price": _to_float(row.get("cntr_uv") or row.get("cntr_pric")),
            "order_id": str(row.get("ord_no") or ""),
            "order_time": str(order_time or ""),
            "exit_ts": _order_time_to_utc(day, order_time),
            "fee_tax": _to_int(row.get("tdy_trde_cmsn")) + _to_int(row.get("tdy_trde_tax")),
        }
    return out


def _sell_only_symbols(snapshot: Mapping[str, Any]) -> set[str]:
    out: set[str] = set()
    for row in _call_rows(snapshot, "ka10170", "tdy_trde_diary"):
        symbol = _symbol(row.get("stk_cd") or row.get("stk_cd_1"))
        if symbol and _to_int(row.get("buy_qty")) == 0 and _to_int(row.get("sell_qty")) > 0:
            out.add(symbol)
    return out


def _find_prior_open_trade(reports_root: Path, day: str, symbol: str) -> tuple[Path | None, Dict[str, Any]]:
    candidates: List[tuple[str, Path, Dict[str, Any]]] = []
    for path in (reports_root / "trades").glob("*/*/TRD_*/lifecycle_bundle.json"):
        payload = _read_json(path)
        trade_day = str(payload.get("day") or path.parts[-4])[:10]
        if trade_day >= day or _symbol(payload.get("symbol")) != symbol:
            continue
        status = str(payload.get("trade_lifecycle_status") or payload.get("status") or "").lower()
        if status not in {"open", "partial"}:
            continue
        candidates.append((trade_day, path.parent, payload))
    if not candidates:
        return None, {}
    candidates.sort(key=lambda item: (item[0], item[1].name), reverse=True)
    return candidates[0][1], candidates[0][2]


def _realized_rows_for_symbol(
    reports_root: Path,
    *,
    symbol: str,
    entry_day: str,
    exit_day: str,
) -> List[Dict[str, Any]]:
    repo_root = reports_root.parent if reports_root.name == "reports" else Path(".")
    snapshots = repo_root / "data" / "logs" / "kiwoom_account_snapshots"
    rows: List[Dict[str, Any]] = []
    for day_dir in sorted(path for path in snapshots.glob("*") if path.is_dir()):
        if day_dir.name < entry_day or day_dir.name > exit_day:
            continue
        snapshot = _read_json(day_dir / "latest.json")
        for row in _call_rows(snapshot, "ka10072", "dt_stk_div_rlzt_pl"):
            if _symbol(row.get("stk_cd") or row.get("stk_cd_1")) != symbol:
                continue
            rows.append({"day": day_dir.name, **row})
    return rows


def _build_truth(
    *,
    lifecycle: Mapping[str, Any],
    symbol: str,
    exit_day: str,
    order: Mapping[str, Any],
    realized_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    entry = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
    total_qty = sum(_to_int(row.get("cntr_qty")) for row in realized_rows) or _to_int(order.get("qty"))
    buy_price = (
        _to_float(realized_rows[0].get("buy_uv"))
        if realized_rows
        else _to_float((entry.get("execution_details") or {}).get("avg_price") or entry.get("price"))
    )
    sell_notional = sum(_to_float(row.get("cntr_pric")) * _to_int(row.get("cntr_qty")) for row in realized_rows)
    sell_price = sell_notional / total_qty if total_qty else _to_float(order.get("price"))
    pnl = sum(_to_float(row.get("tdy_sel_pl") or row.get("tdy_sel_pl_1")) for row in realized_rows)
    fee_tax = sum(
        _to_int(row.get("tdy_trde_cmsn")) + _to_int(row.get("tdy_trde_tax"))
        for row in realized_rows
    )
    buy_notional = buy_price * total_qty
    pnl_pct = pnl / buy_notional if buy_notional else 0.0
    return {
        "symbol": symbol,
        "qty": total_qty,
        "buy_order_no": str(entry.get("order_id") or ""),
        "sell_order_no": str(order.get("order_id") or ""),
        "buy_time": str(entry.get("ts") or ""),
        "sell_time": str(order.get("exit_ts") or ""),
        "buy_price": buy_price,
        "sell_price": sell_price,
        "fee_tax": fee_tax,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "pnl_pct_text": f"{pnl_pct * 100.0:.2f}%",
        "result_label": "profit" if pnl > 0 else "loss" if pnl < 0 else "breakeven",
        "source": "kiwoom.ka10072.carryover_aggregate",
        "match_mode": "prior_open_lifecycle_plus_sell_only_day_and_realized_rows",
        "authoritative": True,
        "exit_day": exit_day,
        "exit_ts": str(order.get("exit_ts") or ""),
        "exit_order_qty": _to_int(order.get("qty")),
        "realized_segments": realized_rows,
    }


def _patch_carryover_lifecycle(payload: Dict[str, Any], truth: Mapping[str, Any]) -> Dict[str, Any]:
    out = _patch_lifecycle_payload(payload, truth)
    exit_payload = dict(out.get("exit") or {})
    exit_payload.update(
        {
            "ts": truth.get("exit_ts"),
            "order_id": truth.get("sell_order_no"),
            "reason_human": "Next-session forced close reconciled from Kiwoom broker truth.",
            "carryover_exit": True,
            "entry_day": str(payload.get("day") or ""),
            "exit_day": truth.get("exit_day"),
            "realized_segments": list(truth.get("realized_segments") or []),
        }
    )
    out["exit"] = exit_payload
    out["remaining_qty"] = 0
    out["carryover_exit"] = {
        "entry_day": str(payload.get("day") or ""),
        "exit_day": truth.get("exit_day"),
        "final_exit_order_id": truth.get("sell_order_no"),
        "final_exit_order_qty": truth.get("exit_order_qty"),
        "source": truth.get("source"),
    }
    lifecycle = dict(out.get("lifecycle") or {})
    lifecycle["entry"] = dict(out.get("entry") or {})
    lifecycle["exit"] = dict(exit_payload)
    out["lifecycle"] = lifecycle
    out["trade_lifecycle"] = lifecycle
    return out


def _regenerate_deterministic_report(reports_root: Path, trade_dir: Path, day: str, trade_id: str) -> Dict[str, Any]:
    paths = trade_artifact_paths(reports_root, day, trade_id, prefer_existing_day_root=True)
    story_input, story_path, source, _existing_score, _rebuilt_score = resolve_story_input_for_regeneration(trade_dir, paths)
    if not story_input:
        return {"ok": False, "reason": "story_input_unavailable"}
    compact = build_ai_trade_report_compact_input(story_input)
    compact_artifact = build_compact_input_artifact(
        component="ai_trade_report",
        run_id=str(story_input.get("run_id") or ""),
        trade_id=trade_id,
        story_id=str(story_input.get("story_id") or trade_id),
        day=day,
        source_artifact_path=story_path,
        source_input=story_input,
        compact_input=compact,
    )
    write_json(paths["ai_trade_report_compact_input_json"], compact_artifact)
    report = build_deterministic_trade_report(story_input)
    report["llm_response_artifact"] = build_llm_response_artifact(
        component="ai_trade_report",
        run_id=str(story_input.get("run_id") or ""),
        trade_id=trade_id,
        story_id=str(story_input.get("story_id") or trade_id),
        day=day,
        status="fallback",
        attempts=[],
        parsed_output={},
        model_info={"provider": "OpenRouter", "model": ""},
        meta={"reason": "carryover_exit_deterministic_regeneration"},
    )
    summary_input = build_trade_summary_input(report)
    summary = build_trade_summary_report(summary_input, enabled=False)
    write_json(paths["ai_trade_report_json"], report)
    paths["ai_trade_report_md"].write_text(render_trade_report_markdown(report), encoding="utf-8-sig")
    write_json(paths["ai_trade_summary_input_json"], summary_input)
    write_json(paths["ai_trade_summary_json"], summary)
    paths["ai_trade_summary_md"].write_text(
        render_trade_summary_markdown_with_evaluation(report, summary),
        encoding="utf-8-sig",
    )
    return {"ok": True, "story_input_source": source}


def _write_exit_day_index(reports_root: Path, exit_day: str, row: Mapping[str, Any]) -> Path:
    path = reports_root / "trades" / exit_day / "carryover_exit_index.json"
    payload = _read_json(path)
    rows = list(payload.get("rows") or [])
    trade_id = str(row.get("trade_id") or "")
    rows = [item for item in rows if isinstance(item, dict) and str(item.get("trade_id") or "") != trade_id]
    rows.append(dict(row))
    write_json(
        path,
        {
            "schema_version": "carryover_exit_index.v1",
            "day": exit_day,
            "rows": rows,
        },
    )
    return path


def reconcile_carryover_exit_reports(
    *,
    reports_root: Path = Path("reports"),
    day: str,
    snapshot: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized_day = str(day or "").strip()[:10]
    snapshot_path = reports_root.parent / "data" / "logs" / "kiwoom_account_snapshots" / normalized_day / "latest.json"
    snapshot_payload = dict(snapshot or _read_json(snapshot_path))
    sell_only = _sell_only_symbols(snapshot_payload)
    orders = _current_sell_orders(snapshot_payload, normalized_day)
    patched: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for symbol in sorted(sell_only):
        order = orders.get(symbol)
        if not order:
            skipped.append({"symbol": symbol, "reason": "sell_order_not_found"})
            continue
        trade_dir, lifecycle = _find_prior_open_trade(reports_root, normalized_day, symbol)
        if trade_dir is None:
            skipped.append({"symbol": symbol, "reason": "prior_open_lifecycle_not_found"})
            continue
        trade_id = str(lifecycle.get("trade_id") or trade_dir.name)
        entry_day = str(lifecycle.get("day") or "")[:10]
        realized_rows = _realized_rows_for_symbol(
            reports_root,
            symbol=symbol,
            entry_day=entry_day,
            exit_day=normalized_day,
        )
        truth = _build_truth(
            lifecycle=lifecycle,
            symbol=symbol,
            exit_day=normalized_day,
            order=order,
            realized_rows=realized_rows,
        )
        patched_lifecycle = _patch_carryover_lifecycle(lifecycle, truth)
        write_json(trade_dir / "lifecycle_bundle.json", patched_lifecycle)
        write_json(trade_dir / "exit.json", dict(patched_lifecycle.get("exit") or {}))
        health_path = trade_dir / "_health.json"
        write_json(health_path, _patch_health_payload(_read_json(health_path), truth))

        regeneration = _regenerate_deterministic_report(
            reports_root,
            trade_dir,
            entry_day,
            trade_id,
        )
        report_path = trade_dir / "reports" / "ai_trade_report.json"
        summary_path = trade_dir / "reports" / "ai_trade_summary.json"
        if report_path.exists():
            write_json(report_path, _patch_report_payload(_read_json(report_path), truth))
        if summary_path.exists():
            write_json(summary_path, _patch_summary_payload(_read_json(summary_path), truth))
        if report_path.exists() and summary_path.exists():
            (trade_dir / "reports" / "ai_trade_summary.md").write_text(
                render_trade_summary_markdown_with_evaluation(_read_json(report_path), _read_json(summary_path)),
                encoding="utf-8-sig",
            )

        index_path = _write_exit_day_index(
            reports_root,
            normalized_day,
            {
                "trade_id": trade_id,
                "symbol": symbol,
                "date": normalized_day,
                "entry_day": entry_day,
                "exit_day": normalized_day,
                "status": "closed",
                "last_action": "SELL",
                "entry_reason": str((patched_lifecycle.get("entry") or {}).get("reason_human") or ""),
                "exit_reason": str((patched_lifecycle.get("exit") or {}).get("reason_human") or ""),
                "trade_root_path": str(trade_dir),
                "carryover_exit": True,
            },
        )
        patched.append(
            {
                "trade_id": trade_id,
                "symbol": symbol,
                "entry_day": entry_day,
                "exit_day": normalized_day,
                "pnl": truth.get("pnl"),
                "pnl_pct": truth.get("pnl_pct"),
                "index_path": str(index_path),
                "regeneration": regeneration,
            }
        )
    return {
        "ok": True,
        "day": normalized_day,
        "snapshot_path": str(snapshot_path),
        "patched_count": len(patched),
        "patched": patched,
        "skipped": skipped,
    }


__all__ = ["reconcile_carryover_exit_reports"]
