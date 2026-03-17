from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import re

from libs.llm.llm_router import LLMRouter
from libs.core.symbols import normalize_symbol


KST = timezone(timedelta(hours=9), name="KST")


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _to_epoch(ts: Any) -> Optional[int]:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return int(ts)
    raw = str(ts).strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except Exception:
        pass
    s = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def _to_datetime(ts: Any) -> Optional[datetime]:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        dt = ts
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(KST)
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(KST)
        except Exception:
            return None
    raw = str(ts).strip()
    if not raw:
        return None
    s = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(KST)
    except Exception:
        return None


def _iso_to_display(ts: Any) -> str:
    dt = _to_datetime(ts)
    if dt is None:
        return str(ts or "")
    return dt.strftime("%Y-%m-%d %H:%M:%S KST")


def _event_day(ts: Any) -> str:
    dt = _to_datetime(ts)
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d")


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _latest_matching(path: Path, prefix: str) -> Dict[str, Any]:
    if not path.exists():
        return {}
    files = sorted(path.glob(f"{prefix}_*.json"))
    if not files:
        return {}
    return _read_json(files[-1])


def _read_day_or_latest(path: Path, prefix: str, day: str) -> Dict[str, Any]:
    if path.exists() and day:
        exact = path / f"{prefix}_{day}.json"
        if exact.exists():
            return _read_json(exact)
    return _latest_matching(path, prefix)


def _latest_matching_path(path: Path, prefix: str) -> str:
    if not path.exists():
        return ""
    files = sorted(path.glob(f"{prefix}_*.json"))
    if not files:
        return ""
    return str(files[-1])


def _day_or_latest_path(path: Path, prefix: str, day: str) -> str:
    if path.exists() and day:
        exact = path / f"{prefix}_{day}.json"
        if exact.exists():
            return str(exact)
    return _latest_matching_path(path, prefix)


def _latest_event_day(event_log_path: Path) -> str:
    latest_day = ""
    latest_epoch = -1
    for row in _iter_jsonl(event_log_path):
        ts = row.get("ts_kst") or row.get("ts")
        epoch = _to_epoch(ts)
        if epoch is None or epoch < latest_epoch:
            continue
        latest_epoch = epoch
        latest_day = _event_day(ts)
    return latest_day


