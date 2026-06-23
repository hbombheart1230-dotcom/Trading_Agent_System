from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from libs.reporting.event_log_reader import iter_jsonl_events
from libs.reporting.llm_artifacts import resolve_trade_day_root
from libs.reporting.llm_artifacts import symbol_artifact_paths
from libs.reporting.operator_period_summary import (
    _operator_pattern_name,
    _operator_reason_name,
    generate_operator_symbol_summary_artifact,
)


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _normalize_pct_like(value: Any) -> Optional[float]:
    parsed = _safe_float(value)
    if parsed is None:
        return None
    # Many artifact-level return fields are stored as ratios (-0.03 => -3.0%),
    # while some repaired/fallback paths already store percent-like values (0.67 => 0.67%).
    if abs(parsed) <= 0.2:
        return parsed * 100.0
    return parsed


def _pick_result_pct(*values: Any) -> Optional[float]:
    normalized: List[float] = []
    for value in values:
        parsed = _normalize_pct_like(value)
        if parsed is not None:
            normalized.append(parsed)
    if not normalized:
        return None
    for parsed in normalized:
        if abs(parsed) > 1e-12:
            return parsed
    return normalized[0]


def _safe_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(value))
    except Exception:
        return 0


def _normalize_ts(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return text


def _to_epoch(value: Any) -> int:
    text = _normalize_ts(value)
    if not text:
        return 0
    try:
        return int(float(text))
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return 0


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []

    def _gen() -> Iterable[Dict[str, Any]]:
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict):
                    yield row

    return _gen()


def _iter_trade_lifecycles(reports_root: Path) -> Iterable[Tuple[Path, Dict[str, Any]]]:
    trades_root = reports_root / "trades"
    if not trades_root.exists():
        return []

    def _gen() -> Iterable[Tuple[Path, Dict[str, Any]]]:
        seen_trade_ids: set[str] = set()
        for path in sorted(trades_root.rglob("lifecycle/trade_lifecycle.json")):
            obj = _read_json(path)
            if obj:
                trade_id = str(obj.get("trade_id") or "").strip()
                if trade_id:
                    seen_trade_ids.add(trade_id)
                yield path, obj

        for path in sorted(trades_root.rglob("lifecycle_bundle.json")):
            bundle = _read_json(path)
            if not bundle:
                continue
            trade_id = str(bundle.get("trade_id") or "").strip()
            if trade_id and trade_id in seen_trade_ids:
                continue
            normalized = _normalize_lifecycle_bundle(bundle)
            if normalized:
                if trade_id:
                    seen_trade_ids.add(trade_id)
                yield path, normalized

    return _gen()


def _iter_trade_lifecycles_for_day(reports_root: Path, day: str) -> Iterable[Tuple[Path, Dict[str, Any]]]:
    day_root = resolve_trade_day_root(reports_root, str(day or "").strip())
    if not day_root.exists():
        return []

    def _gen() -> Iterable[Tuple[Path, Dict[str, Any]]]:
        seen_trade_ids: set[str] = set()
        for path in sorted(day_root.rglob("lifecycle/trade_lifecycle.json")):
            obj = _read_json(path)
            if obj:
                trade_id = str(obj.get("trade_id") or "").strip()
                if trade_id:
                    seen_trade_ids.add(trade_id)
                yield path, obj

        for path in sorted(day_root.rglob("lifecycle_bundle.json")):
            bundle = _read_json(path)
            if not bundle:
                continue
            trade_id = str(bundle.get("trade_id") or "").strip()
            if trade_id and trade_id in seen_trade_ids:
                continue
            normalized = _normalize_lifecycle_bundle(bundle)
            if normalized:
                if trade_id:
                    seen_trade_ids.add(trade_id)
                yield path, normalized

    return _gen()


def _normalize_lifecycle_bundle(bundle: Dict[str, Any]) -> Dict[str, Any]:
    lifecycle = bundle.get("lifecycle") if isinstance(bundle.get("lifecycle"), dict) else {}
    entry = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
    exit_row = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
    trade_outcome = bundle.get("trade_outcome") if isinstance(bundle.get("trade_outcome"), dict) else {}

    if not entry and not exit_row:
        return {}

    summary = {
        "entry_reason_human": str(entry.get("reason_human") or ""),
        "exit_reason_human": str(exit_row.get("reason_human") or trade_outcome.get("exit_reason") or ""),
        "lifecycle_summary_human": str(bundle.get("summary") or trade_outcome.get("summary") or ""),
        "operator_conclusion_human": str(((bundle.get("reporter_status_human") or {}) if isinstance(bundle.get("reporter_status_human"), dict) else {}).get("operator_conclusion_human") or ""),
    }

    normalized = {
        "trade_id": str(bundle.get("trade_id") or ""),
        "symbol": str(bundle.get("symbol") or ""),
        "day": str(bundle.get("day") or ""),
        "status": str(bundle.get("trade_lifecycle_status") or bundle.get("status") or ""),
        "trade_origin": str(
            bundle.get("trade_origin")
            or ("recovered_partial" if str(bundle.get("trade_lifecycle_status") or bundle.get("status") or "").strip().lower() == "partial" else "normal_lifecycle")
        ),
        "lifecycle_completeness": str(
            bundle.get("lifecycle_completeness")
            or ("partial" if str(bundle.get("trade_lifecycle_status") or bundle.get("status") or "").strip().lower() == "partial" else "complete")
        ),
        "evidence_recovery_used": bool(bundle.get("evidence_recovery_used")),
        "entry": entry,
        "exit": exit_row,
        "summary": summary,
        "artifacts": dict(bundle.get("artifacts") or {}),
    }
    return normalized


def _result_pct_from_lifecycle(obj: Dict[str, Any]) -> Optional[float]:
    entry = obj.get("entry") if isinstance(obj.get("entry"), dict) else {}
    exit_row = obj.get("exit") if isinstance(obj.get("exit"), dict) else {}
    entry_price = _safe_float(entry.get("price"))
    exit_price = _safe_float(exit_row.get("price"))
    if entry_price is None or exit_price is None or entry_price == 0:
        return None
    return ((exit_price - entry_price) / entry_price) * 100.0


