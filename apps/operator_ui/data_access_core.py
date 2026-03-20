from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import re
import time

from apps.operator_ui.data_access_reports import load_trade_report_payloads
from apps.operator_ui.data_access_runs import load_run_canonical_sources, prefer_canonical_agent_payload
from apps.operator_ui.data_access_linkage import (
    existing_trade_path as _link_existing_trade_path,
    trade_paths_from_bundle as _link_trade_paths_from_bundle,
    trade_root_from_bundle_path as _link_trade_root_from_bundle_path,
)
from apps.operator_ui.data_access_status import (
    build_portfolio_sync_card as _status_build_portfolio_sync_card,
    normalize_ai_report_diagnostics as _status_normalize_ai_report_diagnostics,
    normalize_report_status as _status_normalize_report_status,
    portfolio_reconciliation_label as _status_portfolio_reconciliation_label,
    portfolio_positions_source_label as _status_portfolio_positions_source_label,
    portfolio_sync_badge_class as _status_portfolio_sync_badge_class,
    portfolio_sync_label as _status_portfolio_sync_label,
    portfolio_sync_sentence as _status_portfolio_sync_sentence,
    report_next_step as _status_report_next_step,
    report_reason_human as _status_report_reason_human,
    report_status_badge_class as _status_report_status_badge_class,
    report_status_label as _status_report_status_label,
    story_type_badge_class as _status_story_type_badge_class,
    story_type_label as _status_story_type_label,
)
from apps.operator_ui.data_access_brief import (
    OPERATOR_BRIEF_REQUIRED_KEYS as BRIEF_REQUIRED_KEYS_MODULE,
    clean_brief_list as _brief_clean_list,
    clean_brief_text as _brief_clean_text,
    is_retryable_brief_failure as _brief_is_retryable_failure,
    operator_brief_is_complete as _brief_is_complete,
    operator_brief_parse_meta as _brief_parse_meta,
)
from libs.llm.llm_router import LLMRouter
from libs.llm.json_response import parse_llm_json_response, required_key_metadata
from libs.llm.model_names import normalize_openrouter_model_name
from libs.core.symbols import normalize_symbol
from libs.reporting.llm_artifacts import (
    build_compact_input_artifact,
    build_llm_response_artifact,
    classify_llm_exception,
    make_attempt,
    trade_artifact_paths,
)


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


def _env_int_with_fallback(*names: str, default: int) -> int:
    for name in names:
        raw = str(os.getenv(name, "") or "").strip()
        if not raw:
            continue
        try:
            value = int(float(raw))
        except Exception:
            continue
        if value > 0:
            return value
    return int(default)


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


def _normalized_feature_coverage(reported: Dict[str, Any], feature_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    computed = _feature_coverage(feature_snapshot)
    if not isinstance(reported, dict) or not reported:
        return computed
    present = _safe_int(reported.get("present"), _safe_int(computed.get("present"), 0))
    total = _safe_int(reported.get("total"), _safe_int(computed.get("total"), 0))
    ratio = _safe_float(reported.get("coverage_ratio"), (float(present) / float(total) if total else 0.0))
    quality = str(reported.get("quality") or "").strip().lower()
    if not quality:
        if total <= 0:
            quality = "missing"
        elif ratio >= 0.75:
            quality = "strong"
        elif ratio >= 0.35:
            quality = "partial"
        else:
            quality = "missing"
    return {
        "present": present,
        "total": total,
        "coverage_ratio": ratio,
        "quality": quality,
        "present_keys": list(reported.get("present_keys") or computed.get("present_keys") or []),
        "missing_keys": list(reported.get("missing_keys") or computed.get("missing_keys") or []),
    }


def _chart_filter_status_and_note(feature_coverage: Dict[str, Any]) -> tuple[str, str]:
    present = _safe_int(feature_coverage.get("present"), 0)
    total = _safe_int(feature_coverage.get("total"), 0)
    ratio = _safe_float(feature_coverage.get("coverage_ratio"), 0.0)
    if total <= 0:
        return "SKIPPED", "feature snapshot not available"
    if ratio >= 0.75:
        status = "PASS"
    elif ratio >= 0.5:
        status = "PARTIAL"
    else:
        status = "FAIL"
    return status, f"{present}/{total} filled"


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
    return _brief_clean_text(v)


def _clean_brief_list(v: Any, *, limit: int) -> List[str]:
    return _brief_clean_list(v, limit=limit)


def _extract_json_object(text: Any) -> Dict[str, Any]:
    parsed = parse_llm_json_response(text)
    obj = parsed.get("full_object") if isinstance(parsed.get("full_object"), dict) else parsed.get("partial_object")
    return dict(obj) if isinstance(obj, dict) else {}


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
    return normalize_openrouter_model_name(model)


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
        "executive_summary",
        "scanner_reason",
        "entry_summary",
        "holding_summary",
        "exit_plan_summary",
        "risk_summary",
        "next_checkpoints",
    ]
    out: Dict[str, Any] = {}
    for key in keys:
        pattern = rf"{key}\s*:\s*(.+)"
        matches = re.findall(pattern, raw, flags=re.IGNORECASE)
        if not matches:
            continue
        if key in {"operator_takeaways", "next_checkpoints"}:
            for candidate in reversed(matches):
                items = [item.strip(" -*") for item in str(candidate).split("|") if item.strip(" -*")]
                if not items:
                    continue
                if key == "operator_takeaways" and all(item.lower().startswith("item") for item in items):
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


def _trade_root_from_bundle_path(bundle_path: Path) -> Path:
    return _link_trade_root_from_bundle_path(bundle_path)


def _trade_paths_from_bundle(bundle_path: Path, *, day_hint: str = "", trade_id_hint: str = "") -> Dict[str, Path]:
    return _link_trade_paths_from_bundle(bundle_path, day_hint=day_hint, trade_id_hint=trade_id_hint)


def _existing_trade_path(paths: Dict[str, Path], *keys: str) -> Path:
    return _link_existing_trade_path(paths, *keys)


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
    return _status_story_type_label(story_type)


def _story_type_badge_class(story_type: Any) -> str:
    return _status_story_type_badge_class(story_type)


def _normalize_report_status(value: Any) -> str:
    return _status_normalize_report_status(value)


def _report_status_label(status: Any) -> str:
    return _status_report_status_label(status)


def _report_status_badge_class(status: Any) -> str:
    return _status_report_status_badge_class(status)


def _report_reason_human(code: Any) -> str:
    return _status_report_reason_human(code)


def _report_next_step(code: Any) -> str:
    return _status_report_next_step(code)


def _portfolio_sync_badge_class(status: Any) -> str:
    return _status_portfolio_sync_badge_class(status)


def _portfolio_sync_label(status: Any) -> str:
    return _status_portfolio_sync_label(status)


def _portfolio_sync_sentence(status: Any) -> str:
    return _status_portfolio_sync_sentence(status)


def _portfolio_positions_source_label(value: Any) -> str:
    return _status_portfolio_positions_source_label(value)


def _portfolio_reconciliation_label(value: Any) -> str:
    return _status_portfolio_reconciliation_label(value)


def _build_portfolio_sync_card(raw: Any) -> Dict[str, Any]:
    return _status_build_portfolio_sync_card(raw)


def _run_activity_meta(runtime_path: Any, execution: Dict[str, Any], guard_reason: Any, monitor_reason: Any) -> Dict[str, str]:
    path = str(runtime_path or "").strip().lower()
    action = str((execution or {}).get("action") or "").strip().upper()
    status = str((execution or {}).get("status") or "").strip()
    guard = str(guard_reason or "").strip().lower()
    monitor = str(monitor_reason or "").strip().lower()
    if action in {"BUY", "SELL"} and status:
        return {
            "activity_kind": "trade",
            "activity_label": "Trade",
            "activity_badge_class": "status-badge status-badge--ok",
        }
    if path == "integrated_chain_monitor_only" and (guard == "noop_intent_skipped" or "hold" in monitor):
        return {
            "activity_kind": "monitoring",
            "activity_label": "Monitoring",
            "activity_badge_class": "status-badge",
        }
    return {
        "activity_kind": "analysis",
        "activity_label": "Analysis",
        "activity_badge_class": "chip",
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
    return _status_normalize_ai_report_diagnostics(
        raw,
        report_exists=report_exists,
        lifecycle_status=lifecycle_status,
        story_type=story_type,
        model_hint=model_hint,
        generation=generation,
    )


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
    seen_bundle_paths: set[str] = set()
    bundle_candidates = sorted(root.glob("**/aggregated_execution_bundle.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for bundle_path in bundle_candidates:
        key_path = str(bundle_path.resolve())
        if key_path in seen_bundle_paths:
            continue
        seen_bundle_paths.add(key_path)
        bundle = _read_json(bundle_path)
        if not bundle:
            continue

        bundle_day = str(bundle.get("day") or "").strip()
        lifecycle_status_hint = str(bundle.get("trade_lifecycle_status") or "").strip()
        trade_id_hint = str(bundle.get("trade_id") or bundle.get("story_id") or "").strip()
        paths = _trade_paths_from_bundle(bundle_path, day_hint=bundle_day, trade_id_hint=trade_id_hint)
        lifecycle_path = _existing_trade_path(paths, "trade_lifecycle_json", "legacy_trade_lifecycle_json")
        lifecycle = _read_json(lifecycle_path) if lifecycle_path.exists() else {}
        trade_id = str(
            lifecycle.get("trade_id")
            or bundle.get("trade_id")
            or bundle.get("story_id")
            or paths.get("trade_root", bundle_path.parent).name
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

        report_json_path = _existing_trade_path(paths, "ai_trade_report_json", "legacy_trade_report_json")
        report_md_path = _existing_trade_path(paths, "ai_trade_report_md", "legacy_trade_report_md")
        story_input_path = _existing_trade_path(paths, "ai_trade_report_input_json", "legacy_trade_story_input_json")
        operator_brief_json_path = _existing_trade_path(paths, "brief_json", "legacy_operator_brief_json")
        operator_brief_md_path = _existing_trade_path(paths, "brief_md", "legacy_operator_brief_md")
        strategist_llm_response_path = _existing_trade_path(paths, "strategist_llm_response_json")
        ai_trade_report_llm_response_path = _existing_trade_path(paths, "ai_trade_report_llm_response_json")
        brief_llm_response_path = _existing_trade_path(paths, "brief_llm_response_json")
        trade_provenance_path = _existing_trade_path(paths, "trade_provenance_json")
        trade_health_path = _existing_trade_path(paths, "trade_health_json")
        trade_artifact_links_path = _existing_trade_path(paths, "trade_artifact_links_json")
        trade_provenance = _read_json(trade_provenance_path) if trade_provenance_path.exists() else {}
        trade_health = _read_json(trade_health_path) if trade_health_path.exists() else {}
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
        path_priority = 2 if bundle_path.parent.name == "lifecycle" else 1
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
            else trade_health.get("ai_report_diagnostics")
            if isinstance(trade_health.get("ai_report_diagnostics"), dict)
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
        report_available = bool(report_exists)
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
            "report_link": f"/reports/trade/{trade_id}" if trade_id and report_exists else "",
            "operator_brief_available": bool(trade_id),
            "operator_brief_link": f"/reports/trade/{trade_id}/brief" if trade_id else "",
            "trade_report_json_path": str(report_json_path) if report_json_path.exists() else "",
            "trade_report_md_path": str(report_md_path) if report_md_path.exists() else "",
            "trade_story_input_path": str(story_input_path) if story_input_path.exists() else "",
            "ai_trade_report_json_path": str(report_json_path) if report_json_path.exists() else "",
            "ai_trade_report_md_path": str(report_md_path) if report_md_path.exists() else "",
            "ai_trade_report_input_path": str(story_input_path) if story_input_path.exists() else "",
            "trade_lifecycle_json_path": str(lifecycle_path) if lifecycle_path.exists() else "",
            "operator_brief_json_path": str(operator_brief_json_path) if operator_brief_json_path.exists() else "",
            "operator_brief_md_path": str(operator_brief_md_path) if operator_brief_md_path.exists() else "",
            "strategist_llm_response_path": str(strategist_llm_response_path) if strategist_llm_response_path.exists() else "",
            "ai_trade_report_llm_response_path": str(ai_trade_report_llm_response_path) if ai_trade_report_llm_response_path.exists() else "",
            "brief_llm_response_path": str(brief_llm_response_path) if brief_llm_response_path.exists() else "",
            "trade_provenance_json_path": str(trade_provenance_path) if trade_provenance_path.exists() else "",
            "trade_health_json_path": str(trade_health_path) if trade_health_path.exists() else "",
            "trade_artifact_links_json_path": str(trade_artifact_links_path) if trade_artifact_links_path.exists() else "",
            "section_provenance": (
                dict(trade_provenance.get("section_provenance") or {})
                if isinstance(trade_provenance, dict)
                else {}
            ),
            "aggregated_bundle_path": str(bundle_path),
            "trade_root_path": str(paths.get("trade_root") or ""),
            "ts_epoch": ts_epoch,
            "_path_priority": path_priority,
        }

        if story_id:
            current_story = by_story_id.get(story_id)
            if (not current_story) or (
                int(record.get("_path_priority") or 0) > int(current_story.get("_path_priority") or 0)
                or (
                    int(record.get("_path_priority") or 0) == int(current_story.get("_path_priority") or 0)
                    and int(record.get("ts_epoch") or 0) >= int(current_story.get("ts_epoch") or 0)
                )
            ):
                by_story_id[story_id] = record
        for rid in linked_run_ids:
            current = by_run_id.get(rid)
            if (not current) or (
                int(record.get("_path_priority") or 0) > int(current.get("_path_priority") or 0)
                or (
                    int(record.get("_path_priority") or 0) == int(current.get("_path_priority") or 0)
                    and int(record.get("ts_epoch") or 0) >= int(current.get("ts_epoch") or 0)
                )
            ):
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
    ai_review = reporter.get("ai_review") if isinstance(reporter.get("ai_review"), dict) else {}
    trade_summary = reporter.get("trade_summary") if isinstance(reporter.get("trade_summary"), dict) else {}
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
    live_allowed_total = 0
    live_blocked_total = 0
    live_noop_total = 0
    live_block_reason_top: Dict[str, int] = {}
    for row in live_verdict_rows:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        allowed = payload.get("allowed")
        reason = str(payload.get("reason") or "").strip()
        if allowed is True:
            live_allowed_total += 1
            continue
        if reason == "noop_intent_skipped":
            live_noop_total += 1
            continue
        if allowed is False:
            live_blocked_total += 1
            if reason:
                live_block_reason_top[reason] = _safe_int(live_block_reason_top.get(reason), 0) + 1
    live_run_total = len(live_route_rows)
    live_execution_total = len(all_today_trades)
    live_action_counts: Dict[str, int] = {}
    for row in all_today_trades:
        action = str(row.get("action") or "").upper().strip()
        if not action:
            continue
        live_action_counts[action] = _safe_int(live_action_counts.get(action), 0) + 1
    live_events_total = live_run_total
    live_symbols_traded = [str(row.get("symbol") or "") for row in traded_symbol_summary[:8] if str(row.get("symbol") or "").strip()]

    reported_run_total = _safe_int(trading.get("run_total"), 0)
    reported_exec_total = _safe_int(trading.get("executions_total"), 0)
    reported_blocked_total = _safe_int(trading.get("blocked_total"), 0)
    reported_daily_events = _safe_int(daily.get("events"), 0)
    reported_daily_approvals = _safe_int(daily.get("approvals"), 0)
    reported_daily_blocks = _safe_int(daily.get("blocks"), 0)
    reported_reporter_trade_count = _safe_int(trade_summary.get("trade_count"), 0)
    reported_reporter_symbols = [str(v or "") for v in list(trade_summary.get("symbols_traded") or []) if str(v or "").strip()]
    live_snapshot_mismatch = any(
        [
            live_run_total > reported_run_total,
            live_execution_total > reported_exec_total,
            live_allowed_total > reported_daily_approvals,
            live_blocked_total != reported_blocked_total and live_execution_total > 0,
            live_events_total > reported_daily_events,
            live_execution_total > reported_reporter_trade_count,
            live_symbols_traded != reported_reporter_symbols[: len(live_symbols_traded)],
        ]
    )

    if latest_day and live_snapshot_mismatch:
        top_block_reason = ""
        if live_block_reason_top:
            top_block_reason = sorted(live_block_reason_top.items(), key=lambda item: (-_safe_int(item[1]), str(item[0])))[0][0]
        executive = {
            "system_status": str(executive.get("system_status") or health.get("system_health_level") or "LIVE"),
            "summary_lines": [
                f"[LIVE] runs={live_run_total}, executions={live_execution_total} (approved={live_allowed_total}, blocked={live_blocked_total}, noop={live_noop_total}).",
                f"Top guard block: {top_block_reason or 'none'}",
            ] + list(executive.get("summary_lines") or []),
        }
        trading = {
            **trading,
            "run_total": live_run_total,
            "executions_total": live_execution_total,
            "blocked_total": live_blocked_total,
        }
        daily = {
            **daily,
            "events": live_events_total,
            "decision_actions": live_action_counts,
            "approvals": live_allowed_total,
            "blocks": live_blocked_total,
        }
        if reporter:
            reporter = {
                **reporter,
                "trade_summary": {
                    **trade_summary,
                    "trade_count": live_execution_total,
                    "symbols_traded": live_symbols_traded,
                },
            }
            ai_review = reporter.get("ai_review") if isinstance(reporter.get("ai_review"), dict) else {}
            trade_summary = reporter.get("trade_summary") if isinstance(reporter.get("trade_summary"), dict) else {}
            if ai_review:
                reporter["ai_review"] = {
                    **ai_review,
                    "status": "snapshot" if str(ai_review.get("status") or "").strip().lower() == "ok" else ai_review.get("status"),
                }

    reported_recon_local = _safe_int(recon_summary.get("local_total"), 0)
    reported_recon_broker = _safe_int(recon_summary.get("broker_total"), 0)
    reported_recon_matched = _safe_int(recon_summary.get("matched_by_ord_no"), 0)
    recon_stale_vs_live = live_execution_total > max(reported_recon_local, reported_recon_broker, reported_recon_matched)
    if latest_day and live_execution_total > 0 and (not reconciliation or recon_stale_vs_live):
        reconciliation = {
            "summary": {
                "local_total": live_execution_total,
                "broker_total": reported_recon_broker,
                "matched_by_ord_no": reported_recon_matched,
                "broker_window_limited": bool(recon_summary.get("broker_window_limited")),
                "pending": True,
                "sentence": "Intraday reconciliation has not been generated yet. Local executions are ahead of broker matching.",
            }
        }
        recon_summary = reconciliation.get("summary") if isinstance(reconciliation.get("summary"), dict) else {}

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
    latest_run_sync = next(
        (
            dict((row or {}).get("portfolio_sync") or {})
            for row in recent_runs
            if isinstance(row, dict)
            and str(((row.get("portfolio_sync") or {}).get("status") or "")).strip().lower() not in {"", "unavailable"}
        ),
        (
            dict((recent_runs[0] or {}).get("portfolio_sync") or {})
            if recent_runs and isinstance(recent_runs[0], dict)
            else _build_portfolio_sync_card({})
        ),
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
            "pending": bool(recon_summary.get("pending")),
            "sentence": str(recon_summary.get("sentence") or ""),
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
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        rid = str(row.get("run_id") or "").strip()
        if rid:
            grouped.setdefault(rid, []).append(row)
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
        run_id = str(row.get("run_id") or "").strip()
        run_rows = grouped.get(run_id) or []
        monitor_summary = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "monitor" and str(r.get("event") or "") == "summary" and isinstance(r.get("payload"), dict)),
            {},
        )
        monitor_trace = next(
            (
                (r.get("payload") or {}).get("payload")
                for r in reversed(run_rows)
                if str(r.get("stage") or "") == "decision_trace"
                and str(r.get("event") or "") == "entry_exit_decision"
                and isinstance(r.get("payload"), dict)
                and str((r.get("payload") or {}).get("agent") or "") == "monitor"
            ),
            {},
        )
        monitor_row = _monitor_row_summary(
            monitor_summary if isinstance(monitor_summary, dict) else {},
            monitor_trace if isinstance(monitor_trace, dict) else {},
        )
        out.append(
            {
                "ts": _iso_to_display(row.get("ts_kst") or row.get("ts")),
                "run_id": run_id,
                "action": action,
                "symbol": symbol,
                "qty": _safe_int(execution.get("qty"), 0),
                "status": str(execution.get("status") or ""),
                "ord_no": str(execution.get("ord_no") or ""),
                "active_exit_axis": str(monitor_row.get("active_exit_axis") or "-"),
                "effective_stop": str(monitor_row.get("effective_stop") or "-"),
                "peak_drawdown": str(monitor_row.get("peak_drawdown") or "-"),
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
        monitor_trace = next(
            (
                (r.get("payload") or {}).get("payload")
                for r in reversed(run_rows)
                if str(r.get("stage") or "") == "decision_trace"
                and str(r.get("event") or "") == "entry_exit_decision"
                and isinstance(r.get("payload"), dict)
                and str((r.get("payload") or {}).get("agent") or "") == "monitor"
            ),
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


def load_recent_runs(
    config: OperatorUIConfig,
    *,
    limit: int = 50,
    mismatch_only: bool = False,
    activity_view: str = "all",
) -> List[Dict[str, Any]]:
    rows = list(_iter_jsonl(config.event_log_path))
    route_rows = [row for row in rows if str(row.get("stage") or "") == "commander_router" and str(row.get("event") or "") == "route"]
    route_rows = sorted(route_rows, key=lambda row: _to_epoch(row.get("ts")) or 0, reverse=True)
    latest_day = _latest_event_day(config.event_log_path)
    if activity_view == "trades" and latest_day:
        day_filtered = [row for row in route_rows if _event_day(row.get("ts")) == latest_day]
        if day_filtered:
            route_rows = day_filtered
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
        monitor_trace = next(
            (
                (r.get("payload") or {}).get("payload")
                for r in reversed(run_rows)
                if str(r.get("stage") or "") == "decision_trace"
                and str(r.get("event") or "") == "entry_exit_decision"
                and isinstance(r.get("payload"), dict)
                and str((r.get("payload") or {}).get("agent") or "") == "monitor"
            ),
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
        fast_path_payload = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "commander_router" and str(r.get("event") or "") == "fast_path" and isinstance(r.get("payload"), dict)),
            {},
        )
        runtime_end_payload = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "commander_router" and str(r.get("event") or "") == "end" and isinstance(r.get("payload"), dict)),
            {},
        )
        execution_payload = next(
            (r.get("payload") for r in reversed(run_rows) if str(r.get("stage") or "") == "execute_from_packet" and str(r.get("event") or "") == "execution" and isinstance(r.get("payload"), dict)),
            {},
        )
        execution = _normalize_execution_payload(execution_payload if isinstance(execution_payload, dict) else {})
        portfolio_sync = _build_portfolio_sync_card(_extract_portfolio_guard_payload_from_run_rows(run_rows))
        monitor_row = _monitor_row_summary(
            monitor_summary if isinstance(monitor_summary, dict) else {},
            monitor_trace if isinstance(monitor_trace, dict) else {},
        )
        selected_candidate = candidate_selection.get("selected_candidate") if isinstance(candidate_selection.get("selected_candidate"), dict) else {}
        feature_snapshot = selected_candidate.get("feature_snapshot") if isinstance(selected_candidate.get("feature_snapshot"), dict) else {}
        feature_coverage = _feature_coverage(feature_snapshot)
        macro_stress_overlay = strategic_frame.get("macro_stress_overlay") if isinstance(strategic_frame.get("macro_stress_overlay"), dict) else {}
        runtime_path = str(runtime_end_payload.get("path") or fast_path_payload.get("path") or "")
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
                "runtime_path": runtime_path,
                "strategist_playbook": str(strategist_summary.get("playbook") or ""),
                "strategist_risk_tone": str(strategist_summary.get("risk_tone") or ""),
                "scanner_top_stock": str(scanner_summary.get("top_stock") or ""),
                "scanner_top_score": _safe_float(scanner_summary.get("top_score"), 0.0),
                "monitor_reason": str(monitor_summary.get("monitor_reason") or ""),
                "exit_reason": str(monitor_summary.get("exit_reason") or ""),
                "active_exit_axis": str(monitor_row.get("active_exit_axis") or "-"),
                "effective_stop": str(monitor_row.get("effective_stop") or "-"),
                "peak_drawdown": str(monitor_row.get("peak_drawdown") or "-"),
                "watch_axes": list(monitor_row.get("watch_axes") or []),
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
                "operator_brief_available": bool(report_meta.get("operator_brief_available")),
                "operator_brief_link": str(report_meta.get("operator_brief_link") or ""),
                "portfolio_sync": portfolio_sync,
                "portfolio_sync_status": str(portfolio_sync.get("status") or "unavailable"),
                "portfolio_sync_label": str(portfolio_sync.get("status_label") or "Sync status unavailable"),
                "portfolio_sync_badge_class": str(portfolio_sync.get("badge_class") or "status-badge"),
                "portfolio_sync_sentence": str(portfolio_sync.get("sentence") or ""),
            }
        row.update(
            _run_activity_meta(
                runtime_path,
                execution,
                verdict_payload.get("reason") if isinstance(verdict_payload, dict) else "",
                monitor_summary.get("monitor_reason") if isinstance(monitor_summary, dict) else "",
            )
        )
        if mismatch_only and row["portfolio_sync_status"] not in {"mismatch", "reader_error"}:
            continue
        if activity_view == "trades" and row.get("activity_kind") != "trade":
            continue
        if activity_view == "monitoring" and row.get("activity_kind") != "monitoring":
            continue
        out.append(row)
        if activity_view != "trades" and len(out) >= max(1, int(limit)):
            break
    return out


OPERATOR_BRIEF_REQUIRED_KEYS = [
    *list(BRIEF_REQUIRED_KEYS_MODULE),
]

OPERATOR_BRIEF_OPTIONAL_KEYS = [
    "executive_summary",
    "scanner_reason",
    "entry_summary",
    "holding_summary",
    "exit_plan_summary",
    "risk_summary",
    "next_checkpoints",
]


def _operator_brief_parse_meta(raw: Any, parsed: Dict[str, Any] | None) -> Dict[str, Any]:
    return _brief_parse_meta(raw, parsed)


def _operator_brief_is_complete(parsed: Dict[str, Any]) -> bool:
    return _brief_is_complete(parsed)


def _is_retryable_brief_failure(status: str, reason: str = "") -> bool:
    return _brief_is_retryable_failure(status, reason)


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
            "ai_trade_report_json": str(meta.get("ai_trade_report_json_path") or meta.get("trade_report_json_path") or ""),
            "ai_trade_report_md": str(meta.get("ai_trade_report_md_path") or meta.get("trade_report_md_path") or ""),
            "ai_trade_report_input": str(meta.get("ai_trade_report_input_path") or meta.get("trade_story_input_path") or ""),
            "trade_lifecycle": str(meta.get("trade_lifecycle_json_path") or ""),
            "aggregated_execution_bundle": str(meta.get("aggregated_bundle_path") or ""),
            "strategist_llm_response": str(meta.get("strategist_llm_response_path") or ""),
            "ai_trade_report_llm_response": str(meta.get("ai_trade_report_llm_response_path") or ""),
            "brief_llm_response": str(meta.get("brief_llm_response_path") or ""),
        },
        "raw_report": report if isinstance(report, dict) else {},
    }