def _feature_coverage(feature_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(feature_snapshot, dict) or not feature_snapshot:
        return {"present": 0, "total": 0, "coverage_ratio": 0.0, "quality": "missing", "present_keys": [], "missing_keys": []}
    key_fields = [
        "engine_ma20_gap",
        "engine_ma60",
        "engine_ma120",
        "engine_adx14",
        "engine_trend_strength",
        "engine_volume_spike20",
        "engine_volatility20",
        "engine_vwap_distance",
        "engine_sector_relative_strength",
        "engine_cross_section_rank",
        "engine_regime",
        "engine_signal_score",
    ]
    present: List[str] = []
    missing: List[str] = []
    for key in key_fields:
        value = feature_snapshot.get(key)
        if value is None:
            missing.append(key)
        else:
            present.append(key)
    total = len(key_fields)
    present_total = len(present)
    ratio = float(present_total) / float(total) if total else 0.0
    if ratio >= 0.75:
        quality = "strong"
    elif ratio >= 0.35:
        quality = "partial"
    else:
        quality = "missing"
    return {
        "present": present_total,
        "total": total,
        "coverage_ratio": ratio,
        "quality": quality,
        "present_keys": present,
        "missing_keys": missing,
    }


def _quote_metrics_snapshot(feature_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(feature_snapshot, dict) or not feature_snapshot:
        return {
            "present": False,
            "skill_quote_price": None,
            "quote_volume": None,
            "quote_trading_value": None,
            "intraday_change_pct": None,
        }
    price = feature_snapshot.get("skill_quote_price")
    volume = feature_snapshot.get("quote_volume")
    trading_value = feature_snapshot.get("quote_trading_value")
    change_pct = feature_snapshot.get("intraday_change_pct")
    return {
        "present": any(v is not None and v != 0 for v in (price, volume, trading_value, change_pct)),
        "skill_quote_price": price,
        "quote_volume": volume,
        "quote_trading_value": trading_value,
        "intraday_change_pct": change_pct,
    }


def _truncate_json(v: Any, max_len: int = 800) -> str:
    try:
        s = json.dumps(v, ensure_ascii=False, indent=2)
    except Exception:
        s = str(v)
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _clean_brief_text(v: Any) -> str:
    s = str(v or "").strip()
    if not s:
        return ""
    s = re.sub(r"^\s*From\s+[A-Za-z0-9_]+\s*-\s*", "", s)
    s = re.sub(r"^\s*[A-Za-z0-9_]+_hint\s*-\s*", "", s)
    s = re.sub(r"\s+", " ", s).strip(" -")
    return s


def _clean_brief_list(v: Any, *, limit: int) -> List[str]:
    if not isinstance(v, list):
        return []
    out: List[str] = []
    for item in v:
        cleaned = _clean_brief_text(item)
        if cleaned:
            out.append(cleaned)
        if len(out) >= limit:
            break
    return out


def _extract_json_object(text: Any) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    if raw.startswith("```"):
        lines = raw.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(raw):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(raw[idx:])
            return obj if isinstance(obj, dict) else {}
        except Exception:
            continue
    return {}


def _salvage_operator_brief_fields(text: Any) -> Dict[str, Any]:
    raw = str(text or "")
    if not raw.strip():
        return {}
    fields = [
        "headline",
        "commander_summary",
        "strategist_summary",
        "scanner_summary",
        "monitor_summary",
        "supervisor_summary",
        "executor_summary",
        "reporter_summary",
    ]
    out: Dict[str, Any] = {}
    for key in fields:
        pattern = rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"'
        match = re.search(pattern, raw, flags=re.DOTALL)
        if not match:
            continue
        try:
            out[key] = json.loads('"' + match.group(1) + '"')
        except Exception:
            out[key] = match.group(1).replace('\\"', '"')
    takeaways_match = re.search(r'"operator_takeaways"\s*:\s*\[(.*)', raw, flags=re.DOTALL)
    if takeaways_match:
        items = re.findall(r'"((?:[^"\\]|\\.)*)"', takeaways_match.group(1), flags=re.DOTALL)
        cleaned: List[str] = []
        for item in items[:5]:
            try:
                cleaned.append(json.loads('"' + item + '"'))
            except Exception:
                cleaned.append(item.replace('\\"', '"'))
        if cleaned:
            out["operator_takeaways"] = cleaned
    return out


def _is_free_model(model: str) -> bool:
    raw = str(model or "").strip().lower()
    return ":free" in raw or raw.endswith("/free")


def _normalize_role_model_name(model: str) -> str:
    raw = str(model or "").strip()
    lowered = raw.lower()
    if lowered == "auto":
        return "openrouter/auto"
    if lowered == "free":
        return "openrouter/free"
    return raw


def _parse_operator_brief_lines(text: Any) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    keys = [
        "headline",
        "commander_summary",
        "strategist_summary",
        "scanner_summary",
        "monitor_summary",
        "supervisor_summary",
        "executor_summary",
        "reporter_summary",
        "operator_takeaways",
    ]
    out: Dict[str, Any] = {}
    for key in keys:
        pattern = rf"{key}\s*:\s*(.+)"
        matches = re.findall(pattern, raw, flags=re.IGNORECASE)
        if not matches:
            continue
        if key == "operator_takeaways":
            for candidate in reversed(matches):
                items = [item.strip(" -*") for item in str(candidate).split("|") if item.strip(" -*")]
                if not items:
                    continue
                if all(item.lower().startswith("item") for item in items):
                    continue
                out[key] = items[:5]
                break
            continue
        for candidate in reversed(matches):
            cleaned = str(candidate).strip().strip('"')
            if not cleaned:
                continue
            if cleaned in {"...", "?"}:
                continue
            out[key] = cleaned
            break
    return out


def _read_exact_day(path: Path, prefix: str, day: str) -> Dict[str, Any]:
    if not path.exists() or not day:
        return {}
    exact = path / f"{prefix}_{day}.json"
    return _read_json(exact)


def _normalize_execution_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "action": "",
            "symbol": "",
            "qty": 0,
            "status": "",
            "ord_no": "",
        }
    order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
    broker = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    response_payload = broker.get("response_payload") if isinstance(broker.get("response_payload"), dict) else {}
    return {
        "action": str(payload.get("action") or order.get("action") or "").upper(),
        "symbol": str(payload.get("symbol") or order.get("symbol") or order.get("stk_cd") or "").strip(),
        "qty": _safe_int(payload.get("qty"), _safe_int(order.get("qty"), _safe_int(order.get("ord_qty"), 0))),
        "status": str(payload.get("fill_status_summary") or payload.get("status") or broker.get("broker_message") or response_payload.get("return_msg") or ""),
        "ord_no": str(payload.get("ord_no") or broker.get("order_id") or response_payload.get("ord_no") or ""),
    }


def _trim_text(value: Any, *, max_len: int = 220) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def _clean_str_list(values: Any, *, limit: int = 8, max_len: int = 220) -> List[str]:
    if not isinstance(values, list):
        return []
    out: List[str] = []
    for row in values:
        text = _trim_text(row, max_len=max_len)
        if text:
            out.append(text)
        if len(out) >= max(1, int(limit)):
            break
    return out


def _story_type_label(story_type: Any) -> str:
    raw = str(story_type or "").strip().lower()
    mapping = {
        "live_trade": "Live trade report",
        "simulation": "Simulation trade report",
        "failed_execution": "Failed execution report",
        "decision_only": "Decision-only summary",
    }
    return mapping.get(raw, "Unknown report type")


def _story_type_badge_class(story_type: Any) -> str:
    raw = str(story_type or "").strip().lower()
    if raw == "live_trade":
        return "status-badge status-badge--ok"
    if raw == "failed_execution":
        return "status-badge status-badge--critical"
    if raw == "simulation":
        return "status-badge status-badge--warn"
    if raw == "decision_only":
        return "status-badge status-badge--warn"
    return "status-badge"


def _normalize_report_status(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"available", "skipped", "pending", "failed"}:
        return raw
    return ""


def _report_status_label(status: Any) -> str:
    raw = _normalize_report_status(status)
    if raw == "available":
        return "AI Report Available"
    if raw == "pending":
        return "AI Report Pending"
    if raw == "failed":
        return "AI Report Failed"
    if raw == "skipped":
        return "AI Report Skipped"
    return "AI Report"


def _report_status_badge_class(status: Any) -> str:
    raw = _normalize_report_status(status)
    if raw == "available":
        return "status-badge status-badge--ok"
    if raw in {"pending", "skipped"}:
        return "status-badge status-badge--warn"
    if raw == "failed":
        return "status-badge status-badge--critical"
    return "status-badge"


def _report_reason_human(code: Any) -> str:
    raw = str(code or "").strip().lower()
    mapping = {
        "no_executed_lifecycle": "No executed trade lifecycle was created for this run.",
        "decision_only_run": "This run was decision-only, so a full AI trade report was not generated.",
        "hold_only_run": "This run only updated hold/monitor state, so a full AI trade report was not generated.",
        "execution_failed": "Execution did not complete successfully, so a full AI trade report was skipped.",
        "missing_story_input": "Trade story input was not created, so report generation could not continue.",
        "llm_generation_failed": "Trade story input existed, but AI report generation failed.",
        "artifact_write_failed": "AI report generation ran, but writing report artifacts failed.",
        "missing_report_linkage": "A linked AI trade report could not be found for this run.",
        "report_not_requested": "AI trade report generation was not requested for this run.",
        "still_open_lifecycle": "This trade lifecycle is still open, so the full AI report is pending.",
        "awaiting_exit_for_full_report": "This trade is still open. The full AI report is generated after exit/closure.",
    }
    return mapping.get(raw, "AI trade report status is not fully classified yet.")


def _report_next_step(code: Any) -> str:
    raw = str(code or "").strip().lower()
    mapping = {
        "no_executed_lifecycle": "Keep using the Operator Brief. A full report is generated only for executed trade lifecycles.",
        "decision_only_run": "Continue with the Operator Brief. Generate AI reports only after executed lifecycle events.",
        "hold_only_run": "Continue monitoring. Generate the full AI report after an executed entry/exit lifecycle is formed.",
        "execution_failed": "Review execution failure details and rerun after execution stabilizes.",
        "missing_story_input": "Inspect story input generation first, then retry report generation.",
        "llm_generation_failed": "Check OpenRouter/model connectivity and retry report generation.",
        "artifact_write_failed": "Check filesystem write path and permissions, then retry.",
        "missing_report_linkage": "Regenerate lifecycle/report linkage for this run and retry.",
        "report_not_requested": "Enable AI trade report generation policy, then rerun.",
        "still_open_lifecycle": "Generate the full AI report after lifecycle exit/closure.",
        "awaiting_exit_for_full_report": "Generate the final AI report after exit/closure.",
    }
    return mapping.get(raw, "Review diagnostics and proceed with the Operator Brief in the meantime.")


def _portfolio_sync_badge_class(status: Any) -> str:
    raw = str(status or "").strip().lower()
    if raw in {"aligned", "reconciled"}:
        return "status-badge status-badge--ok"
    if raw == "unavailable":
        return "status-badge"
    return "status-badge status-badge--critical"


def _portfolio_sync_label(status: Any) -> str:
    raw = str(status or "").strip().lower()
    mapping = {
        "aligned": "Portfolio Sync OK",
        "reconciled": "Portfolio Reconciled",
        "mismatch": "Portfolio Mismatch",
        "reader_error": "Portfolio Reader Error",
        "unavailable": "Sync status unavailable",
    }
    return mapping.get(raw, "Portfolio Sync")


def _portfolio_sync_sentence(status: Any) -> str:
    raw = str(status or "").strip().lower()
    mapping = {
        "aligned": "계좌 보유 종목과 로컬 상태가 일치했습니다.",
        "reconciled": "계좌 보유 종목을 기준으로 로컬 상태를 자동 정합화했습니다.",
        "mismatch": "계좌 보유 종목과 로컬 상태 불일치가 남아 있습니다. 신규 BUY는 차단됩니다.",
        "reader_error": "계좌 조회에 실패했습니다. 신규 BUY는 차단됩니다.",
        "unavailable": "이 run에는 계좌 동기화 상태가 기록되지 않았습니다.",
    }
    return mapping.get(raw, "계좌 동기화 상태를 확인하세요.")


def _portfolio_positions_source_label(value: Any) -> str:
    raw = str(value or "").strip().lower()
    mapping = {
        "reader_positions_authoritative": "Reader positions",
        "reader_positions_authoritative_empty": "Reader says no positions",
        "reader_positions": "Reader positions",
        "persisted_mock_positions": "Local fallback positions",
        "reader_positions_empty": "No positions",
    }
    return mapping.get(raw, raw.replace("_", " ") if raw else "")


def _portfolio_reconciliation_label(value: Any) -> str:
    raw = str(value or "").strip().lower()
    mapping = {
        "aligned": "Already aligned",
        "reader_aligned": "Already aligned",
        "reconciled_to_reader": "Reconciled to account reader",
        "persisted_fallback": "Using local fallback",
        "empty": "No active positions",
    }
    return mapping.get(raw, raw.replace("_", " ") if raw else "")


def _build_portfolio_sync_card(raw: Any) -> Dict[str, Any]:
    guard = raw if isinstance(raw, dict) else {}
    if not guard:
        status = "unavailable"
        return {
            "available": False,
            "status": status,
            "status_label": _portfolio_sync_label(status),
            "badge_class": _portfolio_sync_badge_class(status),
            "sentence": _portfolio_sync_sentence(status),
            "note": "",
            "positions_source": "",
            "positions_source_label": "",
            "reconciliation_status": "",
            "reconciliation_label": "",
            "reader_ok": None,
            "reader_error": "",
            "reader_positions_authoritative": False,
            "positions_mismatch_detected": False,
            "reconciliation_applied": False,
            "reader_positions_count": 0,
            "persisted_positions_count": 0,
        }

    reader_ok = bool(guard.get("reader_ok"))
    mismatch = bool(guard.get("positions_mismatch_detected"))
    reconciled = bool(guard.get("reconciliation_applied"))
    if not reader_ok:
        status = "reader_error"
    elif mismatch and reconciled:
        status = "reconciled"
    elif mismatch:
        status = "mismatch"
    else:
        status = "aligned"

    positions_source = str(guard.get("positions_source") or "")
    reconciliation_status = str(guard.get("reconciliation_status") or "")
    counts_note = (
        f"Reader { _safe_int(guard.get('reader_positions_count'), 0) } / local { _safe_int(guard.get('persisted_positions_count'), 0) }"
    )
    note_bits = [bit for bit in [
        _portfolio_positions_source_label(positions_source),
        _portfolio_reconciliation_label(reconciliation_status),
        counts_note,
    ] if bit]

    return {
        "available": True,
        "status": status,
        "status_label": _portfolio_sync_label(status),
        "badge_class": _portfolio_sync_badge_class(status),
        "sentence": _portfolio_sync_sentence(status),
        "note": " | ".join(note_bits),
        "positions_source": positions_source,
        "positions_source_label": _portfolio_positions_source_label(positions_source),
        "reconciliation_status": reconciliation_status,
        "reconciliation_label": _portfolio_reconciliation_label(reconciliation_status),
        "reader_ok": reader_ok,
        "reader_error": str(guard.get("reader_error") or ""),
        "reader_positions_authoritative": bool(guard.get("reader_positions_authoritative")),
        "positions_mismatch_detected": mismatch,
        "reconciliation_applied": reconciled,
        "reader_positions_count": _safe_int(guard.get("reader_positions_count"), 0),
        "persisted_positions_count": _safe_int(guard.get("persisted_positions_count"), 0),
    }


def _extract_portfolio_guard_payload_from_run_rows(run_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(run_rows, list) or not run_rows:
        return {}
    execution_payload = next(
        (
            r.get("payload")
            for r in reversed(run_rows)
            if str(r.get("stage") or "") == "execute_from_packet"
            and str(r.get("event") or "") == "execution"
            and isinstance(r.get("payload"), dict)
        ),
        {},
    )
    if isinstance(execution_payload, dict) and isinstance(execution_payload.get("portfolio_guard"), dict):
        return dict(execution_payload.get("portfolio_guard") or {})

    verdict_payload = next(
        (
            r.get("payload")
            for r in reversed(run_rows)
            if str(r.get("stage") or "") == "execute_from_packet"
            and str(r.get("event") or "") == "verdict"
            and isinstance(r.get("payload"), dict)
        ),
        {},
    )
    if isinstance(verdict_payload, dict) and isinstance(verdict_payload.get("portfolio_guard"), dict):
        return dict(verdict_payload.get("portfolio_guard") or {})

    portfolio_guard_block_payload = next(
        (
            r.get("payload")
            for r in reversed(run_rows)
            if str(r.get("stage") or "") == "execute_from_packet"
            and str(r.get("event") or "") == "portfolio_guard_block"
            and isinstance(r.get("payload"), dict)
        ),
        {},
    )
    if isinstance(portfolio_guard_block_payload, dict):
        if isinstance(portfolio_guard_block_payload.get("portfolio_guard"), dict):
            return dict(portfolio_guard_block_payload.get("portfolio_guard") or {})
        return dict(portfolio_guard_block_payload)
    return {}


def _normalize_ai_report_diagnostics(
    raw: Any,
    *,
    report_exists: bool,
    lifecycle_status: Any,
    story_type: Any,
    model_hint: Any = "",
    generation: Any = None,
) -> Dict[str, Any]:
    diag = raw if isinstance(raw, dict) else {}
    generation_obj = generation if isinstance(generation, dict) else {}
    lifecycle = str(lifecycle_status or "").strip().lower()
    story = str(story_type or "").strip().lower()

    status = _normalize_report_status(diag.get("report_status"))
    reason_code = str(diag.get("report_reason_code") or "").strip().lower()

    if not status:
        if report_exists:
            status = "available"
            reason_code = reason_code or ""
        elif lifecycle == "open":
            status = "pending"
            reason_code = reason_code or "awaiting_exit_for_full_report"
        elif story == "decision_only":
            status = "skipped"
            reason_code = reason_code or "decision_only_run"
        elif story == "failed_execution":
            status = "skipped"
            reason_code = reason_code or "execution_failed"
        else:
            status = "failed"
            reason_code = reason_code or "missing_report_linkage"

    if status == "available" and not report_exists:
        status = "failed"
        reason_code = "missing_report_linkage"

    reason_human = _trim_text(diag.get("report_reason_human"), max_len=320)
    if not reason_human:
        reason_human = _report_reason_human(reason_code)

    next_step = _trim_text(diag.get("next_expected_step"), max_len=320)
    if not next_step:
        next_step = _report_next_step(reason_code)

    model_used = (
        _trim_text(diag.get("llm_model_used"), max_len=120)
        or _trim_text(diag.get("llm_model"), max_len=120)
        or _trim_text(generation_obj.get("model"), max_len=120)
        or _trim_text(model_hint, max_len=120)
        or "not_captured"
    )
    provider = _trim_text(diag.get("llm_provider"), max_len=64) or "OpenRouter"

    generation_attempted = bool(diag.get("generation_attempted"))
    if not generation_attempted and str(generation_obj.get("status") or "").strip():
        generation_attempted = True
    generation_ts = _trim_text(diag.get("generation_ts"), max_len=64)
    last_error_message = _trim_text(diag.get("last_error_message"), max_len=260)
    if not last_error_message and status == "failed":
        last_error_message = _trim_text(generation_obj.get("reason"), max_len=260)

    story_input_available = bool(diag.get("story_input_available")) if "story_input_available" in diag else True
    report_output_available = (
        bool(diag.get("report_output_available"))
        if "report_output_available" in diag
        else bool(diag.get("report_artifact_available"))
        if "report_artifact_available" in diag
        else report_exists
    )

    return {
        "report_status": status,
        "report_status_label": _report_status_label(status),
        "report_status_badge_class": _report_status_badge_class(status),
        "report_reason_code": reason_code,
        "report_reason_human": reason_human,
        "generation_attempted": generation_attempted,
        "generation_ts": generation_ts,
        "story_input_available": story_input_available,
        "report_output_available": report_output_available,
        "report_artifact_available": report_output_available,
        "llm_provider": provider,
        "llm_model_used": model_used,
        "expected_generation_mode": _trim_text(diag.get("expected_generation_mode"), max_len=120) or "per-trade free model report",
        "next_expected_step": next_step,
        "last_error_message": last_error_message,
    }


def _short_run_id(run_id: Any) -> str:
    text = str(run_id or "").strip()
    if len(text) <= 12:
        return text
    return text[:8] + "..."


def _trade_report_index(config: OperatorUIConfig) -> Dict[str, Dict[str, Any]]:
    root = config.reports_root / "trades"
    if not root.exists():
        return {"by_run_id": {}, "by_story_id": {}}

    by_run_id: Dict[str, Dict[str, Any]] = {}
    by_story_id: Dict[str, Dict[str, Any]] = {}
    for bundle_path in sorted(root.glob("*/*/*/aggregated_execution_bundle.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        bundle = _read_json(bundle_path)
        if not bundle:
            continue

        lifecycle_path = bundle_path.parent / "trade_lifecycle.json"
        lifecycle = _read_json(lifecycle_path) if lifecycle_path.exists() else {}
        trade_id = str(
            lifecycle.get("trade_id")
            or bundle.get("trade_id")
            or bundle.get("story_id")
            or bundle_path.parent.name
        ).strip()
        story_id = trade_id
        run_id = str(bundle.get("run_id") or "").strip()
        linked_run_ids: List[str] = []
        for rid in list(bundle.get("linked_run_ids") or []):
            text = str(rid or "").strip()
            if text:
                linked_run_ids.append(text)
        if isinstance(lifecycle, dict):
            for rid in list(lifecycle.get("run_ids_all") or []):
                text = str(rid or "").strip()
                if text and text not in linked_run_ids:
                    linked_run_ids.append(text)
            entry = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
            exit_ctx = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
            for rid in (entry.get("run_id"), exit_ctx.get("run_id")):
                text = str(rid or "").strip()
                if text and text not in linked_run_ids:
                    linked_run_ids.append(text)
        if run_id and run_id not in linked_run_ids:
            linked_run_ids.append(run_id)

        execution = bundle.get("execution") if isinstance(bundle.get("execution"), dict) else {}
        story_contract = bundle.get("story_contract") if isinstance(bundle.get("story_contract"), dict) else {}
        reporter_status_human = bundle.get("reporter_status_human") if isinstance(bundle.get("reporter_status_human"), dict) else {}
        operator_conclusion_human = bundle.get("operator_conclusion_human") if isinstance(bundle.get("operator_conclusion_human"), dict) else {}
        execution_outcome_human = bundle.get("execution_outcome_human") if isinstance(bundle.get("execution_outcome_human"), dict) else {}

        report_json_path = bundle_path.parent / "trade_report.json"
        report_md_path = bundle_path.parent / "trade_report.md"
        story_input_path = bundle_path.parent / "trade_story_input.json"
        report = _read_json(report_json_path)
        executive = report.get("executive_summary") if isinstance(report.get("executive_summary"), dict) else {}
        reporter_eval = report.get("reporter_evaluation") if isinstance(report.get("reporter_evaluation"), dict) else {}
        final_conclusion = report.get("final_operator_conclusion") if isinstance(report.get("final_operator_conclusion"), dict) else {}
        generation = report.get("generation") if isinstance(report.get("generation"), dict) else {}
        lifecycle_summary_obj = lifecycle.get("summary") if isinstance(lifecycle.get("summary"), dict) else {}
        lifecycle_status = str(lifecycle.get("status") or bundle.get("trade_lifecycle_status") or report.get("status") or "").strip().lower()
        lifecycle_summary = (
            _trim_text(lifecycle_summary_obj.get("lifecycle_summary_human"), max_len=260)
            or _trim_text(bundle.get("trade_lifecycle_summary"), max_len=260)
            or _trim_text(final_conclusion.get("summary"), max_len=260)
        )

        story_type = str(story_contract.get("story_type") or lifecycle.get("story_type") or report.get("story_type") or "").strip().lower()
        execution_mode_label = str(story_contract.get("execution_mode_label") or lifecycle.get("execution_mode_label") or report.get("execution_mode_label") or "").strip()
        report_summary = (
            _trim_text(executive.get("summary"), max_len=260)
            or _trim_text(final_conclusion.get("summary"), max_len=260)
            or _trim_text(operator_conclusion_human.get("summary"), max_len=260)
            or _trim_text(execution_outcome_human.get("summary"), max_len=260)
        )
        reporter_summary = (
            _trim_text(reporter_eval.get("summary"), max_len=220)
            or _trim_text(reporter_status_human.get("summary"), max_len=220)
            or "Reporter linkage summary is not available yet."
        )

        ts_epoch = _to_epoch(bundle.get("ts"))
        if ts_epoch is None:
            ts_epoch = int(bundle_path.stat().st_mtime)
        symbol = normalize_symbol(
            execution.get("symbol") or report.get("symbol") or "",
            allow_test_symbols=True,
        )
        action = str(execution.get("action") or report.get("action") or "").upper()
        report_exists = bool(report_json_path.exists() or report_md_path.exists())
        raw_diagnostics = (
            report.get("ai_report_diagnostics")
            if isinstance(report.get("ai_report_diagnostics"), dict)
            else bundle.get("ai_report_diagnostics")
            if isinstance(bundle.get("ai_report_diagnostics"), dict)
            else lifecycle.get("ai_report_diagnostics")
            if isinstance(lifecycle.get("ai_report_diagnostics"), dict)
            else {}
        )
        diagnostics = _normalize_ai_report_diagnostics(
            raw_diagnostics,
            report_exists=report_exists,
            lifecycle_status=lifecycle_status,
            story_type=story_type,
            model_hint=generation.get("model"),
            generation=generation,
        )
        report_available = bool(diagnostics.get("report_status") == "available" and report_exists)
        record = {
            "trade_id": trade_id,
            "story_id": story_id,
            "run_id": run_id,
            "run_id_short": _short_run_id(run_id),
            "linked_run_ids": linked_run_ids,
            "symbol": symbol,
            "action": action,
            "story_type": story_type,
            "story_type_label": _story_type_label(story_type),
            "story_type_badge_class": _story_type_badge_class(story_type),
            "lifecycle_status": lifecycle_status or "unknown",
            "lifecycle_status_label": (lifecycle_status or "unknown").upper(),
            "lifecycle_summary": lifecycle_summary or "Lifecycle summary is not available yet.",
            "execution_mode_label": execution_mode_label or "not captured",
            "report_available": report_available,
            "report_status": str(diagnostics.get("report_status") or ""),
            "report_status_label": str(diagnostics.get("report_status_label") or _report_status_label("")),
            "report_status_badge_class": str(diagnostics.get("report_status_badge_class") or "status-badge"),
            "report_reason_code": str(diagnostics.get("report_reason_code") or ""),
            "report_reason_human": str(diagnostics.get("report_reason_human") or ""),
            "report_next_expected_step": str(diagnostics.get("next_expected_step") or ""),
            "report_generation_attempted": bool(diagnostics.get("generation_attempted")),
            "report_generation_ts": str(diagnostics.get("generation_ts") or ""),
            "report_generation_model": str(diagnostics.get("llm_model_used") or ""),
            "report_generation_provider": str(diagnostics.get("llm_provider") or "OpenRouter"),
            "ai_report_diagnostics": diagnostics,
            "report_summary": report_summary or "Per-trade report summary was not generated yet.",
            "reporter_status_human": reporter_summary,
            "report_link": f"/reports/trade/{trade_id}" if report_available and trade_id and report_exists else "",
            "trade_report_json_path": str(report_json_path) if report_json_path.exists() else "",
            "trade_report_md_path": str(report_md_path) if report_md_path.exists() else "",
            "trade_story_input_path": str(story_input_path) if story_input_path.exists() else "",
            "trade_lifecycle_json_path": str(lifecycle_path) if lifecycle_path.exists() else "",
            "aggregated_bundle_path": str(bundle_path),
            "ts_epoch": ts_epoch,
        }

        if story_id:
            by_story_id[story_id] = record
        for rid in linked_run_ids:
            current = by_run_id.get(rid)
            if (not current) or int(record.get("ts_epoch") or 0) >= int(current.get("ts_epoch") or 0):
                by_run_id[rid] = record

    return {"by_run_id": by_run_id, "by_story_id": by_story_id}


def _trade_report_meta_for_run(config: OperatorUIConfig, run_id: str) -> Dict[str, Any]:
    index = _trade_report_index(config)
    return dict((index.get("by_run_id") or {}).get(str(run_id or "").strip()) or {})


def _trade_report_meta_for_story(config: OperatorUIConfig, story_id: str) -> Dict[str, Any]:
    index = _trade_report_index(config)
    return dict((index.get("by_story_id") or {}).get(str(story_id or "").strip()) or {})


@dataclass(frozen=True)
class OperatorUIConfig:
    repo_root: Path
    reports_root: Path
    event_log_path: Path
    evidence_log_path: Path
    strategy_memory_path: Path
    operator_ui_cache_path: Path

    @staticmethod
    def from_env(repo_root: Optional[Path] = None) -> "OperatorUIConfig":
        root = Path(repo_root or Path(__file__).resolve().parents[2])
        return OperatorUIConfig(
            repo_root=root,
            reports_root=Path(os.getenv("OPERATOR_UI_REPORTS_ROOT", str(root / "reports"))),
            event_log_path=Path(os.getenv("OPERATOR_UI_EVENT_LOG_PATH", str(root / "data" / "logs" / "events.jsonl"))),
            evidence_log_path=Path(os.getenv("OPERATOR_UI_EVIDENCE_LOG_PATH", str(root / "data" / "evidence_ledger" / "events.jsonl"))),
            strategy_memory_path=Path(os.getenv("OPERATOR_UI_STRATEGY_MEMORY_PATH", str(root / "data" / "strategy_memory" / "daily"))),
            operator_ui_cache_path=Path(os.getenv("OPERATOR_UI_CACHE_PATH", str(root / "data" / "operator_ui" / "brief_cache"))),
        )


def load_overview(config: OperatorUIConfig) -> Dict[str, Any]:
    latest_day = _latest_event_day(config.event_log_path)
    daily = _read_exact_day(config.reports_root / "daily", "daily", latest_day)
    operator_summary = _read_exact_day(config.reports_root / "operator_summary", "operator_summary", latest_day)
    reporter = _read_exact_day(config.reports_root / "dev" / "analysis" / "reporter_analysis", "reporter_analysis", latest_day)
    reconciliation = _read_exact_day(config.reports_root / "reconciliation", "broker_trade_reconciliation", latest_day)

    executive = operator_summary.get("executive_summary") if isinstance(operator_summary.get("executive_summary"), dict) else {}
    health = operator_summary.get("system_health_status") if isinstance(operator_summary.get("system_health_status"), dict) else {}
    trading = operator_summary.get("trading_activity_summary") if isinstance(operator_summary.get("trading_activity_summary"), dict) else {}
    recon_summary = reconciliation.get("summary") if isinstance(reconciliation.get("summary"), dict) else {}
    strategy_memory_timeline = load_strategy_memory_timeline(config, limit=7)
    latest_day = str(latest_day or "")
    all_today_trades = load_recent_trades_for_day(config, latest_day, limit=200)
    today_trades = all_today_trades[:8]
    traded_symbol_summary = summarize_trades_by_symbol(all_today_trades)
    overtrading_warning = build_overtrading_warning(all_today_trades, traded_symbol_summary, reporter)
    latest_prompt = load_latest_strategist_prompt_summary(config, latest_day)
    today_rows = list(_iter_jsonl(config.event_log_path))
    today_rows = [row for row in today_rows if not latest_day or _event_day(row.get("ts_kst") or row.get("ts")) == latest_day]
    live_route_rows = [
        row
        for row in today_rows
        if str(row.get("stage") or "") == "commander_router"
        and str(row.get("event") or "") == "route"
    ]
    live_verdict_rows = [
        row
        for row in today_rows
        if str(row.get("stage") or "") == "execute_from_packet"
        and str(row.get("event") or "") == "verdict"
        and isinstance(row.get("payload"), dict)
    ]
    live_blocked_total = sum(1 for row in live_verdict_rows if not bool((row.get("payload") or {}).get("allowed")))
    live_run_total = len(live_route_rows)
    live_execution_total = len(all_today_trades)

    if not operator_summary and latest_day:
        operator_summary_live_lines: List[str] = []
        if live_run_total:
            operator_summary_live_lines.append(f"live event log fallback active for {latest_day}")
        if live_execution_total:
            operator_summary_live_lines.append(f"today executions observed in log: {live_execution_total}")
        if live_blocked_total:
            operator_summary_live_lines.append(f"today blocked verdicts observed in log: {live_blocked_total}")
        live_status = "LIVE" if (live_run_total or live_execution_total or live_blocked_total) else "UNKNOWN"
        executive = {
            "system_status": live_status,
            "summary_lines": operator_summary_live_lines[:4],
        }
        health = {
            "system_health_level": live_status,
            "recommended_action": (
                [f"review same-day overtrading warning: {overtrading_warning.get('level')}"]
                if str(overtrading_warning.get("level") or "normal") in {"elevated", "high"}
                else ["generate operator summary after closeout to replace live fallback"]
            )[:4],
        }
        trading = {
            "run_total": live_run_total,
            "executions_total": live_execution_total,
            "blocked_total": live_blocked_total,
        }

    if not reporter and latest_day:
        reporter = {
            "ai_review": {"status": "not_generated_yet"},
            "ai_run_grade": "-",
            "ai_summary": "Same-day reporter analysis has not been generated yet.",
            "trade_summary": {
                "trade_count": live_execution_total,
                "symbols_traded": [str(row.get("symbol") or "") for row in traded_symbol_summary[:8]],
            },
        }
    ai_review = reporter.get("ai_review") if isinstance(reporter.get("ai_review"), dict) else {}
    trade_summary = reporter.get("trade_summary") if isinstance(reporter.get("trade_summary"), dict) else {}
    recent_runs = load_recent_runs(config, limit=200)
    latest_run_sync = (
        dict((recent_runs[0] or {}).get("portfolio_sync") or {})
        if recent_runs and isinstance(recent_runs[0], dict)
        else _build_portfolio_sync_card({})
    )
    sync_runs_today = [
        row for row in recent_runs
        if latest_day and str(row.get("ts") or "").startswith(latest_day)
    ]
    sync_summary = {
        "today_total": len(sync_runs_today),
        "aligned_total": sum(1 for row in sync_runs_today if str((row.get("portfolio_sync") or {}).get("status") or "") == "aligned"),
        "reconciled_total": sum(1 for row in sync_runs_today if str((row.get("portfolio_sync") or {}).get("status") or "") == "reconciled"),
        "alert_total": sum(1 for row in sync_runs_today if str((row.get("portfolio_sync") or {}).get("status") or "") in {"mismatch", "reader_error"}),
    }

    return {
        "latest_day": latest_day,
        "daily": {
            "events": _safe_int(daily.get("events"), 0),
            "decision_actions": dict(daily.get("decision_actions") or {}),
            "approvals": _safe_int(daily.get("approvals"), 0),
            "blocks": _safe_int(daily.get("blocks"), 0),
            "path": str(config.reports_root / "daily" / f"daily_{latest_day}.json") if latest_day else "",
        },
        "operator_summary": {
            "system_status": str(executive.get("system_status") or "UNKNOWN"),
            "summary_lines": list(executive.get("summary_lines") or [])[:4],
            "health_level": str(health.get("system_health_level") or "UNKNOWN"),
            "recommended_action": list(health.get("recommended_action") or [])[:4],
            "run_total": _safe_int(trading.get("run_total"), 0),
            "executions_total": _safe_int(trading.get("executions_total"), 0),
            "blocked_total": _safe_int(trading.get("blocked_total"), 0),
            "path": str(config.reports_root / "operator_summary" / f"operator_summary_{latest_day}.json") if latest_day else "",
        },
        "reporter": {
            "trade_count": _safe_int(trade_summary.get("trade_count"), 0),
            "symbols_traded": list(trade_summary.get("symbols_traded") or [])[:8],
            "ai_status": str(ai_review.get("status") or "disabled"),
            "ai_run_grade": str(reporter.get("ai_run_grade") or "N/A"),
            "ai_summary": str(reporter.get("ai_summary") or ""),
            "path": str(config.reports_root / "dev" / "analysis" / "reporter_analysis" / f"reporter_analysis_{latest_day}.json") if latest_day else "",
        },
        "reconciliation": {
            "local_total": _safe_int(recon_summary.get("local_total"), 0),
            "broker_total": _safe_int(recon_summary.get("broker_total"), 0),
            "matched_by_ord_no": _safe_int(recon_summary.get("matched_by_ord_no"), 0),
            "broker_window_limited": bool(recon_summary.get("broker_window_limited")),
            "path": str(config.reports_root / "reconciliation" / f"broker_trade_reconciliation_{latest_day}.json") if latest_day else "",
        },
        "today_trades": today_trades,
        "today_traded_symbols": traded_symbol_summary,
        "overtrading_warning": overtrading_warning,
        "latest_strategist_prompt": latest_prompt,
        "strategy_memory_timeline": strategy_memory_timeline,
        "portfolio_sync": latest_run_sync,
        "portfolio_sync_summary": sync_summary,
    }


def load_recent_trades_for_day(config: OperatorUIConfig, day: str, *, limit: int = 8) -> List[Dict[str, Any]]:
    rows = list(_iter_jsonl(config.event_log_path))
    out: List[Dict[str, Any]] = []
    for row in rows:
        if str(row.get("stage") or "") != "execute_from_packet":
            continue
        if str(row.get("event") or "") != "execution":
            continue
        if day and _event_day(row.get("ts_kst") or row.get("ts")) != day:
            continue
        execution = _normalize_execution_payload(row.get("payload") if isinstance(row.get("payload"), dict) else {})
        action = str(execution.get("action") or "").upper()
        symbol = normalize_symbol(execution.get("symbol"), allow_test_symbols=True)
        if action not in {"BUY", "SELL"}:
            continue
        if not symbol:
            continue
        out.append(
            {
                "ts": _iso_to_display(row.get("ts_kst") or row.get("ts")),
                "run_id": str(row.get("run_id") or ""),
                "action": action,
                "symbol": symbol,
                "qty": _safe_int(execution.get("qty"), 0),
                "status": str(execution.get("status") or ""),
                "ord_no": str(execution.get("ord_no") or ""),
            }
        )
    out = sorted(out, key=lambda row: _to_epoch(row.get("ts")) or 0, reverse=True)
    return out[: max(1, int(limit))]


def summarize_trades_by_symbol(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for trade in trades:
        symbol = normalize_symbol(trade.get("symbol"), allow_test_symbols=True)
        if not symbol:
            continue
        row = grouped.setdefault(
            symbol,
            {
                "symbol": symbol,
                "buy_count": 0,
                "sell_count": 0,
                "net_qty": 0,
                "latest_action": "",
                "latest_ts": "",
                "latest_status": "",
            },
        )
        action = str(trade.get("action") or "").upper()
        qty = _safe_int(trade.get("qty"), 0)
        if action == "BUY":
            row["buy_count"] += 1
            row["net_qty"] += qty
        elif action == "SELL":
            row["sell_count"] += 1
            row["net_qty"] -= qty
        if (_to_epoch(trade.get("ts")) or 0) >= (_to_epoch(row.get("latest_ts")) or 0):
            row["latest_action"] = action
            row["latest_ts"] = str(trade.get("ts") or "")
            row["latest_status"] = str(trade.get("status") or "")
    out = list(grouped.values())
    out.sort(key=lambda row: (_to_epoch(row.get("latest_ts")) or 0, row.get("symbol") or ""), reverse=True)
    return out


def build_overtrading_warning(
    trades: List[Dict[str, Any]],
    traded_symbols: List[Dict[str, Any]],
    reporter_report: Dict[str, Any],
) -> Dict[str, Any]:
    total_executions = len(trades)
    round_trip_symbols = [
        {
            "symbol": row.get("symbol"),
            "buy_count": _safe_int(row.get("buy_count"), 0),
            "sell_count": _safe_int(row.get("sell_count"), 0),
            "round_trips": min(_safe_int(row.get("buy_count"), 0), _safe_int(row.get("sell_count"), 0)),
        }
        for row in traded_symbols
        if _safe_int(row.get("buy_count"), 0) > 0 and _safe_int(row.get("sell_count"), 0) > 0
    ]
    round_trip_symbols.sort(key=lambda row: (row.get("round_trips") or 0, row.get("symbol") or ""), reverse=True)
    ai_findings = list(reporter_report.get("ai_findings") or [])[:4] if isinstance(reporter_report, dict) else []
    reasons: List[str] = []
    level = "normal"
    if total_executions >= 10:
        level = "high"
        reasons.append(f"execution count elevated ({total_executions})")
    elif total_executions >= 5:
        level = "elevated"
        reasons.append(f"execution count moderately elevated ({total_executions})")
    if round_trip_symbols:
        if level == "normal":
            level = "elevated"
        top = round_trip_symbols[0]
        reasons.append(
            f"same-symbol round trips detected on {top.get('symbol')} ({top.get('round_trips')} cycles)"
        )
    if any("overtrading" in str(item).lower() for item in ai_findings):
        if level == "normal":
            level = "elevated"
        reasons.append("reporter flagged overtrading risk")
    if not reasons:
        reasons.append("no immediate overtrading signal in latest execution window")
    return {
        "level": level,
        "total_executions": total_executions,
        "round_trip_symbols": round_trip_symbols[:5],
        "reasons": reasons[:4],
    }


def load_symbol_run_chain(config: OperatorUIConfig, day: str, symbol: str, *, limit: int = 3) -> List[Dict[str, Any]]:
    if not symbol:
        return []
    rows = list(_iter_jsonl(config.event_log_path))
    route_rows = [
        row
        for row in rows
        if str(row.get("stage") or "") == "commander_router"
        and str(row.get("event") or "") == "route"
        and (not day or _event_day(row.get("ts")) == day)
    ]
    route_rows = sorted(route_rows, key=lambda row: _to_epoch(row.get("ts")) or 0, reverse=True)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        rid = str(row.get("run_id") or "").strip()
        if not rid:
            continue
        grouped.setdefault(rid, []).append(row)

    out: List[Dict[str, Any]] = []
    for route in route_rows:
        rid = str(route.get("run_id") or "").strip()
        run_rows = grouped.get(rid) or []
        scanner_summary = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "scanner" and str(r.get("event") or "") == "summary" and isinstance(r.get("payload"), dict)),
            {},
        )
        candidate_selection = next(
            (
                (r.get("payload") or {}).get("payload")
                for r in reversed(run_rows)
                if str(r.get("stage") or "") == "decision_trace"
                and str(r.get("event") or "") == "candidate_selection"
                and isinstance(r.get("payload"), dict)
                and str((r.get("payload") or {}).get("agent") or "") == "scanner"
            ),
            {},
        )
        execution_payload = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "execute_from_packet" and str(r.get("event") or "") == "execution" and isinstance(r.get("payload"), dict)),
            {},
        )
        execution = _normalize_execution_payload(execution_payload if isinstance(execution_payload, dict) else {})
        execution = _normalize_execution_payload(execution_payload if isinstance(execution_payload, dict) else {})
        strategist_summary = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "strategist" and str(r.get("event") or "") == "summary" and isinstance(r.get("payload"), dict)),
            {},
        )
        monitor_summary = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "monitor" and str(r.get("event") or "") == "summary" and isinstance(r.get("payload"), dict)),
            {},
        )
        verdict_payload = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "execute_from_packet" and str(r.get("event") or "") == "verdict" and isinstance(r.get("payload"), dict)),
            {},
        )
        run_symbol = normalize_symbol(
            execution.get("symbol")
            or scanner_summary.get("top_stock")
            or candidate_selection.get("selected_symbol")
            or "",
            allow_test_symbols=True,
        ).strip()
        if run_symbol != symbol:
            continue
        out.append(
            {
                "ts": _iso_to_display(route.get("ts")),
                "run_id": rid,
                "phase": str((route.get("payload") or {}).get("phase") or ""),
                "playbook": str(strategist_summary.get("playbook") or ""),
                "risk_tone": str(strategist_summary.get("risk_tone") or ""),
                "symbol": run_symbol,
                "action": str(execution.get("action") or ""),
                "execution_status": str(execution.get("status") or ""),
                "monitor_reason": str(monitor_summary.get("monitor_reason") or ""),
                "exit_reason": str(monitor_summary.get("exit_reason") or ""),
                "guard_reason": str(verdict_payload.get("reason") or ""),
                "allowed": verdict_payload.get("allowed"),
            }
        )
        if len(out) >= max(1, int(limit)):
            break
    return out