def _list_text(values: Any, *, limit: int = 5) -> List[str]:
    out: List[str] = []
    for value in list(values or []):
        text = str(value or "").strip()
        if not text or text in out:
            continue
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _contains_any(text: str, needles: List[str]) -> bool:
    lowered = str(text or "").strip().lower()
    return any(needle in lowered for needle in needles)


def _clean_symbol_reason(value: Any, *, axis: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if axis == "entry" and (
        lowered.startswith("entry reason was not captured")
        or lowered.startswith("entry evidence was not captured")
        or lowered.startswith("entry context was recovered")
    ):
        return ""
    if axis == "exit" and (
        "position is still open" in lowered
        or "포지션은 아직 열려" in text
        or "청산 근거가 누락" in text
    ):
        return ""
    return _operator_reason_name(text)


def _clean_symbol_pattern(value: Any, *, axis: str, fallback_reason: Any = "") -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if lowered.startswith("scanner selected ") or lowered.startswith("entry reason was not captured") or lowered.startswith("entry evidence was not captured"):
        return ""
    if lowered.startswith("entry context was recovered"):
        return ""
    return _operator_pattern_name(value, axis=axis, fallback_reason=fallback_reason)


def _clean_symbol_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() in {"", "unknown", "none", "null", "-"}:
        return ""
    return text


def _clean_symbol_free_text(value: Any, *, entry_reason: str = "", exit_reason: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if "scanner selected" in text:
        return entry_reason or _clean_symbol_reason(text, axis="entry")
    if "sell was triggered" in text or "sell 실행 및 잔여수량" in lowered:
        return exit_reason or _clean_symbol_reason(text, axis="exit")
    if "trigger_type=trailing_stop" in lowered or "trailing_stop" in lowered:
        return text.replace("trigger_type=trailing_stop", "청산축=추적 손절").replace("trailing_stop", "추적 손절")
    if text.lower() == "unknown":
        return ""
    return text


def _classify_entry_pattern(text: str) -> str:
    if _contains_any(text, ["돌파"]):
        return "breakout"
    if _contains_any(text, ["눌림", "풀백"]):
        return "pullback"
    if _contains_any(text, ["재회복"]):
        return "reclaim"
    if _contains_any(text, ["breakout"]):
        return "breakout"
    if _contains_any(text, ["reclaim"]):
        return "reclaim"
    if _contains_any(text, ["pullback"]):
        return "pullback"
    if _contains_any(text, ["continuation"]):
        return "continuation"
    return "unknown"


def _classify_exit_pattern(text: str) -> str:
    if _contains_any(text, ["장중 저점"]):
        return "intraday_low_break"
    if _contains_any(text, ["vwap 이탈"]):
        return "vwap_breakdown"
    if _contains_any(text, ["고점 대비"]):
        return "peak_drawdown"
    if _contains_any(text, ["손절"]):
        return "hard_stop"
    if _contains_any(text, ["익절", "목표 수익"]):
        return "take_profit"
    if _contains_any(text, ["intraday_low_break"]):
        return "intraday_low_break"
    if _contains_any(text, ["vwap_breakdown"]):
        return "vwap_breakdown"
    if _contains_any(text, ["trend_breakdown"]):
        return "trend_breakdown"
    if _contains_any(text, ["peak_drawdown"]):
        return "peak_drawdown"
    if _contains_any(text, ["hard_stop", "stop_loss"]):
        return "hard_stop"
    if _contains_any(text, ["trailing_stop"]):
        return "trailing_stop"
    if _contains_any(text, ["take_profit"]):
        return "take_profit"
    return "unknown"


def _dict_at(root: Dict[str, Any], *keys: str) -> Dict[str, Any]:
    cur: Any = root
    for key in keys:
        if not isinstance(cur, dict):
            return {}
        cur = cur.get(key)
    return cur if isinstance(cur, dict) else {}


def _summary_input_path_for_report(report_path: Path) -> Path:
    return Path(report_path).with_name("ai_trade_summary_input.json")


def _actual_entry_reason_from_artifacts(
    *,
    report_path: Path,
    report_entry_summary: str,
    bundle: Dict[str, Any],
    feedback: Dict[str, Any],
) -> str:
    summary_input = _read_json(_summary_input_path_for_report(report_path))
    decision_flow = summary_input.get("decision_flow") if isinstance(summary_input.get("decision_flow"), dict) else {}
    for value in (
        decision_flow.get("monitor_fallback_reason"),
        decision_flow.get("actual_entry_reason"),
        decision_flow.get("entry_trigger"),
        _dict_at(bundle, "lifecycle", "entry", "monitor_context").get("trigger_type"),
        _dict_at(bundle, "lifecycle", "entry", "monitor_context").get("entry_reason"),
        _dict_at(bundle, "entry", "monitor_context").get("trigger_type"),
        _dict_at(bundle, "entry", "monitor_context").get("entry_reason"),
        feedback.get("entry_reason"),
    ):
        text = str(value or "").strip()
        if text:
            return text

    # Older reports only stored this inside a Korean sentence in summary text.
    for source in (decision_flow.get("entry_confidence"), decision_flow.get("entry_reason"), report_entry_summary):
        text = str(source or "")
        for pattern in (
            r"실제 트리거는\s+(.+?)(?:였|이었|입니다|였습니다)",
            r"실제 엔트리 경로는\s+(.+?)(?:였|이었|입니다|였습니다)",
            r"실제 엔트리는\s+(.+?)(?:에서\s+확정|로\s+확정|으로\s+확정)",
        ):
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip(" .")
    return ""


def _should_prefer_artifact_entry_reason(raw_reason: Any, artifact_reason: Any) -> bool:
    artifact_text = str(artifact_reason or "").strip()
    if not artifact_text:
        return False
    raw_text = str(raw_reason or "").strip()
    if not raw_text:
        return True
    lowered = raw_text.lower()
    return lowered.startswith("scanner selected ") or lowered.startswith("entry evidence was not captured")


def _clean_lifecycle_summary(
    *,
    trade_id: str,
    status: str,
    entry_reason: str,
    exit_reason: str,
) -> str:
    pieces = [f"거래 {trade_id}" if trade_id else "거래", f"상태 {status or '미기록'}"]
    if entry_reason:
        pieces.append(f"진입 {entry_reason}")
    if exit_reason:
        pieces.append(f"청산 {exit_reason}")
    return " / ".join(pieces)


def _extract_trade_artifact_snapshot(
    *,
    report_path: Path,
    operator_brief_path: Path,
    lifecycle_bundle_path: Path,
) -> Dict[str, Any]:
    report = _read_json(report_path)
    brief = _read_json(operator_brief_path)
    bundle = _read_json(lifecycle_bundle_path)
    report_executive = report.get("executive_summary") if isinstance(report.get("executive_summary"), dict) else {}
    report_market = report.get("market_context_at_entry") if isinstance(report.get("market_context_at_entry"), dict) else {}
    report_entry = report.get("entry_decision") if isinstance(report.get("entry_decision"), dict) else {}
    report_final = report.get("final_operator_conclusion") if isinstance(report.get("final_operator_conclusion"), dict) else {}
    feedback = (
        bundle.get("strategist_feedback_input")
        if isinstance(bundle.get("strategist_feedback_input"), dict)
        else report.get("strategist_feedback_input")
        if isinstance(report.get("strategist_feedback_input"), dict)
        else {}
    )
    shared_facts = (
        bundle.get("shared_facts")
        if isinstance(bundle.get("shared_facts"), dict)
        else report.get("shared_facts")
        if isinstance(report.get("shared_facts"), dict)
        else {}
    )
    trade_outcome = bundle.get("trade_outcome") if isinstance(bundle.get("trade_outcome"), dict) else {}
    report_shared_facts = report.get("shared_facts") if isinstance(report.get("shared_facts"), dict) else {}
    artifact_result_pct = _pick_result_pct(
        trade_outcome.get("return_pct"),
        shared_facts.get("return_pct"),
        shared_facts.get("pnl_pct"),
        report_shared_facts.get("return_pct"),
        report_shared_facts.get("pnl_pct"),
    )
    entry_reason_text = str(report_entry.get("summary") or "").strip()
    actual_entry_reason_text = _actual_entry_reason_from_artifacts(
        report_path=Path(report_path),
        report_entry_summary=entry_reason_text,
        bundle=bundle,
        feedback=feedback,
    )
    exit_reason_text = str(shared_facts.get("exit_reason") or "").strip()
    if not exit_reason_text:
        exit_reason_text = str(report_final.get("summary") or "").strip()
    entry_pattern_type = str(feedback.get("entry_pattern_type") or "").strip() or _classify_entry_pattern(actual_entry_reason_text or entry_reason_text)
    exit_pattern_type = str(feedback.get("exit_pattern_type") or "").strip() or _classify_exit_pattern(exit_reason_text)
    clean_entry_reason = _clean_symbol_reason(actual_entry_reason_text or entry_reason_text, axis="entry")
    clean_exit_reason = _clean_symbol_reason(exit_reason_text, axis="exit")
    return {
        "report_headline": _clean_symbol_free_text(report_executive.get("headline") or report.get("headline"), entry_reason=clean_entry_reason, exit_reason=clean_exit_reason),
        "report_executive_summary": _clean_symbol_free_text(report_executive.get("summary"), entry_reason=clean_entry_reason, exit_reason=clean_exit_reason),
        "report_market_summary": str(report_market.get("summary") or "").strip(),
        "report_entry_summary": clean_entry_reason,
        "actual_entry_reason": clean_entry_reason,
        "report_final_conclusion": _clean_symbol_free_text(report_final.get("summary"), entry_reason=clean_entry_reason, exit_reason=clean_exit_reason),
        "brief_headline": _clean_symbol_free_text(brief.get("headline"), entry_reason=clean_entry_reason, exit_reason=clean_exit_reason),
        "brief_executive_summary": _clean_symbol_free_text(brief.get("executive_summary"), entry_reason=clean_entry_reason, exit_reason=clean_exit_reason),
        "brief_risk_summary": _clean_symbol_free_text(brief.get("risk_summary"), entry_reason=clean_entry_reason, exit_reason=clean_exit_reason),
        "brief_next_checkpoints": _list_text(brief.get("next_checkpoints"), limit=3),
        "entry_pattern_type": _clean_symbol_pattern(entry_pattern_type, axis="entry", fallback_reason=clean_entry_reason),
        "exit_pattern_type": _clean_symbol_pattern(exit_pattern_type, axis="exit", fallback_reason=clean_exit_reason),
        "thesis_invalidation_code": _clean_symbol_code(feedback.get("thesis_invalidation_code")),
        "improvement_tags": _list_text(feedback.get("improvement_tags"), limit=6),
        "review_flags": _list_text(feedback.get("review_flags"), limit=6),
        "artifact_result_pct": artifact_result_pct,
    }


def _hold_seconds_from_lifecycle(obj: Dict[str, Any]) -> Optional[float]:
    entry = obj.get("entry") if isinstance(obj.get("entry"), dict) else {}
    exit_row = obj.get("exit") if isinstance(obj.get("exit"), dict) else {}
    entry_ts = _to_epoch(entry.get("ts"))
    exit_ts = _to_epoch(exit_row.get("ts"))
    if entry_ts > 0 and exit_ts > 0 and exit_ts >= entry_ts:
        return float(exit_ts - entry_ts)
    return None


def _build_history_index(reports_root: Path, symbol: str) -> List[Dict[str, Any]]:
    history: List[Dict[str, Any]] = []
    normalized_symbol = str(symbol or "").strip().upper()
    for path, obj in _iter_trade_lifecycles(reports_root):
        if str(obj.get("symbol") or "").strip().upper() != normalized_symbol:
            continue
        summary = obj.get("summary") if isinstance(obj.get("summary"), dict) else {}
        entry = obj.get("entry") if isinstance(obj.get("entry"), dict) else {}
        exit_row = obj.get("exit") if isinstance(obj.get("exit"), dict) else {}
        artifacts = obj.get("artifacts") if isinstance(obj.get("artifacts"), dict) else {}
        trade_id = str(obj.get("trade_id") or "")
        trade_day = str(obj.get("day") or "")
        trade_root = (
            path.parent
            if path.name == "lifecycle_bundle.json"
            else path.parent.parent
        )
        expected_report_path = trade_root / "reports" / "ai_trade_report.json"
        expected_operator_brief_path = trade_root / "reports" / "operator_brief.json"
        lifecycle_bundle_path = trade_root / "lifecycle_bundle.json"
        artifact_snapshot = _extract_trade_artifact_snapshot(
            report_path=Path(str(artifacts.get("ai_trade_report_json") or expected_report_path)),
            operator_brief_path=Path(str(artifacts.get("operator_brief_json") or expected_operator_brief_path)),
            lifecycle_bundle_path=Path(str(artifacts.get("lifecycle_bundle_json") or lifecycle_bundle_path)),
        )
        trade_status = str(obj.get("status") or "").strip()
        if exit_row:
            last_action = "SELL"
        elif trade_status.lower() == "open":
            last_action = "HOLD"
        elif entry:
            last_action = "BUY"
        else:
            last_action = ""
        run_id = (
            str(entry.get("run_id") or "").strip()
            or str(exit_row.get("run_id") or "").strip()
            or str(obj.get("entry_strategist_run_id") or "").strip()
        )
        result_pct = _result_pct_from_lifecycle(obj)
        if result_pct is None:
            result_pct = _safe_float(artifact_snapshot.get("artifact_result_pct"))
        raw_entry_reason = str(summary.get("entry_reason_human") or "")
        artifact_entry_reason = str(artifact_snapshot.get("actual_entry_reason") or "")
        entry_reason_raw = (
            artifact_entry_reason
            if _should_prefer_artifact_entry_reason(raw_entry_reason, artifact_entry_reason)
            else raw_entry_reason
        )
        entry_reason = _clean_symbol_reason(entry_reason_raw, axis="entry")
        exit_reason = _clean_symbol_reason(summary.get("exit_reason_human"), axis="exit")
        entry_pattern_type = _clean_symbol_pattern(
            artifact_snapshot.get("entry_pattern_type"),
            axis="entry",
            fallback_reason=entry_reason,
        )
        exit_pattern_type = _clean_symbol_pattern(
            artifact_snapshot.get("exit_pattern_type"),
            axis="exit",
            fallback_reason=exit_reason,
        )
        history.append(
            {
                "trade_id": trade_id,
                "date": trade_day,
                "run_id": run_id,
                "status": trade_status,
                "last_status": trade_status,
                "last_action": last_action,
                "entry_reason": entry_reason,
                "exit_reason": exit_reason,
                "lifecycle_summary": _clean_lifecycle_summary(
                    trade_id=trade_id,
                    status=trade_status,
                    entry_reason=entry_reason,
                    exit_reason=exit_reason,
                ),
                "operator_conclusion": str(summary.get("operator_conclusion_human") or ""),
                "playbook": str((((entry.get("strategist_context") or {}) if isinstance(entry.get("strategist_context"), dict) else {}).get("playbook")) or ""),
                "hold_seconds": _hold_seconds_from_lifecycle(obj),
                "result_pct": result_pct,
                "trade_origin": str(obj.get("trade_origin") or ""),
                "lifecycle_completeness": str(obj.get("lifecycle_completeness") or ""),
                "evidence_recovery_used": bool(obj.get("evidence_recovery_used")),
                "report_path": str(artifacts.get("ai_trade_report_json") or expected_report_path),
                "operator_brief_path": str(artifacts.get("operator_brief_json") or expected_operator_brief_path),
                "lifecycle_bundle_path": str(artifacts.get("lifecycle_bundle_json") or lifecycle_bundle_path),
                "trade_root_path": str(trade_root),
                "report_headline": str(artifact_snapshot.get("report_headline") or ""),
                "report_executive_summary": str(artifact_snapshot.get("report_executive_summary") or ""),
                "report_market_summary": str(artifact_snapshot.get("report_market_summary") or ""),
                "report_entry_summary": str(artifact_snapshot.get("report_entry_summary") or entry_reason or ""),
                "report_final_conclusion": str(artifact_snapshot.get("report_final_conclusion") or ""),
                "brief_headline": str(artifact_snapshot.get("brief_headline") or ""),
                "brief_executive_summary": str(artifact_snapshot.get("brief_executive_summary") or ""),
                "brief_risk_summary": str(artifact_snapshot.get("brief_risk_summary") or ""),
                "brief_next_checkpoints": list(artifact_snapshot.get("brief_next_checkpoints") or []),
                "entry_pattern_type": entry_pattern_type,
                "exit_pattern_type": exit_pattern_type,
                "thesis_invalidation_code": _clean_symbol_code(artifact_snapshot.get("thesis_invalidation_code")),
                "improvement_tags": list(artifact_snapshot.get("improvement_tags") or []),
                "review_flags": list(artifact_snapshot.get("review_flags") or []),
            }
        )
    history.sort(key=lambda row: (str(row.get("date") or ""), str(row.get("trade_id") or "")))
    return history


def _collect_symbol_event_insights(events_path: Path, symbol: str) -> Dict[str, List[str]]:
    normalized_symbol = str(symbol or "").strip().upper()
    wait_reasons: Counter[str] = Counter()
    entry_reasons: Counter[str] = Counter()
    exit_reasons: Counter[str] = Counter()

    for row in _iter_jsonl(events_path):
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        event = str(row.get("event") or "").strip()
        stage = str(row.get("stage") or "").strip()

        if stage == "monitor" and event == "entry_decision_detail":
            detail = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
            symbol_value = str(detail.get("symbol") or payload.get("symbol") or "").strip().upper()
            if symbol_value != normalized_symbol:
                continue
            decision = str(detail.get("decision") or "").strip().upper()
            reason = str(detail.get("reason") or "").strip()
            if decision == "WAIT" and reason:
                wait_reasons[reason] += 1
            elif decision == "BUY" and reason:
                clean_reason = _clean_symbol_reason(reason, axis="entry")
                if clean_reason:
                    entry_reasons[clean_reason] += 1
            continue

        if stage == "monitor" and event in {"exit_decision_detail", "state_transition"}:
            detail = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
            symbol_value = str(detail.get("symbol") or payload.get("symbol") or "").strip().upper()
            if symbol_value != normalized_symbol:
                continue
            reason = str(detail.get("final_reason") or detail.get("current_reason") or detail.get("triggered_rule") or "").strip()
            if reason:
                clean_reason = _clean_symbol_reason(reason, axis="exit")
                if clean_reason:
                    exit_reasons[clean_reason] += 1

    return {
        "recent_wait_reasons": [name for name, _count in wait_reasons.most_common(5)],
        "recent_entry_reasons": [name for name, _count in entry_reasons.most_common(5)],
        "recent_exit_reasons": [name for name, _count in exit_reasons.most_common(5)],
        "common_monitor_failures": [name for name, _count in wait_reasons.most_common(5)],
        "wait_reason_distribution": dict(wait_reasons),
    }


def _pattern_rows(history: List[Dict[str, Any]], *, positive: bool) -> List[str]:
    counter: Counter[str] = Counter()
    for row in history:
        result_pct = _safe_float(row.get("result_pct"))
        if result_pct is None:
            continue
        if positive and result_pct <= 0:
            continue
        if (not positive) and result_pct >= 0:
            continue
        pattern_type = _clean_symbol_pattern(
            row.get("entry_pattern_type"),
            axis="entry",
            fallback_reason=row.get("entry_reason"),
        )
        if pattern_type:
            counter[pattern_type] += 1
            continue
        reason = _clean_symbol_reason(row.get("entry_reason"), axis="entry")
        if reason:
            counter[reason] += 1
    return [name for name, _count in counter.most_common(5)]


def _ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _derive_playbook_stats(history: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in history:
        playbook = str(row.get("playbook") or "").strip()
        if not playbook:
            continue
        bucket = grouped.setdefault(
            playbook,
            {
                "count": 0,
                "completed_count": 0,
                "win_count": 0,
                "return_values": [],
            },
        )
        bucket["count"] += 1
        status = str(row.get("status") or "").strip().lower()
        result_pct = _safe_float(row.get("result_pct"))
        if status == "closed":
            bucket["completed_count"] += 1
            if result_pct is not None:
                bucket["return_values"].append(result_pct)
                if result_pct > 0:
                    bucket["win_count"] += 1

    out: Dict[str, Dict[str, Any]] = {}
    for playbook, bucket in grouped.items():
        completed_count = int(bucket.get("completed_count") or 0)
        return_values = [float(v) for v in list(bucket.get("return_values") or [])]
        out[playbook] = {
            "count": int(bucket.get("count") or 0),
            "win_rate": round(_ratio(float(bucket.get("win_count") or 0), float(completed_count)), 4),
            "avg_return_pct": round(sum(return_values) / len(return_values), 4) if return_values else 0.0,
        }
    return out


def _derive_dominant_exit_failure_axis(history: List[Dict[str, Any]]) -> str:
    counter: Counter[str] = Counter()
    for row in history:
        status = str(row.get("status") or "").strip().lower()
        result_pct = _safe_float(row.get("result_pct"))
        if status != "closed" or result_pct is None or result_pct >= 0:
            continue
        exit_pattern = _clean_symbol_pattern(
            row.get("exit_pattern_type"),
            axis="exit",
            fallback_reason=row.get("exit_reason"),
        )
        if exit_pattern:
            counter[exit_pattern] += 1
            continue
        exit_reason = _clean_symbol_reason(row.get("exit_reason"), axis="exit")
        if exit_reason:
            counter[exit_reason] += 1
    if not counter:
        return ""
    return str(counter.most_common(1)[0][0])


def _derive_bias_recommendation(
    *,
    avg_return_pct: float,
    playbook_stats: Dict[str, Dict[str, Any]],
    repeated_blockers: List[str],
) -> Dict[str, Any]:
    prefer_playbook = ""
    avoid_playbook = ""
    scanner_bonus = 0.0
    scanner_penalty = 0.0
    risk_cap = "normal"

    best_playbook = ""
    best_return = -10**9
    worst_playbook = ""
    worst_return = 10**9
    for playbook, stats in playbook_stats.items():
        avg_return = _safe_float((stats or {}).get("avg_return_pct"))
        if avg_return is None:
            continue
        if avg_return > best_return:
            best_return = avg_return
            best_playbook = playbook
        if avg_return < worst_return:
            worst_return = avg_return
            worst_playbook = playbook

    if best_playbook and best_return > 0:
        prefer_playbook = best_playbook
        scanner_bonus = 0.05 if best_return < 1.0 else 0.08

    if worst_playbook and worst_return < 0:
        avoid_playbook = worst_playbook
        scanner_penalty = 0.05 if worst_return > -1.0 else 0.08

    lowered_blockers = {str(x or "").strip().lower() for x in repeated_blockers}
    if avg_return_pct < 0 or {"confirmed_entry", "breakout_readiness"} & lowered_blockers:
        risk_cap = "conservative"
        scanner_penalty = max(scanner_penalty, 0.08 if avg_return_pct < 0 else 0.05)

    return {
        "scanner_penalty": round(scanner_penalty, 4),
        "scanner_bonus": round(scanner_bonus, 4),
        "prefer_playbook": prefer_playbook,
        "avoid_playbook": avoid_playbook,
        "risk_cap": risk_cap,
    }


def build_symbol_memory_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized_symbol = str(payload.get("symbol") or "").strip().upper()
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    pattern_insights = payload.get("pattern_insights") if isinstance(payload.get("pattern_insights"), dict) else {}
    history = payload.get("history_index") if isinstance(payload.get("history_index"), list) else []
    trade_count = _safe_int(summary.get("trade_count"))
    completed_trade_count = _safe_int(summary.get("completed_trade_count"))
    win_count = _safe_int(summary.get("win_count"))
    avg_return_pct = _safe_float(summary.get("avg_return_pct")) or 0.0
    avg_hold_seconds = _safe_float(summary.get("avg_hold_seconds")) or 0.0
    repeated_blockers = _list_text(pattern_insights.get("common_monitor_failures"), limit=5)
    playbook_stats = _derive_playbook_stats(history)
    latest_trade = dict(history[-1]) if history else {}
    dominant_wait_reason = ""
    wait_distribution = summary.get("wait_reason_distribution") if isinstance(summary.get("wait_reason_distribution"), dict) else {}
    if wait_distribution:
        dominant_wait_reason = str(max(wait_distribution.items(), key=lambda item: float(item[1] or 0))[0])

    memory = {
        "schema_version": "symbol_memory.v1",
        "symbol": normalized_symbol,
        "window_label": "rolling_recent",
        "trade_stats": {
            "trade_count": trade_count,
            "completed_trade_count": completed_trade_count,
            "win_rate": round(_ratio(float(win_count), float(completed_trade_count)), 4),
            "avg_return_pct": round(avg_return_pct, 4),
            "avg_hold_seconds": round(avg_hold_seconds, 2),
        },
        "playbook_stats": playbook_stats,
        "pattern_stats": {
            "successful_entry_patterns": list(pattern_insights.get("successful_entry_patterns") or []),
            "failed_entry_patterns": list(pattern_insights.get("failed_entry_patterns") or []),
            "common_monitor_failures": repeated_blockers,
            "recent_entry_pattern_types": list(pattern_insights.get("recent_entry_pattern_types") or []),
            "recent_exit_pattern_types": list(pattern_insights.get("recent_exit_pattern_types") or []),
        },
        "execution_risk": {
            "spread_bps_p50": None,
            "spread_bps_p90": None,
            "slippage_bps_p50": None,
            "execution_risk_level": "not_available",
        },
        "monitor_patterns": {
            "repeated_blockers": repeated_blockers,
            "dominant_wait_reason": dominant_wait_reason,
            "dominant_exit_failure_axis": _derive_dominant_exit_failure_axis(history),
            "hold_refresh_count": 0,
            "hold_refresh_effective_count": 0,
            "hold_refresh_effective_rate": 0.0,
        },
        "bias_recommendation": _derive_bias_recommendation(
            avg_return_pct=avg_return_pct,
            playbook_stats=playbook_stats,
            repeated_blockers=repeated_blockers,
        ),
        "latest_snapshot": {
            "last_trade_id": str(latest_trade.get("trade_id") or ""),
            "last_trade_date": str(latest_trade.get("date") or ""),
            "last_status": str(latest_trade.get("last_status") or latest_trade.get("status") or ""),
        },
    }
    return memory


def build_symbol_trade_summary(events_path: Path, reports_root: Path, symbol: str) -> Dict[str, Any]:
    normalized_symbol = str(symbol or "").strip().upper()
    history = _build_history_index(reports_root, normalized_symbol)
    insights = _collect_symbol_event_insights(events_path, normalized_symbol)
    recent_playbooks: List[str] = []
    for row in reversed(history):
        playbook = str(row.get("playbook") or "").strip()
        if playbook and playbook not in recent_playbooks:
            recent_playbooks.append(playbook)
        if len(recent_playbooks) >= 5:
            break
    history_entry_reasons = [
        _clean_symbol_reason(row.get("entry_reason"), axis="entry")
        for row in reversed(history)
        if _clean_symbol_reason(row.get("entry_reason"), axis="entry")
    ]
    history_exit_reasons = [
        _clean_symbol_reason(row.get("exit_reason"), axis="exit")
        for row in reversed(history)
        if _clean_symbol_reason(row.get("exit_reason"), axis="exit")
    ]
    recent_trade_headlines = [
        str(row.get("brief_headline") or row.get("report_headline") or "").strip()
        for row in reversed(history)
        if str(row.get("brief_headline") or row.get("report_headline") or "").strip()
    ]
    recent_operator_viewpoints = [
        str(row.get("brief_executive_summary") or row.get("report_final_conclusion") or "").strip()
        for row in reversed(history)
        if str(row.get("brief_executive_summary") or row.get("report_final_conclusion") or "").strip()
    ]
    entry_pattern_types = [
        _clean_symbol_pattern(row.get("entry_pattern_type"), axis="entry", fallback_reason=row.get("entry_reason"))
        for row in reversed(history)
        if _clean_symbol_pattern(row.get("entry_pattern_type"), axis="entry", fallback_reason=row.get("entry_reason"))
    ]
    exit_pattern_types = [
        _clean_symbol_pattern(row.get("exit_pattern_type"), axis="exit", fallback_reason=row.get("exit_reason"))
        for row in reversed(history)
        if _clean_symbol_pattern(row.get("exit_pattern_type"), axis="exit", fallback_reason=row.get("exit_reason"))
    ]
    improvement_tag_counter: Counter[str] = Counter()
    review_flag_counter: Counter[str] = Counter()
    for row in history:
        for tag in list(row.get("improvement_tags") or []):
            text = str(tag or "").strip()
            if text:
                improvement_tag_counter[text] += 1
        for flag in list(row.get("review_flags") or []):
            text = str(flag or "").strip()
            if text:
                review_flag_counter[text] += 1

    completed = [row for row in history if str(row.get("status") or "").strip().lower() == "closed"]
    returns = [value for value in (_safe_float(row.get("result_pct")) for row in completed) if value is not None]
    holds = [value for value in (_safe_float(row.get("hold_seconds")) for row in completed) if value is not None]
    win_count = sum(1 for value in returns if value > 0)
    loss_count = sum(1 for value in returns if value < 0)

    summary = {
        "trade_count": len(history),
        "completed_trade_count": len(completed),
        "win_count": win_count,
        "loss_count": loss_count,
        "avg_return_pct": round(sum(returns) / len(returns), 4) if returns else 0.0,
        "avg_hold_seconds": round(sum(holds) / len(holds), 2) if holds else 0.0,
        "recent_playbooks": recent_playbooks,
        "recent_entry_reasons": list(insights.get("recent_entry_reasons") or history_entry_reasons[:5]),
        "recent_exit_reasons": list(insights.get("recent_exit_reasons") or history_exit_reasons[:5]),
        "recent_wait_reasons": list(insights.get("recent_wait_reasons") or []),
        "wait_reason_distribution": dict(insights.get("wait_reason_distribution") or {}),
        "recent_trade_headlines": _list_text(recent_trade_headlines, limit=5),
        "recent_operator_viewpoints": _list_text(recent_operator_viewpoints, limit=5),
    }

    risk_notes: List[str] = []
    if summary["trade_count"] == 0:
        risk_notes.append("저장된 거래 이력이 아직 없어 전략 피드백 근거가 제한적입니다.")
    if summary["completed_trade_count"] > 0 and summary["avg_return_pct"] < 0:
        risk_notes.append("완료된 거래 기준 평균 수익률이 음수여서 동일한 접근의 재사용은 보수적으로 해석해야 합니다.")
    if len(summary["recent_wait_reasons"]) >= 3:
        risk_notes.append("대기 사유가 반복적으로 누적되고 있어 진입 구조와 분봉 조건의 적합성을 점검할 필요가 있습니다.")

    payload = {
        "schema_version": "symbol_trade_report.v1",
        "symbol": normalized_symbol,
        "summary": summary,
        "pattern_insights": {
            "successful_entry_patterns": _pattern_rows(history, positive=True),
            "failed_entry_patterns": _pattern_rows(history, positive=False),
            "common_monitor_failures": list(insights.get("common_monitor_failures") or []),
            "recent_entry_pattern_types": _list_text(entry_pattern_types, limit=5),
            "recent_exit_pattern_types": _list_text(exit_pattern_types, limit=5),
            "recent_improvement_tags": [name for name, _count in improvement_tag_counter.most_common(6)],
            "recent_review_flags": [name for name, _count in review_flag_counter.most_common(6)],
            "risk_notes": risk_notes,
        },
        "history_index": history,
    }
    return payload


def build_daily_trade_index(reports_root: Path, day: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    target_day = str(day or "").strip()
    for _path, obj in _iter_trade_lifecycles_for_day(reports_root, target_day):
        if str(obj.get("day") or "").strip() != target_day:
            continue
        summary = obj.get("summary") if isinstance(obj.get("summary"), dict) else {}
        entry = obj.get("entry") if isinstance(obj.get("entry"), dict) else {}
        exit_row = obj.get("exit") if isinstance(obj.get("exit"), dict) else {}
        out.append(
            {
                "trade_id": str(obj.get("trade_id") or ""),
                "symbol": str(obj.get("symbol") or ""),
                "date": target_day,
                "status": str(obj.get("status") or ""),
                "entry_run_id": str(entry.get("run_id") or ""),
                "exit_run_id": str(exit_row.get("run_id") or ""),
                "entry_reason": _clean_symbol_reason(summary.get("entry_reason_human"), axis="entry"),
                "exit_reason": _clean_symbol_reason(summary.get("exit_reason_human"), axis="exit"),
            }
        )
    carryover_index = _read_json(resolve_trade_day_root(reports_root, target_day) / "carryover_exit_index.json")
    for item in list(carryover_index.get("rows") or []):
        if not isinstance(item, dict):
            continue
        trade_id = str(item.get("trade_id") or "").strip()
        if trade_id and any(str(row.get("trade_id") or "") == trade_id for row in out):
            continue
        out.append(dict(item))
    out.sort(key=lambda row: (str(row.get("symbol") or ""), str(row.get("trade_id") or "")))
    return out


def collect_symbols_for_day(
    events_path: Path,
    reports_root: Path,
    day: str,
    trade_index: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    target_day = str(day or "").strip()
    symbols: List[str] = []
    seen: set[str] = set()

    index_rows = trade_index if trade_index is not None else build_daily_trade_index(reports_root, target_day)
    for row in index_rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)

    for row in iter_jsonl_events(events_path, day=target_day):
        ts_day = datetime.fromtimestamp(_to_epoch(row.get("ts") or (row.get("payload") or {}).get("ts")), tz=timezone.utc).strftime("%Y-%m-%d") if _to_epoch(row.get("ts") or (row.get("payload") or {}).get("ts")) > 0 else ""
        if ts_day != target_day:
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        detail = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
        for candidate in (
            detail.get("symbol"),
            payload.get("symbol"),
            order.get("symbol"),
            order.get("stk_cd"),
        ):
            symbol = str(candidate or "").strip().upper()
            if symbol and symbol not in seen:
                seen.add(symbol)
                symbols.append(symbol)
    return symbols


def _render_symbol_trade_markdown(payload: Dict[str, Any]) -> str:
    symbol = str(payload.get("symbol") or "")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    insights = payload.get("pattern_insights") if isinstance(payload.get("pattern_insights"), dict) else {}
    history = payload.get("history_index") if isinstance(payload.get("history_index"), list) else []

    lines = [
        f"# 심볼 거래 리포트 ({symbol})",
        "",
        "## 요약",
        "",
        f"- 누적 거래 수: **{_safe_int(summary.get('trade_count'))}**",
        f"- 완료 거래 수: **{_safe_int(summary.get('completed_trade_count'))}**",
        f"- 승리/손실: **{_safe_int(summary.get('win_count'))} / {_safe_int(summary.get('loss_count'))}**",
        f"- 평균 수익률: **{float(summary.get('avg_return_pct') or 0.0):.2f}%**",
        f"- 평균 보유 시간: **{float(summary.get('avg_hold_seconds') or 0.0):.0f}초**",
        "",
        "## 최근 관찰 포인트",
        "",
        f"- 최근 playbook: {', '.join(summary.get('recent_playbooks') or []) or '없음'}",
        f"- 최근 진입 사유: {', '.join(summary.get('recent_entry_reasons') or []) or '없음'}",
        f"- 최근 청산 사유: {', '.join(summary.get('recent_exit_reasons') or []) or '없음'}",
        f"- 최근 WAIT 사유: {', '.join(summary.get('recent_wait_reasons') or []) or '없음'}",
        f"- recent trade headlines: {', '.join(summary.get('recent_trade_headlines') or []) or 'none'}",
        f"- recent operator viewpoints: {', '.join(summary.get('recent_operator_viewpoints') or []) or 'none'}",
        "",
        "## 패턴 인사이트",
        "",
        f"- 성과가 좋았던 진입 패턴: {', '.join(insights.get('successful_entry_patterns') or []) or '없음'}",
        f"- 성과가 약했던 진입 패턴: {', '.join(insights.get('failed_entry_patterns') or []) or '없음'}",
        f"- 자주 반복된 모니터 실패 축: {', '.join(insights.get('common_monitor_failures') or []) or '없음'}",
        f"- recent entry pattern types: {', '.join(insights.get('recent_entry_pattern_types') or []) or 'none'}",
        f"- recent exit pattern types: {', '.join(insights.get('recent_exit_pattern_types') or []) or 'none'}",
        f"- recent improvement tags: {', '.join(insights.get('recent_improvement_tags') or []) or 'none'}",
        f"- recent review flags: {', '.join(insights.get('recent_review_flags') or []) or 'none'}",
    ]
    risk_notes = list(insights.get("risk_notes") or [])
    if risk_notes:
        lines.extend(["", "## 리스크 메모", ""])
        for note in risk_notes:
            lines.append(f"- {note}")

    lines.extend(["", "## 거래 이력", ""])
    if not history:
        lines.append("- 저장된 거래 이력이 없습니다.")
    else:
        for row in history[-20:]:
            result_pct = _safe_float(row.get("result_pct"))
            result_text = f"{result_pct:.2f}%" if result_pct is not None else "미기록"
            lines.append(
                f"- {row.get('date')}: {row.get('trade_id')} / 상태 {row.get('status')} / "
                f"진입 {row.get('entry_reason') or '미기록'} / 청산 {row.get('exit_reason') or '미기록'} / 결과 {result_text}"
            )
    lines.append("")
    return "\n".join(lines)


def generate_symbol_trade_report(events_path: Path, reports_root: Path, symbol: str) -> Dict[str, Any]:
    payload = build_symbol_trade_summary(events_path, reports_root, symbol)
    symbol_memory = build_symbol_memory_payload(payload)
    paths = symbol_artifact_paths(reports_root, symbol)
    root_dir = paths["root_dir"]
    root_dir.mkdir(parents=True, exist_ok=True)

    history_index = payload.get("history_index") if isinstance(payload.get("history_index"), list) else []
    latest_trade = dict(history_index[-1]) if history_index else {}
    latest_snapshot = {
        "schema_version": "symbol_latest_snapshot.v1",
        "symbol": str(payload.get("symbol") or ""),
        "summary": dict(payload.get("summary") or {}),
        "last_trade_id": str(latest_trade.get("trade_id") or ""),
        "last_trade_date": str(latest_trade.get("date") or ""),
        "last_action": str(latest_trade.get("last_action") or ""),
        "last_status": str(latest_trade.get("last_status") or latest_trade.get("status") or ""),
        "report_path": str(latest_trade.get("report_path") or ""),
        "trade_origin": str(latest_trade.get("trade_origin") or ""),
        "lifecycle_completeness": str(latest_trade.get("lifecycle_completeness") or ""),
        "evidence_recovery_used": bool(latest_trade.get("evidence_recovery_used")),
        "latest_trade": latest_trade,
    }
    daily_index = sorted({str(row.get("date") or "") for row in history_index if str(row.get("date") or "").strip()})

    paths["symbol_trade_report_json"].write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["symbol_memory_json"].write_text(json.dumps(symbol_memory, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["trade_history_json"].write_text(json.dumps(history_index, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["latest_snapshot_json"].write_text(json.dumps(latest_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["daily_index_json"].write_text(json.dumps({"symbol": payload.get("symbol"), "days": daily_index}, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["symbol_trade_report_md"].write_text(_render_symbol_trade_markdown(payload), encoding="utf-8")
    summary_md, summary_json, _summary_payload = generate_operator_symbol_summary_artifact(
        reports_root=reports_root,
        symbol=symbol,
        symbol_trade_report_payload=payload,
        symbol_memory_payload=symbol_memory,
    )

    return {
        "symbol": str(payload.get("symbol") or ""),
        "report_json_path": str(paths["symbol_trade_report_json"]),
        "report_md_path": str(paths["symbol_trade_report_md"]),
        "symbol_summary_json_path": str(summary_json),
        "symbol_summary_md_path": str(summary_md),
        "symbol_memory_path": str(paths["symbol_memory_json"]),
        "trade_history_path": str(paths["trade_history_json"]),
        "latest_snapshot_path": str(paths["latest_snapshot_json"]),
        "daily_index_path": str(paths["daily_index_json"]),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
    }
