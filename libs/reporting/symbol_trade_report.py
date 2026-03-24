from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from libs.reporting.llm_artifacts import symbol_artifact_paths


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


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
        for path in sorted(trades_root.glob("*/*/lifecycle/trade_lifecycle.json")):
            obj = _read_json(path)
            if obj:
                trade_id = str(obj.get("trade_id") or "").strip()
                if trade_id:
                    seen_trade_ids.add(trade_id)
                yield path, obj

        for path in sorted(trades_root.glob("*/*/lifecycle_bundle.json")):
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
        "entry": entry,
        "exit": exit_row,
        "summary": summary,
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
    for _path, obj in _iter_trade_lifecycles(reports_root):
        if str(obj.get("symbol") or "").strip().upper() != normalized_symbol:
            continue
        summary = obj.get("summary") if isinstance(obj.get("summary"), dict) else {}
        entry = obj.get("entry") if isinstance(obj.get("entry"), dict) else {}
        exit_row = obj.get("exit") if isinstance(obj.get("exit"), dict) else {}
        run_id = (
            str(entry.get("run_id") or "").strip()
            or str(exit_row.get("run_id") or "").strip()
            or str(obj.get("entry_strategist_run_id") or "").strip()
        )
        result_pct = _result_pct_from_lifecycle(obj)
        history.append(
            {
                "trade_id": str(obj.get("trade_id") or ""),
                "date": str(obj.get("day") or ""),
                "run_id": run_id,
                "status": str(obj.get("status") or ""),
                "entry_reason": str(summary.get("entry_reason_human") or ""),
                "exit_reason": str(summary.get("exit_reason_human") or ""),
                "lifecycle_summary": str(summary.get("lifecycle_summary_human") or ""),
                "operator_conclusion": str(summary.get("operator_conclusion_human") or ""),
                "playbook": str((((entry.get("strategist_context") or {}) if isinstance(entry.get("strategist_context"), dict) else {}).get("playbook")) or ""),
                "hold_seconds": _hold_seconds_from_lifecycle(obj),
                "result_pct": result_pct,
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
                entry_reasons[reason] += 1
            continue

        if stage == "monitor" and event in {"exit_decision_detail", "state_transition"}:
            detail = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
            symbol_value = str(detail.get("symbol") or payload.get("symbol") or "").strip().upper()
            if symbol_value != normalized_symbol:
                continue
            reason = str(detail.get("final_reason") or detail.get("current_reason") or detail.get("triggered_rule") or "").strip()
            if reason:
                exit_reasons[reason] += 1

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
        reason = str(row.get("entry_reason") or "").strip()
        if reason:
            counter[reason] += 1
    return [name for name, _count in counter.most_common(5)]


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
        str(row.get("entry_reason") or "").strip()
        for row in reversed(history)
        if str(row.get("entry_reason") or "").strip()
    ]
    history_exit_reasons = [
        str(row.get("exit_reason") or "").strip()
        for row in reversed(history)
        if str(row.get("exit_reason") or "").strip()
    ]

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
            "risk_notes": risk_notes,
        },
        "history_index": history,
    }
    return payload


def build_daily_trade_index(reports_root: Path, day: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    target_day = str(day or "").strip()
    for _path, obj in _iter_trade_lifecycles(reports_root):
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
                "entry_reason": str(summary.get("entry_reason_human") or ""),
                "exit_reason": str(summary.get("exit_reason_human") or ""),
            }
        )
    out.sort(key=lambda row: (str(row.get("symbol") or ""), str(row.get("trade_id") or "")))
    return out


def collect_symbols_for_day(events_path: Path, reports_root: Path, day: str) -> List[str]:
    target_day = str(day or "").strip()
    symbols: List[str] = []
    seen: set[str] = set()

    for row in build_daily_trade_index(reports_root, target_day):
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            symbols.append(symbol)

    for row in _iter_jsonl(events_path):
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
        "",
        "## 패턴 인사이트",
        "",
        f"- 성과가 좋았던 진입 패턴: {', '.join(insights.get('successful_entry_patterns') or []) or '없음'}",
        f"- 성과가 약했던 진입 패턴: {', '.join(insights.get('failed_entry_patterns') or []) or '없음'}",
        f"- 자주 반복된 모니터 실패 축: {', '.join(insights.get('common_monitor_failures') or []) or '없음'}",
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
    paths = symbol_artifact_paths(reports_root, symbol)
    root_dir = paths["root_dir"]
    root_dir.mkdir(parents=True, exist_ok=True)

    history_index = payload.get("history_index") if isinstance(payload.get("history_index"), list) else []
    latest_snapshot = {
        "symbol": str(payload.get("symbol") or ""),
        "summary": dict(payload.get("summary") or {}),
        "latest_trade": dict(history_index[-1]) if history_index else {},
    }
    daily_index = sorted({str(row.get("date") or "") for row in history_index if str(row.get("date") or "").strip()})

    paths["symbol_trade_report_json"].write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["trade_history_json"].write_text(json.dumps(history_index, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["latest_snapshot_json"].write_text(json.dumps(latest_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["daily_index_json"].write_text(json.dumps({"symbol": payload.get("symbol"), "days": daily_index}, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["symbol_trade_report_md"].write_text(_render_symbol_trade_markdown(payload), encoding="utf-8")

    return {
        "symbol": str(payload.get("symbol") or ""),
        "report_json_path": str(paths["symbol_trade_report_json"]),
        "report_md_path": str(paths["symbol_trade_report_md"]),
        "trade_history_path": str(paths["trade_history_json"]),
        "latest_snapshot_path": str(paths["latest_snapshot_json"]),
        "daily_index_path": str(paths["daily_index_json"]),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
    }