def load_latest_strategist_prompt_summary(config: OperatorUIConfig, day: str) -> Dict[str, Any]:
    rows = list(_iter_jsonl(config.evidence_log_path))
    target = {}
    for row in reversed(rows):
        if str(row.get("agent") or "") != "strategist":
            continue
        if str(row.get("stage") or "") != "theme_selection":
            continue
        if day and _event_day(row.get("timestamp")) != day:
            continue
        target = row
        break
    if not target:
        return {}
    raw_input = target.get("raw_input") if isinstance(target.get("raw_input"), dict) else {}
    parsed_output = target.get("parsed_output") if isinstance(target.get("parsed_output"), dict) else {}
    prompt = str(target.get("llm_prompt") or "")
    compact_prompt = prompt if len(prompt) <= 400 else prompt[:397] + "..."
    return {
        "run_id": str(target.get("run_id") or ""),
        "timestamp": str(target.get("timestamp") or ""),
        "news_query_targets": list(raw_input.get("news_query_targets") or [])[:8],
        "themes": list(parsed_output.get("themes") or [])[:6],
        "playbook": str(parsed_output.get("playbook") or ""),
        "market_regime": str(parsed_output.get("market_regime") or ""),
        "prompt_excerpt": compact_prompt,
    }


def load_recent_runs(config: OperatorUIConfig, *, limit: int = 50, mismatch_only: bool = False) -> List[Dict[str, Any]]:
    rows = list(_iter_jsonl(config.event_log_path))
    route_rows = [row for row in rows if str(row.get("stage") or "") == "commander_router" and str(row.get("event") or "") == "route"]
    route_rows = sorted(route_rows, key=lambda row: _to_epoch(row.get("ts")) or 0, reverse=True)[: max(1, int(limit))]
    target_run_ids = {str(row.get("run_id") or "").strip() for row in route_rows if str(row.get("run_id") or "").strip()}
    grouped: Dict[str, List[Dict[str, Any]]] = {rid: [] for rid in target_run_ids}
    report_index = _trade_report_index(config)
    reports_by_run = report_index.get("by_run_id") or {}
    for row in rows:
        rid = str(row.get("run_id") or "").strip()
        if rid in grouped:
            grouped[rid].append(row)

    out: List[Dict[str, Any]] = []
    for route in route_rows:
        rid = str(route.get("run_id") or "").strip()
        run_rows = grouped.get(rid) or []
        strategist_summary = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "strategist" and str(r.get("event") or "") == "summary" and isinstance(r.get("payload"), dict)),
            {},
        )
        scanner_summary = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "scanner" and str(r.get("event") or "") == "summary" and isinstance(r.get("payload"), dict)),
            {},
        )
        monitor_summary = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "monitor" and str(r.get("event") or "") == "summary" and isinstance(r.get("payload"), dict)),
            {},
        )
        strategic_frame = next(
            (
                (r.get("payload") or {}).get("payload")
                for r in reversed(run_rows)
                if str(r.get("stage") or "") == "decision_trace"
                and str(r.get("event") or "") == "strategic_frame"
                and isinstance(r.get("payload"), dict)
                and str((r.get("payload") or {}).get("agent") or "") == "strategist"
            ),
            {},
        )
        candidate_selection = next(
            (
                (r.get("payload") or {}).get("payload")
                for r in reversed(run_rows)
                if str(r.get("stage") or "") == "decision_trace"
                and str(r.get("event") or "") == "candidate_selection"
                and isinstance(r.get("payload"), dict)
                and str((r.get("payload") or {}).get("agent") or "") == "scanner"
            ),
            {},
        )
        verdict_payload = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "execute_from_packet" and str(r.get("event") or "") == "verdict" and isinstance(r.get("payload"), dict)),
            {},
        )
        execution_payload = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "execute_from_packet" and str(r.get("event") or "") == "execution" and isinstance(r.get("payload"), dict)),
            {},
        )
        execution = _normalize_execution_payload(execution_payload if isinstance(execution_payload, dict) else {})
        portfolio_sync = _build_portfolio_sync_card(_extract_portfolio_guard_payload_from_run_rows(run_rows))
        selected_candidate = candidate_selection.get("selected_candidate") if isinstance(candidate_selection.get("selected_candidate"), dict) else {}
        feature_snapshot = selected_candidate.get("feature_snapshot") if isinstance(selected_candidate.get("feature_snapshot"), dict) else {}
        feature_coverage = _feature_coverage(feature_snapshot)
        macro_stress_overlay = strategic_frame.get("macro_stress_overlay") if isinstance(strategic_frame.get("macro_stress_overlay"), dict) else {}
        report_meta = reports_by_run.get(rid) if isinstance(reports_by_run.get(rid), dict) else {}
        if report_meta:
            report_diag = (
                report_meta.get("ai_report_diagnostics")
                if isinstance(report_meta.get("ai_report_diagnostics"), dict)
                else {}
            )
        else:
            execution_action = str(execution.get("action") or "").upper()
            monitor_reason_text = str(monitor_summary.get("monitor_reason") or "").strip().lower()
            if execution_action in {"BUY", "SELL"}:
                report_diag = _normalize_ai_report_diagnostics(
                    {
                        "report_status": "failed",
                        "report_reason_code": "missing_report_linkage",
                        "report_reason_human": _report_reason_human("missing_report_linkage"),
                        "next_expected_step": _report_next_step("missing_report_linkage"),
                        "generation_attempted": False,
                        "story_input_available": False,
                        "report_output_available": False,
                    },
                    report_exists=False,
                    lifecycle_status="",
                    story_type="",
                )
            elif "hold" in monitor_reason_text:
                report_diag = _normalize_ai_report_diagnostics(
                    {
                        "report_status": "skipped",
                        "report_reason_code": "hold_only_run",
                        "report_reason_human": _report_reason_human("hold_only_run"),
                        "next_expected_step": _report_next_step("hold_only_run"),
                    },
                    report_exists=False,
                    lifecycle_status="",
                    story_type="decision_only",
                )
            else:
                report_diag = _normalize_ai_report_diagnostics(
                    {
                        "report_status": "skipped",
                        "report_reason_code": "decision_only_run",
                        "report_reason_human": _report_reason_human("decision_only_run"),
                        "next_expected_step": _report_next_step("decision_only_run"),
                    },
                    report_exists=False,
                    lifecycle_status="",
                    story_type="decision_only",
                )
        row = {
                "run_id": rid,
                "run_id_short": _short_run_id(rid),
                "ts": _iso_to_display(route.get("ts")),
                "mode": str((route.get("payload") or {}).get("mode") or ""),
                "phase": str((route.get("payload") or {}).get("phase") or ""),
                "strategist_playbook": str(strategist_summary.get("playbook") or ""),
                "strategist_risk_tone": str(strategist_summary.get("risk_tone") or ""),
                "scanner_top_stock": str(scanner_summary.get("top_stock") or ""),
                "scanner_top_score": _safe_float(scanner_summary.get("top_score"), 0.0),
                "monitor_reason": str(monitor_summary.get("monitor_reason") or ""),
                "exit_reason": str(monitor_summary.get("exit_reason") or ""),
                "supervisor_allowed": verdict_payload.get("allowed"),
                "guard_reason": str(verdict_payload.get("reason") or ""),
                "execution_status": str(execution.get("status") or ""),
                "execution_action": str(execution.get("action") or ""),
                "symbol": normalize_symbol(execution.get("symbol") or scanner_summary.get("top_stock") or "", allow_test_symbols=True),
                "macro_stress_active": bool(macro_stress_overlay.get("active")),
                "macro_stress_flags": list(macro_stress_overlay.get("stress_flags") or [])[:3],
                "feature_coverage_quality": str(feature_coverage.get("quality") or "missing"),
                "feature_coverage_ratio": _safe_float(feature_coverage.get("coverage_ratio"), 0.0),
                "report_available": bool(report_meta.get("report_available")),
                "report_status": str(report_meta.get("report_status") or report_diag.get("report_status") or "skipped"),
                "report_status_label": str(report_meta.get("report_status_label") or report_diag.get("report_status_label") or _report_status_label("skipped")),
                "report_status_badge_class": str(report_meta.get("report_status_badge_class") or report_diag.get("report_status_badge_class") or _report_status_badge_class("skipped")),
                "report_reason_human": str(report_meta.get("report_reason_human") or report_diag.get("report_reason_human") or ""),
                "report_next_expected_step": str(report_meta.get("report_next_expected_step") or report_diag.get("next_expected_step") or ""),
                "report_generation_model": str(report_meta.get("report_generation_model") or report_diag.get("llm_model_used") or ""),
                "trade_id": str(report_meta.get("trade_id") or ""),
                "story_id": str(report_meta.get("story_id") or ""),
                "story_type": str(report_meta.get("story_type") or ""),
                "story_type_label": str(report_meta.get("story_type_label") or "No linked report"),
                "story_type_badge_class": str(report_meta.get("story_type_badge_class") or "status-badge"),
                "lifecycle_status": str(report_meta.get("lifecycle_status") or ""),
                "lifecycle_summary": str(report_meta.get("lifecycle_summary") or ""),
                "execution_mode_label": str(report_meta.get("execution_mode_label") or "-"),
                "report_summary": str(report_meta.get("report_summary") or "No linked trade report for this run."),
                "reporter_status_human": str(report_meta.get("reporter_status_human") or ""),
                "report_link": str(report_meta.get("report_link") or ""),
                "portfolio_sync": portfolio_sync,
                "portfolio_sync_status": str(portfolio_sync.get("status") or "unavailable"),
                "portfolio_sync_label": str(portfolio_sync.get("status_label") or "Sync status unavailable"),
                "portfolio_sync_badge_class": str(portfolio_sync.get("badge_class") or "status-badge"),
                "portfolio_sync_sentence": str(portfolio_sync.get("sentence") or ""),
            }
        if mismatch_only and row["portfolio_sync_status"] not in {"mismatch", "reader_error"}:
            continue
        out.append(row)
    return out


def _latest_evidence(rows: List[Dict[str, Any]], *, agent: str, stage: str) -> Dict[str, Any]:
    for row in reversed(rows):
        if str(row.get("agent") or "").strip() != agent:
            continue
        if str(row.get("stage") or "").strip() != stage:
            continue
        return row
    return {}


def _reporter_snippet_for_run(config: OperatorUIConfig, run_id: str, run_day: str) -> Dict[str, Any]:
    path = config.reports_root / "dev" / "analysis" / "reporter_analysis" / f"reporter_analysis_{run_day}.json"
    report = _read_json(path)
    if not report:
        return {
            "report_path": str(path),
            "found": False,
            "ai_summary": "",
            "ai_run_grade": "",
            "reason": "same_day_report_missing",
        }
    chains = ((report.get("decision_trace_chain_summary") or {}).get("chains") or []) if isinstance(report.get("decision_trace_chain_summary"), dict) else []
    chain = next((c for c in chains if isinstance(c, dict) and str(c.get("run_id") or "").strip() == run_id), {})
    if not chain:
        return {
            "report_path": str(path),
            "found": False,
            "ai_summary": "",
            "ai_run_grade": str(report.get("ai_run_grade") or ""),
            "reason": "run_not_linked_in_same_day_report",
        }
    return {
        "report_path": str(path),
        "found": True,
        "ai_summary": str(report.get("ai_summary") or ""),
        "ai_run_grade": str(report.get("ai_run_grade") or ""),
        "chain": chain,
    }


def _report_section(report: Dict[str, Any], key: str, fallback_summary: str = "") -> Dict[str, Any]:
    section = report.get(key) if isinstance(report.get(key), dict) else {}
    return {
        "summary": _trim_text(section.get("summary"), max_len=1000) or _trim_text(fallback_summary, max_len=1000),
        "bullets": _clean_str_list(section.get("bullets"), limit=12, max_len=280),
        "status": _trim_text(section.get("status"), max_len=64),
        "grade": _trim_text(section.get("grade"), max_len=32),
    }