def load_operator_brief_detail(config: OperatorUIConfig, story_id: str) -> Dict[str, Any]:
    meta = _trade_report_meta_for_story(config, story_id)
    if not meta:
        return {"found": False, "story_id": str(story_id or "")}

    run_id = str(meta.get("run_id") or "").strip()
    json_path = Path(str(meta.get("operator_brief_json_path") or ""))
    md_path = Path(str(meta.get("operator_brief_md_path") or ""))
    brief = {}
    if not _operator_brief_force_regenerate_enabled():
        brief = _read_json(json_path) if json_path.exists() else {}

    if not isinstance(brief, dict) or not brief:
        if run_id:
            detail = load_run_detail(config, run_id)
            if not detail.get("found"):
                return {"found": False, "story_id": str(story_id or ""), "trade_id": str(meta.get("trade_id") or "")}
            trade_report = detail.get("trade_report") if isinstance(detail.get("trade_report"), dict) else {}
            brief = detail.get("operator_brief") if isinstance(detail.get("operator_brief"), dict) else {}
            json_path = Path(str(trade_report.get("operator_brief_json_path") or ""))
            md_path = Path(str(trade_report.get("operator_brief_md_path") or ""))

    if not isinstance(brief, dict) or not brief:
        return {
            "found": False,
            "story_id": str(meta.get("story_id") or story_id),
            "trade_id": str(meta.get("trade_id") or ""),
            "reason": "operator_brief_not_available",
        }

    sections = brief.get("sections") if isinstance(brief.get("sections"), dict) else {}
    status = str(brief.get("status") or "").strip().lower()
    executive = sections.get("executive_decision") if isinstance(sections.get("executive_decision"), dict) else {}
    ai_trade = sections.get("ai_trade_report") if isinstance(sections.get("ai_trade_report"), dict) else {}
    conclusion = sections.get("operator_conclusion") if isinstance(sections.get("operator_conclusion"), dict) else {}

    return {
        "found": True,
        "trade_id": str(meta.get("trade_id") or meta.get("story_id") or story_id),
        "story_id": str(meta.get("story_id") or story_id),
        "run_id": run_id,
        "run_link": f"/runs/{run_id}" if run_id else "",
        "report_link": str(meta.get("report_link") or ""),
        "headline": str(brief.get("headline") or ""),
        "status": str(brief.get("status") or ""),
        "model": str(brief.get("model") or ""),
        "saved_at": str(brief.get("saved_at") or ""),
        "trade_summary": str(meta.get("report_summary") or ""),
        "lifecycle_status": str(meta.get("lifecycle_status") or ""),
        "story_type_label": str(meta.get("story_type_label") or ""),
        "story_type_badge_class": str(meta.get("story_type_badge_class") or "status-badge"),
        "execution_mode_label": str(meta.get("execution_mode_label") or "-"),
        "operator_takeaways": _clean_str_list(brief.get("operator_takeaways"), limit=8, max_len=220),
        "sections": sections,
        "executive_action": str(executive.get("final_action") or executive.get("action") or meta.get("action") or "-"),
        "executive_symbol": normalize_symbol(executive.get("symbol") or meta.get("symbol") or "", allow_test_symbols=True),
        "ai_trade_status_label": str(ai_trade.get("status_label") or meta.get("report_status_label") or "-"),
        "ai_trade_status_badge_class": str(ai_trade.get("status_badge_class") or meta.get("report_status_badge_class") or "status-badge"),
        "watch_next": _clean_str_list(conclusion.get("watch_next"), limit=8, max_len=220),
        "thesis_invalidation": _clean_str_list(conclusion.get("thesis_invalidation"), limit=8, max_len=220),
        "paths": {
            "operator_brief_json": str(json_path) if json_path.exists() else "",
            "operator_brief_md": str(md_path) if md_path.exists() else "",
        },
        "raw_brief": brief,
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


def _friendly_exit_reason(reason: Any) -> str:
    raw = str(reason or "").strip().lower()
    normalized = raw.replace(" ", "_")
    mapping = {
        "hard_stop": "Hard stop",
        "stop_loss": "Adaptive stop",
        "take_profit": "Take profit",
        "trailing_stop": "Trailing stop",
        "peak_drawdown": "Peak drawdown",
        "vwap_breakdown": "VWAP breakdown",
        "intraday_low_break": "Intraday low break",
        "trend_breakdown": "Trend breakdown",
        "volatility_expansion": "Volatility expansion",
        "news_shock": "News shock",
        "hold": "No trigger yet",
        "no_position": "No position",
        "price_unavailable": "Price unavailable",
    }
    return mapping.get(normalized, str(reason or "-").replace("_", " ") if str(reason or "").strip() else "-")


def _monitor_watch_axes(thresholds: Dict[str, Any]) -> List[str]:
    if not isinstance(thresholds, dict):
        return []
    out: List[str] = []
    if _safe_float(thresholds.get("hard_stop_pct"), 0.0) > 0.0:
        out.append("Hard stop")
    if _safe_float(thresholds.get("effective_stop_loss_pct"), 0.0) > 0.0:
        reason = _friendly_exit_reason(thresholds.get("effective_stop_reason") or "stop_loss")
        out.append(reason)
    if _safe_float(thresholds.get("take_profit_pct"), 0.0) > 0.0:
        out.append("Take profit")
    if _safe_float(thresholds.get("peak_drawdown_exit_pct"), 0.0) > 0.0:
        out.append("Peak drawdown")
    if _safe_float(thresholds.get("vwap_breakdown_pct"), 0.0) > 0.0:
        out.append("VWAP breakdown")
    if _safe_float(thresholds.get("intraday_low_break_pct"), 0.0) > 0.0:
        out.append("Intraday low break")
    if _safe_float(thresholds.get("trend_strength_floor"), 0.0) > 0.0:
        out.append("Trend breakdown")
    if _safe_float(thresholds.get("trailing_stop_pct"), 0.0) > 0.0:
        out.append("Trailing stop")
    if _safe_float(thresholds.get("vol_expansion_ratio"), 0.0) > 0.0:
        out.append("Volatility expansion")
    seen: List[str] = []
    for item in out:
        if item not in seen:
            seen.append(item)
    return seen[:6]


def _monitor_row_summary(monitor_summary: Dict[str, Any], monitor_trace: Dict[str, Any]) -> Dict[str, Any]:
    summary = monitor_summary if isinstance(monitor_summary, dict) else {}
    trace = monitor_trace if isinstance(monitor_trace, dict) else {}
    thresholds = trace.get("thresholds") if isinstance(trace.get("thresholds"), dict) else {}
    live_monitor_reason = str(summary.get("monitor_reason") or trace.get("monitor_reason") or "").strip()
    live_exit_reason = str(summary.get("exit_reason") or trace.get("exit_reason") or "").strip()
    effective_stop_loss = thresholds.get("effective_stop_loss_pct")
    peak_drawdown_raw = trace.get("peak_drawdown")
    if peak_drawdown_raw in (None, ""):
        peak_drawdown_raw = summary.get("peak_drawdown")
    return {
        "active_exit_axis": _friendly_exit_reason(live_exit_reason or str(thresholds.get("effective_stop_reason") or "").strip() or live_monitor_reason or "hold"),
        "effective_stop": _format_percent(effective_stop_loss, 2) if effective_stop_loss not in (None, "") else "-",
        "peak_drawdown": _format_percent(peak_drawdown_raw, 2) if peak_drawdown_raw not in (None, "") else "-",
        "watch_axes": _monitor_watch_axes(thresholds),
    }


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


def _section_value_quality(value: Any) -> int:
    if value in (None, "", [], {}):
        return 0
    if isinstance(value, str):
        lower = value.strip().lower()
        if not lower or lower in {"not_captured", "-", "unknown", "none"} or "not_captured" in lower:
            return 0
        return 2
    if isinstance(value, bool):
        return 1
    if isinstance(value, (int, float)):
        return 1
    if isinstance(value, list):
        return sum(_section_value_quality(item) for item in value[:12])
    if isinstance(value, dict):
        return sum(_section_value_quality(item) for item in list(value.values())[:20])
    return 0


def _prefer_richer_trade_report_section(*sections: Any) -> Dict[str, Any]:
    best: Dict[str, Any] = {}
    best_score = -1
    for section in sections:
        if not isinstance(section, dict) or not section:
            continue
        score = 0
        for key, value in section.items():
            if key == "summary":
                score += _section_value_quality(value)
            elif key == "bullets":
                score += _section_value_quality(value)
            else:
                score += _section_value_quality(value)
        if score > best_score:
            best = section
            best_score = score
    return dict(best or {})


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


def _normalize_canonical_monitor_snapshot(snapshot: Dict[str, Any], story_monitor: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not isinstance(snapshot, dict):
        snapshot = {}
    if not isinstance(story_monitor, dict):
        story_monitor = {}

    posture = str(snapshot.get("posture") or story_monitor.get("posture") or "").strip()
    trigger_type = str(snapshot.get("trigger_type") or story_monitor.get("trigger_type") or "").strip()
    raw_effective_reason = str(
        snapshot.get("effective_stop_reason")
        or story_monitor.get("effective_stop_reason")
        or trigger_type
        or ""
    ).strip()
    effective_reason = _friendly_exit_reason(raw_effective_reason) if raw_effective_reason else ""

    stop_loss_pct = snapshot.get("stop_loss_pct")
    if stop_loss_pct in (None, ""):
        stop_loss_pct = story_monitor.get("stop_loss_pct")
    effective_stop_loss_pct = snapshot.get("effective_stop_loss_pct")
    if effective_stop_loss_pct in (None, ""):
        effective_stop_loss_pct = story_monitor.get("effective_stop_loss_pct")
    take_profit_pct = snapshot.get("take_profit_pct")
    if take_profit_pct in (None, ""):
        take_profit_pct = story_monitor.get("take_profit_pct")

    position_age_seconds = snapshot.get("position_age_seconds")
    if position_age_seconds in (None, ""):
        position_age_seconds = story_monitor.get("position_age_seconds")

    active_exit_axis = str(snapshot.get("active_exit_axis") or "").strip()
    if not active_exit_axis:
        if trigger_type:
            active_exit_axis = _friendly_exit_reason(trigger_type)
        elif raw_effective_reason:
            active_exit_axis = _friendly_exit_reason(raw_effective_reason)
        elif posture.upper() == "HOLD":
            active_exit_axis = "No trigger yet"
    else:
        active_exit_axis = _friendly_exit_reason(active_exit_axis)

    def _fmt_optional_price(value: Any) -> str:
        if value in (None, ""):
            return ""
        return _format_float(value, 2)

    def _fmt_optional_pct(value: Any) -> str:
        if value in (None, ""):
            return ""
        return _format_percent(value, 2)

    watch_axes = [str(x or "") for x in list(snapshot.get("watch_axes") or []) if str(x or "").strip()]
    hold_reasons = [str(x or "") for x in list(snapshot.get("hold_reasons") or []) if str(x or "").strip()]
    exit_triggers = [str(x or "") for x in list(snapshot.get("exit_triggers") or []) if str(x or "").strip()]
    if not hold_reasons:
        hold_reasons = [str(x or "") for x in list(story_monitor.get("bullets") or []) if str(x or "").strip()][:4]

    return {
        "posture": posture,
        "holding_time": (
            _format_duration(position_age_seconds)
            if position_age_seconds not in (None, "")
            else str(snapshot.get("holding_time") or "").strip()
        ),
        "stop_loss": (
            _format_percent(stop_loss_pct, 2)
            if stop_loss_pct not in (None, "")
            else str(snapshot.get("stop_loss") or "").strip()
        ),
        "effective_stop": (
            _format_percent(effective_stop_loss_pct, 2)
            if effective_stop_loss_pct not in (None, "")
            else str(snapshot.get("effective_stop") or "").strip()
        ),
        "effective_stop_reason": effective_reason,
        "take_profit": (
            _format_percent(take_profit_pct, 2)
            if take_profit_pct not in (None, "")
            else str(snapshot.get("take_profit") or "").strip()
        ),
        "current_price": _fmt_optional_price(snapshot.get("current_price")),
        "average_price": _fmt_optional_price(snapshot.get("average_price")),
        "peak_price": _fmt_optional_price(snapshot.get("peak_price")),
        "current_drawdown": _fmt_optional_pct(snapshot.get("current_drawdown")),
        "peak_drawdown": _fmt_optional_pct(snapshot.get("peak_drawdown")),
        "vwap_distance": _fmt_optional_pct(snapshot.get("vwap_distance")),
        "price_source": str(snapshot.get("price_source") or story_monitor.get("price_source") or "").strip(),
        "feature_source": str(snapshot.get("feature_source") or story_monitor.get("feature_source") or "").strip(),
        "price_source_policy": str(snapshot.get("price_source_policy") or story_monitor.get("price_source_policy") or "").strip(),
        "active_exit_axis": active_exit_axis,
        "watch_axes": watch_axes,
        "hold_reasons": hold_reasons[:6],
        "exit_triggers": exit_triggers[:6],
    }


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

    market_context = _prefer_richer_trade_report_section(
        story_input.get("market_context_human"),
        report.get("market_context_at_entry"),
        report.get("market_context"),
    )
    selection = _prefer_richer_trade_report_section(
        story_input.get("scanner_reason_human"),
        report.get("why_this_symbol_was_chosen"),
        report.get("why_this_symbol"),
    )
    filters = _prefer_richer_trade_report_section(
        story_input.get("filters_human"),
        report.get("scanner_filters"),
        report.get("scanner_logic_and_filters"),
    )
    monitor = _prefer_richer_trade_report_section(
        story_input.get("monitor_reason_human"),
        report.get("holding_monitoring_story"),
        report.get("monitor_trigger_reasoning"),
    )
    guard = _prefer_richer_trade_report_section(
        story_input.get("guard_reason_human"),
        report.get("guard_approval_result"),
    )
    execution = _prefer_richer_trade_report_section(
        story_input.get("execution_outcome_human"),
        report.get("execution_quality"),
        report.get("execution_result"),
    )
    reporter_eval = _prefer_richer_trade_report_section(
        story_input.get("reporter_status_human"),
        report.get("reporter_evaluation"),
        lifecycle.get("reporter"),
    )
    conclusion = _prefer_richer_trade_report_section(
        story_input.get("operator_conclusion_human"),
        report.get("final_operator_conclusion"),
        lifecycle.get("summary"),
    )
    executive = _prefer_richer_trade_report_section(report.get("executive_summary"))
    lifecycle_summary = lifecycle.get("summary") if isinstance(lifecycle.get("summary"), dict) else {}
    entry_summary = story_input.get("entry_summary") if isinstance(story_input.get("entry_summary"), dict) else {}
    exit_summary = story_input.get("exit_summary") if isinstance(story_input.get("exit_summary"), dict) else {}
    story_monitor = story_input.get("monitor_reason_human") if isinstance(story_input.get("monitor_reason_human"), dict) else {}
    report_monitor_snapshot = report.get("monitor_snapshot") if isinstance(report.get("monitor_snapshot"), dict) else {}
    monitor_snapshot = _normalize_canonical_monitor_snapshot(report_monitor_snapshot, story_monitor)

    market_bullets = _trade_report_section_bullets(market_context)
    selection_bullets = _trade_report_section_bullets(selection)
    filter_bullets = _trade_report_section_bullets(filters, limit=8)
    monitor_bullets = _trade_report_section_bullets(monitor)
    execution_bullets = _trade_report_section_bullets(execution)
    market_regime = str(
        market_context.get("regime")
        or _extract_labeled_bullet(market_bullets, ["market regime", "regime", "시장 레짐", "시장 환경"])
        or ""
    )
    market_sentiment = str(
        market_context.get("market_sentiment")
        or _extract_labeled_bullet(market_bullets, ["market sentiment", "시장 심리"])
        or ""
    )
    global_sentiment = str(
        market_context.get("global_sentiment_score")
        or _extract_labeled_bullet(market_bullets, ["global sentiment score", "global sentiment", "글로벌 감성 점수"])
        or ""
    )
    vix_level = str(
        market_context.get("vix_level")
        or _extract_labeled_bullet(market_bullets, ["vix / fear index level", "vix", "vix 수준", "vix / fear index", "vix / 공포 지수 수준"])
        or ""
    )
    universe_size = _extract_labeled_int(selection_bullets, ["universe scanned", "스캐너 후보 수", "후보 수"])
    selected_rank = _extract_labeled_int(selection_bullets, ["selected rank", "최종 선정 순위", "선정 순위"])
    canonical_filter_rows = _parse_canonical_filter_bullets(filter_bullets)
    strategist_evidence = story_input.get("strategist_evidence") if isinstance(story_input.get("strategist_evidence"), dict) else {}
    scanner_evidence = story_input.get("scanner_evidence") if isinstance(story_input.get("scanner_evidence"), dict) else {}
    monitor_timeline = story_input.get("monitor_timeline") if isinstance(story_input.get("monitor_timeline"), dict) else {}
    top_candidates = [dict(row) for row in list(selection.get("top_candidates") or []) if isinstance(row, dict)][:3]
    runner_ups = [dict(row) for row in list(selection.get("runner_ups") or []) if isinstance(row, dict)][:3]
    selection_reason_rows = [dict(row) for row in list(scanner_evidence.get("candidate_selection_reasons") or []) if isinstance(row, dict)]
    selection_reason_payload = (
        selection_reason_rows[0].get("payload")
        if selection_reason_rows and isinstance(selection_reason_rows[0].get("payload"), dict)
        else {}
    )
    why_selected = [str(x or "") for x in list(selection.get("why_selected") or selection_reason_payload.get("why_selected") or []) if str(x or "").strip()][:4]
    runner_ups_lost: List[Dict[str, Any]] = []
    for row in list(selection.get("runner_ups_lost") or selection_reason_payload.get("runner_ups_lost") or selection_reason_payload.get("runner_up_reasons") or []):
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip()
        why_lost = [
            str(x or "")
            for x in list(row.get("why_lost") or row.get("lost_because") or [])
            if str(x or "").strip()
        ][:4]
        summary = str(row.get("summary") or "; ".join(why_lost)).strip()
        if not symbol and not summary:
            continue
        runner_ups_lost.append(
            {
                "symbol": symbol,
                "why_lost": why_lost,
                "summary": summary,
            }
        )
        if len(runner_ups_lost) >= 3:
            break
    selection_basis = str(selection.get("selection_basis") or selection_reason_payload.get("final_decision_basis") or "").strip()
    tie_break_rule = str(selection.get("tie_break_rule") or selection_reason_payload.get("tie_break_rule") or "").strip()

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
            or monitor_snapshot.get("posture")
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
        "headline_count": market_context.get("headline_count"),
        "news_query_count": market_context.get("news_query_count"),
        "news_query_targets": [str(x or "") for x in list(market_context.get("news_query_targets") or [])[:6] if str(x or "").strip()],
        "market_news_titles": [str(x or "") for x in list(market_context.get("market_news_titles") or [])[:3] if str(x or "").strip()],
        "candidate_news_titles": [str(x or "") for x in list(market_context.get("candidate_news_titles") or [])[:3] if str(x or "").strip()],
        "market_context_summary": _trade_report_section_summary(market_context),
        "market_context_bullets": market_bullets,
        "selection_summary": _trade_report_section_summary(selection),
        "selection_bullets": selection_bullets,
        "universe_size": universe_size,
        "selected_rank": selected_rank,
        "selected_score": selection.get("selected_score"),
        "selected_sources": [str(x or "") for x in list(selection.get("selected_sources") or [])[:5] if str(x or "").strip()],
        "why_selected": why_selected,
        "selection_basis": selection_basis,
        "tie_break_rule": tie_break_rule,
        "top_candidates": top_candidates,
        "runner_ups": runner_ups,
        "runner_ups_lost": runner_ups_lost,
        "filters_summary": _trade_report_section_summary(filters),
        "filter_bullets": filter_bullets,
        "filter_rows": canonical_filter_rows,
        "monitor_summary": _trade_report_section_summary(monitor),
        "monitor_bullets": monitor_bullets,
        "monitor_snapshot": monitor_snapshot if isinstance(monitor_snapshot, dict) else {},
        "monitor_decision_chain": [str(x or "") for x in list(monitor.get("decision_reason_chain") or [])[:6] if str(x or "").strip()],
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
        "evidence": {
            "strategist": {
                "market_context_snapshots": len(list(strategist_evidence.get("market_context_snapshots") or [])),
                "global_sentiment_breakdowns": len(list(strategist_evidence.get("global_sentiment_breakdowns") or [])),
                "news_evidence_ranked": len(list(strategist_evidence.get("news_evidence_ranked") or [])),
                "decision_frames": len(list(strategist_evidence.get("decision_frames") or [])),
                "llm_response_saved": len(list(strategist_evidence.get("llm_response_saved") or [])),
            },
            "scanner": {
                "candidate_pool_snapshots": len(list(scanner_evidence.get("candidate_pool_snapshots") or [])),
                "candidate_ranking_tables": len(list(scanner_evidence.get("candidate_ranking_tables") or [])),
                "candidate_selection_reasons": len(list(scanner_evidence.get("candidate_selection_reasons") or [])),
                "selection_outputs": len(list(scanner_evidence.get("selection_outputs") or [])),
            },
            "monitor": {
                "threshold_snapshots": len(list(monitor_timeline.get("threshold_snapshots") or [])),
                "state_transitions": len(list(monitor_timeline.get("state_transitions") or [])),
                "exit_decision_details": len(list(monitor_timeline.get("exit_decision_details") or [])),
                "cycle_summaries": len(list(monitor_timeline.get("cycle_summaries") or [])),
            },
        },
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
    canonical_monitor_snapshot = (
        canonical_trade.get("monitor_snapshot")
        if isinstance(canonical_trade.get("monitor_snapshot"), dict)
        else {}
    )

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
    feature_coverage = _normalized_feature_coverage(
        scanner.get("feature_coverage") if isinstance(scanner.get("feature_coverage"), dict) else {},
        feature_snapshot,
    )
    quote_metrics = scanner.get("quote_metrics") if isinstance(scanner.get("quote_metrics"), dict) else _quote_metrics_snapshot(feature_snapshot)

    monitor_summary = monitor.get("summary") if isinstance(monitor.get("summary"), dict) else {}
    monitor_trace = monitor.get("decision_trace") if isinstance(monitor.get("decision_trace"), dict) else {}
    thresholds = monitor_trace.get("thresholds") if isinstance(monitor_trace.get("thresholds"), dict) else {}
    live_monitor_reason = str(monitor_summary.get("monitor_reason") or monitor_trace.get("monitor_reason") or "").strip()
    live_exit_reason = str(monitor_summary.get("exit_reason") or monitor_trace.get("exit_reason") or "").strip()

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
    report_lifecycle_status = str(trade_report.get("lifecycle_status") or canonical_trade.get("lifecycle_status") or "").strip().lower()
    canonical_action = str(canonical_trade.get("current_action") or "").upper()
    monitor_reason = str(canonical_trade.get("monitor_summary") or live_monitor_reason or "").strip()
    exit_reason = str(canonical_trade.get("exit_reason") or live_exit_reason or "").strip()
    if execution_action == "SELL":
        final_action = "SELL"
    elif execution_action == "BUY" and report_lifecycle_status != "closed":
        final_action = "BUY"
    elif canonical_action in {"BUY", "SELL", "HOLD", "WAIT"}:
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
    canonical_selection_basis = _clean_brief_text(canonical_trade.get("selection_basis") or "")
    if canonical_trade.get("selection_summary"):
        selection_reasons.append(str(canonical_trade.get("selection_summary")))
    if canonical_selection_basis and canonical_selection_basis not in selection_reasons:
        selection_reasons.append(canonical_selection_basis)
    for reason in list(canonical_trade.get("why_selected") or [])[:4]:
        cleaned = _clean_brief_text(reason)
        if cleaned and cleaned not in selection_reasons:
            selection_reasons.append(cleaned)
    if selected_why and selected_why not in selection_reasons:
        selection_reasons.append(selected_why)
    for bullet in list(canonical_trade.get("selection_bullets") or [])[:4]:
        text = str(bullet or "").strip()
        if text.lower().startswith("chart / feature coverage:"):
            continue
        if text and text not in selection_reasons:
            selection_reasons.append(text)
    if feature_coverage.get("total"):
        selection_reasons.append(
            f"chart feature coverage {feature_coverage.get('present')}/{feature_coverage.get('total')} ({feature_coverage.get('quality') or '-'})"
        )
    if quote_metrics.get("quote_trading_value") is not None:
        selection_reasons.append("acceptable turnover and tradability")
    if strategist_summary.get("playbook"):
        selection_reasons.append(f"aligned with playbook {strategist_summary.get('playbook')}")

    comparison_reasons: List[str] = []
    canonical_runner_ups_lost = [dict(row) for row in list(canonical_trade.get("runner_ups_lost") or []) if isinstance(row, dict)]
    if canonical_runner_ups_lost:
        for row in canonical_runner_ups_lost[:3]:
            symbol = str(row.get("symbol") or "").strip()
            summary = _clean_brief_text(row.get("summary") or "; ".join(list(row.get("why_lost") or [])))
            if symbol and summary:
                comparison_reasons.append(f"{symbol} was weaker: {summary}")
    elif len(top_candidates) >= 2:
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

    chart_status, chart_note = _chart_filter_status_and_note(feature_coverage)

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
    effective_stop_loss = thresholds.get("effective_stop_loss_pct")
    effective_stop_reason = str(thresholds.get("effective_stop_reason") or "").strip()
    if stop_loss is None:
        stop_loss = thresholds.get("stop_loss")
    if take_profit is None:
        take_profit = thresholds.get("take_profit")
    stop_loss_text = _format_percent(stop_loss, 2) if stop_loss is not None else "-"
    take_profit_text = _format_percent(take_profit, 2) if take_profit is not None else "-"
    effective_stop_text = _format_percent(effective_stop_loss, 2) if effective_stop_loss not in (None, "") else stop_loss_text
    current_price = monitor_trace.get("price")
    avg_price_monitor = monitor_trace.get("avg_price")
    peak_price = monitor_trace.get("peak_price") or monitor_summary.get("peak_price")
    peak_drawdown_raw = monitor_trace.get("peak_drawdown")
    if peak_drawdown_raw in (None, ""):
        peak_drawdown_raw = monitor_summary.get("peak_drawdown")
    vwap_distance_raw = monitor_trace.get("vwap_distance")
    if vwap_distance_raw in (None, ""):
        vwap_distance_raw = monitor_summary.get("vwap_distance")
    current_drawdown_raw = None
    if _safe_float(current_price, 0.0) > 0.0 and _safe_float(peak_price, 0.0) > 0.0:
        current_drawdown_raw = (_safe_float(current_price, 0.0) / _safe_float(peak_price, 1.0)) - 1.0
    elif peak_drawdown_raw not in (None, ""):
        current_drawdown_raw = peak_drawdown_raw
    watch_axes = _monitor_watch_axes(thresholds)
    active_exit_axis = _friendly_exit_reason(live_exit_reason or effective_stop_reason or live_monitor_reason or exit_reason or monitor_reason or "hold")
    holding_time = _format_duration(monitor_summary.get("position_age_seconds") or monitor_trace.get("position_age_seconds"))

    canonical_holding_time = str(canonical_monitor_snapshot.get("holding_time") or "").strip()
    canonical_posture = str(canonical_monitor_snapshot.get("posture") or "").strip()
    canonical_current_price = str(canonical_monitor_snapshot.get("current_price") or "").strip()
    canonical_average_price = str(canonical_monitor_snapshot.get("average_price") or "").strip()
    canonical_peak_price = str(canonical_monitor_snapshot.get("peak_price") or "").strip()
    canonical_current_drawdown = str(canonical_monitor_snapshot.get("current_drawdown") or "").strip()
    canonical_peak_drawdown = str(canonical_monitor_snapshot.get("peak_drawdown") or "").strip()
    canonical_vwap_distance = str(canonical_monitor_snapshot.get("vwap_distance") or "").strip()
    canonical_stop_loss = str(canonical_monitor_snapshot.get("stop_loss") or "").strip()
    canonical_effective_stop = str(canonical_monitor_snapshot.get("effective_stop") or "").strip()
    canonical_effective_stop_reason = str(canonical_monitor_snapshot.get("effective_stop_reason") or "").strip()
    canonical_take_profit = str(canonical_monitor_snapshot.get("take_profit") or "").strip()
    canonical_price_source = str(canonical_monitor_snapshot.get("price_source") or "").strip()
    canonical_feature_source = str(canonical_monitor_snapshot.get("feature_source") or "").strip()
    canonical_price_source_policy = str(canonical_monitor_snapshot.get("price_source_policy") or "").strip()
    canonical_active_exit_axis = str(canonical_monitor_snapshot.get("active_exit_axis") or "").strip()
    canonical_watch_axes = [str(x or "") for x in list(canonical_monitor_snapshot.get("watch_axes") or []) if str(x or "").strip()]
    canonical_hold_reasons = [str(x or "") for x in list(canonical_monitor_snapshot.get("hold_reasons") or []) if str(x or "").strip()]
    canonical_exit_triggers = [str(x or "") for x in list(canonical_monitor_snapshot.get("exit_triggers") or []) if str(x or "").strip()]

    entry_evaluated = bool(
        canonical_monitor_snapshot.get("entry_evaluated")
        or monitor_summary.get("entry_evaluated")
        or monitor_trace.get("entry_evaluated")
    )
    entry_triggered = bool(
        canonical_monitor_snapshot.get("entry_triggered")
        or monitor_summary.get("entry_triggered")
        or monitor_trace.get("entry_triggered")
    )
    entry_reason_code = str(
        canonical_monitor_snapshot.get("entry_reason")
        or monitor_summary.get("entry_reason")
        or monitor_trace.get("entry_reason")
        or ""
    ).strip()
    entry_pattern = str(
        canonical_monitor_snapshot.get("entry_pattern")
        or monitor_summary.get("entry_pattern")
        or monitor_trace.get("entry_pattern")
        or ""
    ).strip()
    entry_metrics = (
        canonical_monitor_snapshot.get("entry_metrics")
        if isinstance(canonical_monitor_snapshot.get("entry_metrics"), dict)
        else (
            monitor_summary.get("entry_metrics")
            if isinstance(monitor_summary.get("entry_metrics"), dict)
            else (
                monitor_trace.get("entry_metrics")
                if isinstance(monitor_trace.get("entry_metrics"), dict)
                else {}
            )
        )
    )
    entry_guard_reason = str(
        canonical_monitor_snapshot.get("entry_guard_reason")
        or monitor_summary.get("entry_guard_reason")
        or monitor_trace.get("entry_guard_reason")
        or ""
    ).strip()
    entry_signal_chain = [
        str(x or "")
        for x in list(
            canonical_monitor_snapshot.get("entry_signal_chain")
            or monitor_summary.get("entry_signal_chain")
            or monitor_trace.get("entry_signal_chain")
            or []
        )
        if str(x or "").strip()
    ]

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

    canonical_report_summary = str(canonical_trade.get("report_summary") or "")
    generic_lifecycle_summary = canonical_report_summary.lower().startswith("current lifecycle status is")
    if canonical_report_summary and not (final_action == "SELL" and generic_lifecycle_summary):
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

    filter_rows = [dict(row) for row in list(canonical_trade.get("filter_rows") or []) if isinstance(row, dict)]
    if filter_rows:
        for row in filter_rows:
            name = str(row.get("name") or "").strip().lower()
            if name == "chart completeness filter":
                row["status"] = chart_status
                row["note"] = chart_note
                break
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
            "top_candidates": list(canonical_trade.get("top_candidates") or top_candidates[:3])[:3],
        },
        "entry_timing": {
            "decision": "BUY" if entry_triggered or final_action == "BUY" else "WAIT",
            "evaluated": entry_evaluated,
            "triggered": entry_triggered,
            "reason_code": entry_reason_code,
            "reason_text": str(canonical_trade.get("entry_reason") or ""),
            "pattern": entry_pattern,
            "signal_chain": entry_signal_chain[:5],
            "metrics": dict(entry_metrics or {}),
            "guard_reason": entry_guard_reason,
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
            "tie_break_rule": str(canonical_trade.get("tie_break_rule") or scanner_trace.get("tie_break_rule") or "higher composite score, then stronger feature coverage"),
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
            "posture": canonical_posture or final_action,
            "holding_time": canonical_holding_time or holding_time,
            "stop_loss": canonical_stop_loss or stop_loss_text,
            "effective_stop": canonical_effective_stop or effective_stop_text,
            "effective_stop_reason": (
                canonical_effective_stop_reason
                or (_friendly_exit_reason(effective_stop_reason or "stop_loss") if effective_stop_text != "-" else "-")
            ),
            "take_profit": canonical_take_profit or take_profit_text,
            "current_price": canonical_current_price or (_format_float(current_price, 2) if current_price not in (None, "") else "-"),
            "average_price": canonical_average_price or (_format_float(avg_price_monitor, 2) if avg_price_monitor not in (None, "") else "-"),
            "peak_price": canonical_peak_price or (_format_float(peak_price, 2) if peak_price not in (None, "") else "-"),
            "current_drawdown": canonical_current_drawdown or (_format_percent(current_drawdown_raw, 2) if current_drawdown_raw not in (None, "") else "-"),
            "peak_drawdown": canonical_peak_drawdown or (_format_percent(peak_drawdown_raw, 2) if peak_drawdown_raw not in (None, "") else "-"),
            "vwap_distance": canonical_vwap_distance or (_format_percent(vwap_distance_raw, 2) if vwap_distance_raw not in (None, "") else "-"),
            "price_source": canonical_price_source or str(monitor_trace.get("price_source") or monitor_summary.get("price_source") or "-"),
            "feature_source": canonical_feature_source or str(monitor_trace.get("feature_source") or monitor_summary.get("feature_source") or "-"),
            "price_source_policy": canonical_price_source_policy or str(monitor_trace.get("price_source_policy") or monitor_summary.get("price_source_policy") or ""),
            "active_exit_axis": (_friendly_exit_reason(canonical_active_exit_axis) if canonical_active_exit_axis else "") or active_exit_axis,
            "watch_axes": canonical_watch_axes or watch_axes,
            "hold_reasons": canonical_hold_reasons or hold_reasons[:4],
            "exit_triggers": canonical_exit_triggers or exit_triggers[:3],
        },
        "exit_plan": {
            "current_action": final_action,
            "summary": str(canonical_trade.get("exit_reason") or exit_reason or monitor_reason or ""),
            "effective_stop": canonical_effective_stop or effective_stop_text,
            "effective_stop_reason": (
                canonical_effective_stop_reason
                or (_friendly_exit_reason(effective_stop_reason or "stop_loss") if effective_stop_text != "-" else "-")
            ),
            "take_profit": canonical_take_profit or take_profit_text,
            "active_exit_axis": (_friendly_exit_reason(canonical_active_exit_axis) if canonical_active_exit_axis else "") or active_exit_axis,
            "exit_triggers": canonical_exit_triggers or exit_triggers[:3],
            "watch_axes": canonical_watch_axes or watch_axes,
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
        "risk_alerts": {
            "defensive_mode": defensive_mode,
            "weak_factors": weak_factors[:4],
            "thesis_invalidation": thesis_invalidation[:3],
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
        global_bits.append(f"global sentiment score={_safe_float(global_inputs.get('score'), 0.0):.2f}")
    if fear_index.get("level") is not None:
        global_bits.append(f"VIX={_safe_float(fear_index.get('level'), 0.0):.2f}")
    macro_moves = global_inputs.get("macro_moves") if isinstance(global_inputs.get("macro_moves"), dict) else {}
    if macro_moves.get("dxy_pct") is not None:
        global_bits.append(f"dollar index={_safe_float(macro_moves.get('dxy_pct'), 0.0):.2f}")

    selected_feature_snapshot = selected.get("feature_snapshot") if isinstance(selected.get("feature_snapshot"), dict) else {}
    feature_coverage = _normalized_feature_coverage(
        scanner.get("feature_coverage") if isinstance(scanner.get("feature_coverage"), dict) else {},
        selected_feature_snapshot,
    )
    _, fallback_chart_note = _chart_filter_status_and_note(feature_coverage)
    quote_metrics = scanner.get("quote_metrics") if isinstance(scanner.get("quote_metrics"), dict) else {}
    canonical_market_summary = str(canonical_trade.get("market_context_summary") or "").strip()
    canonical_selection_summary = str(canonical_trade.get("selection_summary") or "").strip()
    canonical_monitor_summary = str(canonical_trade.get("monitor_summary") or "").strip()
    canonical_guard_summary = str(canonical_trade.get("guard_summary") or "").strip()
    canonical_execution_summary = str(canonical_trade.get("execution_summary") or "").strip()
    canonical_reporter_summary = str(canonical_trade.get("reporter_summary") or "").strip()
    canonical_lifecycle_summary = str(canonical_trade.get("lifecycle_summary") or "").strip()
    canonical_report_summary = str(canonical_trade.get("report_summary") or "").strip()
    headline_action = str(canonical_trade.get("action") or trade_report.get("action") or "").strip().upper()
    headline_symbol = normalize_symbol(
        canonical_trade.get("symbol") or trade_report.get("symbol") or selected.get("symbol") or scanner_summary.get("top_stock") or "",
        allow_test_symbols=True,
    )
    headline_fallback = " ".join(part for part in [headline_action, headline_symbol, "Operator Summary"] if str(part or "").strip())
    headline = (
        str(canonical_trade.get("headline") or "").strip()
        or headline_fallback
        or f"{detail.get('run_id') or '-'} Operator Summary"
    )

    return {
        "status": "fallback",
        "model": "",
        "headline": headline,
        "commander_summary": (
            f"Commander ran the {((detail.get('commander') or {}).get('phase') or '-')} phase "
            f"through the {((detail.get('commander') or {}).get('path') or '-')} path."
        ),
        "strategist_summary": (
            canonical_market_summary
            or (
                f"Strategist reviewed {', '.join(global_bits) or 'market inputs'}, checked news query targets "
                f"{', '.join(_clean_brief_list(strategist_summary.get('news_query_targets'), limit=6)) or '-'}, and summarized the market into "
                f"themes {', '.join(_clean_brief_list(strategist_summary.get('themes'), limit=4)) or '-'} with playbook {strategist_summary.get('playbook') or '-'}."
            )
        ),
        "scanner_summary": (
            canonical_selection_summary
            or (
                f"Scanner reviewed {int(scanner_summary.get('candidate_pool_after_filter') or 0)} Kiwoom candidates, ranked "
                f"{_clean_brief_text(scanner_summary.get('top_stock') or selected.get('symbol') or '-')} first, and recorded the reason as "
                f"{selected.get('why') or '-'}."
            )
        ),
        "monitor_summary": (
            canonical_monitor_summary
            or (
                f"Monitor evaluated {monitor_summary.get('monitor_reason') or monitor_trace.get('monitor_reason') or '-'} "
                f"with exit={monitor_summary.get('exit_reason') or monitor_trace.get('exit_reason') or '-'}."
            )
        ),
        "supervisor_summary": (
            canonical_guard_summary
            or f"Supervisor concluded allowed={supervisor.get('allowed')} / reason={supervisor.get('reason') or '-'}."
        ),
        "executor_summary": (
            canonical_execution_summary
            or (
                f"Executor finished with {executor.get('action') or 'NOOP'} {executor.get('symbol') or ''} "
                f"status={executor.get('fill_status_summary') or executor.get('status') or '-'}."
            )
        ),
        "reporter_summary": (
            ("" if prefer_runtime_reporter else canonical_reporter_summary)
            or (
                f"Reporter recorded grade={reporter.get('ai_run_grade') or '-'} / "
                f"summary={reporter.get('ai_summary') or 'No same-day reporter summary is available yet.'}"
            )
        ),
        "operator_takeaways": [
            canonical_market_summary or f"News / macro inputs: {', '.join(global_bits) or 'no market inputs captured'}",
            (
                f"Chart / feature coverage: {fallback_chart_note}"
                if _safe_int(feature_coverage.get("total"), 0) > 0
                else str(canonical_trade.get("filters_summary") or "")
            )
            or f"Chart / feature coverage: {feature_coverage.get('quality') or '-'} ({feature_coverage.get('present') or 0}/{feature_coverage.get('total') or 0})",
            canonical_lifecycle_summary or canonical_report_summary or f"Live quote: price {quote_metrics.get('skill_quote_price') or '-'} volume {quote_metrics.get('quote_volume') or '-'} trading_value {quote_metrics.get('quote_trading_value') or '-'}",
        ],
    }


def _failure_operator_brief(
    detail: Dict[str, Any],
    *,
    status: str,
    model: str,
    reason: str,
    failure_status: str = "",
) -> Dict[str, Any]:
    trade_report = detail.get("trade_report") if isinstance(detail.get("trade_report"), dict) else {}
    symbol = normalize_symbol(
        trade_report.get("symbol")
        or (((detail.get("scanner") or {}).get("summary") or {}).get("top_stock") if isinstance(detail.get("scanner"), dict) else "")
        or "",
        allow_test_symbols=True,
    )
    action = str(trade_report.get("action") or "").strip().upper() or "WAIT"
    return {
        "status": str(status or "fallback"),
        "model": str(model or ""),
        "headline": " ".join(part for part in ["AI Brief Failed", action, symbol] if str(part or "").strip()),
        "commander_summary": "",
        "strategist_summary": "",
        "scanner_summary": "",
        "monitor_summary": "",
        "supervisor_summary": "",
        "executor_summary": "",
        "reporter_summary": "",
        "operator_takeaways": [],
        "reason": str(reason or "brief_generation_failed"),
        "failure": {
            "status": str(failure_status or status or "error"),
            "reason": str(reason or "brief_generation_failed"),
        },
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
    feature_coverage = _normalized_feature_coverage(
        scanner.get("feature_coverage") if isinstance(scanner.get("feature_coverage"), dict) else {},
        feature_snapshot,
    )
    chart_status, chart_note = _chart_filter_status_and_note(feature_coverage)
    canonical_filter_bullets = list(canonical_trade.get("filter_bullets") or [])[:8]
    canonical_selection_bullets = list(canonical_trade.get("selection_bullets") or [])[:6]
    if _safe_int(feature_coverage.get("total"), 0) > 0:
        updated_bullets: List[str] = []
        replaced_chart_bullet = False
        for bullet in canonical_filter_bullets:
            text = str(bullet or "").strip()
            if text.lower().startswith("chart completeness filter:"):
                updated_bullets.append(f"chart completeness filter: {chart_status} - {chart_note}")
                replaced_chart_bullet = True
            else:
                updated_bullets.append(text)
        if not replaced_chart_bullet:
            updated_bullets.append(f"chart completeness filter: {chart_status} - {chart_note}")
        canonical_filter_bullets = updated_bullets[:8]
        canonical_filters_summary = (
            f"Scanner and guard checks used normalized chart coverage with {feature_coverage.get('present')}/{feature_coverage.get('total')} captured features."
        )
        updated_selection_bullets: List[str] = []
        replaced_selection_chart_bullet = False
        for bullet in canonical_selection_bullets:
            text = str(bullet or "").strip()
            if text.lower().startswith("chart / feature coverage:"):
                updated_selection_bullets.append(
                    f"Chart / feature coverage: {feature_coverage.get('present')}/{feature_coverage.get('total')}"
                )
                replaced_selection_chart_bullet = True
            else:
                updated_selection_bullets.append(text)
        if not replaced_selection_chart_bullet:
            updated_selection_bullets.append(
                f"Chart / feature coverage: {feature_coverage.get('present')}/{feature_coverage.get('total')}"
            )
        canonical_selection_bullets = updated_selection_bullets[:6]
    else:
        canonical_filters_summary = canonical_trade.get("filters_summary")
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
            "market_regime": strategist_summary.get("market_regime") or canonical_trade.get("market_regime"),
            "market_sentiment": strategist_summary.get("market_sentiment") or canonical_trade.get("market_sentiment"),
            "themes": list(strategist_summary.get("themes") or canonical_trade.get("themes") or [])[:5],
            "playbook": strategist_summary.get("playbook") or canonical_trade.get("playbook"),
            "scanner_bias": strategist_summary.get("scanner_bias"),
            "risk_tone": strategist_summary.get("risk_tone"),
            "monitor_guidance": strategist_summary.get("monitor_guidance"),
            "news_query_targets": list(strategist_summary.get("news_query_targets") or canonical_trade.get("news_query_targets") or [])[:8],
            "news_query_reasoning": strategist_summary.get("news_query_reasoning"),
            "global_sentiment_inputs": raw_input.get("global_sentiment_inputs") if isinstance(raw_input.get("global_sentiment_inputs"), dict) else {},
            "market_news_titles": [str((x or {}).get("title") or "") for x in list(raw_input.get("collected_market_news") or [])[:4] if isinstance(x, dict)] or list(canonical_trade.get("market_news_titles") or [])[:4],
            "candidate_news_titles": [str((x or {}).get("title") or "") for x in list(raw_input.get("collected_candidate_news") or [])[:4] if isinstance(x, dict)] or list(canonical_trade.get("candidate_news_titles") or [])[:4],
            "llm_status": strategist_summary.get("llm_frame_status"),
            "llm_low_confidence": strategist_summary.get("llm_frame_low_confidence"),
            "canonical_summary": canonical_trade.get("market_context_summary"),
            "canonical_bullets": list(canonical_trade.get("market_context_bullets") or [])[:6],
        },
        "scanner": {
            "candidate_source": scanner.get("summary", {}).get("candidate_source") if isinstance(scanner.get("summary"), dict) else "",
            "candidate_pool_before_filter": (scanner.get("summary") or {}).get("candidate_pool_before_filter") if isinstance(scanner.get("summary"), dict) else None,
            "candidate_pool_after_filter": (scanner.get("summary") or {}).get("candidate_pool_after_filter") if isinstance(scanner.get("summary"), dict) else None,
            "top_ranked_symbols": list(canonical_trade.get("top_candidates") or [])[:5]
            or (
                list((scanner.get("summary") or {}).get("top_ranked_symbols") or [])[:5]
                if isinstance(scanner.get("summary"), dict)
                else []
            ),
            "source_mix": scanner_trace.get("kiwoom_pool_source_mix") if isinstance(scanner_trace.get("kiwoom_pool_source_mix"), dict) else {},
            "selected_symbol": scanner_trace.get("selected_symbol") or selected.get("symbol"),
            "selected_reason": canonical_trade.get("selection_basis")
            or canonical_trade.get("selection_summary")
            or selected.get("why"),
            "source_scores": selected.get("source_scores") if isinstance(selected.get("source_scores"), dict) else {},
            "score_total": selected.get("score_total"),
            "confidence": selected.get("confidence"),
            "feature_coverage": feature_coverage,
            "quote_metrics": scanner.get("quote_metrics") if isinstance(scanner.get("quote_metrics"), dict) else {},
            "score_breakdown": score_breakdown,
            "component_snapshot": component_snapshot,
            "feature_snapshot": feature_snapshot,
            "why_selected": list(canonical_trade.get("why_selected") or [])[:4],
            "tie_break_rule": canonical_trade.get("tie_break_rule"),
            "runner_ups": list(canonical_trade.get("runner_ups") or [])[:3],
            "runner_ups_lost": list(canonical_trade.get("runner_ups_lost") or [])[:3],
            "canonical_bullets": canonical_selection_bullets,
            "canonical_filters_summary": canonical_filters_summary,
            "canonical_filter_bullets": canonical_filter_bullets,
        },
        "monitor": {
            "monitor_reason": monitor_summary.get("monitor_reason") or monitor_trace.get("monitor_reason") or canonical_trade.get("monitor_summary"),
            "exit_reason": monitor_summary.get("exit_reason") or monitor_trace.get("exit_reason") or canonical_trade.get("exit_reason"),
            "position_age_seconds": monitor_summary.get("position_age_seconds"),
            "entry_evaluated": monitor_summary.get("entry_evaluated"),
            "entry_triggered": monitor_summary.get("entry_triggered"),
            "entry_reason": monitor_summary.get("entry_reason") or monitor_trace.get("entry_reason"),
            "entry_pattern": monitor_summary.get("entry_pattern") or monitor_trace.get("entry_pattern"),
            "entry_guard_reason": monitor_summary.get("entry_guard_reason") or monitor_trace.get("entry_guard_reason"),
            "entry_intent_submitted": monitor_summary.get("entry_intent_submitted"),
            "entry_metrics": monitor_summary.get("entry_metrics") if isinstance(monitor_summary.get("entry_metrics"), dict) else {},
            "entry_thresholds": monitor_summary.get("entry_thresholds") if isinstance(monitor_summary.get("entry_thresholds"), dict) else {},
            "thresholds": monitor_trace.get("thresholds") if isinstance(monitor_trace.get("thresholds"), dict) else {},
            "strategy_frame_adjustments": list(monitor_trace.get("strategy_frame_adjustments") or [])[:6],
            "exit_policy_guard_adjustments": list(monitor_trace.get("exit_policy_guard_adjustments") or [])[:6],
            "canonical_bullets": list(canonical_trade.get("monitor_bullets") or [])[:6],
            "canonical_snapshot": dict(canonical_trade.get("monitor_snapshot") or {}),
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


def _compact_scalar_map(data: Any, *, limit: int = 8, max_len: int = 120) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    out: Dict[str, Any] = {}
    for key, value in list(data.items()):
        if len(out) >= max(1, int(limit)):
            break
        if isinstance(value, (int, float, bool)) or value is None:
            out[str(key)] = value
            continue
        text = _trim_text(value, max_len=max_len)
        if text:
            out[str(key)] = text
    return out


def _compact_ranked_symbols(rows: Any, *, limit: int = 3) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in rows:
        if len(out) >= max(1, int(limit)):
            break
        if isinstance(item, dict):
            row = {
                "symbol": _trim_text(item.get("symbol") or item.get("code") or item.get("ticker"), max_len=24),
                "score": item.get("score_total") if item.get("score_total") is not None else item.get("score"),
                "reason": _trim_text(item.get("reason") or item.get("why"), max_len=160),
            }
        else:
            row = {
                "symbol": _trim_text(item, max_len=24),
                "score": None,
                "reason": "",
            }
        if row["symbol"]:
            out.append(row)
    return out


def _compact_monitor_thresholds(data: Any) -> Dict[str, Any]:
    row = data if isinstance(data, dict) else {}
    keys = (
        "hard_stop_pct",
        "effective_stop_loss_pct",
        "effective_stop_reason",
        "take_profit_pct",
        "peak_drawdown_exit_pct",
        "trailing_stop_pct",
        "vwap_breakdown_pct",
        "intraday_low_break_pct",
        "trend_strength_floor",
        "exit_confirm_required",
        "exit_confirm_count",
    )
    return {key: row.get(key) for key in keys if key in row}


def _compact_canonical_trade_for_brief(data: Any) -> Dict[str, Any]:
    row = data if isinstance(data, dict) else {}
    return {
        "available": bool(row.get("available")),
        "trade_id": _trim_text(row.get("trade_id"), max_len=80),
        "story_type": _trim_text(row.get("story_type"), max_len=32),
        "execution_mode_label": _trim_text(row.get("execution_mode_label"), max_len=48),
        "lifecycle_status": _trim_text(row.get("lifecycle_status"), max_len=24),
        "lifecycle_summary": _trim_text(row.get("lifecycle_summary"), max_len=220),
        "current_action": _trim_text(row.get("current_action"), max_len=24),
        "entry_reason": _trim_text(row.get("entry_reason"), max_len=180),
        "exit_reason": _trim_text(row.get("exit_reason"), max_len=180),
        "market_context_summary": _trim_text(row.get("market_context_summary"), max_len=220),
        "market_context_bullets": _clean_str_list(row.get("market_context_bullets"), limit=6, max_len=180),
        "headline_count": row.get("headline_count"),
        "news_query_count": row.get("news_query_count"),
        "news_query_targets": _clean_str_list(row.get("news_query_targets"), limit=6, max_len=80),
        "market_news_titles": _clean_str_list(row.get("market_news_titles"), limit=3, max_len=120),
        "candidate_news_titles": _clean_str_list(row.get("candidate_news_titles"), limit=3, max_len=120),
        "selection_summary": _trim_text(row.get("selection_summary"), max_len=220),
        "selection_bullets": _clean_str_list(row.get("selection_bullets"), limit=6, max_len=180),
        "selected_score": row.get("selected_score"),
        "selected_sources": _clean_str_list(row.get("selected_sources"), limit=5, max_len=80),
        "why_selected": _clean_str_list(row.get("why_selected"), limit=4, max_len=160),
        "selection_basis": _trim_text(row.get("selection_basis"), max_len=220),
        "tie_break_rule": _trim_text(row.get("tie_break_rule"), max_len=160),
        "top_candidates": _compact_ranked_symbols(row.get("top_candidates"), limit=3),
        "runner_ups": _compact_ranked_symbols(row.get("runner_ups"), limit=3),
        "runner_ups_lost": [
            {
                "symbol": _trim_text((item or {}).get("symbol"), max_len=24),
                "summary": _trim_text((item or {}).get("summary"), max_len=180),
            }
            for item in list(row.get("runner_ups_lost") or [])[:3]
            if isinstance(item, dict) and (_trim_text((item or {}).get("symbol"), max_len=24) or _trim_text((item or {}).get("summary"), max_len=180))
        ],
        "filters_summary": _trim_text(row.get("filters_summary"), max_len=220),
        "filter_bullets": _clean_str_list(row.get("filter_bullets"), limit=5, max_len=180),
        "monitor_summary": _trim_text(row.get("monitor_summary"), max_len=220),
        "monitor_bullets": _clean_str_list(row.get("monitor_bullets"), limit=6, max_len=180),
        "monitor_snapshot": _compact_scalar_map(row.get("monitor_snapshot"), limit=10, max_len=120),
        "monitor_decision_chain": _clean_str_list(row.get("monitor_decision_chain"), limit=5, max_len=120),
        "guard_summary": _trim_text(row.get("guard_summary"), max_len=180),
        "execution_summary": _trim_text(row.get("execution_summary"), max_len=180),
        "execution_bullets": _clean_str_list(row.get("execution_bullets"), limit=4, max_len=160),
        "reporter_summary": _trim_text(row.get("reporter_summary"), max_len=180),
        "reporter_status": _trim_text(row.get("reporter_status"), max_len=32),
        "reporter_grade": _trim_text(row.get("reporter_grade"), max_len=16),
    }


def _compact_operator_brief_input_for_llm(prepared_input: Dict[str, Any]) -> Dict[str, Any]:
    strategist = prepared_input.get("strategist") if isinstance(prepared_input.get("strategist"), dict) else {}
    scanner = prepared_input.get("scanner") if isinstance(prepared_input.get("scanner"), dict) else {}
    monitor = prepared_input.get("monitor") if isinstance(prepared_input.get("monitor"), dict) else {}
    commander = prepared_input.get("commander") if isinstance(prepared_input.get("commander"), dict) else {}
    reporter = prepared_input.get("reporter") if isinstance(prepared_input.get("reporter"), dict) else {}
    supervisor = prepared_input.get("supervisor") if isinstance(prepared_input.get("supervisor"), dict) else {}
    executor = prepared_input.get("executor") if isinstance(prepared_input.get("executor"), dict) else {}
    trade_report = prepared_input.get("trade_report") if isinstance(prepared_input.get("trade_report"), dict) else {}
    return {
        "run_id": _trim_text(prepared_input.get("run_id"), max_len=80),
        "commander": {
            "mode": _trim_text(commander.get("mode"), max_len=24),
            "phase": _trim_text(commander.get("phase"), max_len=24),
            "path": _trim_text(commander.get("path"), max_len=80),
            "status": _trim_text(commander.get("status"), max_len=24),
        },
        "strategist": {
            "market_regime": _trim_text(strategist.get("market_regime"), max_len=24),
            "market_sentiment": _trim_text(strategist.get("market_sentiment"), max_len=24),
            "themes": _clean_str_list(strategist.get("themes"), limit=4, max_len=80),
            "playbook": _trim_text(strategist.get("playbook"), max_len=32),
            "scanner_bias": _trim_text(strategist.get("scanner_bias"), max_len=120),
            "risk_tone": _trim_text(strategist.get("risk_tone"), max_len=120),
            "monitor_guidance": _trim_text(strategist.get("monitor_guidance"), max_len=180),
            "news_query_targets": _clean_str_list(strategist.get("news_query_targets"), limit=5, max_len=80),
            "news_query_reasoning": _trim_text(strategist.get("news_query_reasoning"), max_len=180),
            "global_sentiment_inputs": _compact_scalar_map(strategist.get("global_sentiment_inputs"), limit=8, max_len=80),
            "market_news_titles": _clean_str_list(strategist.get("market_news_titles"), limit=3, max_len=120),
            "candidate_news_titles": _clean_str_list(strategist.get("candidate_news_titles"), limit=3, max_len=120),
            "llm_status": _trim_text(strategist.get("llm_status"), max_len=24),
            "llm_low_confidence": strategist.get("llm_low_confidence"),
            "canonical_summary": _trim_text(strategist.get("canonical_summary"), max_len=220),
            "canonical_bullets": _clean_str_list(strategist.get("canonical_bullets"), limit=4, max_len=180),
        },
        "scanner": {
            "candidate_source": _trim_text(scanner.get("candidate_source"), max_len=60),
            "candidate_pool_before_filter": scanner.get("candidate_pool_before_filter"),
            "candidate_pool_after_filter": scanner.get("candidate_pool_after_filter"),
            "top_ranked_symbols": _compact_ranked_symbols(scanner.get("top_ranked_symbols"), limit=3),
            "source_mix": _compact_scalar_map(scanner.get("source_mix"), limit=6, max_len=60),
            "selected_symbol": _trim_text(scanner.get("selected_symbol"), max_len=24),
            "selected_reason": _trim_text(scanner.get("selected_reason"), max_len=220),
            "source_scores": _compact_scalar_map(scanner.get("source_scores"), limit=6, max_len=80),
            "score_total": scanner.get("score_total"),
            "confidence": scanner.get("confidence"),
            "feature_coverage": _compact_scalar_map(scanner.get("feature_coverage"), limit=6, max_len=80),
            "quote_metrics": _compact_scalar_map(scanner.get("quote_metrics"), limit=6, max_len=80),
            "score_breakdown": _compact_scalar_map(scanner.get("score_breakdown"), limit=8, max_len=80),
            "why_selected": _clean_str_list(scanner.get("why_selected"), limit=4, max_len=160),
            "tie_break_rule": _trim_text(scanner.get("tie_break_rule"), max_len=160),
            "runner_ups": _compact_ranked_symbols(scanner.get("runner_ups"), limit=3),
            "runner_ups_lost": [
                {
                    "symbol": _trim_text((item or {}).get("symbol"), max_len=24),
                    "summary": _trim_text((item or {}).get("summary"), max_len=160),
                }
                for item in list(scanner.get("runner_ups_lost") or [])[:3]
                if isinstance(item, dict)
            ],
            "canonical_bullets": _clean_str_list(scanner.get("canonical_bullets"), limit=4, max_len=180),
            "canonical_filters_summary": _trim_text(scanner.get("canonical_filters_summary"), max_len=180),
            "canonical_filter_bullets": _clean_str_list(scanner.get("canonical_filter_bullets"), limit=4, max_len=160),
        },
        "monitor": {
            "monitor_reason": _trim_text(monitor.get("monitor_reason"), max_len=220),
            "exit_reason": _trim_text(monitor.get("exit_reason"), max_len=120),
            "position_age_seconds": monitor.get("position_age_seconds"),
            "entry_evaluated": monitor.get("entry_evaluated"),
            "entry_triggered": monitor.get("entry_triggered"),
            "entry_reason": _trim_text(monitor.get("entry_reason"), max_len=160),
            "entry_pattern": _trim_text(monitor.get("entry_pattern"), max_len=80),
            "entry_guard_reason": _trim_text(monitor.get("entry_guard_reason"), max_len=120),
            "entry_intent_submitted": monitor.get("entry_intent_submitted"),
            "entry_metrics": _compact_scalar_map(monitor.get("entry_metrics"), limit=10, max_len=80),
            "entry_thresholds": _compact_scalar_map(monitor.get("entry_thresholds"), limit=8, max_len=80),
            "thresholds": _compact_monitor_thresholds(monitor.get("thresholds")),
            "strategy_frame_adjustments": _clean_str_list(monitor.get("strategy_frame_adjustments"), limit=4, max_len=120),
            "exit_policy_guard_adjustments": _clean_str_list(monitor.get("exit_policy_guard_adjustments"), limit=4, max_len=120),
            "canonical_bullets": _clean_str_list(monitor.get("canonical_bullets"), limit=4, max_len=160),
            "canonical_snapshot": _compact_scalar_map(monitor.get("canonical_snapshot"), limit=10, max_len=120),
        },
        "supervisor": _compact_scalar_map(supervisor, limit=8, max_len=120),
        "executor": {
            "action": _trim_text(executor.get("action"), max_len=24),
            "symbol": _trim_text(executor.get("symbol"), max_len=24),
            "qty": executor.get("qty"),
            "status": _trim_text(executor.get("status"), max_len=160),
            "canonical_summary": _trim_text(executor.get("canonical_summary"), max_len=180),
            "canonical_bullets": _clean_str_list(executor.get("canonical_bullets"), limit=4, max_len=160),
        },
        "reporter": {
            "ai_summary": _trim_text(reporter.get("ai_summary"), max_len=180),
            "ai_run_grade": _trim_text(reporter.get("ai_run_grade"), max_len=16),
            "found": reporter.get("found"),
            "status": _trim_text(reporter.get("status"), max_len=24),
            "reason": _trim_text(reporter.get("reason"), max_len=180),
        },
        "trade_report": {
            "report_available": trade_report.get("report_available"),
            "trade_id": _trim_text(trade_report.get("trade_id"), max_len=80),
            "lifecycle_status": _trim_text(trade_report.get("lifecycle_status"), max_len=24),
            "lifecycle_summary": _trim_text(trade_report.get("lifecycle_summary"), max_len=180),
            "story_type": _trim_text(trade_report.get("story_type"), max_len=32),
            "execution_mode_label": _trim_text(trade_report.get("execution_mode_label"), max_len=48),
            "summary": _trim_text(trade_report.get("summary"), max_len=180),
        },
        "canonical_trade": _compact_canonical_trade_for_brief(prepared_input.get("canonical_trade")),
    }


_BRIEF_INTERNAL_TEXT_MARKERS = (
    "canonical_trade.available",
    "reports/trades",
    "source of truth",
    "run-level",
    "1차 source of truth",
)


def _contains_internal_brief_marker(text: Any) -> bool:
    raw = str(text or "").strip().lower()
    if not raw:
        return False
    return any(marker in raw for marker in _BRIEF_INTERNAL_TEXT_MARKERS)


def _sanitize_operator_brief_text(text: Any) -> str:
    cleaned = _trim_text(text, max_len=1000)
    if not cleaned:
        return ""
    if _contains_internal_brief_marker(cleaned):
        return ""
    replacements = [
        ("minute-candle", "분봉"),
        ("minute candle", "분봉"),
        ("defensive_exit", "방어형 청산"),
        ("no_position", "포지션 없음"),
        ("No trigger yet", "아직 청산 신호는 확인되지 않았습니다."),
        ("Peak drawdown", "고점 대비 하락폭"),
        ("Hard stop", "고정 손절 기준"),
        ("Adaptive stop", "상황 대응형 손절 기준"),
        ("Take profit", "목표 수익 실현 기준"),
        ("Regime", "시장 상태"),
        ("regime", "시장 상태"),
        ("Universe scanned", "비교 후보 수"),
        ("Selected rank", "선정 순위"),
        ("Posture", "현재 포지션 판단"),
        ("Trigger", "감시 신호"),
        ("Exit trigger", "청산 신호"),
    ]
    for src, dst in replacements:
        cleaned = cleaned.replace(src, dst)
    cleaned = re.sub(r"\bBUY\b", "매수", cleaned)
    cleaned = re.sub(r"\bSELL\b", "매도", cleaned)
    cleaned = re.sub(r"\bHOLD\b", "보유 유지", cleaned)
    cleaned = re.sub(r"\bWAIT\b", "진입 보류", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _count_hangul_chars(text: Any) -> int:
    raw = str(text or "")
    return sum(1 for ch in raw if "\uac00" <= ch <= "\ud7a3")


def _contains_forbidden_brief_script(text: Any) -> bool:
    raw = str(text or "")
    return bool(re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", raw))


def _operator_brief_language_ok(candidate: Dict[str, Any]) -> bool:
    text_fields = [
        "headline",
        "commander_summary",
        "strategist_summary",
        "scanner_summary",
        "monitor_summary",
        "supervisor_summary",
        "executor_summary",
        "reporter_summary",
        "executive_summary",
        "scanner_reason",
        "entry_summary",
        "holding_summary",
        "exit_plan_summary",
        "risk_summary",
    ]
    total_hangul = 0
    for key in text_fields:
        value = str(candidate.get(key) or "").strip()
        if not value:
            continue
        if _contains_forbidden_brief_script(value):
            return False
        hangul_count = _count_hangul_chars(value)
        total_hangul += hangul_count
        ascii_letters = len(re.findall(r"[A-Za-z]", value))
        if hangul_count == 0 and ascii_letters >= 12:
            return False
    for key in ("operator_takeaways", "next_checkpoints"):
        for item in list(candidate.get(key) or []):
            value = str(item or "").strip()
            if not value:
                continue
            if _contains_forbidden_brief_script(value):
                return False
    return total_hangul > 0


def _prefer_richer_brief_text(primary: Any, fallback: Any, *, min_primary_len: int = 48) -> str:
    cleaned_primary = _sanitize_operator_brief_text(primary)
    cleaned_fallback = _sanitize_operator_brief_text(fallback)
    if not cleaned_primary:
        return cleaned_fallback
    if not cleaned_fallback:
        return cleaned_primary
    primary_hangul = _count_hangul_chars(cleaned_primary) > 0
    fallback_hangul = _count_hangul_chars(cleaned_fallback) > 0
    if fallback_hangul and not primary_hangul and len(cleaned_fallback) >= len(cleaned_primary) + 16:
        return cleaned_fallback
    if len(cleaned_primary) < min_primary_len and len(cleaned_fallback) >= len(cleaned_primary) + 20:
        return cleaned_fallback
    return cleaned_primary


def _should_replace_brief_monitor_summary(detail: Dict[str, Any], summary_text: str) -> bool:
    raw = str(summary_text or "").strip().lower()
    if not raw:
        return True
    if "no_position" not in raw and "포지션 없음" not in raw:
        return False
    trade_report = detail.get("trade_report") if isinstance(detail.get("trade_report"), dict) else {}
    lifecycle_status = str(trade_report.get("lifecycle_status") or "").strip().lower()
    report_action = str(trade_report.get("action") or "").strip().upper()
    executor = detail.get("executor") if isinstance(detail.get("executor"), dict) else {}
    execution = executor.get("execution") if isinstance(executor.get("execution"), dict) else {}
    execution_action = str(execution.get("action") or "").strip().upper()
    if lifecycle_status == "open" and (report_action == "BUY" or execution_action == "BUY"):
        return True
    if lifecycle_status == "closed" and (report_action == "SELL" or execution_action == "SELL"):
        return True
    return False


def _sanitize_operator_brief_result(detail: Dict[str, Any], candidate: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(candidate or {})
    for key in (
        "headline",
        "commander_summary",
        "strategist_summary",
        "scanner_summary",
        "monitor_summary",
        "supervisor_summary",
        "executor_summary",
        "reporter_summary",
    ):
        cleaned = _prefer_richer_brief_text(out.get(key), fallback.get(key))
        if key == "monitor_summary" and _should_replace_brief_monitor_summary(detail, cleaned):
            cleaned = _sanitize_operator_brief_text(fallback.get(key))
        out[key] = cleaned

    for key in (
        "executive_summary",
        "scanner_reason",
        "entry_summary",
        "holding_summary",
        "exit_plan_summary",
        "risk_summary",
    ):
        out[key] = _sanitize_operator_brief_text(out.get(key))

    next_checkpoints: List[str] = []
    seen_checkpoints: set[str] = set()
    for value in list(out.get("next_checkpoints") or []):
        cleaned = _sanitize_operator_brief_text(value)
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen_checkpoints:
            continue
        next_checkpoints.append(cleaned)
        seen_checkpoints.add(lowered)
        if len(next_checkpoints) >= 5:
            break
    if next_checkpoints:
        out["next_checkpoints"] = next_checkpoints

    candidate_takeaways: List[str] = []
    fallback_takeaways: List[str] = []
    seen_takeaways: set[str] = set()

    def _collect_takeaways(values: Any, target: List[str]) -> None:
        for value in list(values or []):
            cleaned = _sanitize_operator_brief_text(value)
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen_takeaways:
                continue
            target.append(cleaned)
            seen_takeaways.add(lowered)
            if len(target) >= 5:
                break

    _collect_takeaways(out.get("operator_takeaways"), candidate_takeaways)
    _collect_takeaways(fallback.get("operator_takeaways"), fallback_takeaways)
    candidate_hangul = sum(1 for item in candidate_takeaways if _count_hangul_chars(item) > 0)
    fallback_hangul = sum(1 for item in fallback_takeaways if _count_hangul_chars(item) > 0)
    if (
        len(candidate_takeaways) < 4
        or (fallback_hangul > candidate_hangul and len(fallback_takeaways) >= len(candidate_takeaways))
        or (sum(len(item) for item in candidate_takeaways) < max(120, sum(len(item) for item in fallback_takeaways) // 2))
    ):
        out["operator_takeaways"] = fallback_takeaways[:5] or candidate_takeaways[:5]
    else:
        out["operator_takeaways"] = candidate_takeaways[:5]
    return out


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
        "executive_summary": "string",
        "scanner_reason": "string",
        "entry_summary": "string",
        "holding_summary": "string",
        "exit_plan_summary": "string",
        "risk_summary": "string",
        "next_checkpoints": ["string"],
    }
    system_prompt = (
        "당신은 한국 주식 운영자를 위한 운영자 브리프 작성자입니다. "
        "반드시 JSON 객체 하나만 반환하고, 모든 설명 문장은 자연스러운 한국어로 작성하십시오. "
        "영어, 중국어, 일본어 문장은 사용하지 마십시오. "
        "VWAP, RSI, ADX, 종목코드처럼 시장에서 통용되는 짧은 용어만 예외적으로 허용됩니다."
    )
    user_prompt = (
        "입력 데이터를 바탕으로 운영자가 10초 안에 상황을 이해할 수 있는 간결한 브리프를 작성하십시오.\n"
        "작성 규칙:\n"
        "- 전체 흐름은 반드시 Scanner -> Entry -> Holding -> Exit 순서를 유지하십시오.\n"
        "- 모든 설명 값은 자연스러운 한국어 문장으로 작성하십시오.\n"
        "- entry_summary는 반드시 분봉 기준 진입 시점이나 진입 보류 이유를 설명해야 합니다.\n"
        "- 분봉 데이터가 없거나 진입 조건이 충족되지 않으면, 예를 들어 \"이번 거래는 분봉 데이터가 확보되지 않아 진입 근거를 확인할 수 없었습니다. 따라서 신규 진입은 보류 대상으로 해석했습니다.\"처럼 보수적으로 설명하십시오.\n"
        "- BUY가 이미 체결되었고 lifecycle이 열려 있으면 no_position이라고 쓰지 말고 현재 보유 상태를 설명하십시오.\n"
        "- SELL이 이미 체결되었고 lifecycle이 닫혀 있으면 어떤 청산 신호로 종료되었는지 분명하게 설명하십시오.\n"
        "- scanner_reason에는 후보 순위, 후보 수, 핵심 선정 이유 2~3개를 담으십시오.\n"
        "- holding_summary에는 현재 손익, 포지션 상태, 시장 해석을 담으십시오.\n"
        "- exit_plan_summary에는 어떤 조건에서 청산할지 조건형 문장으로 설명하십시오.\n"
        "- risk_summary에는 현재 리스크 요인을 2~3개로 정리하십시오.\n"
        "- next_checkpoints에는 운영자가 다음에 확인할 짧은 체크포인트를 넣으십시오.\n"
        "- canonical_trade.available, reports/trades, source of truth, run-level 같은 내부 문구는 절대 노출하지 마십시오.\n"
        f"계약: {json.dumps(contract, ensure_ascii=False)}\n"
        f"입력: {json.dumps(compact_input, ensure_ascii=False)}"
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
        "executive_summary": "string",
        "scanner_reason": "string",
        "entry_summary": "string",
        "holding_summary": "string",
        "exit_plan_summary": "string",
        "risk_summary": "string",
        "next_checkpoints": ["string"],
    }
    return [
        {
            "role": "system",
            "content": (
                "운영자 브리프를 계약에 맞는 JSON 객체 하나로 복구하십시오. "
                "모든 설명 값은 자연스러운 한국어로 작성하고, 중국어·일본어·영어 문장은 결과에 남기지 마십시오."
            ),
        },
        {
            "role": "user",
            "content": (
                f"계약: {json.dumps(contract, ensure_ascii=False)}\n"
                f"입력: {raw_text}"
            ),
        },
    ]

def _build_operator_brief_line_messages(compact_input: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "JSON 생성이 어렵다면 key:value 형식의 줄 단위 응답으로만 작성하십시오. "
                "각 값은 여전히 자연스러운 한국어 문장이어야 합니다."
            ),
        },
        {
            "role": "user",
            "content": (
                "아래 형식만 사용하십시오:\n"
                "headline: ...\n"
                "commander_summary: ...\n"
                "strategist_summary: ...\n"
                "scanner_summary: ...\n"
                "monitor_summary: ...\n"
                "supervisor_summary: ...\n"
                "executor_summary: ...\n"
                "reporter_summary: ...\n"
                "executive_summary: ...\n"
                "scanner_reason: ...\n"
                "entry_summary: ...\n"
                "holding_summary: ...\n"
                "exit_plan_summary: ...\n"
                "risk_summary: ...\n"
                "next_checkpoints: 항목1 | 항목2 | 항목3\n"
                "operator_takeaways: 항목1 | 항목2 | 항목3\n"
                f"입력: {json.dumps(compact_input, ensure_ascii=False)}"
            ),
        },
    ]

def _operator_brief_force_regenerate_enabled() -> bool:
    raw = str(os.getenv("OPERATOR_UI_RUN_BRIEF_FORCE_REGENERATE", "") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _load_operator_brief(detail: Dict[str, Any]) -> Dict[str, Any]:
    fallback = _fallback_operator_brief(detail)
    trade_report = detail.get("trade_report") if isinstance(detail.get("trade_report"), dict) else {}
    run_id = str(detail.get("run_id") or "").strip()
    trade_id = str(trade_report.get("trade_id") or trade_report.get("story_id") or "").strip()
    day_match = re.search(r"\d{4}-\d{2}-\d{2}", str(detail.get("started_at") or ""))
    day = day_match.group(0) if day_match else ""
    attempts: List[Dict[str, Any]] = []

    def finalize(result: Dict[str, Any]) -> Dict[str, Any]:
        out = _sanitize_operator_brief_result(detail, result, fallback)
        headline = str(out.get("headline") or "").strip()
        fallback_headline = str(fallback.get("headline") or "").strip()
        expected_date = ""
        headline_date = ""
        started_at = str(detail.get("started_at") or "").strip()
        started_match = re.search(r"\d{4}-\d{2}-\d{2}", started_at)
        headline_match = re.search(r"\d{4}-\d{2}-\d{2}", headline)
        if started_match:
            expected_date = started_match.group(0)
        if headline_match:
            headline_date = headline_match.group(0)
        if not headline:
            out["headline"] = fallback_headline
        elif expected_date and headline_date and headline_date != expected_date:
            out["headline"] = fallback_headline
        parsed_output = {
            "headline": str(out.get("headline") or ""),
            "commander_summary": str(out.get("commander_summary") or ""),
            "strategist_summary": str(out.get("strategist_summary") or ""),
            "scanner_summary": str(out.get("scanner_summary") or ""),
            "monitor_summary": str(out.get("monitor_summary") or ""),
            "supervisor_summary": str(out.get("supervisor_summary") or ""),
            "executor_summary": str(out.get("executor_summary") or ""),
            "reporter_summary": str(out.get("reporter_summary") or ""),
            "operator_takeaways": [str(x or "") for x in list(out.get("operator_takeaways") or []) if str(x or "").strip()],
            "executive_summary": str(out.get("executive_summary") or ""),
            "scanner_reason": str(out.get("scanner_reason") or ""),
            "entry_summary": str(out.get("entry_summary") or ""),
            "holding_summary": str(out.get("holding_summary") or ""),
            "exit_plan_summary": str(out.get("exit_plan_summary") or ""),
            "risk_summary": str(out.get("risk_summary") or ""),
            "next_checkpoints": [str(x or "") for x in list(out.get("next_checkpoints") or []) if str(x or "").strip()],
        }
        latency_ms = 0
        if attempts:
            latency_ms = sum(int(row.get("latency_ms") or 0) for row in attempts)
        out["llm_response_artifact"] = build_llm_response_artifact(
            component="brief",
            run_id=run_id,
            trade_id=trade_id,
            story_id=trade_id,
            day=day,
            status=str(out.get("status") or "fallback"),
            attempts=attempts,
            parsed_output=parsed_output,
            model_info={"provider": "OpenRouter", "model": str(out.get("model") or "")},
            latency_ms=latency_ms,
            meta={
                "reason": str(out.get("reason") or ""),
                "parse_mode": str(out.get("parse_mode") or ""),
                "required_keys_expected": list(out.get("required_keys_expected") or []),
                "required_keys_present": list(out.get("required_keys_present") or []),
                "required_keys_missing": list(out.get("required_keys_missing") or []),
                "completeness_score": float(out.get("completeness_score") or 0.0),
                "used_fallback_sections": list(out.get("used_fallback_sections") or []),
                "finish_reason": str(out.get("finish_reason") or ""),
                "error": str((out.get("failure") or {}).get("reason") or out.get("reason") or ""),
            },
        )
        return out

    router = LLMRouter.from_env()
    if router.client is None:
        return finalize(
            {
                **_failure_operator_brief(detail, status="fallback", model="", reason="llm_client_unavailable", failure_status="error"),
                "parse_mode": "none",
                "required_keys_expected": list(OPERATOR_BRIEF_REQUIRED_KEYS),
                "required_keys_present": [],
                "required_keys_missing": list(OPERATOR_BRIEF_REQUIRED_KEYS),
                "completeness_score": 0.0,
                "used_fallback_sections": list(OPERATOR_BRIEF_REQUIRED_KEYS),
            }
        )
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
    prepared_input = _build_operator_brief_input(detail)
    compact_input = _compact_operator_brief_input_for_llm(prepared_input)
    _save_operator_brief_input_artifact(detail, prepared_input, compact_input)
    messages = _build_operator_brief_messages(compact_input)
    timeout_sec = int(float(os.getenv("OPERATOR_UI_RUN_BRIEF_TIMEOUT_SEC", "8")))
    retry_max = max(0, int(float(os.getenv("OPERATOR_UI_RUN_BRIEF_RETRY_MAX", "1"))))
    brief_token_budget = _env_int_with_fallback(
        "OPERATOR_UI_RUN_BRIEF_MAX_TOKENS",
        "OPENROUTER_DEFAULT_MAX_TOKENS",
        default=700,
    )
    brief_repair_token_budget = _env_int_with_fallback(
        "OPERATOR_UI_RUN_BRIEF_REPAIR_MAX_TOKENS",
        "OPERATOR_UI_RUN_BRIEF_MAX_TOKENS",
        "OPENROUTER_DEFAULT_MAX_TOKENS",
        default=max(600, brief_token_budget),
    )
    brief_line_token_budget = _env_int_with_fallback(
        "OPERATOR_UI_RUN_BRIEF_LINE_MAX_TOKENS",
        "OPERATOR_UI_RUN_BRIEF_REPAIR_MAX_TOKENS",
        "OPERATOR_UI_RUN_BRIEF_MAX_TOKENS",
        "OPENROUTER_DEFAULT_MAX_TOKENS",
        default=max(500, brief_token_budget),
    )
    primary_policy = {
        "temperature": float(os.getenv("OPERATOR_UI_RUN_BRIEF_TEMPERATURE", "0.1")),
        "max_tokens": brief_token_budget,
        "timeout_sec": timeout_sec,
        "response_format": {"type": "json_object"},
        **({"model": model} if model else {}),
    }
    primary_status = "error"
    primary_reason = ""
    primary_raw = ""
    primary_partial: Dict[str, Any] = {}
    primary_parse_meta: Dict[str, Any] = {
        "parse_mode": "none",
        "required_keys_expected": list(OPERATOR_BRIEF_REQUIRED_KEYS),
        "required_keys_present": [],
        "required_keys_missing": list(OPERATOR_BRIEF_REQUIRED_KEYS),
        "completeness_score": 0.0,
    }
    for attempt_index in range(retry_max + 1):
        step = "first_attempt" if attempt_index == 0 else f"retry_{attempt_index}"
        primary_t0 = time.perf_counter()
        try:
            raw = router.chat("operator_ui", messages, policy=primary_policy)
        except Exception as exc:
            status = classify_llm_exception(exc)
            reason = f"{type(exc).__name__}:{exc}"
            primary_status = status
            primary_reason = reason
            attempts.append(
                make_attempt(
                    step=step,
                    messages=messages,
                    raw_response_text=f"ERROR:{reason}",
                    parsed_output={},
                    model=model,
                    latency_ms=int((time.perf_counter() - primary_t0) * 1000),
                    status=status,
                    meta={
                        "role": "brief",
                        "error": reason,
                        "parse_mode": "none",
                        "required_keys_expected": list(OPERATOR_BRIEF_REQUIRED_KEYS),
                        "required_keys_present": [],
                        "required_keys_missing": list(OPERATOR_BRIEF_REQUIRED_KEYS),
                        "completeness_score": 0.0,
                    },
                )
            )
            if attempt_index < retry_max and _is_retryable_brief_failure(status, reason):
                continue
            break
        primary_latency_ms = int((time.perf_counter() - primary_t0) * 1000)
        primary_raw = raw
        parsed_result = parse_llm_json_response(raw)
        parsed_candidate = (
            parsed_result.get("full_object")
            if isinstance(parsed_result.get("full_object"), dict)
            else parsed_result.get("partial_object")
        )
        parsed_candidate = dict(parsed_candidate) if isinstance(parsed_candidate, dict) else {}
        parse_meta = _operator_brief_parse_meta(raw, parsed_candidate)
        primary_parse_meta = dict(parse_meta)
        # Mixed-language output is treated as a failure because this document is
        # the operator-facing single source for fast review, and partial Korean
        # mixed with Chinese/Japanese/English reads like a broken brief rather
        # than a usable status update.
        language_ok = _operator_brief_language_ok(parsed_candidate)
        if bool(parsed_result.get("is_full")) and _operator_brief_is_complete(parsed_candidate) and language_ok:
            attempts.append(
                make_attempt(
                    step=step,
                    messages=messages,
                    raw_response_text=raw,
                    parsed_output=parsed_candidate,
                    model=model,
                    latency_ms=primary_latency_ms,
                    status="ok",
                    meta={"role": "brief", "language_ok": True, **parse_meta},
                )
            )
            return finalize({
                "status": "ok",
                "model": model,
                "headline": str(parsed_candidate.get("headline") or fallback.get("headline") or ""),
                "commander_summary": str(parsed_candidate.get("commander_summary") or fallback.get("commander_summary") or ""),
                "strategist_summary": str(parsed_candidate.get("strategist_summary") or fallback.get("strategist_summary") or ""),
                "scanner_summary": str(parsed_candidate.get("scanner_summary") or fallback.get("scanner_summary") or ""),
                "monitor_summary": str(parsed_candidate.get("monitor_summary") or fallback.get("monitor_summary") or ""),
                "supervisor_summary": str(parsed_candidate.get("supervisor_summary") or fallback.get("supervisor_summary") or ""),
                "executor_summary": str(parsed_candidate.get("executor_summary") or fallback.get("executor_summary") or ""),
                "reporter_summary": str(parsed_candidate.get("reporter_summary") or fallback.get("reporter_summary") or ""),
                "operator_takeaways": [str(x or "") for x in list(parsed_candidate.get("operator_takeaways") or [])[:5] if str(x or "").strip()] or list(fallback.get("operator_takeaways") or []),
                "executive_summary": str(parsed_candidate.get("executive_summary") or ""),
                "scanner_reason": str(parsed_candidate.get("scanner_reason") or ""),
                "entry_summary": str(parsed_candidate.get("entry_summary") or ""),
                "holding_summary": str(parsed_candidate.get("holding_summary") or ""),
                "exit_plan_summary": str(parsed_candidate.get("exit_plan_summary") or ""),
                "risk_summary": str(parsed_candidate.get("risk_summary") or ""),
                "next_checkpoints": [str(x or "") for x in list(parsed_candidate.get("next_checkpoints") or [])[:5] if str(x or "").strip()],
                **parse_meta,
                "used_fallback_sections": [],
            })
        primary_partial = dict(parsed_candidate) if parsed_candidate else {}
        if parsed_candidate and not language_ok:
            primary_status = "partial"
            primary_reason = "language_policy_failed"
        elif not bool(parsed_result.get("raw_nonempty")):
            primary_status = "empty_response"
            primary_reason = "empty_response"
        elif parsed_candidate:
            primary_status = "partial"
            primary_reason = "brief_json_incomplete_or_partial"
        else:
            primary_status = "parse_error"
            primary_reason = "parse_error"
        attempts.append(
            make_attempt(
                step=step,
                messages=messages,
                raw_response_text=raw,
                parsed_output=parsed_candidate,
                model=model,
                latency_ms=primary_latency_ms,
                status=primary_status,
                meta={"role": "brief", "error": primary_reason, "language_ok": language_ok, **parse_meta},
            )
        )
        if attempt_index < retry_max and _is_retryable_brief_failure(primary_status, primary_reason):
            continue
        break

    repair_messages = _build_operator_brief_repair_messages(primary_raw)
    repair_policy = {
        "temperature": 0.0,
        "max_tokens": brief_repair_token_budget,
        "timeout_sec": timeout_sec,
        "response_format": {"type": "json_object"},
        **({"model": model} if model else {}),
    }
    repair_t0 = time.perf_counter()
    try:
        repair_raw = router.chat(
            "operator_ui",
            repair_messages,
            policy=repair_policy,
        )
    except Exception as exc:
        repair_raw = ""
        repair_error = f"{type(exc).__name__}:{exc}"
    else:
        repair_error = ""
    repair_latency_ms = int((time.perf_counter() - repair_t0) * 1000)
    repair_result = parse_llm_json_response(repair_raw)
    repaired = repair_result.get("full_object") if isinstance(repair_result.get("full_object"), dict) else repair_result.get("partial_object")
    repaired = dict(repaired) if isinstance(repaired, dict) else {}
    repair_meta = _operator_brief_parse_meta(repair_raw, repaired)
    repair_language_ok = _operator_brief_language_ok(repaired)
    if bool(repair_result.get("is_full")) and _operator_brief_is_complete(repaired) and repair_language_ok:
        attempts.append(
            make_attempt(
                step="repaired_attempt",
                messages=repair_messages,
                raw_response_text=repair_raw,
                parsed_output=repaired,
                model=model,
                latency_ms=repair_latency_ms,
                status="repaired",
                meta={"role": "brief", "language_ok": True, **repair_meta},
            )
        )
        return finalize({
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
            "executive_summary": str(repaired.get("executive_summary") or ""),
            "scanner_reason": str(repaired.get("scanner_reason") or ""),
            "entry_summary": str(repaired.get("entry_summary") or ""),
            "holding_summary": str(repaired.get("holding_summary") or ""),
            "exit_plan_summary": str(repaired.get("exit_plan_summary") or ""),
            "risk_summary": str(repaired.get("risk_summary") or ""),
            "next_checkpoints": [str(x or "") for x in list(repaired.get("next_checkpoints") or [])[:5] if str(x or "").strip()],
            "reason": "llm_repair_pass",
            **repair_meta,
            "used_fallback_sections": [],
        })
    attempts.append(
        make_attempt(
            step="repaired_attempt",
            messages=repair_messages,
            raw_response_text=repair_raw,
            parsed_output=repaired,
            model=model,
            latency_ms=repair_latency_ms,
            status="empty_response" if not str(repair_raw or "").strip() else ("partial" if repaired else "parse_error"),
            meta={
                "role": "brief",
                "error": repair_error or ("language_policy_failed" if repaired and not repair_language_ok else ("repair_empty_response" if not str(repair_raw or "").strip() else "repair_parse_error")),
                "language_ok": repair_language_ok,
                **repair_meta,
            },
        )
    )
    if _is_free_model(model):
        line_messages = _build_operator_brief_line_messages(compact_input)
        line_policy = {
            "temperature": 0.0,
            "max_tokens": brief_line_token_budget,
            "timeout_sec": timeout_sec,
            **({"model": model} if model else {}),
        }
        line_t0 = time.perf_counter()
        try:
            line_raw = router.chat(
                "operator_ui",
                line_messages,
                policy=line_policy,
            )
        except Exception as exc:
            line_raw = ""
            line_error = f"{type(exc).__name__}:{exc}"
        else:
            line_error = ""
        line_latency_ms = int((time.perf_counter() - line_t0) * 1000)
        line_parsed = _parse_operator_brief_lines(line_raw)
        line_meta = required_key_metadata(line_parsed, OPERATOR_BRIEF_REQUIRED_KEYS)
        line_language_ok = _operator_brief_language_ok(line_parsed)
        if line_parsed and not line_meta.get("required_keys_missing") and line_language_ok:
            attempts.append(
                make_attempt(
                    step="line_repair_attempt",
                    messages=line_messages,
                    raw_response_text=line_raw,
                    parsed_output=line_parsed,
                    model=model,
                    latency_ms=line_latency_ms,
                    status="salvaged",
                    meta={
                        "role": "brief",
                        "parse_mode": "none",
                        "language_ok": True,
                        **line_meta,
                        "used_fallback_sections": [],
                    },
                )
            )
            return finalize({
                "status": "salvaged",
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
                "executive_summary": str(line_parsed.get("executive_summary") or ""),
                "scanner_reason": str(line_parsed.get("scanner_reason") or ""),
                "entry_summary": str(line_parsed.get("entry_summary") or ""),
                "holding_summary": str(line_parsed.get("holding_summary") or ""),
                "exit_plan_summary": str(line_parsed.get("exit_plan_summary") or ""),
                "risk_summary": str(line_parsed.get("risk_summary") or ""),
                "next_checkpoints": [str(x or "") for x in list(line_parsed.get("next_checkpoints") or [])[:5] if str(x or "").strip()],
                "reason": "llm_line_repair_pass",
                "parse_mode": "none",
                **line_meta,
                "used_fallback_sections": [],
            })
        attempts.append(
            make_attempt(
                step="line_repair_attempt",
                messages=line_messages,
                raw_response_text=line_raw,
                parsed_output=line_parsed,
                model=model,
                latency_ms=line_latency_ms,
                status="empty_response" if not str(line_raw or "").strip() else ("partial" if line_parsed else "parse_error"),
                meta={
                    "role": "brief",
                    "error": line_error or ("language_policy_failed" if line_parsed and not line_language_ok else ("line_repair_empty_response" if not str(line_raw or "").strip() else "line_repair_parse_error")),
                    "parse_mode": "none",
                    "language_ok": line_language_ok,
                    **line_meta,
                },
            )
        )

    fallback_brief = _failure_operator_brief(
        detail,
        status="fallback",
        model=model,
        reason=primary_reason or "brief_generation_failed",
        failure_status=primary_status,
    )
    fallback_brief.update(
        {
            "fallback_rendered": True,
            "parse_mode": str(primary_parse_meta.get("parse_mode") or "none"),
            "required_keys_expected": list(primary_parse_meta.get("required_keys_expected") or OPERATOR_BRIEF_REQUIRED_KEYS),
            "required_keys_present": list(primary_parse_meta.get("required_keys_present") or []),
            "required_keys_missing": list(primary_parse_meta.get("required_keys_missing") or OPERATOR_BRIEF_REQUIRED_KEYS),
            "completeness_score": float(primary_parse_meta.get("completeness_score") or 0.0),
            "used_fallback_sections": list(OPERATOR_BRIEF_REQUIRED_KEYS),
        }
    )
    if primary_partial:
        fallback_brief["failure"]["partial_fields_recovered"] = sorted(primary_partial.keys())
    return finalize(fallback_brief)


def _load_cached_operator_brief(config: OperatorUIConfig, run_id: str) -> Dict[str, Any]:
    if _operator_brief_force_regenerate_enabled():
        return {}
    if not run_id:
        return {}
    path = config.operator_ui_cache_path / f"{run_id}.json"
    cached = _read_json(path)
    if not isinstance(cached, dict):
        return {}
    if int(cached.get("version") or 0) < 12:
        return {}
    return cached


def _save_cached_operator_brief(config: OperatorUIConfig, run_id: str, brief: Dict[str, Any]) -> None:
    if not run_id or not isinstance(brief, dict):
        return
    path = config.operator_ui_cache_path / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(brief)
    payload["version"] = 12
    payload["cached_at"] = datetime.now(tz=KST).isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _operator_brief_artifact_paths(detail: Dict[str, Any]) -> tuple[Path | None, Path | None]:
    trade_report = detail.get("trade_report") if isinstance(detail.get("trade_report"), dict) else {}
    trade_root_path = Path(str(trade_report.get("trade_root_path") or "")).resolve() if str(trade_report.get("trade_root_path") or "").strip() else None
    if trade_root_path is not None:
        return trade_root_path / "brief" / "operator_brief.json", trade_root_path / "brief" / "operator_brief.md"
    candidate_paths = [
        str(trade_report.get("operator_brief_json_path") or ""),
        str(trade_report.get("trade_report_json_path") or ""),
        str(trade_report.get("trade_story_input_path") or ""),
        str(trade_report.get("trade_lifecycle_json_path") or ""),
        str(trade_report.get("aggregated_bundle_path") or ""),
    ]
    for raw in candidate_paths:
        text = str(raw or "").strip()
        if not text:
            continue
        path = Path(text)
        if path.name == "operator_brief.json":
            return path, path.with_suffix(".md")
        if path.suffix:
            parent = path.parent
            if parent.name in {"ai_trade_report", "lifecycle", "strategist", "brief", "evidence"}:
                parent = parent.parent
        else:
            parent = path
        brief_json = parent / "brief" / "operator_brief.json"
        brief_md = parent / "brief" / "operator_brief.md"
        if brief_json.exists() or brief_md.exists():
            return brief_json, brief_md
        return parent / "operator_brief.json", parent / "operator_brief.md"
    return None, None


def _operator_brief_input_artifact_path(detail: Dict[str, Any]) -> Path | None:
    trade_report = detail.get("trade_report") if isinstance(detail.get("trade_report"), dict) else {}
    trade_root_path = Path(str(trade_report.get("trade_root_path") or "")).resolve() if str(trade_report.get("trade_root_path") or "").strip() else None
    if trade_root_path is not None:
        return trade_root_path / "brief" / "brief_input.json"
    brief_json, _brief_md = _operator_brief_artifact_paths(detail)
    if brief_json is None:
        return None
    return brief_json.parent / "brief_input.json"


def _operator_brief_compact_input_artifact_path(detail: Dict[str, Any]) -> Path | None:
    trade_report = detail.get("trade_report") if isinstance(detail.get("trade_report"), dict) else {}
    trade_root_path = Path(str(trade_report.get("trade_root_path") or "")).resolve() if str(trade_report.get("trade_root_path") or "").strip() else None
    if trade_root_path is not None:
        return trade_root_path / "brief" / "brief_compact_input.json"
    brief_json, _brief_md = _operator_brief_artifact_paths(detail)
    if brief_json is None:
        return None
    return brief_json.parent / "brief_compact_input.json"


def _save_operator_brief_input_artifact(detail: Dict[str, Any], prepared_input: Dict[str, Any], llm_compact_input: Dict[str, Any] | None = None) -> None:
    path = _operator_brief_input_artifact_path(detail)
    compact_path = _operator_brief_compact_input_artifact_path(detail)
    if path is None and compact_path is None:
        return
    try:
        payload = dict(prepared_input or {})
        payload["saved_at"] = datetime.now(tz=KST).isoformat()
        compact_payload = dict(llm_compact_input or _compact_operator_brief_input_for_llm(payload))
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if compact_path is not None:
            trade_report = detail.get("trade_report") if isinstance(detail.get("trade_report"), dict) else {}
            compact_path.parent.mkdir(parents=True, exist_ok=True)
            compact_artifact = build_compact_input_artifact(
                component="brief",
                run_id=str(detail.get("run_id") or ""),
                trade_id=str(trade_report.get("trade_id") or trade_report.get("story_id") or ""),
                story_id=str(trade_report.get("story_id") or trade_report.get("trade_id") or ""),
                day=str((trade_report.get("day") or "")).strip(),
                source_artifact_path=str(path) if path is not None else "",
                source_input=payload,
                compact_input=compact_payload,
            )
            compact_path.write_text(json.dumps(compact_artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def _render_operator_brief_markdown(brief: Dict[str, Any]) -> str:
    def _action_label(action: Any) -> str:
        mapping = {
            "BUY": "매수",
            "SELL": "매도",
            "HOLD": "보유 유지",
            "WAIT": "진입 보류",
        }
        return mapping.get(str(action or "").strip().upper(), str(action or "-").strip() or "-")

    def _metric_text(value: Any) -> str:
        text = str(value or "").strip()
        return text or "-"

    def _axis_label(value: Any) -> str:
        raw = _sanitize_operator_brief_text(value)
        lowered = raw.lower()
        mapping = {
            "고정 손절 기준": "고정 손절 기준",
            "상황 대응형 손절 기준": "상황 대응형 손절 기준",
            "목표 수익 실현 기준": "목표 수익 실현 기준",
            "hard stop": "고정 손절 기준",
            "adaptive stop": "상황 대응형 손절 기준",
            "take profit": "목표 수익 실현 기준",
            "vwap breakdown": "VWAP 이탈",
            "vwap_breakdown": "VWAP 이탈",
            "peak drawdown": "고점 대비 하락폭 확대",
            "peak_drawdown": "고점 대비 하락폭 확대",
            "prior low break": "직전 저점 이탈",
            "prior_low_break": "직전 저점 이탈",
            "intraday low break": "장중 저점 이탈",
            "intraday_low_break": "장중 저점 이탈",
            "confirmed_exit_signal": "청산 확인 신호",
            "defensive exit": "방어형 청산 신호",
            "defensive_exit": "방어형 청산 신호",
            "방어형 청산": "방어형 청산 신호",
        }
        return mapping.get(lowered, raw or "감시 조건 변화")

    def _narrative_text(text: Any) -> str:
        raw_source = _trim_text(text, max_len=1000)
        cleaned = _sanitize_operator_brief_text(text)
        if not cleaned:
            return ""
        raw_lower = raw_source.lower()
        m = re.fullmatch(r"universe scanned\s*:\s*(\d+)", raw_lower)
        if m:
            return f"총 {m.group(1)}개 후보를 비교했습니다."
        m = re.fullmatch(r"selected rank\s*:\s*#?(\d+)", raw_lower)
        if m:
            return f"비교 대상 중 {m.group(1)}순위로 선정되었습니다."
        m = re.fullmatch(r"posture\s*:\s*(buy|sell|hold|wait)", raw_lower)
        if m:
            return f"현재 포지션 판단은 {_action_label(m.group(1))}입니다."
        m = re.fullmatch(r"trigger\s*:\s*(.+)", raw_lower)
        if m:
            trigger = m.group(1).strip()
            if trigger in {"-", "no", "none"}:
                return "추가 진입 또는 청산을 확정할 신호는 아직 확인되지 않았습니다."
            return f"현재 감시 신호는 {cleaned.split(':', 1)[-1].strip()}입니다."
        m = re.fullmatch(r"exit trigger\s*:\s*(.+)", raw_lower)
        if m:
            trigger = m.group(1).strip()
            if trigger in {"-", "no", "none"}:
                return "아직 청산 신호는 확인되지 않았습니다."
            return f"현재 확인된 청산 신호는 {cleaned.split(':', 1)[-1].strip()}입니다."
        if raw_lower.startswith("runner-up symbols had weaker coverage"):
            return "후순위 후보는 차트 완성도와 보조 신호가 더 약했습니다."
        m = re.fullmatch(r"chart / feature coverage\s*:\s*(\d+)/(\d+)", raw_lower)
        if m:
            return f"차트와 피처 확인 항목은 {m.group(1)}/{m.group(2)} 수준으로 확보되었습니다."
        m = re.fullmatch(r"chart completeness filter\s*:\s*pass\s*-\s*(.+)", raw_lower)
        if m:
            return f"차트 확인 조건은 {m.group(1).strip()} 수준으로 충족되었습니다."
        if raw_lower.startswith("liquidity filter:"):
            return "유동성 조건은 충족되었습니다."
        if raw_lower.startswith("turnover filter:"):
            return "거래대금 조건은 충족되었습니다."
        if re.match(r"^[A-Za-z][A-Za-z0-9 /_-]*:\s*", raw_source):
            return ""
        return cleaned

    def _append_list(lines: List[str], items: List[str], *, limit: int = 3) -> None:
        appended = 0
        for item in items:
            text = _narrative_text(item)
            if not text or _count_hangul_chars(text) <= 0:
                continue
            lines.append(f"- {text}")
            appended += 1
            if appended >= limit:
                break

    def _vwap_interpretation(value: Any) -> str:
        raw = _safe_float(value, None)
        if raw is None:
            return "-"
        if raw >= 0.02:
            return f"{_format_percent(raw, 2)} (과도 확장으로 추격 진입에 주의가 필요한 구간입니다.)"
        if raw >= 0.0:
            return f"+{abs(raw) * 100:.2f}% (VWAP 위에서 흐름을 유지하고 있습니다.)"
        if raw <= -0.01:
            return f"{_format_percent(raw, 2)} (VWAP 아래로 밀리며 약세 압력이 커진 구간입니다.)"
        return f"{_format_percent(raw, 2)} (중립 범위 안에서 움직이고 있습니다.)"

    def _entry_reason_text(reason_code: str, pattern: str, metrics: Dict[str, Any]) -> str:
        reason = str(reason_code or "").strip().lower()
        metric_map = metrics if isinstance(metrics, dict) else {}
        recent_high = metric_map.get("recent_high")
        vwap = metric_map.get("vwap")
        volume_ratio = metric_map.get("volume_ratio")
        vwap_distance = metric_map.get("vwap_distance")
        pullback_pct = metric_map.get("pullback_pct")
        if pattern == "breakout_vwap_hold":
            parts = ["분봉 기준으로 최근 고점 돌파와 VWAP 상회 유지, 거래량 확인이 함께 맞물려 진입했습니다."]
            if recent_high not in (None, ""):
                parts.append(f"최근 고점 기준값은 {_format_float(recent_high, 2)}였습니다.")
            if vwap not in (None, ""):
                parts.append(f"당시 VWAP 기준값은 {_format_float(vwap, 2)}였습니다.")
            if volume_ratio not in (None, ""):
                parts.append(f"거래량은 평시 대비 {_format_float(volume_ratio, 2)}배 수준으로 확인됐습니다.")
            return " ".join(parts)
        if pattern == "pullback_rebound":
            parts = ["분봉 기준으로 눌림 이후 반등이 확인됐고, VWAP 재안착 흐름까지 확인되어 진입했습니다."]
            if pullback_pct not in (None, ""):
                parts.append(f"눌림 폭은 {_format_percent(pullback_pct, 2)} 수준이었습니다.")
            if volume_ratio not in (None, ""):
                parts.append(f"거래량은 평시 대비 {_format_float(volume_ratio, 2)}배 수준으로 확인됐습니다.")
            return " ".join(parts)
        mapping = {
            "minute_candle_missing": "이번 거래는 분봉 데이터가 확보되지 않아 진입 근거를 확인할 수 없었습니다. 따라서 신규 진입은 보류 대상으로 해석했습니다.",
            "data_incomplete": "체결 이전 분봉 기록이 충분하지 않아 진입 시점을 확정하기 어렵습니다. 현재 문서는 보유 관리와 청산 기준 중심으로 정리했습니다.",
            "no_breakout_signal": "저장된 분봉 범위에서는 최근 고점 돌파나 첫 눌림목 반등 신호가 확인되지 않았습니다. 따라서 진입은 보류 판단으로 정리했습니다.",
            "vwap_not_confirmed": "분봉 흐름에서 VWAP 상회 유지나 재안착이 확인되지 않았습니다. 추격 진입 위험을 피하기 위해 진입 보류로 해석했습니다.",
            "volume_insufficient": "분봉 거래량이 돌파 신호를 뒷받침할 만큼 충분하지 않았습니다. 따라서 이번 구간은 보수적으로 진입 보류로 판단했습니다.",
            "too_extended_from_vwap": "VWAP 대비 과도하게 확장된 상태여서 추격 진입을 피했습니다.",
            "post_exit_cooldown": "직전 청산 직후 재진입 쿨다운 구간이라 신규 진입을 보류했습니다.",
            "buy_blocked_open_position": "기존 보유 포지션이 있어 신규 진입을 차단했습니다.",
            "no_position": "저장된 데이터 범위 안에서는 체결 직전 분봉 진입 근거가 충분히 남아 있지 않았습니다. 이번 문서는 진입 해석보다 이후 보유 관리 기록을 중심으로 정리했습니다.",
            "peak_drawdown": "이번 저장값에는 진입 근거보다 청산 관리 신호가 더 선명하게 남아 있습니다. 진입 시점의 분봉 근거는 별도로 확인되지 않아 보수적으로 정리했습니다.",
            "hard_stop": "이번 저장값에는 진입 근거보다 손절 관리 신호가 더 분명하게 남아 있습니다. 진입 시점의 분봉 근거는 별도로 확인되지 않아 보수적으로 정리했습니다.",
        }
        if mapping.get(reason):
            return mapping[reason]
        if str(reason_code or "").strip():
            return f"분봉 조건 점검 결과 {str(reason_code or '').strip()} 상태로 해석되어 진입을 보류했습니다."
        if vwap_distance not in (None, ""):
            return f"분봉 조건을 점검 중이며 현재 VWAP 이격은 {_format_percent(vwap_distance, 2)} 수준입니다. 추가 확인 전까지는 보수적으로 접근합니다."
        return "분봉 데이터와 체결 근거를 보수적으로 점검한 결과, 당장 진입을 확정하기보다 추가 확인이 필요한 상태로 해석했습니다."

    def _default_next_checkpoints(entry: Dict[str, Any], monitor: Dict[str, Any], exit_plan: Dict[str, Any], posture_action: str) -> List[str]:
        metrics = entry.get("metrics") if isinstance(entry.get("metrics"), dict) else {}
        watch_axes = [str(x or "").strip() for x in list(exit_plan.get("watch_axes") or monitor.get("watch_axes") or []) if str(x or "").strip()]
        derived: List[str] = []
        if posture_action == "WAIT":
            if metrics.get("recent_high") not in (None, ""):
                derived.append("분봉 기준으로 최근 고점 재돌파 여부를 다음 체크포인트로 확인합니다.")
            if metrics.get("volume_ratio") not in (None, ""):
                derived.append("거래량 증가가 다시 동반되는지 확인합니다.")
            if not derived:
                derived.append("분봉 기준으로 재돌파 여부와 거래량 증가 여부를 다음 체크포인트로 설정합니다.")
        elif posture_action in {"BUY", "HOLD"}:
            derived.append("분봉 기준으로 지지선 유지 여부와 거래량 둔화 여부를 먼저 확인합니다.")
            if any("vwap" in axis.lower() for axis in watch_axes):
                derived.append("VWAP 재이탈 여부와 거래량 감소 여부를 중심으로 모니터링합니다.")
            derived.append("현재 보유 상태에서는 고점 대비 하락폭과 거래량 둔화를 주요 확인 지표로 봅니다.")
        else:
            derived.append("청산 이후에는 동일 종목의 재돌파 여부와 거래대금 회복 여부를 다시 확인합니다.")
        return derived[:3]

    valid_statuses = {"", "ok", "partial", "salvaged", "repaired", "fallback"}
    status = str(brief.get("status") or "").strip().lower()
    if status not in valid_statuses:
        failure = brief.get("failure") if isinstance(brief.get("failure"), dict) else {}
        lines = [
            "# 운영자 브리프",
            "",
            "## 1. 최종 판단 요약",
            "",
            "- 저장된 요약 결과가 완전하지 않아 현재 판단을 보수적으로 다시 정리했습니다.",
            "",
            "## 2. 종목 선정 이유",
            "",
            "- 저장 범위가 제한되어 종목 선정 배경은 간단히만 확인됩니다.",
            "",
            "## 3. 진입 근거",
            "",
            "- 저장된 데이터가 부족해 진입 시점의 분봉 근거는 보수적으로 해석합니다.",
            "",
            "## 4. 현재 상태",
            "",
            f"- 현재 브리프 상태는 {_metric_text(brief.get('status'))}이며 추가 확인이 필요합니다.",
            "",
            "## 5. 청산 계획",
            "",
            "- 청산 계획은 저장된 데이터 범위 안에서 다시 확인해야 합니다.",
            "",
            "## 6. 리스크 요인",
            "",
            f"- 생성 과정에서 {_metric_text(failure.get('reason') or brief.get('reason'))} 이슈가 있어 일부 설명이 축약되었습니다.",
            "",
            "## 7. 다음 체크포인트",
            "",
            "- 저장 구조와 LLM 응답 상태를 다시 확인합니다.",
            "",
        ]
        return "\n".join(lines)

    sections = brief.get("sections") if isinstance(brief.get("sections"), dict) else {}
    executive = sections.get("executive_decision") if isinstance(sections.get("executive_decision"), dict) else {}
    selection = sections.get("why_symbol_chosen") if isinstance(sections.get("why_symbol_chosen"), dict) else {}
    market = sections.get("market_context") if isinstance(sections.get("market_context"), dict) else {}
    monitor = sections.get("position_monitor_reasoning") if isinstance(sections.get("position_monitor_reasoning"), dict) else {}
    entry = sections.get("entry_timing") if isinstance(sections.get("entry_timing"), dict) else {}
    exit_plan = sections.get("exit_plan") if isinstance(exit_plan := sections.get("exit_plan"), dict) else {}
    operator_conclusion = sections.get("operator_conclusion") if isinstance(sections.get("operator_conclusion"), dict) else {}
    risk_alerts = sections.get("risk_alerts") if isinstance(sections.get("risk_alerts"), dict) else {}

    selected_symbol = str(executive.get("symbol") or "-")
    final_action = str(executive.get("final_action") or operator_conclusion.get("current_action") or "").strip().upper()
    posture_action = str(monitor.get("posture") or final_action).strip().upper()
    headline = str(brief.get("headline") or "").strip()
    executive_summary = _narrative_text("" if status == "fallback" else (str(brief.get("executive_summary") or "").strip() or headline))
    scanner_reason = _narrative_text("" if status == "fallback" else str(brief.get("scanner_reason") or brief.get("scanner_summary") or "").strip())
    holding_summary = _narrative_text("" if status == "fallback" else str(brief.get("holding_summary") or brief.get("monitor_summary") or "").strip())
    exit_plan_summary = _narrative_text("" if status == "fallback" else str(brief.get("exit_plan_summary") or "").strip())
    risk_summary = _narrative_text("" if status == "fallback" else str(brief.get("risk_summary") or "").strip())
    next_checkpoints = [] if status == "fallback" else [_narrative_text(x) for x in list(brief.get("next_checkpoints") or []) if _narrative_text(x)]
    takeaways = [_narrative_text(x) for x in list(brief.get("operator_takeaways") or []) if _narrative_text(x)]

    universe_size_raw = _safe_int(selection.get("universe_size"), 0)
    selected_rank_raw = _safe_int(selection.get("selected_rank"), 0) or 1
    selection_reasons = [str(x or "").strip() for x in list(selection.get("selection_reasons") or []) if str(x or "").strip()]
    comparison_reasons = [str(x or "").strip() for x in list(selection.get("comparison_reasons") or []) if str(x or "").strip()]
    signal_source = " ".join([scanner_reason] + selection_reasons + comparison_reasons).lower()
    signal_phrases: List[str] = []
    if any(token in signal_source for token in ["거래량", "volume", "trading value", "거래대금"]):
        signal_phrases.append("거래량과 거래대금 흐름이 함께 확인되었습니다.")
    if any(token in signal_source for token in ["돌파", "breakout"]):
        signal_phrases.append("단기 돌파 시도 흐름이 포착되었습니다.")
    if any(token in signal_source for token in ["변동성", "volatility"]):
        signal_phrases.append("단기 변동성 확대가 함께 관찰되었습니다.")
    if any(token in signal_source for token in ["눌림", "pullback", "반등", "rebound"]):
        signal_phrases.append("눌림 이후 반등 가능성도 함께 점검됐습니다.")
    if not scanner_reason or not any(token in scanner_reason for token in ["후보", "선정", "순위"]):
        if universe_size_raw > 0:
            scanner_reason = f"총 {universe_size_raw}개 후보 중 {selected_rank_raw}순위 감시 대상으로 선정되었습니다."
        else:
            scanner_reason = "저장된 후보 비교 정보는 제한적이지만, 이번 종목은 우선 감시 대상으로 선정되었습니다."
    if signal_phrases and all(phrase not in scanner_reason for phrase in signal_phrases[:2]):
        scanner_reason = " ".join([scanner_reason] + signal_phrases[:2])

    entry_summary = _narrative_text(str(brief.get("entry_summary") or "").strip())
    if not entry_summary:
        entry_reason_text = _narrative_text(str(entry.get("reason_text") or "").strip())
        if _count_hangul_chars(entry_reason_text) > 0 and status != "fallback":
            entry_summary = entry_reason_text
        else:
            entry_summary = _entry_reason_text(
                str(entry.get("reason_code") or ""),
                str(entry.get("pattern") or ""),
                entry.get("metrics") if isinstance(entry.get("metrics"), dict) else {},
            )

    if not executive_summary:
        executive_summary = f"{selected_symbol}의 현재 최종 판단은 {_action_label(posture_action)}입니다."

    if not holding_summary:
        holding_summary = (
            f"{selected_symbol}은 현재 {_action_label(monitor.get('posture') or final_action)} 상태입니다. "
            f"현재가는 {_metric_text(monitor.get('current_price'))}, 평균 단가는 {_metric_text(monitor.get('average_price'))}이며, "
            f"현재 관리는 {_axis_label(monitor.get('active_exit_axis') or '-')} 기준으로 이어가고 있습니다."
        )

    if not exit_plan_summary:
        effective_stop = _metric_text(exit_plan.get("effective_stop") or monitor.get("effective_stop"))
        effective_stop_reason = _axis_label(exit_plan.get("effective_stop_reason") or monitor.get("effective_stop_reason"))
        take_profit = _metric_text(exit_plan.get("take_profit") or monitor.get("take_profit"))
        watch_axes = [_axis_label(x) for x in list(exit_plan.get("watch_axes") or monitor.get("watch_axes") or [])[:2] if str(x or "").strip()]
        axes_text = ", ".join(watch_axes) if watch_axes else "감시 조건 변화"
        exit_plan_summary = (
            f"우선 {effective_stop_reason}을 기준으로 대응하고, 기준값은 {effective_stop} 수준으로 보고 있습니다. "
            f"목표 수익 실현 기준은 {take_profit} 수준이며, {axes_text}가 나타나면 다시 판단합니다."
        )

    if not risk_summary:
        weak_factors = [_narrative_text(x) for x in list(risk_alerts.get("weak_factors") or []) if _narrative_text(x)]
        if weak_factors and status != "fallback":
            risk_summary = " ".join(weak_factors[:3])
        elif bool(risk_alerts.get("defensive_mode")):
            risk_summary = "거시 스트레스 신호가 남아 있어 방어적으로 대응할 필요가 있습니다."
        else:
            risk_summary = "현재 확보된 데이터 기준으로 추가 리스크는 제한적이지만, 분봉 구조 변화와 거래량 둔화 여부를 계속 확인해야 합니다."

    if not next_checkpoints:
        next_checkpoints = [_narrative_text(x) for x in list(operator_conclusion.get("watch_next") or []) if _narrative_text(x)]
    if not next_checkpoints and takeaways:
        next_checkpoints = takeaways[:3]
    if not next_checkpoints:
        next_checkpoints = _default_next_checkpoints(entry, monitor, exit_plan, posture_action)

    lines = [
        "# 운영자 브리프",
        "",
        "## 1. 최종 판단 요약",
        "",
        f"- {executive_summary}",
        "",
        "## 2. 종목 선정 이유",
        "",
        f"- {scanner_reason}",
    ]
    _append_list(lines, selection_reasons, limit=3)
    _append_list(lines, comparison_reasons, limit=2)

    lines.extend([
        "",
        "## 3. 진입 근거",
        "",
        f"- {entry_summary}",
    ])
    entry_metrics = entry.get("metrics") if isinstance(entry.get("metrics"), dict) else {}
    if entry_metrics.get("recent_high") not in (None, ""):
        lines.append(f"- 최근 고점 기준값은 {_format_float(entry_metrics.get('recent_high'), 2)}였습니다.")
    if entry_metrics.get("vwap") not in (None, ""):
        lines.append(f"- 당시 VWAP 기준값은 {_format_float(entry_metrics.get('vwap'), 2)}였습니다.")
    if entry_metrics.get("vwap_distance") not in (None, ""):
        lines.append(f"- VWAP 이격은 {_vwap_interpretation(entry_metrics.get('vwap_distance'))}")
    if entry_metrics.get("volume_ratio") not in (None, ""):
        lines.append(f"- 거래량은 평시 대비 {_format_float(entry_metrics.get('volume_ratio'), 2)}배 수준으로 확인됐습니다.")
    if entry_metrics.get("pullback_pct") not in (None, ""):
        lines.append(f"- 눌림 폭은 {_format_percent(entry_metrics.get('pullback_pct'), 2)} 수준이었습니다.")

    lines.extend([
        "",
        "## 4. 현재 상태",
        "",
        f"- {holding_summary}",
        f"- 현재 포지션 판단은 {_action_label(monitor.get('posture') or final_action)}입니다.",
        f"- 평균 단가는 {_metric_text(monitor.get('average_price'))}, 현재가는 {_metric_text(monitor.get('current_price'))}, 장중 고점은 {_metric_text(monitor.get('peak_price'))}입니다.",
        f"- 현재 손익은 {_metric_text(monitor.get('current_drawdown'))}이며, 고점 대비 하락폭은 {_metric_text(monitor.get('peak_drawdown'))}입니다.",
    ])
    hold_reasons = [str(x or "").strip() for x in list(monitor.get("hold_reasons") or []) if str(x or "").strip()]
    _append_list(lines, hold_reasons, limit=3)

    lines.extend([
        "",
        "## 5. 청산 계획",
        "",
        f"- {exit_plan_summary}",
        f"- 현재 {_axis_label(exit_plan.get('effective_stop_reason') or monitor.get('effective_stop_reason'))}은 {_metric_text(exit_plan.get('effective_stop') or monitor.get('effective_stop'))} 수준으로 보고 있습니다.",
        f"- 목표 수익 실현 기준은 {_metric_text(exit_plan.get('take_profit') or monitor.get('take_profit'))} 수준입니다.",
        f"- 주요 감시 조건은 {', '.join([_axis_label(x) for x in list(exit_plan.get('watch_axes') or monitor.get('watch_axes') or [])[:3] if str(x or '').strip()]) or '감시 조건 변화'}입니다.",
    ])
    exit_triggers = [str(x or "").strip() for x in list(exit_plan.get("exit_triggers") or monitor.get("exit_triggers") or []) if str(x or "").strip()]
    _append_list(lines, exit_triggers, limit=3)

    lines.extend([
        "",
        "## 6. 리스크 요인",
        "",
        f"- {risk_summary}",
    ])
    weak_factors = [str(x or "").strip() for x in list(risk_alerts.get("weak_factors") or []) if str(x or "").strip()]
    _append_list(lines, weak_factors, limit=3)
    if str(market.get("global_sentiment") or "-") != "-" or str(market.get("vix") or "-") != "-":
        lines.append(f"- 시장 맥락상 글로벌 감성은 {_metric_text(market.get('global_sentiment'))}, VIX는 {_metric_text(market.get('vix'))} 수준입니다.")

    lines.extend([
        "",
        "## 7. 다음 체크포인트",
        "",
    ])
    _append_list(lines, next_checkpoints or takeaways, limit=4)
    if lines[-1] != "":
        lines.append("")
    return "\n".join(lines)
def _operator_brief_source_signature(detail: Dict[str, Any]) -> str:
    trade_report = detail.get("trade_report") if isinstance(detail.get("trade_report"), dict) else {}
    candidate_paths = [
        trade_report.get("trade_report_json_path"),
        trade_report.get("trade_story_input_path"),
        trade_report.get("trade_lifecycle_json_path"),
        trade_report.get("ai_trade_report_llm_response_path"),
    ]
    parts: List[str] = []
    for raw in candidate_paths:
        text = str(raw or "").strip()
        if not text:
            continue
        path = Path(text)
        if not path.exists() or path.is_dir():
            continue
        stat = path.stat()
        parts.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
    if not parts:
        parts.extend(
            [
                f"run_id:{str(detail.get('run_id') or '').strip()}",
                f"trade_id:{str(trade_report.get('trade_id') or '').strip()}",
                f"report_status:{str(trade_report.get('report_status') or '').strip()}",
                f"lifecycle_status:{str(trade_report.get('lifecycle_status') or '').strip()}",
            ]
        )
    return "|".join(parts)


def _saved_operator_brief_matches_detail(saved: Dict[str, Any], detail: Dict[str, Any]) -> bool:
    trade_report = detail.get("trade_report") if isinstance(detail.get("trade_report"), dict) else {}
    if str(saved.get("run_id") or "").strip() != str(detail.get("run_id") or "").strip():
        return False
    if str(saved.get("trade_id") or "").strip() != str(trade_report.get("trade_id") or "").strip():
        return False
    if str(saved.get("story_id") or "").strip() != str(trade_report.get("story_id") or "").strip():
        return False
    if str(saved.get("lifecycle_status") or "").strip() != str(trade_report.get("lifecycle_status") or "").strip():
        return False
    if str(saved.get("report_status") or "").strip() != str(trade_report.get("report_status") or "").strip():
        return False
    if str(saved.get("source_signature") or "").strip() != _operator_brief_source_signature(detail):
        return False
    return True


def _load_saved_operator_brief(detail: Dict[str, Any]) -> Dict[str, Any]:
    if _operator_brief_force_regenerate_enabled():
        return {}
    json_path, _ = _operator_brief_artifact_paths(detail)
    if json_path is None or not json_path.exists():
        return {}
    payload = _read_json(json_path)
    if not isinstance(payload, dict):
        return {}
    if int(payload.get("version") or 0) < 12:
        return {}
    if not _saved_operator_brief_matches_detail(payload, detail):
        return {}
    return payload


def _save_operator_brief_artifact(detail: Dict[str, Any], brief: Dict[str, Any]) -> None:
    if not isinstance(brief, dict) or not brief:
        return
    json_path, md_path = _operator_brief_artifact_paths(detail)
    if json_path is None or md_path is None:
        return
    trade_report = detail.get("trade_report") if isinstance(detail.get("trade_report"), dict) else {}
    payload = dict(brief)
    sections = payload.get("sections") if isinstance(payload.get("sections"), dict) else {}
    monitor_section = (
        sections.get("position_monitor_reasoning")
        if isinstance(sections.get("position_monitor_reasoning"), dict)
        else {}
    )
    payload["monitor_snapshot"] = {
        "posture": str(monitor_section.get("posture") or ""),
        "holding_time": str(monitor_section.get("holding_time") or ""),
        "stop_loss": str(monitor_section.get("stop_loss") or ""),
        "effective_stop": str(monitor_section.get("effective_stop") or ""),
        "effective_stop_reason": str(monitor_section.get("effective_stop_reason") or ""),
        "take_profit": str(monitor_section.get("take_profit") or ""),
        "current_price": str(monitor_section.get("current_price") or ""),
        "average_price": str(monitor_section.get("average_price") or ""),
        "peak_price": str(monitor_section.get("peak_price") or ""),
        "current_drawdown": str(monitor_section.get("current_drawdown") or ""),
        "peak_drawdown": str(monitor_section.get("peak_drawdown") or ""),
        "vwap_distance": str(monitor_section.get("vwap_distance") or ""),
        "price_source": str(monitor_section.get("price_source") or ""),
        "feature_source": str(monitor_section.get("feature_source") or ""),
        "price_source_policy": str(monitor_section.get("price_source_policy") or ""),
        "active_exit_axis": str(monitor_section.get("active_exit_axis") or ""),
        "watch_axes": [str(x or "") for x in list(monitor_section.get("watch_axes") or []) if str(x or "").strip()][:6],
        "hold_reasons": [str(x or "") for x in list(monitor_section.get("hold_reasons") or []) if str(x or "").strip()][:6],
        "exit_triggers": [str(x or "") for x in list(monitor_section.get("exit_triggers") or []) if str(x or "").strip()][:6],
    }
    payload["version"] = 12
    payload["saved_at"] = datetime.now(tz=KST).isoformat()
    payload["run_id"] = str(detail.get("run_id") or "")
    payload["trade_id"] = str(trade_report.get("trade_id") or "")
    payload["story_id"] = str(trade_report.get("story_id") or "")
    payload["lifecycle_status"] = str(trade_report.get("lifecycle_status") or "")
    payload["report_status"] = str(trade_report.get("report_status") or "")
    payload["source_signature"] = _operator_brief_source_signature(detail)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_operator_brief_markdown(payload), encoding="utf-8")
    trade_root = json_path.parent.parent if json_path.parent.name == "brief" else json_path.parent
    legacy_json_path = trade_root / "operator_brief.json"
    legacy_md_path = trade_root / "operator_brief.md"
    if legacy_json_path != json_path:
        legacy_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if legacy_md_path != md_path:
        legacy_md_path.write_text(_render_operator_brief_markdown(payload), encoding="utf-8")
    llm_response_artifact = payload.get("llm_response_artifact") if isinstance(payload.get("llm_response_artifact"), dict) else {}
    if llm_response_artifact:
        brief_llm_path = json_path.parent / "brief_llm_response.json"
        brief_llm_path.write_text(json.dumps(llm_response_artifact, ensure_ascii=False, indent=2), encoding="utf-8")
        legacy_brief_llm_path = trade_root / "brief_llm_response.json"
        if legacy_brief_llm_path != brief_llm_path:
            legacy_brief_llm_path.write_text(json.dumps(llm_response_artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    bundle_candidates = [
        trade_root / "lifecycle" / "aggregated_execution_bundle.json",
        trade_root / "aggregated_execution_bundle.json",
    ]
    for bundle_path in bundle_candidates:
        if not bundle_path.exists():
            continue
        bundle = _read_json(bundle_path)
        if not isinstance(bundle, dict) or not bundle:
            continue
        artifacts = bundle.get("artifacts") if isinstance(bundle.get("artifacts"), dict) else {}
        brief_input_path = json_path.parent / "brief_input.json"
        brief_compact_input_path = json_path.parent / "brief_compact_input.json"
        artifacts["brief_json"] = str(json_path)
        artifacts["brief_md"] = str(md_path)
        artifacts["brief_input_json"] = str(brief_input_path) if brief_input_path.exists() else ""
        artifacts["brief_compact_input_json"] = str(brief_compact_input_path) if brief_compact_input_path.exists() else ""
        artifacts["brief_llm_response_json"] = str(json_path.parent / "brief_llm_response.json") if llm_response_artifact else ""
        bundle["artifacts"] = artifacts
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        break


def _load_operator_brief_with_cache(config: OperatorUIConfig, detail: Dict[str, Any]) -> Dict[str, Any]:
    run_id = str(detail.get("run_id") or "").strip()
    saved = _load_saved_operator_brief(detail)
    if saved:
        _save_cached_operator_brief(config, run_id, saved)
        return _attach_operator_brief_sections(saved, detail)
    cached = _load_cached_operator_brief(config, run_id)
    if cached and _saved_operator_brief_matches_detail(cached, detail):
        _save_operator_brief_artifact(detail, _attach_operator_brief_sections(cached, detail))
        return _attach_operator_brief_sections(cached, detail)
    brief = _attach_operator_brief_sections(_load_operator_brief(detail), detail)
    _save_cached_operator_brief(config, run_id, brief)
    _save_operator_brief_artifact(detail, brief)
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
    canonical_sources = load_run_canonical_sources(config.reports_root, str(run_id or ""), run_day)
    commander_summary, commander_provenance = prefer_canonical_agent_payload(
        canonical_sources,
        "commander",
        {
            "mode": str((route_row.get("payload") or {}).get("mode") or ""),
            "phase": str((route_row.get("payload") or {}).get("phase") or ""),
            "status": str((end_row.get("payload") or {}).get("status") or ""),
            "path": str((end_row.get("payload") or {}).get("path") or ""),
        },
        fallback_source="event_log",
    )
    strategist_summary, strategist_provenance = prefer_canonical_agent_payload(
        canonical_sources,
        "strategist",
        strategist_summary if isinstance(strategist_summary, dict) else {},
        fallback_source="event_log",
    )
    scanner_summary, scanner_provenance = prefer_canonical_agent_payload(
        canonical_sources,
        "scanner",
        scanner_summary if isinstance(scanner_summary, dict) else {},
        fallback_source="event_log",
    )
    monitor_summary, monitor_provenance = prefer_canonical_agent_payload(
        canonical_sources,
        "monitor",
        monitor_summary if isinstance(monitor_summary, dict) else {},
        fallback_source="event_log",
    )
    verdict_payload, supervisor_provenance = prefer_canonical_agent_payload(
        canonical_sources,
        "supervisor",
        verdict_payload if isinstance(verdict_payload, dict) else {},
        fallback_source="event_log",
    )
    execution_payload, executor_provenance = prefer_canonical_agent_payload(
        canonical_sources,
        "executor",
        execution_payload if isinstance(execution_payload, dict) else {},
        fallback_source="event_log",
    )
    normalized_execution = _normalize_execution_payload(execution_payload if isinstance(execution_payload, dict) else {})
    if not strategist_llm and isinstance(strategist_summary.get("llm_metadata_summary"), dict):
        strategist_llm = dict(strategist_summary.get("llm_metadata_summary") or {})
    if not isinstance(strategic_frame, dict) or not strategic_frame:
        strategic_frame = dict(strategist_summary or {})
    if (not isinstance(candidate_selection, dict) or not candidate_selection) and isinstance(scanner_summary.get("selected_candidate"), dict):
        candidate_selection = {
            "selected_symbol": scanner_summary.get("selected_symbol") or scanner_summary.get("top_stock"),
            "candidate_pool_size": scanner_summary.get("candidate_pool_after_filter") or scanner_summary.get("universe_size"),
            "selected_candidate": dict(scanner_summary.get("selected_candidate") or {}),
        }
    elif scanner_provenance == "canonical":
        candidate_selection = dict(candidate_selection or {})
        selected_candidate = (
            candidate_selection.get("selected_candidate")
            if isinstance(candidate_selection.get("selected_candidate"), dict)
            else {}
        )
        merged_selected_candidate = dict(selected_candidate or {})
        merged_selected_candidate.update(
            dict(scanner_summary.get("selected_candidate") or {})
            if isinstance(scanner_summary.get("selected_candidate"), dict)
            else {}
        )
        candidate_selection["selected_symbol"] = (
            scanner_summary.get("selected_symbol")
            or scanner_summary.get("top_stock")
            or candidate_selection.get("selected_symbol")
        )
        candidate_selection["candidate_pool_size"] = (
            scanner_summary.get("candidate_pool_after_filter")
            or scanner_summary.get("universe_size")
            or candidate_selection.get("candidate_pool_size")
        )
        candidate_selection["selected_candidate"] = merged_selected_candidate
    if not isinstance(entry_exit_decision, dict) or not entry_exit_decision:
        entry_exit_decision = dict(monitor_summary or {})
    elif monitor_provenance == "canonical":
        entry_exit_decision = {**dict(entry_exit_decision or {}), **dict(monitor_summary or {})}
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
        report_payloads = load_trade_report_payloads(trade_report_meta, read_json=_read_json)
        story_input_data = dict(report_payloads.get("story_input_data") or {})
        lifecycle_data = dict(report_payloads.get("lifecycle_data") or {})
        report_data = dict(report_payloads.get("report_data") or {})
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
            "operator_brief_available": bool(trade_report_meta.get("operator_brief_available")),
            "operator_brief_link": str(trade_report_meta.get("operator_brief_link") or ""),
            "operator_brief_json_path": str(trade_report_meta.get("operator_brief_json_path") or ""),
            "operator_brief_md_path": str(trade_report_meta.get("operator_brief_md_path") or ""),
            "trade_report_json_path": str(trade_report_meta.get("trade_report_json_path") or ""),
            "trade_report_md_path": str(trade_report_meta.get("trade_report_md_path") or ""),
            "trade_story_input_path": str(trade_report_meta.get("trade_story_input_path") or ""),
            "ai_trade_report_json_path": str(trade_report_meta.get("ai_trade_report_json_path") or trade_report_meta.get("trade_report_json_path") or ""),
            "ai_trade_report_md_path": str(trade_report_meta.get("ai_trade_report_md_path") or trade_report_meta.get("trade_report_md_path") or ""),
            "ai_trade_report_input_path": str(trade_report_meta.get("ai_trade_report_input_path") or trade_report_meta.get("trade_story_input_path") or ""),
            "trade_lifecycle_json_path": str(trade_report_meta.get("trade_lifecycle_json_path") or ""),
            "aggregated_bundle_path": str(trade_report_meta.get("aggregated_bundle_path") or ""),
            "trade_root_path": str(trade_report_meta.get("trade_root_path") or ""),
            "strategist_llm_response_path": str(trade_report_meta.get("strategist_llm_response_path") or ""),
            "ai_trade_report_llm_response_path": str(trade_report_meta.get("ai_trade_report_llm_response_path") or ""),
            "brief_llm_response_path": str(trade_report_meta.get("brief_llm_response_path") or ""),
            "trade_provenance_json_path": str(trade_report_meta.get("trade_provenance_json_path") or ""),
            "trade_health_json_path": str(trade_report_meta.get("trade_health_json_path") or ""),
            "trade_artifact_links_json_path": str(trade_report_meta.get("trade_artifact_links_json_path") or ""),
            "section_provenance": dict(trade_report_meta.get("section_provenance") or {}) if isinstance(trade_report_meta.get("section_provenance"), dict) else {},
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
            "operator_brief_available": False,
            "operator_brief_link": "",
            "operator_brief_json_path": "",
            "operator_brief_md_path": "",
            "trade_report_json_path": "",
            "trade_report_md_path": "",
            "trade_story_input_path": "",
            "ai_trade_report_json_path": "",
            "ai_trade_report_md_path": "",
            "ai_trade_report_input_path": "",
            "trade_lifecycle_json_path": "",
            "aggregated_bundle_path": "",
            "trade_root_path": "",
            "strategist_llm_response_path": "",
            "ai_trade_report_llm_response_path": "",
            "brief_llm_response_path": "",
            "trade_provenance_json_path": "",
            "trade_health_json_path": "",
            "trade_artifact_links_json_path": "",
            "section_provenance": {},
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
            "mode": str(commander_summary.get("mode") or commander_summary.get("command") or (route_row.get("payload") or {}).get("mode") or ""),
            "phase": str(commander_summary.get("phase") or ((commander_summary.get("blocked_allowed_details") or {}) if isinstance(commander_summary.get("blocked_allowed_details"), dict) else {}).get("phase") or (route_row.get("payload") or {}).get("phase") or ""),
            "agents": list(commander_summary.get("invoked_agents") or (route_row.get("payload") or {}).get("agents") or []),
            "status": str(commander_summary.get("status") or (end_row.get("payload") or {}).get("status") or ""),
            "path": str(commander_summary.get("path") or commander_summary.get("decision") or (end_row.get("payload") or {}).get("path") or ""),
            "reason": str(commander_summary.get("reason") or ""),
            "provenance": commander_provenance,
            "artifact": commander_summary if isinstance(commander_summary, dict) else {},
        },
        "strategist": {
            "summary": strategist_summary,
            "llm": strategist_llm,
            "decision_trace": strategic_frame if isinstance(strategic_frame, dict) else {},
            "provenance": strategist_provenance,
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
            "provenance": scanner_provenance,
        },
        "monitor": {
            "summary": monitor_summary,
            "decision_trace": entry_exit_decision if isinstance(entry_exit_decision, dict) else {},
            "provenance": monitor_provenance,
        },
        "supervisor": {
            "verdict": verdict_payload,
            "provenance": supervisor_provenance,
        },
        "executor": {
            "execution": execution_payload,
            "provenance": executor_provenance,
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
        "canonical_sources": canonical_sources,
        "artifact_provenance": {
            "commander": commander_provenance,
            "strategist": strategist_provenance,
            "scanner": scanner_provenance,
            "monitor": monitor_provenance,
            "supervisor": supervisor_provenance,
            "executor": executor_provenance,
            "reporter": "direct_artifact",
        },
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
    trade_report = detail.get("trade_report") if isinstance(detail.get("trade_report"), dict) else {}
    if trade_report:
        brief_json_path, brief_md_path = _operator_brief_artifact_paths(detail)
        trade_report["operator_brief_json_path"] = (
            str(brief_json_path) if brief_json_path is not None and brief_json_path.exists() else ""
        )
        trade_report["operator_brief_md_path"] = (
            str(brief_md_path) if brief_md_path is not None and brief_md_path.exists() else ""
        )
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

