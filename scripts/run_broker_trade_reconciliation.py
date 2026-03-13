from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.catalog.api_catalog import ApiCatalog, ApiNotFoundError
from libs.core.settings import Settings
from libs.catalog.api_request_builder import PreparedRequest
from libs.execution.executors.factory import get_executor


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def _normalize_symbol(code: Any) -> str:
    s = str(code or "").strip()
    if s.startswith("A") and len(s) > 1:
        return s[1:]
    return s


def _normalize_side(v: Any) -> str:
    raw = str(v or "").strip().upper()
    if raw in {"BUY", "B", "2", "매수"}:
        return "BUY"
    if raw in {"SELL", "S", "1", "매도"}:
        return "SELL"
    if "매수" in raw:
        return "BUY"
    if "매도" in raw:
        return "SELL"
    return raw


def _to_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    raw = str(v).strip().replace(",", "").lstrip("+")
    if not raw:
        return None
    try:
        return int(float(raw))
    except Exception:
        return None


def _pick(payload: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    rows = payload.get(key)
    return rows if isinstance(rows, list) else []


def _ensure_catalog() -> Path:
    catalog_path = Path("data/specs/api_catalog.jsonl")
    if catalog_path.exists():
        return catalog_path
    import scripts.build_api_catalog as bac

    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    bac.main()
    return catalog_path


def _require_api(catalog: ApiCatalog, api_id: str, title: str) -> str:
    if catalog.has(api_id):
        return api_id
    for spec in catalog.list_specs():
        if (spec.title or "").strip() == title:
            return spec.api_id
    raise ApiNotFoundError(f"Missing API: {api_id} / {title}")


def _call(executor: Any, catalog: ApiCatalog, api_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    spec = catalog.get(api_id)
    req = PreparedRequest(
        api_id=api_id,
        method=spec.method or "POST",
        path=spec.path,
        headers={},
        query={},
        body=body,
    )
    result = executor.execute(req)
    payload = result.response.payload if result and result.response else {}
    return payload if isinstance(payload, dict) else {}


def load_local_execution_rows(event_log_path: Path, *, day: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for rec in _iter_jsonl(event_log_path):
        ts_kst = str(rec.get("ts_kst") or "")
        if not ts_kst.startswith(day):
            continue
        if rec.get("stage") != "execute_from_packet" or rec.get("event") != "execution":
            continue
        payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
        order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
        inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        inner_meta = inner.get("meta") if isinstance(inner.get("meta"), dict) else {}
        broker_ok = bool(inner.get("broker_message")) or bool(inner.get("order_id")) or bool(inner.get("json"))
        if not broker_ok:
            continue
        effective_mode = str(inner.get("effective_mode") or "")
        executor_name = str(inner_meta.get("executor") or "")
        ord_no = str(inner.get("order_id") or "")
        symbol = _normalize_symbol(order.get("symbol") or order.get("stk_cd"))
        if effective_mode == "mock_executor" or executor_name == "mock":
            continue
        if ord_no.startswith("A") and str(inner.get("broker_message") or "").strip().lower() == "accepted":
            continue
        if not ord_no or not symbol:
            continue
        rows.append(
            {
                "run_id": str(rec.get("run_id") or ""),
                "ts_kst": ts_kst,
                "ord_no": ord_no,
                "symbol": symbol,
                "side": _normalize_side(order.get("action")),
                "qty": _to_int(order.get("qty") or order.get("ord_qty")),
                "broker_message": str(inner.get("broker_message") or ""),
                "effective_mode": effective_mode,
            }
        )
    return rows


def fetch_broker_filled_rows(*, day: str) -> Dict[str, Any]:
    _ = Settings.from_env()
    catalog = ApiCatalog.load(str(_ensure_catalog()))
    executor = get_executor(catalog=catalog)
    api_id = _require_api(catalog, "kt00009", "계좌별주문체결현황요청")
    body = {
        "ord_dt": day.replace("-", ""),
        "qry_tp": "4",
        "mrkt_tp": "0",
        "stk_bond_tp": "1",
        "sell_tp": "0",
        "stk_cd": "",
        "fr_ord_no": "",
        "dmst_stex_tp": "KRX",
    }
    payload = _call(executor, catalog, api_id, body)
    rows = []
    for row in _pick(payload, "acnt_ord_cntr_prst_array"):
        rows.append(
            {
                "ord_no": str(row.get("ord_no") or "").strip(),
                "symbol": _normalize_symbol(row.get("stk_cd")),
                "side": _normalize_side(row.get("io_tp_nm") or row.get("trde_tp")),
                "order_qty": _to_int(row.get("ord_qty")),
                "filled_qty": _to_int(row.get("cntr_qty")),
                "order_price": _to_int(row.get("ord_uv")),
                "filled_price": _to_int(row.get("cntr_uv")),
                "status": str(row.get("acpt_tp") or "").strip(),
                "order_time": str(row.get("ord_tm") or "").strip(),
                "raw": row,
            }
        )
    return {"body": body, "rows": rows, "payload_keys": sorted(payload.keys())}


def reconcile_rows(local_rows: List[Dict[str, Any]], broker_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    local_by_ord = {str(row.get("ord_no") or ""): row for row in local_rows if str(row.get("ord_no") or "")}
    broker_by_ord = {str(row.get("ord_no") or ""): row for row in broker_rows if str(row.get("ord_no") or "")}
    missing_in_local = [row for ord_no, row in broker_by_ord.items() if ord_no not in local_by_ord]
    missing_in_broker = [row for ord_no, row in local_by_ord.items() if ord_no not in broker_by_ord]

    local_counts = Counter((str(r.get("symbol") or ""), str(r.get("side") or "")) for r in local_rows)
    broker_counts = Counter((str(r.get("symbol") or ""), str(r.get("side") or "")) for r in broker_rows)

    return {
        "local_total": len(local_rows),
        "broker_total": len(broker_rows),
        "matched_by_ord_no": len([k for k in local_by_ord.keys() if k in broker_by_ord]),
        "broker_window_limited": bool(local_rows and broker_rows and len(local_rows) > len(broker_rows) and len([k for k in local_by_ord.keys() if k in broker_by_ord]) == len(broker_rows)),
        "missing_in_local_total": len(missing_in_local),
        "missing_in_broker_total": len(missing_in_broker),
        "missing_in_local": missing_in_local[:20],
        "missing_in_broker": missing_in_broker[:20],
        "local_counts": {f"{sym}:{side}": cnt for (sym, side), cnt in sorted(local_counts.items())},
        "broker_counts": {f"{sym}:{side}": cnt for (sym, side), cnt in sorted(broker_counts.items())},
    }


def _render_md(report: Dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# Broker Trade Reconciliation",
        "",
        f"- Day: {report.get('day')}",
        f"- Event log: `{report.get('event_log_path')}`",
        f"- Generated at: {report.get('generated_at')}",
        "",
        "## Summary",
        "",
        f"- Local executions: {int(summary.get('local_total') or 0)}",
        f"- Broker rows: {int(summary.get('broker_total') or 0)}",
        f"- Matched by ord_no: {int(summary.get('matched_by_ord_no') or 0)}",
        f"- Broker window limited: {bool(summary.get('broker_window_limited'))}",
        f"- Missing in local: {int(summary.get('missing_in_local_total') or 0)}",
        f"- Missing in broker: {int(summary.get('missing_in_broker_total') or 0)}",
        "",
        "## Local Counts",
    ]
    local_counts = summary.get("local_counts") if isinstance(summary.get("local_counts"), dict) else {}
    if local_counts:
        lines.extend([f"- `{k}`: {v}" for k, v in local_counts.items()])
    else:
        lines.append("- none")
    lines.extend(["", "## Broker Counts"])
    broker_counts = summary.get("broker_counts") if isinstance(summary.get("broker_counts"), dict) else {}
    if broker_counts:
        lines.extend([f"- `{k}`: {v}" for k, v in broker_counts.items()])
    else:
        lines.append("- none")
    for title, key in (("Missing In Local", "missing_in_local"), ("Missing In Broker", "missing_in_broker")):
        lines.extend(["", f"## {title}"])
        rows = summary.get(key) if isinstance(summary.get(key), list) else []
        if not rows:
            lines.append("- none")
            continue
        for row in rows:
            lines.append(
                f"- ord_no={row.get('ord_no')} symbol={row.get('symbol')} side={row.get('side')} "
                f"qty={row.get('filled_qty') or row.get('qty') or row.get('order_qty')}"
            )
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Compare Kiwoom mock broker fill history with local execution events.")
    p.add_argument("--day", default=datetime.now(UTC).astimezone().date().isoformat())
    p.add_argument("--event-log-path", default="data/logs/events.jsonl")
    p.add_argument("--report-dir", default="reports/reconciliation")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    day = str(args.day).strip()
    event_log_path = Path(str(args.event_log_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    report_dir.mkdir(parents=True, exist_ok=True)

    local_rows = load_local_execution_rows(event_log_path, day=day)
    broker_result = fetch_broker_filled_rows(day=day)
    broker_rows = list(broker_result.get("rows") or [])
    summary = reconcile_rows(local_rows, broker_rows)
    report = {
        "day": day,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "event_log_path": str(event_log_path),
        "broker_query": broker_result.get("body"),
        "broker_payload_keys": broker_result.get("payload_keys"),
        "summary": summary,
    }

    json_path = report_dir / f"broker_trade_reconciliation_{day}.json"
    md_path = report_dir / f"broker_trade_reconciliation_{day}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(
            f"day={day} matched={summary['matched_by_ord_no']} "
            f"missing_local={summary['missing_in_local_total']} "
            f"missing_broker={summary['missing_in_broker_total']} "
            f"report_json={json_path} report_md={md_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