def load_trade_report_detail(config: OperatorUIConfig, story_id: str) -> Dict[str, Any]:
    meta = _trade_report_meta_for_story(config, story_id)
    if not meta:
        return {"found": False, "story_id": str(story_id or "")}

    report_path = Path(str(meta.get("trade_report_json_path") or ""))
    bundle_path = Path(str(meta.get("aggregated_bundle_path") or ""))
    lifecycle_path = Path(str(meta.get("trade_lifecycle_json_path") or ""))
    report = _read_json(report_path) if report_path.exists() else {}
    bundle = _read_json(bundle_path) if bundle_path.exists() else {}
    lifecycle = _read_json(lifecycle_path) if lifecycle_path.exists() else {}
    market_context_human = bundle.get("market_context_human") if isinstance(bundle.get("market_context_human"), dict) else {}
    scanner_reason_human = bundle.get("scanner_reason_human") if isinstance(bundle.get("scanner_reason_human"), dict) else {}
    filters_human = bundle.get("filters_human") if isinstance(bundle.get("filters_human"), dict) else {}
    monitor_reason_human = bundle.get("monitor_reason_human") if isinstance(bundle.get("monitor_reason_human"), dict) else {}
    guard_reason_human = bundle.get("guard_reason_human") if isinstance(bundle.get("guard_reason_human"), dict) else {}
    execution_outcome_human = bundle.get("execution_outcome_human") if isinstance(bundle.get("execution_outcome_human"), dict) else {}
    reporter_status_human = bundle.get("reporter_status_human") if isinstance(bundle.get("reporter_status_human"), dict) else {}
    operator_conclusion_human = bundle.get("operator_conclusion_human") if isinstance(bundle.get("operator_conclusion_human"), dict) else {}

    lifecycle_entry = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
    lifecycle_holding = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
    lifecycle_exit = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
    lifecycle_summary_obj = lifecycle.get("summary") if isinstance(lifecycle.get("summary"), dict) else {}
    lifecycle_reporter = lifecycle.get("reporter") if isinstance(lifecycle.get("reporter"), dict) else {}

    executive = _report_section(
        report,
        "executive_summary",
        lifecycle_summary_obj.get("lifecycle_summary_human") or operator_conclusion_human.get("summary") or execution_outcome_human.get("summary") or "",
    )
    market_context = _report_section(
        report,
        "market_context_at_entry",
        (lifecycle_entry.get("strategist_context") or {}).get("market_context_summary") if isinstance(lifecycle_entry.get("strategist_context"), dict) else market_context_human.get("summary") or "",
    )
    why_symbol = _report_section(
        report,
        "why_this_symbol_was_chosen",
        lifecycle_entry.get("reason_human") or scanner_reason_human.get("summary") or "",
    )
    scanner_filters = _report_section(
        report,
        "scanner_filters",
        filters_human.get("summary") or "",
    )
    entry_decision = _report_section(
        report,
        "entry_decision",
        lifecycle_entry.get("reason_human") or scanner_reason_human.get("summary") or "",
    )
    holding_story = _report_section(
        report,
        "holding_monitoring_story",
        monitor_reason_human.get("summary")
        or (
            f"Holding phase captured {len(list(lifecycle_holding.get('run_ids') or []))} runs."
            if list(lifecycle_holding.get("run_ids") or [])
            else ""
        ),
    )
    exit_decision = _report_section(
        report,
        "exit_decision",
        lifecycle_exit.get("reason_human")
        or (
            "Position is still open; no closing SELL execution has been captured yet."
            if str(lifecycle.get("status") or "").lower() == "open"
            else ""
        ),
    )
    execution_quality = _report_section(report, "execution_quality", execution_outcome_human.get("summary") or "")
    guard_result = _report_section(report, "guard_approval_result", guard_reason_human.get("summary") or "")
    reporter_eval = _report_section(report, "reporter_evaluation", reporter_status_human.get("summary") or "")
    weak_points = _report_section(
        report,
        "errors_weaknesses_improvement_points",
        "No explicit weaknesses were captured beyond standard warnings.",
    )
    final_conclusion = report.get("final_operator_conclusion") if isinstance(report.get("final_operator_conclusion"), dict) else {}
    timeline = [
        row
        for row in list(report.get("full_timeline") or report.get("timeline") or lifecycle.get("timeline") or bundle.get("timeline") or [])
        if isinstance(row, dict)
    ][:24]
    generation = report.get("generation") if isinstance(report.get("generation"), dict) else {}
    report_exists = bool(report_path.exists() or Path(str(meta.get("trade_report_md_path") or "")).exists())
    diagnostics = _normalize_ai_report_diagnostics(
        report.get("ai_report_diagnostics")
        if isinstance(report.get("ai_report_diagnostics"), dict)
        else bundle.get("ai_report_diagnostics")
        if isinstance(bundle.get("ai_report_diagnostics"), dict)
        else lifecycle.get("ai_report_diagnostics")
        if isinstance(lifecycle.get("ai_report_diagnostics"), dict)
        else {},
        report_exists=report_exists,
        lifecycle_status=meta.get("lifecycle_status") or lifecycle.get("status"),
        story_type=meta.get("story_type") or report.get("story_type"),
        model_hint=generation.get("model"),
        generation=generation,
    )
    action = _trim_text(report.get("action"), max_len=32) or _trim_text(meta.get("action"), max_len=32) or "WAIT"
    symbol = normalize_symbol(
        report.get("symbol") or meta.get("symbol") or "",
        allow_test_symbols=True,
    )
    reporter_status = _trim_text(reporter_eval.get("status"), max_len=48) or _trim_text(reporter_status_human.get("status"), max_len=48) or "-"
    reporter_grade = _trim_text(reporter_eval.get("grade"), max_len=24) or _trim_text(reporter_status_human.get("grade"), max_len=24) or "-"

    return {
        "found": True,
        "trade_id": str(meta.get("trade_id") or meta.get("story_id") or story_id),
        "story_id": str(meta.get("story_id") or story_id),
        "run_id": str(meta.get("run_id") or ""),
        "run_link": f"/runs/{meta.get('run_id')}" if str(meta.get("run_id") or "").strip() else "",
        "symbol": symbol,
        "action": action,
        "status": str(meta.get("lifecycle_status") or report.get("status") or lifecycle.get("status") or ""),
        "lifecycle_summary": str(meta.get("lifecycle_summary") or lifecycle_summary_obj.get("lifecycle_summary_human") or ""),
        "story_type": str(meta.get("story_type") or report.get("story_type") or ""),
        "story_type_label": str(meta.get("story_type_label") or _story_type_label(report.get("story_type"))),
        "story_type_badge_class": str(meta.get("story_type_badge_class") or _story_type_badge_class(report.get("story_type"))),
        "execution_mode_label": str(meta.get("execution_mode_label") or report.get("execution_mode_label") or "not captured"),
        "report_available": bool(diagnostics.get("report_status") == "available" and report_exists),
        "report_summary": str(meta.get("report_summary") or executive.get("summary") or ""),
        "reporter_status_human": str(meta.get("reporter_status_human") or reporter_eval.get("summary") or ""),
        "ai_report_diagnostics": diagnostics,
        "executive_summary": executive,
        "market_context": market_context,
        "why_this_symbol": why_symbol,
        "entry_decision": entry_decision,
        "holding_monitoring_story": holding_story,
        "exit_decision": exit_decision,
        "scanner_logic_and_filters": scanner_filters,
        "monitor_trigger_reasoning": holding_story,
        "guard_approval_result": guard_result,
        "execution_result": execution_quality,
        "execution_quality": execution_quality,
        "reporter_evaluation": {
            **reporter_eval,
            "status": reporter_status,
            "grade": reporter_grade or _trim_text(lifecycle_reporter.get("grade"), max_len=24) or "-",
        },
        "errors_weaknesses_improvement_points": weak_points,
        "timeline": timeline,
        "full_timeline": timeline,
        "trade_lifecycle": lifecycle if isinstance(lifecycle, dict) else {},
        "final_operator_conclusion": {
            "summary": _trim_text(final_conclusion.get("summary"), max_len=1000) or _trim_text(operator_conclusion_human.get("summary"), max_len=1000),
            "current_action": _trim_text(final_conclusion.get("current_action"), max_len=32) or _trim_text(action, max_len=32),
            "watch_next": _clean_str_list(final_conclusion.get("watch_next"), limit=8, max_len=220)
            or _clean_str_list(operator_conclusion_human.get("watch_next"), limit=8, max_len=220),
            "thesis_invalidation": _clean_str_list(final_conclusion.get("thesis_invalidation"), limit=8, max_len=220)
            or _clean_str_list(operator_conclusion_human.get("thesis_invalidation"), limit=8, max_len=220),
        },
        "generation": {
            "status": _trim_text(generation.get("status"), max_len=48) or "not_captured",
            "mode": _trim_text(generation.get("mode"), max_len=48) or "not_captured",
            "model": _trim_text(generation.get("model"), max_len=120) or "not_captured",
            "reason": _trim_text(generation.get("reason"), max_len=320),
        },
        "paths": {
            "trade_report_json": str(meta.get("trade_report_json_path") or ""),
            "trade_report_md": str(meta.get("trade_report_md_path") or ""),
            "trade_story_input": str(meta.get("trade_story_input_path") or ""),
            "trade_lifecycle": str(meta.get("trade_lifecycle_json_path") or ""),
            "aggregated_execution_bundle": str(meta.get("aggregated_bundle_path") or ""),
        },
        "raw_report": report if isinstance(report, dict) else {},
    }


_FEATURE_NAME_MAP: Dict[str, str] = {
    "engine_ma20_gap": "MA20 gap support",
    "engine_ma60": "MA60 trend anchor",
    "engine_ma120": "MA120 long trend",
    "engine_adx14": "ADX trend strength",
    "engine_trend_strength": "trend strength score",
    "engine_volume_spike20": "volume expansion",
    "engine_volatility20": "volatility profile",
    "engine_vwap_distance": "VWAP distance",
    "engine_sector_relative_strength": "sector relative strength",
    "engine_cross_section_rank": "cross-sectional rank",
    "engine_regime": "regime detection",
    "engine_signal_score": "composite signal score",
}


def _format_float(v: Any, digits: int = 2) -> str:
    if v is None or v == "":
        return "-"
    try:
        return f"{float(v):.{digits}f}"
    except Exception:
        return str(v)


def _format_percent(v: Any, digits: int = 1) -> str:
    if v is None or v == "":
        return "-"
    try:
        num = float(v)
    except Exception:
        return str(v)
    if abs(num) <= 1.0:
        num *= 100.0
    return f"{num:.{digits}f}%"


def _format_duration(seconds: Any) -> str:
    total = _safe_int(seconds, -1)
    if total < 0:
        return "-"
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total / 60.0:.1f}m"
    return f"{total / 3600.0:.1f}h"


def _friendly_feature_name(key: str) -> str:
    k = str(key or "").strip()
    if not k:
        return "-"
    if k in _FEATURE_NAME_MAP:
        return _FEATURE_NAME_MAP[k]
    return k.replace("engine_", "").replace("_", " ")


def _build_top_candidates(scanner_summary: Dict[str, Any], scanner_trace: Dict[str, Any], selected_symbol: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    raw_ranked = scanner_summary.get("top_ranked_symbols") if isinstance(scanner_summary, dict) else []
    if isinstance(raw_ranked, list):
        for idx, item in enumerate(raw_ranked[:5], start=1):
            if isinstance(item, dict):
                symbol = normalize_symbol(
                    item.get("symbol")
                    or item.get("code")
                    or item.get("ticker")
                    or item.get("stock")
                    or "",
                    allow_test_symbols=True,
                )
                reason = str(item.get("reason") or item.get("why") or "").strip()
                score = item.get("score_total") if item.get("score_total") is not None else item.get("score")
            else:
                symbol = normalize_symbol(item, allow_test_symbols=True)
                reason = ""
                score = None
            if not symbol:
                continue
            out.append(
                {
                    "rank": idx,
                    "symbol": symbol,
                    "reason": reason,
                    "score": score,
                }
            )
    ranked_candidates = scanner_trace.get("ranked_candidates") if isinstance(scanner_trace, dict) else []
    if isinstance(ranked_candidates, list):
        seen = {str(row.get("symbol") or "") for row in out}
        for item in ranked_candidates[:5]:
            if not isinstance(item, dict):
                continue
            symbol = normalize_symbol(
                item.get("symbol")
                or item.get("code")
                or item.get("ticker")
                or "",
                allow_test_symbols=True,
            )
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            out.append(
                {
                    "rank": len(out) + 1,
                    "symbol": symbol,
                    "reason": str(item.get("reason") or item.get("why") or "").strip(),
                    "score": item.get("score_total") if item.get("score_total") is not None else item.get("score"),
                }
            )
    if selected_symbol and not any(str(row.get("symbol") or "") == selected_symbol for row in out):
        out.insert(
            0,
            {
                "rank": 1,
                "symbol": selected_symbol,
                "reason": "",
                "score": None,
            },
        )
    for idx, row in enumerate(out, start=1):
        row["rank"] = idx
    return out[:5]


def _trade_report_artifact_payload(trade_report: Dict[str, Any], key: str) -> Dict[str, Any]:
    payload = trade_report.get(key) if isinstance(trade_report, dict) else {}
    return payload if isinstance(payload, dict) else {}


def _trade_report_section_payload(*sections: Any) -> Dict[str, Any]:
    for section in sections:
        if isinstance(section, dict) and section:
            return section
    return {}


def _trade_report_section_summary(section: Dict[str, Any], fallback: str = "") -> str:
    if not isinstance(section, dict):
        return str(fallback or "")
    return str(section.get("summary") or fallback or "")


def _trade_report_section_bullets(section: Dict[str, Any], *, limit: int = 6) -> List[str]:
    if not isinstance(section, dict):
        return []
    return [str(x or "") for x in list(section.get("bullets") or [])[:limit] if str(x or "").strip()]


def _extract_labeled_bullet(bullets: List[str], labels: List[str]) -> str:
    normalized_labels = [str(label or "").strip().lower() for label in labels if str(label or "").strip()]
    for bullet in bullets:
        text = str(bullet or "").strip()
        lower = text.lower()
        for label in normalized_labels:
            prefix = f"{label}:"
            if lower.startswith(prefix):
                return text.split(":", 1)[1].strip()
    return ""


def _extract_labeled_int(bullets: List[str], labels: List[str]) -> Optional[int]:
    value = _extract_labeled_bullet(bullets, labels)
    if not value:
        return None
    match = re.search(r"-?\d+", value)
    if not match:
        return None
    return _safe_int(match.group(0), 0)


def _parse_canonical_filter_bullets(bullets: List[str]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for bullet in bullets:
        text = str(bullet or "").strip()
        if not text or ":" not in text:
            continue
        name_raw, rest = text.split(":", 1)
        name = name_raw.strip().title()
        status = "INFO"
        note = rest.strip()
        match = re.match(r"\s*(PASS|FAIL|PARTIAL|SKIPPED|NOT_AVAILABLE)\s*[-:]?\s*(.*)$", note, flags=re.IGNORECASE)
        if match:
            status = match.group(1).upper()
            note = match.group(2).strip() or note.strip()
        rows.append({"name": name, "status": status, "note": note})
    return rows


def _prefer_runtime_reporter_state(reporter: Dict[str, Any]) -> bool:
    if not isinstance(reporter, dict):
        return False
    return bool(reporter.get("reason") or reporter.get("ai_summary") or reporter.get("found"))


def _build_canonical_trade_brief_input(trade_report: Dict[str, Any]) -> Dict[str, Any]:
    story_input = _trade_report_artifact_payload(trade_report, "story_input_data")
    lifecycle = _trade_report_artifact_payload(trade_report, "lifecycle_data")
    report = _trade_report_artifact_payload(trade_report, "report_data")
    if not (story_input or lifecycle or report):
        return {
            "available": False,
            "trade_id": str(trade_report.get("trade_id") or ""),
            "story_type": str(trade_report.get("story_type_label") or trade_report.get("story_type") or ""),
            "execution_mode_label": str(trade_report.get("execution_mode_label") or ""),
            "lifecycle_status": str(trade_report.get("lifecycle_status") or ""),
            "lifecycle_summary": str(trade_report.get("lifecycle_summary") or ""),
            "report_summary": str(trade_report.get("report_summary") or ""),
            "reporter_summary": str(trade_report.get("reporter_status_human") or ""),
        }

    market_context = _trade_report_section_payload(
        story_input.get("market_context_human"),
        report.get("market_context_at_entry"),
        report.get("market_context"),
    )
    selection = _trade_report_section_payload(
        story_input.get("scanner_reason_human"),
        report.get("why_this_symbol_was_chosen"),
        report.get("why_this_symbol"),
    )
    filters = _trade_report_section_payload(
        story_input.get("filters_human"),
        report.get("scanner_filters"),
        report.get("scanner_logic_and_filters"),
    )
    monitor = _trade_report_section_payload(
        story_input.get("monitor_reason_human"),
        report.get("holding_monitoring_story"),
        report.get("monitor_trigger_reasoning"),
    )
    guard = _trade_report_section_payload(
        story_input.get("guard_reason_human"),
        report.get("guard_approval_result"),
    )
    execution = _trade_report_section_payload(
        story_input.get("execution_outcome_human"),
        report.get("execution_quality"),
        report.get("execution_result"),
    )
    reporter_eval = _trade_report_section_payload(
        story_input.get("reporter_status_human"),
        report.get("reporter_evaluation"),
        lifecycle.get("reporter"),
    )
    conclusion = _trade_report_section_payload(
        story_input.get("operator_conclusion_human"),
        report.get("final_operator_conclusion"),
        lifecycle.get("summary"),
    )
    executive = _trade_report_section_payload(report.get("executive_summary"))
    lifecycle_summary = lifecycle.get("summary") if isinstance(lifecycle.get("summary"), dict) else {}
    entry_summary = story_input.get("entry_summary") if isinstance(story_input.get("entry_summary"), dict) else {}
    exit_summary = story_input.get("exit_summary") if isinstance(story_input.get("exit_summary"), dict) else {}

    market_bullets = _trade_report_section_bullets(market_context)
    selection_bullets = _trade_report_section_bullets(selection)
    filter_bullets = _trade_report_section_bullets(filters, limit=8)
    monitor_bullets = _trade_report_section_bullets(monitor)
    execution_bullets = _trade_report_section_bullets(execution)
    market_regime = str(market_context.get("regime") or _extract_labeled_bullet(market_bullets, ["market regime", "regime"]) or "")
    market_sentiment = str(
        market_context.get("market_sentiment")
        or _extract_labeled_bullet(market_bullets, ["market sentiment"])
        or ""
    )
    global_sentiment = str(
        market_context.get("global_sentiment_score")
        or _extract_labeled_bullet(market_bullets, ["global sentiment score", "global sentiment"])
        or ""
    )
    vix_level = str(
        market_context.get("vix_level")
        or _extract_labeled_bullet(market_bullets, ["vix / fear index level", "vix"])
        or ""
    )
    universe_size = _extract_labeled_int(selection_bullets, ["universe scanned"])
    selected_rank = _extract_labeled_int(selection_bullets, ["selected rank"])
    canonical_filter_rows = _parse_canonical_filter_bullets(filter_bullets)

    return {
        "available": True,
        "trade_id": str(trade_report.get("trade_id") or story_input.get("trade_id") or lifecycle.get("trade_id") or ""),
        "story_type": str(trade_report.get("story_type_label") or trade_report.get("story_type") or story_input.get("story_type") or ""),
        "execution_mode_label": str(trade_report.get("execution_mode_label") or story_input.get("execution_mode_label") or lifecycle.get("execution_mode_label") or ""),
        "lifecycle_status": str(trade_report.get("lifecycle_status") or lifecycle.get("status") or ""),
        "lifecycle_summary": str(
            trade_report.get("lifecycle_summary")
            or lifecycle_summary.get("lifecycle_summary_human")
            or conclusion.get("summary")
            or ""
        ),
        "headline": str(executive.get("headline") or ""),
        "current_action": str(
            conclusion.get("current_action")
            or report.get("action")
            or story_input.get("action")
            or trade_report.get("action")
            or ""
        ),
        "symbol": str(report.get("symbol") or story_input.get("symbol") or trade_report.get("symbol") or ""),
        "market_regime": market_regime,
        "market_sentiment": market_sentiment,
        "global_sentiment": global_sentiment,
        "vix": vix_level,
        "playbook": str(market_context.get("playbook") or ""),
        "themes": [str(x or "") for x in list(market_context.get("themes") or [])[:6] if str(x or "").strip()],
        "market_context_summary": _trade_report_section_summary(market_context),
        "market_context_bullets": market_bullets,
        "selection_summary": _trade_report_section_summary(selection),
        "selection_bullets": selection_bullets,
        "universe_size": universe_size,
        "selected_rank": selected_rank,
        "filters_summary": _trade_report_section_summary(filters),
        "filter_bullets": filter_bullets,
        "filter_rows": canonical_filter_rows,
        "monitor_summary": _trade_report_section_summary(monitor),
        "monitor_bullets": monitor_bullets,
        "guard_summary": _trade_report_section_summary(guard),
        "execution_summary": _trade_report_section_summary(execution),
        "execution_bullets": execution_bullets,
        "report_summary": str(trade_report.get("report_summary") or executive.get("summary") or ""),
        "reporter_status": str(reporter_eval.get("status") or lifecycle.get("reporter", {}).get("status_human") or ""),
        "reporter_grade": str(reporter_eval.get("grade") or lifecycle.get("reporter", {}).get("grade") or ""),
        "reporter_summary": _trade_report_section_summary(reporter_eval, str(trade_report.get("reporter_status_human") or "")),
        "entry_reason": str(entry_summary.get("reason_human") or lifecycle_summary.get("entry_reason_human") or ""),
        "exit_reason": str(exit_summary.get("reason_human") or lifecycle_summary.get("exit_reason_human") or ""),
        "timeline": [dict(x) for x in list(story_input.get("timeline") or lifecycle.get("timeline") or report.get("timeline") or []) if isinstance(x, dict)][:10],
    }


def _build_operator_brief_sections(detail: Dict[str, Any]) -> Dict[str, Any]:
    strategist = detail.get("strategist") if isinstance(detail.get("strategist"), dict) else {}
    scanner = detail.get("scanner") if isinstance(detail.get("scanner"), dict) else {}
    monitor = detail.get("monitor") if isinstance(detail.get("monitor"), dict) else {}
    supervisor = detail.get("supervisor") if isinstance(detail.get("supervisor"), dict) else {}
    executor = detail.get("executor") if isinstance(detail.get("executor"), dict) else {}
    reporter = detail.get("reporter") if isinstance(detail.get("reporter"), dict) else {}
    trade_report = detail.get("trade_report") if isinstance(detail.get("trade_report"), dict) else {}
    canonical_trade = _build_canonical_trade_brief_input(trade_report)

    strategist_summary = strategist.get("summary") if isinstance(strategist.get("summary"), dict) else {}
    strategist_trace = strategist.get("decision_trace") if isinstance(strategist.get("decision_trace"), dict) else {}
    strategist_evidence = strategist.get("evidence") if isinstance(strategist.get("evidence"), dict) else {}
    strategist_raw_input = strategist_evidence.get("raw_input") if isinstance(strategist_evidence.get("raw_input"), dict) else {}

    scanner_summary = scanner.get("summary") if isinstance(scanner.get("summary"), dict) else {}
    scanner_trace = scanner.get("decision_trace") if isinstance(scanner.get("decision_trace"), dict) else {}
    selected_candidate = scanner_trace.get("selected_candidate") if isinstance(scanner_trace.get("selected_candidate"), dict) else {}
    feature_snapshot = selected_candidate.get("feature_snapshot") if isinstance(selected_candidate.get("feature_snapshot"), dict) else {}
    score_breakdown = selected_candidate.get("score_breakdown") if isinstance(selected_candidate.get("score_breakdown"), dict) else {}
    source_scores = selected_candidate.get("source_scores") if isinstance(selected_candidate.get("source_scores"), dict) else {}
    feature_coverage = scanner.get("feature_coverage") if isinstance(scanner.get("feature_coverage"), dict) else _feature_coverage(feature_snapshot)
    quote_metrics = scanner.get("quote_metrics") if isinstance(scanner.get("quote_metrics"), dict) else _quote_metrics_snapshot(feature_snapshot)

    monitor_summary = monitor.get("summary") if isinstance(monitor.get("summary"), dict) else {}
    monitor_trace = monitor.get("decision_trace") if isinstance(monitor.get("decision_trace"), dict) else {}
    thresholds = monitor_trace.get("thresholds") if isinstance(monitor_trace.get("thresholds"), dict) else {}

    verdict = supervisor.get("verdict") if isinstance(supervisor.get("verdict"), dict) else {}
    execution = _normalize_execution_payload(executor.get("execution") if isinstance(executor.get("execution"), dict) else {})

    selected_symbol = normalize_symbol(
        canonical_trade.get("symbol")
        or execution.get("symbol")
        or scanner_trace.get("selected_symbol")
        or scanner_summary.get("top_stock")
        or selected_candidate.get("symbol")
        or "",
        allow_test_symbols=True,
    ).strip()
    top_candidates = _build_top_candidates(scanner_summary, scanner_trace, selected_symbol)
    selected_rank = _safe_int(
        canonical_trade.get("selected_rank"),
        next((int(row.get("rank") or 0) for row in top_candidates if str(row.get("symbol") or "") == selected_symbol), 0),
    )
    universe_size = _safe_int(
        canonical_trade.get("universe_size"),
        _safe_int(scanner_summary.get("candidate_pool_after_filter"), _safe_int(scanner_trace.get("candidate_pool_size"), len(top_candidates))),
    )

    execution_action = str(execution.get("action") or "").upper()
    canonical_action = str(canonical_trade.get("current_action") or "").upper()
    monitor_reason = str(canonical_trade.get("monitor_summary") or monitor_summary.get("monitor_reason") or monitor_trace.get("monitor_reason") or "").strip()
    exit_reason = str(canonical_trade.get("exit_reason") or monitor_summary.get("exit_reason") or monitor_trace.get("exit_reason") or "").strip()
    if canonical_action in {"BUY", "SELL", "HOLD", "WAIT"}:
        final_action = canonical_action
    elif execution_action in {"BUY", "SELL"}:
        final_action = execution_action
    elif not selected_symbol:
        final_action = "WAIT"
    elif "hold" in exit_reason.lower() or "hold" in monitor_reason.lower():
        final_action = "HOLD"
    elif monitor_reason.lower() == "no_position":
        final_action = "WAIT"
    else:
        final_action = "HOLD"

    confidence_raw = (
        selected_candidate.get("confidence")
        if selected_candidate.get("confidence") is not None
        else selected_candidate.get("score_total")
    )
    confidence = _format_float(confidence_raw, 2) if confidence_raw is not None else ""

    selection_reasons: List[str] = []
    selected_why = _clean_brief_text(selected_candidate.get("why") or scanner_trace.get("selected_reason") or "")
    if canonical_trade.get("selection_summary"):
        selection_reasons.append(str(canonical_trade.get("selection_summary")))
    if selected_why and selected_why not in selection_reasons:
        selection_reasons.append(selected_why)
    for bullet in list(canonical_trade.get("selection_bullets") or [])[:4]:
        if bullet not in selection_reasons:
            selection_reasons.append(bullet)
    if feature_coverage.get("total"):
        selection_reasons.append(
            f"chart feature coverage {feature_coverage.get('present')}/{feature_coverage.get('total')} ({feature_coverage.get('quality') or '-'})"
        )
    if quote_metrics.get("quote_trading_value") is not None:
        selection_reasons.append("acceptable turnover and tradability")
    if strategist_summary.get("playbook"):
        selection_reasons.append(f"aligned with playbook {strategist_summary.get('playbook')}")

    comparison_reasons: List[str] = []
    if len(top_candidates) >= 2:
        for row in top_candidates[1:3]:
            reason = _clean_brief_text(row.get("reason"))
            if reason:
                comparison_reasons.append(f"{row.get('symbol')} was weaker: {reason}")
        if not comparison_reasons:
            comparison_reasons.append("other candidates had lower composite rank or weaker feature coverage")
    else:
        comparison_reasons.append("only one ranked candidate was persisted for this run")

    global_inputs = strategist_raw_input.get("global_sentiment_inputs") if isinstance(strategist_raw_input.get("global_sentiment_inputs"), dict) else {}
    fear_index = global_inputs.get("fear_index") if isinstance(global_inputs.get("fear_index"), dict) else {}
    macro_moves = global_inputs.get("macro_moves") if isinstance(global_inputs.get("macro_moves"), dict) else {}
    global_score = canonical_trade.get("global_sentiment") or global_inputs.get("score")
    vix_level = canonical_trade.get("vix") or fear_index.get("level")
    market_news_titles = [str((x or {}).get("title") or "") for x in list(strategist_raw_input.get("collected_market_news") or []) if isinstance(x, dict)]
    news_targets = list(strategist_summary.get("news_query_targets") or strategist_raw_input.get("news_query_targets") or [])
    macro_stress_overlay = strategist_trace.get("macro_stress_overlay") if isinstance(strategist_trace.get("macro_stress_overlay"), dict) else {}
    defensive_mode = bool(macro_stress_overlay.get("active")) or str(strategist_summary.get("playbook") or "").lower() == "defensive" or (_safe_float(vix_level, 0.0) >= 25.0 if vix_level is not None else False)
    if canonical_trade.get("market_context_summary"):
        news_summary = str(canonical_trade.get("market_context_summary"))
    elif market_news_titles:
        news_summary = "; ".join([title for title in market_news_titles[:2] if title]) or "market news sampled"
    elif news_targets:
        news_summary = "no strong market-moving headline was retained in this run"
    else:
        news_summary = "no meaningful news input was captured"

    detected_themes = _clean_brief_list(canonical_trade.get("themes") or strategist_summary.get("themes"), limit=6)
    theme_match = _clean_brief_text(
        selected_candidate.get("theme_match")
        or selected_candidate.get("sector_theme")
        or selected_candidate.get("theme")
        or ""
    )
    if not theme_match and selected_why and detected_themes:
        lowered = selected_why.lower()
        for theme in detected_themes:
            if str(theme).lower() in lowered:
                theme_match = theme
                break
    if detected_themes and theme_match:
        priority_alignment = "yes"
        theme_priority = "high-priority theme"
    elif detected_themes and selected_symbol:
        priority_alignment = "partial"
        theme_priority = "fallback theme match"
    elif detected_themes:
        priority_alignment = "unknown"
        theme_priority = "theme detected but symbol linkage unavailable"
    else:
        priority_alignment = "no"
        theme_priority = "no explicit theme detected"

    sector_strength = feature_snapshot.get("engine_sector_relative_strength")
    sentiment_gate_status = "SKIPPED"
    sentiment_gate_note = "sentiment input not available"
    if global_score is not None:
        sentiment_gate_status = "PASS" if _safe_float(global_score, 0.0) >= -0.35 else "FAIL"
        sentiment_gate_note = f"global sentiment {_format_float(global_score, 2)}"

    liquidity_status = "SKIPPED"
    liquidity_note = "quote volume not available"
    if quote_metrics.get("quote_volume") is not None:
        liquidity_status = "PASS" if _safe_float(quote_metrics.get("quote_volume"), 0.0) > 0 else "FAIL"
        liquidity_note = f"quote volume {quote_metrics.get('quote_volume')}"

    turnover_status = "SKIPPED"
    turnover_note = "turnover metric not available"
    if quote_metrics.get("quote_trading_value") is not None:
        turnover_status = "PASS" if _safe_float(quote_metrics.get("quote_trading_value"), 0.0) > 0 else "FAIL"
        turnover_note = f"trading value {quote_metrics.get('quote_trading_value')}"

    sector_status = "SKIPPED"
    sector_note = "sector relative strength not available"
    if sector_strength is not None:
        sector_status = "PASS" if _safe_float(sector_strength, 0.0) >= 0 else "FAIL"
        sector_note = f"sector relative strength {_format_float(sector_strength, 2)}"

    coverage_ratio = _safe_float(feature_coverage.get("coverage_ratio"), 0.0)
    if _safe_int(feature_coverage.get("total"), 0) <= 0:
        chart_status = "SKIPPED"
        chart_note = "feature snapshot not available"
    elif coverage_ratio >= 0.75:
        chart_status = "PASS"
        chart_note = f"{feature_coverage.get('present')}/{feature_coverage.get('total')} filled"
    elif coverage_ratio >= 0.5:
        chart_status = "PARTIAL"
        chart_note = f"{feature_coverage.get('present')}/{feature_coverage.get('total')} filled"
    else:
        chart_status = "FAIL"
        chart_note = f"{feature_coverage.get('present')}/{feature_coverage.get('total')} filled"

    risk_status = "PASS" if bool(verdict.get("allowed")) else "FAIL"
    risk_note = str(verdict.get("reason") or ("order allowed" if risk_status == "PASS" else "order blocked"))

    change_pct = quote_metrics.get("intraday_change_pct")
    anomaly_status = "SKIPPED"
    anomaly_note = "intraday change metric not available"
    if change_pct is not None:
        anomaly_status = "PASS" if abs(_safe_float(change_pct, 0.0)) <= 12.0 else "FAIL"
        anomaly_note = f"intraday change {_format_percent(change_pct, 2)}"

    spread_bps = selected_candidate.get("spread_bps")
    spread_status = "SKIPPED"
    spread_note = "spread/slippage metric not available in this run"
    if spread_bps is not None:
        spread_status = "PASS" if _safe_float(spread_bps, 9999.0) <= 50.0 else "FAIL"
        spread_note = f"spread {spread_bps} bps"

    ranking_basis: List[str] = []
    for key in list(score_breakdown.keys())[:6]:
        ranking_basis.append(_friendly_feature_name(key))
    if not ranking_basis:
        for key in list(source_scores.keys())[:6]:
            ranking_basis.append(str(key).replace("_", " "))
    if not ranking_basis:
        ranking_basis = ["trading value", "volume", "sector strength", "chart feature coverage"]

    component_scores: List[str] = []
    for key, value in list(score_breakdown.items())[:6]:
        component_scores.append(f"{_friendly_feature_name(str(key))}: {_format_float(value, 3)}")
    if not component_scores:
        for key, value in list(source_scores.items())[:6]:
            component_scores.append(f"{str(key).replace('_', ' ')}: {_format_float(value, 3)}")

    positive_factors: List[str] = []
    if selected_why:
        positive_factors.append(selected_why)
    if _safe_float(quote_metrics.get("quote_trading_value"), 0.0) > 0:
        positive_factors.append("strong tradable turnover")
    if chart_status == "PASS":
        positive_factors.append("robust chart feature coverage")
    if sector_status == "PASS":
        positive_factors.append("sector alignment is acceptable")
    if not positive_factors:
        positive_factors.append("selected symbol retained highest available composite rank")

    weak_factors: List[str] = []
    missing_keys = list(feature_coverage.get("missing_keys") or [])
    if missing_keys:
        weak_factors.append(
            "missing features: " + ", ".join(_friendly_feature_name(k) for k in missing_keys[:2])
        )
    volatility20 = feature_snapshot.get("engine_volatility20")
    if volatility20 is not None and _safe_float(volatility20, 0.0) >= 0.3:
        weak_factors.append("elevated short-term volatility remains")
    if sentiment_gate_status == "FAIL":
        weak_factors.append("negative global sentiment requires tighter monitoring")
    if not weak_factors:
        weak_factors.append("no major weakness persisted in this run snapshot")

    present_feature_names = [_friendly_feature_name(k) for k in list(feature_coverage.get("present_keys") or [])[:6]]
    missing_feature_names = [_friendly_feature_name(k) for k in missing_keys[:4]]
    if chart_status == "PASS":
        chart_interpretation = "feature coverage is robust enough for scanner ranking confidence"
    elif chart_status == "PARTIAL":
        chart_interpretation = "feature coverage is usable but needs caution on weaker technical inputs"
    else:
        chart_interpretation = "feature coverage is insufficient; treat selection confidence conservatively"

    stop_loss = thresholds.get("stop_loss_pct")
    take_profit = thresholds.get("take_profit_pct")
    if stop_loss is None:
        stop_loss = thresholds.get("stop_loss")
    if take_profit is None:
        take_profit = thresholds.get("take_profit")
    stop_loss_text = _format_percent(stop_loss, 2) if stop_loss is not None else "-"
    take_profit_text = _format_percent(take_profit, 2) if take_profit is not None else "-"
    holding_time = _format_duration(monitor_summary.get("position_age_seconds") or monitor_trace.get("position_age_seconds"))

    hold_reasons: List[str] = []
    if final_action == "HOLD":
        hold_reasons.append("no explicit exit trigger was hit yet")
        hold_reasons.append(f"monitor reason: {monitor_reason or '-'} / exit reason: {exit_reason or '-'}")
    elif final_action == "WAIT":
        hold_reasons.append("entry is waiting because no active position or execution signal is confirmed")
        hold_reasons.append(f"monitor reason: {monitor_reason or '-'}")
    elif final_action == "BUY":
        hold_reasons.append("scanner selection passed gating and execution was approved")
    elif final_action == "SELL":
        hold_reasons.append("monitor/supervisor flow reached sell execution condition")
    if chart_status in {"PASS", "PARTIAL"}:
        hold_reasons.append(f"chart coverage state: {feature_coverage.get('quality') or '-'}")

    exit_triggers = [
        "stop-loss breach",
        "take-profit hit",
        "monitor quality deterioration",
    ]
    if stop_loss_text != "-" or take_profit_text != "-":
        exit_triggers = [
            f"stop-loss trigger ({stop_loss_text})" if stop_loss_text != "-" else "stop-loss trigger",
            f"take-profit trigger ({take_profit_text})" if take_profit_text != "-" else "take-profit trigger",
            "risk gate failure or abnormal volatility expansion",
        ]

    prefer_runtime_reporter = _prefer_runtime_reporter_state(reporter)
    reporter_found = bool(reporter.get("found")) if prefer_runtime_reporter else (
        bool(reporter.get("found")) or str(canonical_trade.get("reporter_status") or "").strip().lower() == "linked"
    )
    reporter_reason_key = str(reporter.get("reason") or "").strip()
    if reporter_found:
        reporter_status = "linked"
        reporter_reason = "same-day reporter analysis is linked to this run"
    elif reporter_reason_key == "same_day_report_missing":
        reporter_status = "pending"
        reporter_reason = "same-day reporter analysis file is not generated yet"
    elif reporter_reason_key == "run_not_linked_in_same_day_report":
        reporter_status = "pending"
        reporter_reason = "same-day reporter analysis exists, but this run_id is not linked yet"
    else:
        reporter_status = "missing"
        reporter_reason = "reporter linkage is unavailable for this run"

    run_grade = str((reporter.get("ai_run_grade") if prefer_runtime_reporter else "") or canonical_trade.get("reporter_grade") or reporter.get("ai_run_grade") or "").strip()
    ai_summary = str((reporter.get("ai_summary") if prefer_runtime_reporter else "") or canonical_trade.get("reporter_summary") or reporter.get("ai_summary") or "").strip()
    strategy_alignment = "strategy frame and scanner trace were captured"
    execution_quality = "execution log present" if execution_action in {"BUY", "SELL"} else "no executed order in this run"
    monitor_consistency = f"monitor={monitor_reason or '-'} / exit={exit_reason or '-'}"
    if reporter_found:
        trade_quality = f"grade {run_grade}" if run_grade else "grade not provided"
        key_finding = ai_summary or "reporter summary exists but key finding text is empty"
    else:
        trade_quality = "post-trade quality grade is pending"
        key_finding = ai_summary or reporter_reason

    if canonical_trade.get("report_summary"):
        decision_reason = str(canonical_trade.get("report_summary"))
    elif final_action == "BUY":
        decision_reason = (
            f"scanner rank #{selected_rank or 1} out of {max(universe_size, 1)} with strong selection factors, "
            f"chart coverage {feature_coverage.get('present')}/{feature_coverage.get('total')}, and approved execution."
        )
    elif final_action == "SELL":
        decision_reason = (
            f"monitor/supervisor flow triggered SELL for {selected_symbol or '-'} "
            f"after exit condition review ({exit_reason or monitor_reason or 'triggered'})."
        )
    elif final_action == "HOLD":
        decision_reason = (
            f"scanner rank #{selected_rank or 1} candidate is retained with chart coverage "
            f"{feature_coverage.get('present')}/{feature_coverage.get('total')}, and no active exit trigger yet."
        )
    else:
        decision_reason = (
            f"no executable BUY/SELL action yet; waiting for entry confirmation while monitoring {selected_symbol or 'candidate'}."
        )

    watch_next: List[str] = []
    if take_profit_text != "-":
        watch_next.append(f"take-profit proximity ({take_profit_text})")
    if stop_loss_text != "-":
        watch_next.append(f"stop-loss proximity ({stop_loss_text})")
    if vix_level is not None:
        watch_next.append(f"volatility trend (VIX {_format_float(vix_level, 2)})")
    if detected_themes:
        watch_next.append(f"theme strength drift ({', '.join(detected_themes[:2])})")
    if not watch_next:
        watch_next = ["entry/exit trigger activation", "volatility expansion", "sector weakness"]

    thesis_invalidation = [
        "stop-loss breach or abnormal drawdown",
        "scanner and monitor signal divergence",
        "negative macro/news regime shift",
    ]

    report_available = bool(trade_report.get("report_available"))
    report_diag = (
        trade_report.get("ai_report_diagnostics")
        if isinstance(trade_report.get("ai_report_diagnostics"), dict)
        else {}
    )
    report_status = str(
        report_diag.get("report_status")
        or trade_report.get("report_status")
        or ("available" if report_available else "skipped")
    ).strip().lower()
    report_reason = str(
        report_diag.get("report_reason_human")
        or trade_report.get("report_reason_human")
        or _report_reason_human(trade_report.get("report_reason_code"))
    ).strip()
    report_next_step = str(
        report_diag.get("next_expected_step")
        or trade_report.get("report_next_expected_step")
        or _report_next_step(trade_report.get("report_reason_code"))
    ).strip()
    report_model = str(
        report_diag.get("llm_model_used")
        or trade_report.get("report_generation_model")
        or "-"
    ).strip()
    report_trade_id = str(trade_report.get("trade_id") or "")
    report_lifecycle_status = str(trade_report.get("lifecycle_status") or "")
    report_lifecycle_summary = str(trade_report.get("lifecycle_summary") or "")
    report_story_type = str(trade_report.get("story_type_label") or trade_report.get("story_type") or "No linked report")
    report_mode = str(trade_report.get("execution_mode_label") or "-")
    report_summary = str(trade_report.get("report_summary") or "")
    report_link = str(trade_report.get("report_link") or "")

    macro_summary: List[str] = []
    if macro_moves.get("dxy_pct") is not None:
        macro_summary.append(f"DXY change {_format_percent(macro_moves.get('dxy_pct'), 2)}")
    if macro_moves.get("tnx_delta") is not None:
        macro_summary.append(f"US10Y delta {_format_float(macro_moves.get('tnx_delta'), 3)}")
    for bullet in list(canonical_trade.get("market_context_bullets") or [])[:4]:
        if bullet not in macro_summary:
            macro_summary.append(bullet)

    filter_rows = list(canonical_trade.get("filter_rows") or [])
    if filter_rows:
        filters_and_gates = filter_rows[:8]
    else:
        filters_and_gates = [
            {"name": "Liquidity filter", "status": liquidity_status, "note": liquidity_note},
            {"name": "Turnover filter", "status": turnover_status, "note": turnover_note},
            {"name": "Sector strength filter", "status": sector_status, "note": sector_note},
            {"name": "Chart completeness filter", "status": chart_status, "note": chart_note},
            {"name": "Sentiment gate", "status": sentiment_gate_status, "note": sentiment_gate_note},
            {"name": "Risk gate", "status": risk_status, "note": risk_note},
            {"name": "Price anomaly filter", "status": anomaly_status, "note": anomaly_note},
            {"name": "Spread/slippage filter", "status": spread_status, "note": spread_note},
        ]

    hold_reason_rows = list(canonical_trade.get("monitor_bullets") or [])
    if hold_reason_rows:
        hold_reasons = hold_reason_rows[:4]

    return {
        "executive_decision": {
            "final_action": final_action,
            "symbol": selected_symbol or "-",
            "reason": decision_reason,
            "confidence": confidence,
            "selected_rank": selected_rank or None,
            "universe_size": universe_size or None,
        },
        "why_symbol_chosen": {
            "selected": bool(selected_symbol),
            "universe_size": universe_size or None,
            "selected_rank": selected_rank or None,
            "selection_reasons": selection_reasons or ["selection rationale was not explicitly persisted"],
            "comparison_reasons": comparison_reasons,
            "top_candidates": top_candidates[:3],
        },
        "market_context": {
            "market_regime": str(canonical_trade.get("market_regime") or strategist_summary.get("market_regime") or strategist_trace.get("market_regime") or "-"),
            "global_sentiment": _format_float(global_score, 2) if global_score is not None else "-",
            "vix": _format_float(vix_level, 2) if vix_level is not None else "-",
            "macro_summary": macro_summary,
            "news_summary": news_summary,
            "news_targets": _clean_brief_list(news_targets, limit=6),
            "defensive_mode": "enabled" if defensive_mode else "disabled",
        },
        "theme_detection": {
            "detected_themes": detected_themes,
            "symbol_theme_match": theme_match or "not explicitly tagged",
            "priority_alignment": priority_alignment,
            "theme_priority_bucket": theme_priority,
        },
        "filters_and_gates": filters_and_gates,
        "scanner_ranking_explanation": {
            "ranking_basis": ranking_basis,
            "component_scores": component_scores,
            "tie_break_rule": str(scanner_trace.get("tie_break_rule") or "higher composite score, then stronger feature coverage"),
            "positive_factors": positive_factors[:5],
            "weak_factors": weak_factors[:4],
        },
        "chart_feature_coverage": {
            "present": _safe_int(feature_coverage.get("present"), 0),
            "total": _safe_int(feature_coverage.get("total"), 0),
            "quality": str(feature_coverage.get("quality") or "missing"),
            "confirmed_features": present_feature_names,
            "missing_features": missing_feature_names,
            "interpretation": chart_interpretation,
        },
        "position_monitor_reasoning": {
            "posture": final_action,
            "holding_time": holding_time,
            "stop_loss": stop_loss_text,
            "take_profit": take_profit_text,
            "hold_reasons": hold_reasons[:4],
            "exit_triggers": exit_triggers[:3],
        },
        "reporter_evaluation": {
            "status": reporter_status,
            "reason": reporter_reason,
            "strategy_alignment": strategy_alignment,
            "execution_quality": execution_quality,
            "monitor_consistency": monitor_consistency,
            "run_grade": run_grade or "-",
            "trade_quality": trade_quality,
            "key_finding": key_finding,
        },
        "ai_trade_report": {
            "status": report_status,
            "status_label": _report_status_label(report_status),
            "status_badge_class": _report_status_badge_class(report_status),
            "reason": report_reason or "AI report diagnostics were not captured.",
            "next_step": report_next_step or "Continue with Operator Brief while report diagnostics are resolved.",
            "model": report_model or "-",
            "available": report_available,
            "trade_id": report_trade_id,
            "lifecycle_status": report_lifecycle_status or "-",
            "lifecycle_summary": report_lifecycle_summary or "-",
            "story_type": report_story_type,
            "execution_mode_label": report_mode,
            "summary": report_summary or "No per-trade AI report is linked to this run yet.",
            "link": report_link,
        },
        "operator_conclusion": {
            "current_action": final_action,
            "watch_next": watch_next[:4],
            "thesis_invalidation": thesis_invalidation,
        },
    }


def _attach_operator_brief_sections(brief: Dict[str, Any], detail: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(brief or {})
    out["sections"] = _build_operator_brief_sections(detail)
    return out





def _fallback_operator_brief(detail: Dict[str, Any]) -> Dict[str, Any]:
    trade_report = detail.get("trade_report") if isinstance(detail.get("trade_report"), dict) else {}
    canonical_trade = _build_canonical_trade_brief_input(trade_report)
    strategist = detail.get("strategist") if isinstance(detail.get("strategist"), dict) else {}
    strategist_summary = strategist.get("summary") if isinstance(strategist.get("summary"), dict) else {}
    strategist_evidence = strategist.get("evidence") if isinstance(strategist.get("evidence"), dict) else {}
    raw_input = strategist_evidence.get("raw_input") if isinstance(strategist_evidence.get("raw_input"), dict) else {}
    global_inputs = raw_input.get("global_sentiment_inputs") if isinstance(raw_input.get("global_sentiment_inputs"), dict) else {}
    fear_index = global_inputs.get("fear_index") if isinstance(global_inputs.get("fear_index"), dict) else {}
    scanner = detail.get("scanner") if isinstance(detail.get("scanner"), dict) else {}
    scanner_summary = scanner.get("summary") if isinstance(scanner.get("summary"), dict) else {}
    scanner_trace = scanner.get("decision_trace") if isinstance(scanner.get("decision_trace"), dict) else {}
    selected = (scanner_trace.get("selected_candidate") or {}) if isinstance(scanner_trace.get("selected_candidate"), dict) else {}
    monitor = detail.get("monitor") if isinstance(detail.get("monitor"), dict) else {}
    monitor_summary = monitor.get("summary") if isinstance(monitor.get("summary"), dict) else {}
    monitor_trace = monitor.get("decision_trace") if isinstance(monitor.get("decision_trace"), dict) else {}
    supervisor = (detail.get("supervisor") or {}).get("verdict") if isinstance(detail.get("supervisor"), dict) else {}
    executor = (detail.get("executor") or {}).get("execution") if isinstance(detail.get("executor"), dict) else {}
    reporter = detail.get("reporter") if isinstance(detail.get("reporter"), dict) else {}
    prefer_runtime_reporter = _prefer_runtime_reporter_state(reporter)

    global_bits: List[str] = []
    if global_inputs.get("score") is not None:
        global_bits.append(f"\uae00\ub85c\ubc8c \uac10\uc131 \uc810\uc218={_safe_float(global_inputs.get('score'), 0.0):.2f}")
    if fear_index.get("level") is not None:
        global_bits.append(f"VIX={_safe_float(fear_index.get('level'), 0.0):.2f}")
    macro_moves = global_inputs.get("macro_moves") if isinstance(global_inputs.get("macro_moves"), dict) else {}
    if macro_moves.get("dxy_pct") is not None:
        global_bits.append(f"\ub2ec\ub7ec\uc9c0\uc218={_safe_float(macro_moves.get('dxy_pct'), 0.0):.2f}")

    feature_coverage = scanner.get("feature_coverage") if isinstance(scanner.get("feature_coverage"), dict) else {}
    quote_metrics = scanner.get("quote_metrics") if isinstance(scanner.get("quote_metrics"), dict) else {}
    canonical_market_summary = str(canonical_trade.get("market_context_summary") or "").strip()
    canonical_selection_summary = str(canonical_trade.get("selection_summary") or "").strip()
    canonical_monitor_summary = str(canonical_trade.get("monitor_summary") or "").strip()
    canonical_guard_summary = str(canonical_trade.get("guard_summary") or "").strip()
    canonical_execution_summary = str(canonical_trade.get("execution_summary") or "").strip()
    canonical_reporter_summary = str(canonical_trade.get("reporter_summary") or "").strip()
    canonical_lifecycle_summary = str(canonical_trade.get("lifecycle_summary") or "").strip()
    canonical_report_summary = str(canonical_trade.get("report_summary") or "").strip()
    headline = (
        str(canonical_trade.get("headline") or "").strip()
        or f"{detail.get('run_id') or '-'} 운영 요약"
    )

    return {
        "status": "fallback",
        "model": "",
        "headline": headline,
        "commander_summary": (
            f"\uc9c0\ud718\uc790\ub294 {((detail.get('commander') or {}).get('phase') or '-')} phase\uc5d0\uc11c "
            f"{((detail.get('commander') or {}).get('path') or '-')} \uacbd\ub85c\ub97c \uc2e4\ud589\ud588\uc2b5\ub2c8\ub2e4."
        ),
        "strategist_summary": (
            canonical_market_summary
            or (
                f"\uc804\ub7b5\uac00\ub294 {', '.join(global_bits) or '\uc2dc\uc7a5 \uc785\ub825'}\uc744 \ucc38\uace0\ud558\uace0, \ub274\uc2a4 \uc9c8\uc758 "
                f"{', '.join(_clean_brief_list(strategist_summary.get('news_query_targets'), limit=6)) or '-'}\ub85c \ubd84\uc704\uae30\ub97c \ud655\uc778\ud55c \ub4a4 "
                f"\ud14c\ub9c8 {', '.join(_clean_brief_list(strategist_summary.get('themes'), limit=4)) or '-'}, "
                f"\ud50c\ub808\uc774\ubd81 {strategist_summary.get('playbook') or '-'}\ub85c \uc815\ub9ac\ud588\uc2b5\ub2c8\ub2e4."
            )
        ),
        "scanner_summary": (
            canonical_selection_summary
            or (
                f"\uc2a4\uce90\ub108\ub294 Kiwoom \ud6c4\ubcf4 {int(scanner_summary.get('candidate_pool_after_filter') or 0)}\uac1c \uc911 "
                f"{_clean_brief_text(scanner_summary.get('top_stock') or selected.get('symbol') or '-')}\ub97c 1\ub4f1\uc73c\ub85c \uace8\ub790\uace0 \uc774\uc720\ub294 "
                f"{selected.get('why') or '-'}\uc785\ub2c8\ub2e4."
            )
        ),
        "monitor_summary": (
            canonical_monitor_summary
            or (
                f"\ubaa8\ub2c8\ud130\ub294 {monitor_summary.get('monitor_reason') or monitor_trace.get('monitor_reason') or '-'} \uc0c1\ud0dc\ub97c \ubcf4\uace0, "
                f"exit={monitor_summary.get('exit_reason') or monitor_trace.get('exit_reason') or '-'}\ub85c \ud310\ub2e8\ud588\uc2b5\ub2c8\ub2e4."
            )
        ),
        "supervisor_summary": (
            canonical_guard_summary
            or f"\uac10\ub3c5\uad00\uc740 allowed={supervisor.get('allowed')} / reason={supervisor.get('reason') or '-'}\ub85c \uacb0\ub860\ub0c8\uc2b5\ub2c8\ub2e4."
        ),
        "executor_summary": (
            canonical_execution_summary
            or (
                f"\uc218\ud589\uc790\ub294 {executor.get('action') or 'NOOP'} {executor.get('symbol') or ''} "
                f"status={executor.get('fill_status_summary') or executor.get('status') or '-'}\ub85c \ub9c8\ubb34\ub9ac\ud588\uc2b5\ub2c8\ub2e4."
            )
        ),
        "reporter_summary": (
            ("" if prefer_runtime_reporter else canonical_reporter_summary)
            or (
                f"\ub9ac\ud3ec\ud130\ub294 grade={reporter.get('ai_run_grade') or '-'} / "
                f"summary={reporter.get('ai_summary') or '\uac19\uc740 \ub0a0\uc9dc reporter \uc694\uc57d\uc774 \uc544\uc9c1 \uc5c6\uc2b5\ub2c8\ub2e4.'}"
            )
        ),
        "operator_takeaways": [
            canonical_market_summary or f"\ub274\uc2a4/\uac70\uc2dc \uc785\ub825: {', '.join(global_bits) or '\uc2dc\uc7a5 \uc785\ub825 \uc5c6\uc74c'}",
            str(canonical_trade.get("filters_summary") or "") or f"\ucc28\ud2b8/feature coverage: {feature_coverage.get('quality') or '-'} ({feature_coverage.get('present') or 0}/{feature_coverage.get('total') or 0})",
            canonical_lifecycle_summary or canonical_report_summary or f"\uc2e4\uc2dc\uac04 quote: \uac00\uaca9 {quote_metrics.get('skill_quote_price') or '-'} \uac70\ub798\ub7c9 {quote_metrics.get('quote_volume') or '-'} \uac70\ub798\ub300\uae08 {quote_metrics.get('quote_trading_value') or '-'}",
        ],
    }


def _build_operator_brief_input(detail: Dict[str, Any]) -> Dict[str, Any]:
    strategist = detail.get("strategist") if isinstance(detail.get("strategist"), dict) else {}
    scanner = detail.get("scanner") if isinstance(detail.get("scanner"), dict) else {}
    monitor = detail.get("monitor") if isinstance(detail.get("monitor"), dict) else {}
    commander = detail.get("commander") if isinstance(detail.get("commander"), dict) else {}
    reporter = detail.get("reporter") if isinstance(detail.get("reporter"), dict) else {}
    trade_report = detail.get("trade_report") if isinstance(detail.get("trade_report"), dict) else {}
    canonical_trade = _build_canonical_trade_brief_input(trade_report)
    prefer_runtime_reporter = _prefer_runtime_reporter_state(reporter)
    strategist_summary = strategist.get("summary") if isinstance(strategist.get("summary"), dict) else {}
    strategist_evidence = strategist.get("evidence") if isinstance(strategist.get("evidence"), dict) else {}
    raw_input = strategist_evidence.get("raw_input") if isinstance(strategist_evidence.get("raw_input"), dict) else {}
    scanner_trace = scanner.get("decision_trace") if isinstance(scanner.get("decision_trace"), dict) else {}
    selected = scanner_trace.get("selected_candidate") if isinstance(scanner_trace.get("selected_candidate"), dict) else {}
    score_breakdown = selected.get("score_breakdown") if isinstance(selected.get("score_breakdown"), dict) else {}
    component_snapshot = selected.get("component_snapshot") if isinstance(selected.get("component_snapshot"), dict) else {}
    feature_snapshot = selected.get("feature_snapshot") if isinstance(selected.get("feature_snapshot"), dict) else {}
    monitor_summary = monitor.get("summary") if isinstance(monitor.get("summary"), dict) else {}
    monitor_trace = monitor.get("decision_trace") if isinstance(monitor.get("decision_trace"), dict) else {}
    return {
        "run_id": detail.get("run_id"),
        "commander": {
            "mode": commander.get("mode"),
            "phase": commander.get("phase"),
            "path": commander.get("path"),
            "status": commander.get("status"),
        },
        "strategist": {
            "market_regime": canonical_trade.get("market_regime") or strategist_summary.get("market_regime"),
            "market_sentiment": canonical_trade.get("market_sentiment") or strategist_summary.get("market_sentiment"),
            "themes": list(canonical_trade.get("themes") or strategist_summary.get("themes") or [])[:5],
            "playbook": canonical_trade.get("playbook") or strategist_summary.get("playbook"),
            "scanner_bias": strategist_summary.get("scanner_bias"),
            "risk_tone": strategist_summary.get("risk_tone"),
            "monitor_guidance": strategist_summary.get("monitor_guidance"),
            "news_query_targets": list(strategist_summary.get("news_query_targets") or [])[:8],
            "news_query_reasoning": strategist_summary.get("news_query_reasoning"),
            "global_sentiment_inputs": raw_input.get("global_sentiment_inputs") if isinstance(raw_input.get("global_sentiment_inputs"), dict) else {},
            "market_news_titles": [str((x or {}).get("title") or "") for x in list(raw_input.get("collected_market_news") or [])[:4] if isinstance(x, dict)],
            "candidate_news_titles": [str((x or {}).get("title") or "") for x in list(raw_input.get("collected_candidate_news") or [])[:4] if isinstance(x, dict)],
            "llm_status": strategist_summary.get("llm_frame_status"),
            "llm_low_confidence": strategist_summary.get("llm_frame_low_confidence"),
            "canonical_summary": canonical_trade.get("market_context_summary"),
            "canonical_bullets": list(canonical_trade.get("market_context_bullets") or [])[:6],
        },
        "scanner": {
            "candidate_source": scanner.get("summary", {}).get("candidate_source") if isinstance(scanner.get("summary"), dict) else "",
            "candidate_pool_before_filter": (scanner.get("summary") or {}).get("candidate_pool_before_filter") if isinstance(scanner.get("summary"), dict) else None,
            "candidate_pool_after_filter": (scanner.get("summary") or {}).get("candidate_pool_after_filter") if isinstance(scanner.get("summary"), dict) else None,
            "top_ranked_symbols": list((scanner.get("summary") or {}).get("top_ranked_symbols") or [])[:5] if isinstance(scanner.get("summary"), dict) else [],
            "source_mix": scanner_trace.get("kiwoom_pool_source_mix") if isinstance(scanner_trace.get("kiwoom_pool_source_mix"), dict) else {},
            "selected_symbol": scanner_trace.get("selected_symbol") or selected.get("symbol"),
            "selected_reason": canonical_trade.get("selection_summary") or selected.get("why"),
            "source_scores": selected.get("source_scores") if isinstance(selected.get("source_scores"), dict) else {},
            "score_total": selected.get("score_total"),
            "confidence": selected.get("confidence"),
            "feature_coverage": scanner.get("feature_coverage") if isinstance(scanner.get("feature_coverage"), dict) else {},
            "quote_metrics": scanner.get("quote_metrics") if isinstance(scanner.get("quote_metrics"), dict) else {},
            "score_breakdown": score_breakdown,
            "component_snapshot": component_snapshot,
            "feature_snapshot": feature_snapshot,
            "canonical_bullets": list(canonical_trade.get("selection_bullets") or [])[:6],
            "canonical_filters_summary": canonical_trade.get("filters_summary"),
            "canonical_filter_bullets": list(canonical_trade.get("filter_bullets") or [])[:8],
        },
        "monitor": {
            "monitor_reason": canonical_trade.get("monitor_summary") or monitor_summary.get("monitor_reason") or monitor_trace.get("monitor_reason"),
            "exit_reason": canonical_trade.get("exit_reason") or monitor_summary.get("exit_reason") or monitor_trace.get("exit_reason"),
            "position_age_seconds": monitor_summary.get("position_age_seconds"),
            "thresholds": monitor_trace.get("thresholds") if isinstance(monitor_trace.get("thresholds"), dict) else {},
            "strategy_frame_adjustments": list(monitor_trace.get("strategy_frame_adjustments") or [])[:6],
            "exit_policy_guard_adjustments": list(monitor_trace.get("exit_policy_guard_adjustments") or [])[:6],
            "canonical_bullets": list(canonical_trade.get("monitor_bullets") or [])[:6],
        },
        "supervisor": {
            **((((detail.get("supervisor") or {}).get("verdict") or {}) if isinstance(detail.get("supervisor"), dict) else {})),
            "canonical_summary": canonical_trade.get("guard_summary"),
        },
        "executor": {
            **((((detail.get("executor") or {}).get("execution") or {}) if isinstance(detail.get("executor"), dict) else {})),
            "canonical_summary": canonical_trade.get("execution_summary"),
            "canonical_bullets": list(canonical_trade.get("execution_bullets") or [])[:6],
        },
        "reporter": {
            "ai_summary": reporter.get("ai_summary") if prefer_runtime_reporter else (canonical_trade.get("reporter_summary") or reporter.get("ai_summary")),
            "ai_run_grade": reporter.get("ai_run_grade") if prefer_runtime_reporter else (canonical_trade.get("reporter_grade") or reporter.get("ai_run_grade")),
            "found": reporter.get("found"),
            "status": canonical_trade.get("reporter_status"),
            "reason": reporter.get("reason"),
        },
        "trade_report": {
            "report_available": trade_report.get("report_available"),
            "trade_id": trade_report.get("trade_id"),
            "lifecycle_status": trade_report.get("lifecycle_status"),
            "lifecycle_summary": trade_report.get("lifecycle_summary"),
            "story_type": trade_report.get("story_type_label") or trade_report.get("story_type"),
            "execution_mode_label": trade_report.get("execution_mode_label"),
            "summary": trade_report.get("report_summary"),
            "reporter_status_human": trade_report.get("reporter_status_human"),
        },
        "canonical_trade": canonical_trade,
    }


def _build_operator_brief_messages(compact_input: Dict[str, Any]) -> List[Dict[str, str]]:
    contract = {
        "headline": "string",
        "commander_summary": "string",
        "strategist_summary": "string",
        "scanner_summary": "string",
        "monitor_summary": "string",
        "supervisor_summary": "string",
        "executor_summary": "string",
        "reporter_summary": "string",
        "operator_takeaways": ["string"],
    }
    system_prompt = (
        "\ub2f9\uc2e0\uc740 \ud2b8\ub808\uc774\ub529 \uc6b4\uc601 \ud654\uba74\uc6a9 \ud55c\uae00 \ube0c\ub9ac\ud504 \uc791\uc131\uae30\uc785\ub2c8\ub2e4. "
        "\uc6b4\uc601\uc790\uac00 \ud55c \ubc88\uc5d0 \uc774\ud574\ud560 \uc218 \uc788\ub3c4\ub85d \uc9e7\uace0 \uc815\ud655\ud558\uac8c \uc815\ub9ac\ud558\uc138\uc694. "
        "\ubc18\ub4dc\uc2dc JSON\ub9cc \ucd9c\ub825\ud558\uace0 \uc124\uba85\ubb38\uc774\ub098 \uc8fc\uc11d\uc740 \uc4f0\uc9c0 \ub9c8\uc138\uc694."
    )
    user_prompt = (
        "\uc544\ub798 \uc2e4\ud589 \uae30\ub85d\uc744 \ubc14\ud0d5\uc73c\ub85c \uc9c0\ud718\uc790, \uc804\ub7b5\uac00, \uc2a4\uce90\ub108, \ubaa8\ub2c8\ud130, \uac10\ub3c5\uad00, \uc218\ud589\uc790, \ub9ac\ud3ec\ud130\uac00 \uac01\uac01 \ubb34\uc5c7\uc744 \ud588\ub294\uc9c0 "
        "\uc6b4\uc601\uc790\uc5d0\uac8c \ubc14\ub85c \uc77d\ud788\ub294 \ud55c\uad6d\uc5b4\ub85c \uc694\uc57d\ud558\uc138\uc694.\n"
        "\ube0c\ub9ac\ud504\uc5d0\ub294 \ub2e4\uc74c\uc774 \ud3ec\ud568\ub3fc\uc57c \ud569\ub2c8\ub2e4.\n"
        "- canonical_trade.available=true \uba74 reports/trades \uc0b0\ucd9c\ubb3c(trade_story_input, trade_lifecycle, trade_report)\uc744 1\ucc28 source of truth\ub85c \uc0ac\uc6a9\ud558\uace0 run-level \ub85c\uadf8\ub294 \ube48\uce78 \ubcf4\uc644\uc5d0\ub9cc \uc0ac\uc6a9\n"
        "- \uc804\ub7b5\uac00\uac00 \uc5b4\ub5a4 \ub274\uc2a4/\uae00\ub85c\ubc8c \uac10\uc131/VIX/\uac70\uc2dc \uc785\ub825\uc744 \ubd24\ub294\uc9c0\n"
        "- \uc2a4\uce90\ub108\uac00 Kiwoom \ud6c4\ubcf4 \uc911 \uc5b4\ub5a4 \uc885\ubaa9\uc744 \uc65c 1\ub4f1\uc73c\ub85c \uace8\ub790\ub294\uc9c0\n"
        "- \ucc28\ud2b8/feature/\uc2e4\uc2dc\uac04 quote\uac00 \uc5bc\ub9c8\ub098 \ucc44\uc6cc\uc84c\ub294\uc9c0\n"
        "- \ubaa8\ub2c8\ud130\uac00 \uc65c hold/buy/sell/block \ud588\ub294\uc9c0\n"
        "- \uac10\ub3c5\uad00\uacfc \uc218\ud589\uc790\uc758 \ucd5c\uc885 \uacb0\ub860\n"
        "- \ub9ac\ud3ec\ud130\uc758 \uc0ac\ud6c4 \ud3c9\uac00\n"
        "\uac01 \ud56d\ubaa9\uc740 \uc9e7\uace0 \uba85\ud655\ud558\uac8c \uc4f0\uace0, \uc804\uccb4\ub294 120\uc790 \ub0b4\uc678 \ubb38\uc7a5 \uc704\uc8fc\ub85c \uc815\ub9ac\ud558\uc138\uc694.\n"
        "operator_takeaways\ub294 3\uac1c \uc774\ud558\ub85c \uc791\uc131\ud558\uc138\uc694.\n"
        f"\uacc4\uc57d: {json.dumps(contract, ensure_ascii=False)}\n"
        f"\uc785\ub825: {json.dumps(compact_input, ensure_ascii=False)}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _build_operator_brief_repair_messages(raw_text: str) -> List[Dict[str, str]]:
    contract = {
        "headline": "string",
        "commander_summary": "string",
        "strategist_summary": "string",
        "scanner_summary": "string",
        "monitor_summary": "string",
        "supervisor_summary": "string",
        "executor_summary": "string",
        "reporter_summary": "string",
        "operator_takeaways": ["string"],
    }
    return [
        {
            "role": "system",
            "content": (
                "\ub2f9\uc2e0\uc740 \ube0c\ub9ac\ud504 \ubcf5\uad6c\uae30\uc785\ub2c8\ub2e4. "
                "\uc785\ub825 \ud14d\uc2a4\ud2b8\ub97c \uacc4\uc57d\uc5d0 \ub9de\ub294 JSON \ud558\ub098\ub85c\ub9cc \uc815\ub9ac\ud558\uc138\uc694. "
                "\uc124\uba85\uc774\ub098 \uc8fc\uc11d \uc5c6\uc774 JSON \uac1d\uccb4\ub9cc \ucd9c\ub825\ud558\uc138\uc694."
            ),
        },
        {
            "role": "user",
            "content": (
                f"\uacc4\uc57d: {json.dumps(contract, ensure_ascii=False)}\n"
                f"\uc785\ub825: {raw_text}"
            ),
        },
    ]


def _build_operator_brief_line_messages(compact_input: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "\ub2f9\uc2e0\uc740 \ube0c\ub9ac\ud504 \ubcf5\uad6c\uae30\uc785\ub2c8\ub2e4. "
                "JSON\uc774 \uc5b4\ub824\uc6b0\uba74 \uc544\ub798 key:value \ud615\uc2dd\uc73c\ub85c\ub9cc \ub2f5\ud558\uc138\uc694. "
                "\ubd88\ud544\uc694\ud55c \uc11c\ub860 \uc5c6\uc774 \ud544\uc694\ud55c \uc904\ub9cc \ucd9c\ub825\ud558\uc138\uc694."
            ),
        },
        {
            "role": "user",
            "content": (
                "\ub2e4\uc74c \ud615\uc2dd\uc73c\ub85c\ub9cc \ub2f5\ud558\uc138\uc694:\n"
                "headline: ...\n"
                "commander_summary: ...\n"
                "strategist_summary: ...\n"
                "scanner_summary: ...\n"
                "monitor_summary: ...\n"
                "supervisor_summary: ...\n"
                "executor_summary: ...\n"
                "reporter_summary: ...\n"
                "operator_takeaways: item1 | item2 | item3\n"
                f"\uc785\ub825: {json.dumps(compact_input, ensure_ascii=False)}"
            ),
        },
    ]


def _load_operator_brief(detail: Dict[str, Any]) -> Dict[str, Any]:
    fallback = _fallback_operator_brief(detail)
    router = LLMRouter.from_env()
    if router.client is None:
        return fallback
    explicit_model = str(
        os.getenv("OPERATOR_UI_RUN_BRIEF_MODEL", "")
        or os.getenv("OPENROUTER_MODEL_OPERATOR_UI", "")
        or os.getenv("OPENROUTER_MODEL_REPORTER_INTRADAY", "")
        or ""
    ).strip()
    if hasattr(router, "resolve"):
        route = router.resolve("operator_ui", policy={"model": explicit_model} if explicit_model else None)
        model = str(getattr(route, "model", "") or explicit_model or "").strip()
    else:
        model = _normalize_role_model_name(
            explicit_model
            or os.getenv("OPENROUTER_DEFAULT_MODEL", "")
            or ""
        )
    compact_input = _build_operator_brief_input(detail)
    messages = _build_operator_brief_messages(compact_input)
    try:
        raw = router.chat(
            "operator_ui",
            messages,
            policy={
                "temperature": float(os.getenv("OPERATOR_UI_RUN_BRIEF_TEMPERATURE", "0.1")),
                "max_tokens": int(float(os.getenv("OPERATOR_UI_RUN_BRIEF_MAX_TOKENS", "700"))),
                "timeout_sec": int(float(os.getenv("OPERATOR_UI_RUN_BRIEF_TIMEOUT_SEC", "2"))),
                "response_format": {"type": "json_object"},
                **({"model": model} if model else {}),
            },
        )
    except Exception as exc:
        fallback["model"] = model
        fallback["reason"] = f"llm_error:{exc}"
        return fallback
    parsed = _extract_json_object(raw)
    if not parsed:
        if _is_free_model(model) and not str(raw or "").strip():
            fallback["status"] = "fallback"
            fallback["model"] = model
            fallback["reason"] = "free_model_empty_response"
            return fallback
        try:
            repair_raw = router.chat(
                "operator_ui",
                _build_operator_brief_repair_messages(raw),
                policy={
                    "temperature": 0.0,
                    "max_tokens": 600,
                    "timeout_sec": int(float(os.getenv("OPERATOR_UI_RUN_BRIEF_TIMEOUT_SEC", "2"))),
                    "response_format": {"type": "json_object"},
                    **({"model": model} if model else {}),
                },
            )
        except Exception:
            repair_raw = ""
        repaired = _extract_json_object(repair_raw)
        if repaired:
            return {
                "status": "repaired",
                "model": model,
                "headline": str(repaired.get("headline") or fallback.get("headline") or ""),
                "commander_summary": str(repaired.get("commander_summary") or fallback.get("commander_summary") or ""),
                "strategist_summary": str(repaired.get("strategist_summary") or fallback.get("strategist_summary") or ""),
                "scanner_summary": str(repaired.get("scanner_summary") or fallback.get("scanner_summary") or ""),
                "monitor_summary": str(repaired.get("monitor_summary") or fallback.get("monitor_summary") or ""),
                "supervisor_summary": str(repaired.get("supervisor_summary") or fallback.get("supervisor_summary") or ""),
                "executor_summary": str(repaired.get("executor_summary") or fallback.get("executor_summary") or ""),
                "reporter_summary": str(repaired.get("reporter_summary") or fallback.get("reporter_summary") or ""),
                "operator_takeaways": [str(x or "") for x in list(repaired.get("operator_takeaways") or [])[:5] if str(x or "").strip()] or list(fallback.get("operator_takeaways") or []),
                "reason": "llm_repair_pass",
            }
        if _is_free_model(model):
            salvaged = _salvage_operator_brief_fields(raw)
            if salvaged:
                return {
                    "status": "salvaged",
                    "model": model,
                    "headline": str(salvaged.get("headline") or fallback.get("headline") or ""),
                    "commander_summary": str(salvaged.get("commander_summary") or fallback.get("commander_summary") or ""),
                    "strategist_summary": str(salvaged.get("strategist_summary") or fallback.get("strategist_summary") or ""),
                    "scanner_summary": str(salvaged.get("scanner_summary") or fallback.get("scanner_summary") or ""),
                    "monitor_summary": str(salvaged.get("monitor_summary") or fallback.get("monitor_summary") or ""),
                    "supervisor_summary": str(salvaged.get("supervisor_summary") or fallback.get("supervisor_summary") or ""),
                    "executor_summary": str(salvaged.get("executor_summary") or fallback.get("executor_summary") or ""),
                    "reporter_summary": str(salvaged.get("reporter_summary") or fallback.get("reporter_summary") or ""),
                    "operator_takeaways": [str(x or "") for x in list(salvaged.get("operator_takeaways") or [])[:5] if str(x or "").strip()] or list(fallback.get("operator_takeaways") or []),
                    "reason": "free_model_salvage_pass",
                }
            try:
                line_raw = router.chat(
                    "operator_ui",
                    _build_operator_brief_line_messages(compact_input),
                    policy={
                        "temperature": 0.0,
                        "max_tokens": 500,
                        "timeout_sec": int(float(os.getenv("OPERATOR_UI_RUN_BRIEF_TIMEOUT_SEC", "2"))),
                        **({"model": model} if model else {}),
                    },
                )
            except Exception:
                line_raw = ""
            line_parsed = _parse_operator_brief_lines(line_raw)
            if line_parsed:
                return {
                    "status": "line_repaired",
                    "model": model,
                    "headline": str(line_parsed.get("headline") or fallback.get("headline") or ""),
                    "commander_summary": str(line_parsed.get("commander_summary") or fallback.get("commander_summary") or ""),
                    "strategist_summary": str(line_parsed.get("strategist_summary") or fallback.get("strategist_summary") or ""),
                    "scanner_summary": str(line_parsed.get("scanner_summary") or fallback.get("scanner_summary") or ""),
                    "monitor_summary": str(line_parsed.get("monitor_summary") or fallback.get("monitor_summary") or ""),
                    "supervisor_summary": str(line_parsed.get("supervisor_summary") or fallback.get("supervisor_summary") or ""),
                    "executor_summary": str(line_parsed.get("executor_summary") or fallback.get("executor_summary") or ""),
                    "reporter_summary": str(line_parsed.get("reporter_summary") or fallback.get("reporter_summary") or ""),
                    "operator_takeaways": [str(x or "") for x in list(line_parsed.get("operator_takeaways") or [])[:5] if str(x or "").strip()] or list(fallback.get("operator_takeaways") or []),
                    "reason": "llm_line_repair_pass",
                }
        salvaged = _salvage_operator_brief_fields(raw)
        if salvaged:
            return {
                "status": "salvaged",
                "model": model,
                "headline": str(salvaged.get("headline") or fallback.get("headline") or ""),
                "commander_summary": str(salvaged.get("commander_summary") or fallback.get("commander_summary") or ""),
                "strategist_summary": str(salvaged.get("strategist_summary") or fallback.get("strategist_summary") or ""),
                "scanner_summary": str(salvaged.get("scanner_summary") or fallback.get("scanner_summary") or ""),
                "monitor_summary": str(salvaged.get("monitor_summary") or fallback.get("monitor_summary") or ""),
                "supervisor_summary": str(salvaged.get("supervisor_summary") or fallback.get("supervisor_summary") or ""),
                "executor_summary": str(salvaged.get("executor_summary") or fallback.get("executor_summary") or ""),
                "reporter_summary": str(salvaged.get("reporter_summary") or fallback.get("reporter_summary") or ""),
                "operator_takeaways": [str(x or "") for x in list(salvaged.get("operator_takeaways") or [])[:5] if str(x or "").strip()] or list(fallback.get("operator_takeaways") or []),
                "reason": "llm_partial_salvage",
            }
        fallback["model"] = model
        fallback["reason"] = "llm_parse_error"
        return fallback
    return {
        "status": "ok",
        "model": model,
        "headline": str(parsed.get("headline") or fallback.get("headline") or ""),
        "commander_summary": str(parsed.get("commander_summary") or fallback.get("commander_summary") or ""),
        "strategist_summary": str(parsed.get("strategist_summary") or fallback.get("strategist_summary") or ""),
        "scanner_summary": str(parsed.get("scanner_summary") or fallback.get("scanner_summary") or ""),
        "monitor_summary": str(parsed.get("monitor_summary") or fallback.get("monitor_summary") or ""),
        "supervisor_summary": str(parsed.get("supervisor_summary") or fallback.get("supervisor_summary") or ""),
        "executor_summary": str(parsed.get("executor_summary") or fallback.get("executor_summary") or ""),
        "reporter_summary": str(parsed.get("reporter_summary") or fallback.get("reporter_summary") or ""),
        "operator_takeaways": [str(x or "") for x in list(parsed.get("operator_takeaways") or [])[:5] if str(x or "").strip()] or list(fallback.get("operator_takeaways") or []),
    }


def _load_cached_operator_brief(config: OperatorUIConfig, run_id: str) -> Dict[str, Any]:
    if not run_id:
        return {}
    path = config.operator_ui_cache_path / f"{run_id}.json"
    cached = _read_json(path)
    if not isinstance(cached, dict):
        return {}
    if int(cached.get("version") or 0) < 4:
        return {}
    return cached


def _save_cached_operator_brief(config: OperatorUIConfig, run_id: str, brief: Dict[str, Any]) -> None:
    if not run_id or not isinstance(brief, dict):
        return
    path = config.operator_ui_cache_path / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(brief)
    payload["version"] = 4
    payload["cached_at"] = datetime.now(tz=KST).isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_operator_brief_with_cache(config: OperatorUIConfig, detail: Dict[str, Any]) -> Dict[str, Any]:
    run_id = str(detail.get("run_id") or "").strip()
    cached = _load_cached_operator_brief(config, run_id)
    if cached:
        return _attach_operator_brief_sections(cached, detail)
    brief = _attach_operator_brief_sections(_load_operator_brief(detail), detail)
    _save_cached_operator_brief(config, run_id, brief)
    return brief


def load_run_detail(config: OperatorUIConfig, run_id: str) -> Dict[str, Any]:
    all_rows = [row for row in _iter_jsonl(config.event_log_path) if str(row.get("run_id") or "").strip() == str(run_id or "").strip()]
    all_rows = sorted(all_rows, key=lambda row: _to_epoch(row.get("ts")) or 0)
    evidence_rows = [row for row in _iter_jsonl(config.evidence_log_path) if str(row.get("run_id") or "").strip() == str(run_id or "").strip()]
    evidence_rows = sorted(evidence_rows, key=lambda row: _to_epoch(row.get("timestamp")) or 0)

    if not all_rows:
        return {"run_id": str(run_id or ""), "found": False}

    route_row = next((r for r in all_rows if str(r.get("stage") or "") == "commander_router" and str(r.get("event") or "") == "route"), {})
    end_row = next((r for r in reversed(all_rows) if str(r.get("stage") or "") == "commander_router" and str(r.get("event") or "") == "end"), {})
    strategist_summary = next((r.get("payload") for r in reversed(all_rows) if str(r.get("stage") or "") == "strategist" and str(r.get("event") or "") == "summary" and isinstance(r.get("payload"), dict)), {})
    strategist_llm = next((r.get("payload") for r in reversed(all_rows) if str(r.get("stage") or "") == "strategist_llm" and str(r.get("event") or "") == "result" and isinstance(r.get("payload"), dict)), {})
    scanner_summary = next((r.get("payload") for r in reversed(all_rows) if str(r.get("stage") or "") == "scanner" and str(r.get("event") or "") == "summary" and isinstance(r.get("payload"), dict)), {})
    monitor_summary = next((r.get("payload") for r in reversed(all_rows) if str(r.get("stage") or "") == "monitor" and str(r.get("event") or "") == "summary" and isinstance(r.get("payload"), dict)), {})
    verdict_payload = next((r.get("payload") for r in reversed(all_rows) if str(r.get("stage") or "") == "execute_from_packet" and str(r.get("event") or "") == "verdict" and isinstance(r.get("payload"), dict)), {})
    execution_payload = next((r.get("payload") for r in reversed(all_rows) if str(r.get("stage") or "") == "execute_from_packet" and str(r.get("event") or "") == "execution" and isinstance(r.get("payload"), dict)), {})
    normalized_execution = _normalize_execution_payload(execution_payload if isinstance(execution_payload, dict) else {})
    portfolio_sync = _build_portfolio_sync_card(_extract_portfolio_guard_payload_from_run_rows(all_rows))

    strategic_frame = next(
        (
            (r.get("payload") or {}).get("payload")
            for r in reversed(all_rows)
            if str(r.get("stage") or "") == "decision_trace"
            and str(r.get("event") or "") == "strategic_frame"
            and isinstance(r.get("payload"), dict)
            and str((r.get("payload") or {}).get("agent") or "") == "strategist"
        ),
        {},
    )
    candidate_selection = next(
        (
            (r.get("payload") or {}).get("payload")
            for r in reversed(all_rows)
            if str(r.get("stage") or "") == "decision_trace"
            and str(r.get("event") or "") == "candidate_selection"
            and isinstance(r.get("payload"), dict)
            and str((r.get("payload") or {}).get("agent") or "") == "scanner"
        ),
        {},
    )
    entry_exit_decision = next(
        (
            (r.get("payload") or {}).get("payload")
            for r in reversed(all_rows)
            if str(r.get("stage") or "") == "decision_trace"
            and str(r.get("event") or "") == "entry_exit_decision"
            and isinstance(r.get("payload"), dict)
            and str((r.get("payload") or {}).get("agent") or "") == "monitor"
        ),
        {},
    )
    selected_candidate = candidate_selection.get("selected_candidate") if isinstance(candidate_selection.get("selected_candidate"), dict) else {}
    feature_snapshot = selected_candidate.get("feature_snapshot") if isinstance(selected_candidate.get("feature_snapshot"), dict) else {}
    feature_coverage = _feature_coverage(feature_snapshot)
    quote_metrics = _quote_metrics_snapshot(feature_snapshot)

    strategist_evidence = _latest_evidence(evidence_rows, agent="strategist", stage="theme_selection")
    reporter_evidence = _latest_evidence(evidence_rows, agent="reporter", stage="post_run_analysis")
    first_dt = _to_datetime(all_rows[0].get("ts"))
    run_day = first_dt.strftime("%Y-%m-%d") if first_dt else ""
    primary_symbol = normalize_symbol(
        normalized_execution.get("symbol")
        or scanner_summary.get("top_stock")
        or candidate_selection.get("selected_symbol")
        or "",
        allow_test_symbols=True,
    ).strip()
    same_day_symbol_trades = []
    if primary_symbol:
        same_day_symbol_trades = [
            trade
            for trade in load_recent_trades_for_day(config, run_day, limit=500)
            if str(trade.get("symbol") or "").strip() == primary_symbol
        ]
    same_day_symbol_run_chain = load_symbol_run_chain(config, run_day, primary_symbol, limit=3) if primary_symbol else []
    trade_report_meta = _trade_report_meta_for_run(config, str(run_id or ""))
    if trade_report_meta:
        story_input_path = Path(str(trade_report_meta.get("trade_story_input_path") or ""))
        lifecycle_path = Path(str(trade_report_meta.get("trade_lifecycle_json_path") or ""))
        report_json_path = Path(str(trade_report_meta.get("trade_report_json_path") or ""))
        story_input_data = _read_json(story_input_path) if story_input_path.exists() else {}
        lifecycle_data = _read_json(lifecycle_path) if lifecycle_path.exists() else {}
        report_data = _read_json(report_json_path) if report_json_path.exists() else {}
        ai_diag = (
            trade_report_meta.get("ai_report_diagnostics")
            if isinstance(trade_report_meta.get("ai_report_diagnostics"), dict)
            else {}
        )
        if not ai_diag:
            ai_diag = _normalize_ai_report_diagnostics(
                {},
                report_exists=bool(trade_report_meta.get("trade_report_json_path") or trade_report_meta.get("trade_report_md_path")),
                lifecycle_status=trade_report_meta.get("lifecycle_status"),
                story_type=trade_report_meta.get("story_type"),
                model_hint=trade_report_meta.get("report_generation_model"),
            )
        trade_report_card = {
            "report_available": bool(trade_report_meta.get("report_available")),
            "trade_id": str(trade_report_meta.get("trade_id") or ""),
            "story_id": str(trade_report_meta.get("story_id") or ""),
            "story_type": str(trade_report_meta.get("story_type") or ""),
            "story_type_label": str(trade_report_meta.get("story_type_label") or ""),
            "story_type_badge_class": str(trade_report_meta.get("story_type_badge_class") or "status-badge"),
            "lifecycle_status": str(trade_report_meta.get("lifecycle_status") or ""),
            "lifecycle_summary": str(trade_report_meta.get("lifecycle_summary") or ""),
            "execution_mode_label": str(trade_report_meta.get("execution_mode_label") or "-"),
            "report_status": str(trade_report_meta.get("report_status") or ai_diag.get("report_status") or "skipped"),
            "report_status_label": str(trade_report_meta.get("report_status_label") or ai_diag.get("report_status_label") or _report_status_label("skipped")),
            "report_status_badge_class": str(trade_report_meta.get("report_status_badge_class") or ai_diag.get("report_status_badge_class") or _report_status_badge_class("skipped")),
            "report_reason_code": str(trade_report_meta.get("report_reason_code") or ai_diag.get("report_reason_code") or ""),
            "report_reason_human": str(trade_report_meta.get("report_reason_human") or ai_diag.get("report_reason_human") or ""),
            "report_next_expected_step": str(trade_report_meta.get("report_next_expected_step") or ai_diag.get("next_expected_step") or ""),
            "report_generation_model": str(trade_report_meta.get("report_generation_model") or ai_diag.get("llm_model_used") or ""),
            "report_generation_provider": str(trade_report_meta.get("report_generation_provider") or ai_diag.get("llm_provider") or "OpenRouter"),
            "report_summary": str(trade_report_meta.get("report_summary") or ""),
            "reporter_status_human": str(trade_report_meta.get("reporter_status_human") or ""),
            "report_link": str(trade_report_meta.get("report_link") or ""),
            "symbol": str(trade_report_meta.get("symbol") or primary_symbol or ""),
            "action": str(trade_report_meta.get("action") or normalized_execution.get("action") or ""),
            "missing_reason": str(trade_report_meta.get("report_reason_human") or ai_diag.get("report_reason_human") or ""),
            "ai_report_diagnostics": ai_diag,
            "story_input_data": story_input_data if isinstance(story_input_data, dict) else {},
            "lifecycle_data": lifecycle_data if isinstance(lifecycle_data, dict) else {},
            "report_data": report_data if isinstance(report_data, dict) else {},
        }
    else:
        execution_action = str(normalized_execution.get("action") or "").upper()
        monitor_reason_text = str(monitor_summary.get("monitor_reason") or entry_exit_decision.get("monitor_reason") or "").strip().lower()
        if execution_action in {"BUY", "SELL"}:
            reason_code = "missing_report_linkage"
            status = "failed"
        elif "hold" in monitor_reason_text:
            reason_code = "hold_only_run"
            status = "skipped"
        else:
            reason_code = "decision_only_run"
            status = "skipped"
        ai_diag = _normalize_ai_report_diagnostics(
            {
                "report_status": status,
                "report_reason_code": reason_code,
                "report_reason_human": _report_reason_human(reason_code),
                "next_expected_step": _report_next_step(reason_code),
                "generation_attempted": False,
                "story_input_available": False,
                "report_output_available": False,
            },
            report_exists=False,
            lifecycle_status="",
            story_type="decision_only" if status == "skipped" else "",
            model_hint="",
        )
        trade_report_card = {
            "report_available": False,
            "trade_id": "",
            "story_id": "",
            "story_type": "",
            "story_type_label": "No linked trade report",
            "story_type_badge_class": "status-badge",
            "lifecycle_status": "",
            "lifecycle_summary": "",
            "execution_mode_label": "-",
            "report_status": str(ai_diag.get("report_status") or "skipped"),
            "report_status_label": str(ai_diag.get("report_status_label") or _report_status_label("skipped")),
            "report_status_badge_class": str(ai_diag.get("report_status_badge_class") or _report_status_badge_class("skipped")),
            "report_reason_code": str(ai_diag.get("report_reason_code") or ""),
            "report_reason_human": str(ai_diag.get("report_reason_human") or ""),
            "report_next_expected_step": str(ai_diag.get("next_expected_step") or ""),
            "report_generation_model": str(ai_diag.get("llm_model_used") or ""),
            "report_generation_provider": str(ai_diag.get("llm_provider") or "OpenRouter"),
            "report_summary": "",
            "reporter_status_human": "",
            "report_link": "",
            "symbol": primary_symbol or str(normalized_execution.get("symbol") or scanner_summary.get("top_stock") or ""),
            "action": str(normalized_execution.get("action") or ""),
            "missing_reason": str(ai_diag.get("report_reason_human") or "No linked trade report for this run."),
            "ai_report_diagnostics": ai_diag,
            "story_input_data": {},
            "lifecycle_data": {},
            "report_data": {},
        }

    detail = {
        "found": True,
        "run_id": str(run_id or ""),
        "started_at": _iso_to_display(route_row.get("ts")),
        "completed_at": _iso_to_display(end_row.get("ts")),
        "commander": {
            "mode": str((route_row.get("payload") or {}).get("mode") or ""),
            "phase": str((route_row.get("payload") or {}).get("phase") or ""),
            "agents": list((route_row.get("payload") or {}).get("agents") or []),
            "status": str((end_row.get("payload") or {}).get("status") or ""),
            "path": str((end_row.get("payload") or {}).get("path") or ""),
        },
        "strategist": {
            "summary": strategist_summary,
            "llm": strategist_llm,
            "decision_trace": strategic_frame if isinstance(strategic_frame, dict) else {},
            "evidence": {
                "raw_input": strategist_evidence.get("raw_input") if isinstance(strategist_evidence.get("raw_input"), dict) else {},
                "llm_prompt": str(strategist_evidence.get("llm_prompt") or ""),
                "llm_response": str(strategist_evidence.get("llm_response") or ""),
                "parsed_output": strategist_evidence.get("parsed_output") if isinstance(strategist_evidence.get("parsed_output"), dict) else {},
            },
        },
        "scanner": {
            "summary": scanner_summary,
            "decision_trace": candidate_selection if isinstance(candidate_selection, dict) else {},
            "feature_coverage": feature_coverage,
            "quote_metrics": quote_metrics,
        },
        "monitor": {
            "summary": monitor_summary,
            "decision_trace": entry_exit_decision if isinstance(entry_exit_decision, dict) else {},
        },
        "supervisor": {
            "verdict": verdict_payload,
        },
        "executor": {
            "execution": execution_payload,
        },
        "portfolio_sync": portfolio_sync,
        "same_day_symbol_trade_history": {
            "day": run_day,
            "symbol": primary_symbol,
            "trade_count": len(same_day_symbol_trades),
            "trades": same_day_symbol_trades[:20],
        },
        "same_day_symbol_run_chain": {
            "day": run_day,
            "symbol": primary_symbol,
            "run_count": len(same_day_symbol_run_chain),
            "runs": same_day_symbol_run_chain,
        },
        "trade_report": trade_report_card,
        "reporter": _reporter_snippet_for_run(config, str(run_id or ""), run_day),
        "raw_event_count": len(all_rows),
        "stage_counts": _count_stages(all_rows),
        "event_preview": [
            {
                "ts": _iso_to_display(row.get("ts")),
                "stage": str(row.get("stage") or ""),
                "event": str(row.get("event") or ""),
                "payload": _truncate_json(row.get("payload")),
            }
            for row in all_rows[:120]
        ],
    }
    detail["operator_brief"] = _load_operator_brief_with_cache(config, detail)
    return detail


def load_strategy_memory_timeline(config: OperatorUIConfig, *, limit: int = 7) -> List[Dict[str, Any]]:
    root = config.strategy_memory_path
    if not root.exists():
        return []
    files = sorted(root.glob("*.json"), reverse=True)[: max(1, int(limit))]
    out: List[Dict[str, Any]] = []
    for path in files:
        obj = _read_json(path)
        latest = obj.get("latest_feedback") if isinstance(obj.get("latest_feedback"), dict) else {}
        out.append(
            {
                "day": str(obj.get("day") or path.stem),
                "updated_at": str(obj.get("updated_at") or ""),
                "latest_run_id": str(obj.get("latest_run_id") or ""),
                "trade_count": _safe_int((latest.get("trade_summary") or {}).get("trade_count"), 0) if isinstance(latest.get("trade_summary"), dict) else 0,
                "monitor_status": str((latest.get("monitor_evaluation") or {}).get("monitor_status") or "") if isinstance(latest.get("monitor_evaluation"), dict) else "",
                "theme_alignment_status": str((latest.get("strategist_evaluation") or {}).get("theme_alignment_status") or "") if isinstance(latest.get("strategist_evaluation"), dict) else "",
                "ai_findings": list(latest.get("ai_findings") or [])[:2],
                "path": str(path),
            }
        )
    return out


def _count_stages(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        key = str(row.get("stage") or "").strip()
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def load_health(config: OperatorUIConfig) -> Dict[str, Any]:
    latest_day = _latest_event_day(config.event_log_path)
    operator_summary = _read_exact_day(config.reports_root / "operator_summary", "operator_summary", latest_day)
    reporter = _read_exact_day(config.reports_root / "dev" / "analysis" / "reporter_analysis", "reporter_analysis", latest_day)
    if operator_summary:
        executive = operator_summary.get("executive_summary") if isinstance(operator_summary.get("executive_summary"), dict) else {}
        system_status = str(executive.get("system_status") or "UNKNOWN")
    else:
        system_status = "LIVE" if latest_day else "UNKNOWN"
    if reporter:
        ai_review = reporter.get("ai_review") if isinstance(reporter.get("ai_review"), dict) else {}
        ai_review_status = str(ai_review.get("status") or "disabled")
    else:
        ai_review_status = "not_generated_yet" if latest_day else "disabled"
    return {
        "status": "ok",
        "latest_day": latest_day,
        "system_status": system_status,
        "ai_review_status": ai_review_status,
        "event_log_path": str(config.event_log_path),
        "reports_root": str(config.reports_root),
    }
