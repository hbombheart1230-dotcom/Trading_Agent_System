from __future__ import annotations

import calendar
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from libs.performance.strategy_memory import sync_strategy_memory_artifacts
from libs.reporting.llm_artifacts import (
    daily_artifact_paths,
    monthly_artifact_paths,
    operator_summary_artifact_root,
    symbol_artifact_paths,
    weekly_artifact_paths,
)


_WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")
_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _parse_day(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except Exception:
        return None


def _period_from_week(week: str) -> Tuple[str, date, date]:
    text = str(week or "").strip()
    match = _WEEK_RE.match(text)
    if not match:
        raise ValueError(f"invalid week key: {text!r}; expected YYYY-Www")
    year = int(match.group(1))
    week_num = int(match.group(2))
    start = date.fromisocalendar(year, week_num, 1)
    end = date.fromisocalendar(year, week_num, 7)
    return f"{year:04d}-W{week_num:02d}", start, end


def _period_from_month(month: str) -> Tuple[str, date, date]:
    text = str(month or "").strip()
    match = _MONTH_RE.match(text)
    if not match:
        raise ValueError(f"invalid month key: {text!r}; expected YYYY-MM")
    year = int(match.group(1))
    month_num = int(match.group(2))
    last_day = calendar.monthrange(year, month_num)[1]
    return f"{year:04d}-{month_num:02d}", date(year, month_num, 1), date(year, month_num, last_day)


def default_week_key(day: date | None = None) -> str:
    target = day or date.today()
    iso = target.isocalendar()
    return f"{iso.year:04d}-W{iso.week:02d}"


def default_month_key(day: date | None = None) -> str:
    target = day or date.today()
    return f"{target.year:04d}-{target.month:02d}"


def _iter_symbol_trade_history(reports_root: Path) -> Iterable[Dict[str, Any]]:
    symbol_root = operator_summary_artifact_root(reports_root) / "symbols"
    if not symbol_root.exists():
        return []

    def gen() -> Iterable[Dict[str, Any]]:
        seen: set[tuple[str, str]] = set()
        for path in sorted(symbol_root.glob("*/trade_history.json")):
            payload = _read_json(path)
            if not isinstance(payload, list):
                continue
            symbol_hint = path.parent.name.upper()
            for row in payload:
                if not isinstance(row, dict):
                    continue
                symbol = str(row.get("symbol") or symbol_hint).strip().upper()
                trade_id = str(row.get("trade_id") or "").strip()
                key = (symbol, trade_id or f"{path}:{len(seen)}")
                if key in seen:
                    continue
                seen.add(key)
                out = dict(row)
                out["symbol"] = symbol
                yield out

    return gen()


def _top_counter(counter: Counter[str], limit: int = 5) -> List[Dict[str, Any]]:
    return [
        {"name": name, "count": int(count)}
        for name, count in counter.most_common(limit)
        if str(name or "").strip()
    ]


def _symbol_rows(rows: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("symbol") or "").strip().upper()].append(row)

    out: List[Dict[str, Any]] = []
    for symbol, items in grouped.items():
        closed = [
            row
            for row in items
            if str(row.get("last_status") or row.get("status") or "").strip().lower() == "closed"
        ]
        returns = [value for value in (_safe_float(row.get("result_pct")) for row in closed) if value is not None]
        win_count = sum(1 for value in returns if value > 0)
        loss_count = sum(1 for value in returns if value < 0)
        out.append(
            {
                "symbol": symbol,
                "trade_count": len(items),
                "closed_trade_count": len(closed),
                "win_count": win_count,
                "loss_count": loss_count,
                "avg_return_pct": round(sum(returns) / len(returns), 4) if returns else 0.0,
            }
        )
    out.sort(key=lambda row: (int(row.get("trade_count") or 0), abs(float(row.get("avg_return_pct") or 0.0))), reverse=True)
    return out[:limit]


def _trade_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    closed_rows = [
        row
        for row in rows
        if str(row.get("last_status") or row.get("status") or "").strip().lower() == "closed"
    ]
    returns = [value for value in (_safe_float(row.get("result_pct")) for row in closed_rows) if value is not None]
    hold_seconds = [value for value in (_safe_float(row.get("hold_seconds")) for row in closed_rows) if value is not None]
    win_count = sum(1 for value in returns if value > 0)
    loss_count = sum(1 for value in returns if value < 0)
    flat_count = sum(1 for value in returns if value == 0)
    return {
        "trade_count": len(rows),
        "closed_trade_count": len(closed_rows),
        "return_sample_count": len(returns),
        "win_count": win_count,
        "loss_count": loss_count,
        "flat_count": flat_count,
        "win_rate": round(win_count / len(returns), 4) if returns else 0.0,
        "avg_return_pct": round(sum(returns) / len(returns), 4) if returns else 0.0,
        "avg_hold_seconds": round(sum(hold_seconds) / len(hold_seconds), 2) if hold_seconds else 0.0,
    }


def _pattern_counters(rows: List[Dict[str, Any]]) -> Dict[str, Counter[str]]:
    return {
        "entry_reasons": Counter(str(row.get("entry_reason") or "").strip() for row in rows if str(row.get("entry_reason") or "").strip()),
        "exit_reasons": Counter(str(row.get("exit_reason") or "").strip() for row in rows if str(row.get("exit_reason") or "").strip()),
        "entry_pattern_types": Counter(str(row.get("entry_pattern_type") or "").strip() for row in rows if str(row.get("entry_pattern_type") or "").strip()),
        "exit_pattern_types": Counter(str(row.get("exit_pattern_type") or "").strip() for row in rows if str(row.get("exit_pattern_type") or "").strip()),
        "playbooks": Counter(str(row.get("playbook") or "").strip() for row in rows if str(row.get("playbook") or "").strip()),
    }


def _pattern_payload(counters: Dict[str, Counter[str]]) -> Dict[str, Any]:
    return {
        "top_entry_reasons": _top_counter(counters.get("entry_reasons") or Counter()),
        "top_exit_reasons": _top_counter(counters.get("exit_reasons") or Counter()),
        "top_entry_pattern_types": _top_counter(counters.get("entry_pattern_types") or Counter()),
        "top_exit_pattern_types": _top_counter(counters.get("exit_pattern_types") or Counter()),
        "top_playbooks": _top_counter(counters.get("playbooks") or Counter()),
    }


def _operator_readout(
    *,
    trade_count: int,
    avg_return_pct: float,
    win_rate: float,
    exit_counts: Counter[str],
    entry_counts: Counter[str],
) -> Dict[str, Any]:
    positives: List[str] = []
    issues: List[str] = []
    actions: List[str] = []

    if trade_count > 0:
        positives.append("기간 내 체결/청산 기록이 운영 요약으로 연결됐습니다.")
    if entry_counts:
        positives.append("진입 패턴과 선택 사유가 집계 가능할 만큼 누적됐습니다.")
    if avg_return_pct < 0:
        issues.append("완료 거래 기준 평균 수익률이 음수입니다.")
    if win_rate < 0.2 and trade_count > 0:
        issues.append("승률이 낮아 현재 진입-청산 조합의 기대값 점검이 필요합니다.")
    if any("peak_drawdown" in name for name, _ in exit_counts.most_common(3)):
        issues.append("peak_drawdown 청산이 상위 반복 패턴입니다.")
        actions.append("peak_drawdown 발동 조건과 보유 유지 조건을 함께 재검토합니다.")
    if any("breakout" in name for name, _ in entry_counts.most_common(3)):
        actions.append("breakout 진입 후 유지 실패가 반복되는지 종목별로 분리해 봅니다.")
    if not actions:
        actions.append("기간 내 주요 손익 기여 종목과 exit 사유를 우선 검수합니다.")

    root_cause = "후보 포착 자체보다 진입 이후 보유/청산 밸런스가 성과를 제한하는 구조로 보입니다."
    if avg_return_pct >= 0:
        root_cause = "성과는 방어됐으나 반복 패턴이 유지되는지 다음 기간까지 확인이 필요합니다."

    return {
        "good_points": positives or ["집계 가능한 거래 표본이 아직 부족합니다."],
        "issues": issues or ["치명적인 반복 손실 패턴은 아직 집계되지 않았습니다."],
        "root_cause": root_cause,
        "recommended_actions": actions,
    }


def build_operator_period_summary(
    *,
    reports_root: Path,
    period_type: str,
    period_key: str,
) -> Dict[str, Any]:
    normalized_type = str(period_type or "").strip().lower()
    if normalized_type == "weekly":
        normalized_key, start, end = _period_from_week(period_key)
    elif normalized_type == "monthly":
        normalized_key, start, end = _period_from_month(period_key)
    else:
        raise ValueError(f"unsupported period_type: {period_type!r}")

    rows: List[Dict[str, Any]] = []
    for row in _iter_symbol_trade_history(reports_root):
        row_day = _parse_day(row.get("date"))
        if row_day is None or row_day < start or row_day > end:
            continue
        rows.append(row)

    metrics = _trade_metrics(rows)
    counters = _pattern_counters(rows)

    summary = {
        "schema_version": "operator_period_summary.v1",
        "period_type": normalized_type,
        "period_key": normalized_key,
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "generated_at": _utc_now_iso(),
        "source": {
            "type": "operator_symbol_trade_history",
            "root": str(operator_summary_artifact_root(reports_root) / "symbols"),
        },
        "metrics": {
            **metrics,
        },
        "patterns": _pattern_payload(counters),
        "symbol_summary": _symbol_rows(rows),
    }
    summary["operator_readout"] = _operator_readout(
        trade_count=len(rows),
        avg_return_pct=float(metrics.get("avg_return_pct") or 0.0),
        win_rate=float(metrics.get("win_rate") or 0.0),
        exit_counts=counters.get("exit_reasons") or Counter(),
        entry_counts=counters.get("entry_reasons") or Counter(),
    )
    return summary


def build_operator_daily_summary_artifact_payload(
    *,
    reports_root: Path,
    day: str,
    daily_report_payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized_day = str(day or "").strip()
    rows = [
        row
        for row in _iter_symbol_trade_history(reports_root)
        if str(row.get("date") or "").strip() == normalized_day
    ]
    metrics = _trade_metrics(rows)
    counters = _pattern_counters(rows)
    source_payload = dict(daily_report_payload or {})
    trade_index = source_payload.get("trade_index") if isinstance(source_payload.get("trade_index"), list) else []
    if metrics["trade_count"] == 0 and trade_index:
        metrics["trade_count"] = len(trade_index)

    summary = {
        "schema_version": "operator_daily_summary.v1",
        "period_type": "daily",
        "day": normalized_day,
        "generated_at": _utc_now_iso(),
        "source": {
            "type": "daily_report_plus_operator_symbol_trade_history",
            "daily_report_json": str(daily_artifact_paths(reports_root, normalized_day)["daily_report_json"]),
            "symbol_history_root": str(operator_summary_artifact_root(reports_root) / "symbols"),
        },
        "runtime_activity": {
            "events": _safe_int(source_payload.get("events")),
            "approvals": _safe_int(source_payload.get("approvals")),
            "blocks": _safe_int(source_payload.get("blocks")),
            "symbols_observed_count": len(list(source_payload.get("symbols_observed") or [])),
            "generated_symbol_report_count": _safe_int(source_payload.get("generated_symbol_report_count")),
        },
        "metrics": metrics,
        "patterns": _pattern_payload(counters),
        "symbol_summary": _symbol_rows(rows),
    }
    summary["operator_readout"] = _operator_readout(
        trade_count=int(metrics.get("trade_count") or 0),
        avg_return_pct=float(metrics.get("avg_return_pct") or 0.0),
        win_rate=float(metrics.get("win_rate") or 0.0),
        exit_counts=counters.get("exit_reasons") or Counter(),
        entry_counts=counters.get("entry_reasons") or Counter(),
    )
    return summary


def build_operator_symbol_summary_artifact_payload(
    *,
    reports_root: Path,
    symbol: str,
    symbol_trade_report_payload: Dict[str, Any] | None = None,
    symbol_memory_payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized_symbol = str(symbol or "").strip().upper()
    payload = dict(symbol_trade_report_payload or {})
    history = payload.get("history_index") if isinstance(payload.get("history_index"), list) else []
    rows = [dict(row, symbol=normalized_symbol) for row in history if isinstance(row, dict)]
    metrics = _trade_metrics(rows)
    counters = _pattern_counters(rows)
    pattern_insights = payload.get("pattern_insights") if isinstance(payload.get("pattern_insights"), dict) else {}
    memory = dict(symbol_memory_payload or {})

    summary = {
        "schema_version": "operator_symbol_summary.v1",
        "period_type": "symbol",
        "symbol": normalized_symbol,
        "generated_at": _utc_now_iso(),
        "source": {
            "type": "symbol_trade_report",
            "symbol_trade_report_json": str(symbol_artifact_paths(reports_root, normalized_symbol)["symbol_trade_report_json"]),
            "symbol_memory_json": str(symbol_artifact_paths(reports_root, normalized_symbol)["symbol_memory_json"]),
        },
        "metrics": metrics,
        "patterns": _pattern_payload(counters),
        "symbol_memory": {
            "available": bool(memory),
            "trade_stats": dict(memory.get("trade_stats") or {}) if isinstance(memory.get("trade_stats"), dict) else {},
            "bias_recommendation": dict(memory.get("bias_recommendation") or {}) if isinstance(memory.get("bias_recommendation"), dict) else {},
            "latest_snapshot": dict(memory.get("latest_snapshot") or {}) if isinstance(memory.get("latest_snapshot"), dict) else {},
        },
        "risk_notes": list(pattern_insights.get("risk_notes") or []),
    }
    summary["operator_readout"] = _operator_readout(
        trade_count=int(metrics.get("trade_count") or 0),
        avg_return_pct=float(metrics.get("avg_return_pct") or 0.0),
        win_rate=float(metrics.get("win_rate") or 0.0),
        exit_counts=counters.get("exit_reasons") or Counter(),
        entry_counts=counters.get("entry_reasons") or Counter(),
    )
    return summary


def render_operator_period_summary_markdown(payload: Dict[str, Any]) -> str:
    period_type = str(payload.get("period_type") or "").strip().lower()
    period_label = "Weekly" if period_type == "weekly" else "Monthly"
    period_key = str(payload.get("period_key") or "")
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    patterns = payload.get("patterns") if isinstance(payload.get("patterns"), dict) else {}
    readout = payload.get("operator_readout") if isinstance(payload.get("operator_readout"), dict) else {}
    date_range = payload.get("date_range") if isinstance(payload.get("date_range"), dict) else {}
    symbols = payload.get("symbol_summary") if isinstance(payload.get("symbol_summary"), list) else []

    lines = [
        f"# {period_label} Summary ({period_key})",
        "",
        "---",
        "",
        "## 운영 요약",
        "",
        f"- 기간: {date_range.get('start') or '-'} ~ {date_range.get('end') or '-'}",
        f"- 총 거래: {_safe_int(metrics.get('trade_count'))}건",
        f"- 완료 거래: {_safe_int(metrics.get('closed_trade_count'))}건",
        f"- 성과: **승률 {float(metrics.get('win_rate') or 0.0) * 100:.2f}% / 평균 {float(metrics.get('avg_return_pct') or 0.0):.2f}%**",
        "",
        "### 잘된 점",
    ]
    for item in list(readout.get("good_points") or []):
        lines.append(f"- {item}")
    lines += ["", "### 문제점"]
    for idx, item in enumerate(list(readout.get("issues") or []), start=1):
        lines.append(f"{idx}. {item}")
    lines += [
        "",
        "### 원인 해석",
        f"**{readout.get('root_cause') or '-'}**",
        "",
        "### 권고 액션",
    ]
    for idx, item in enumerate(list(readout.get("recommended_actions") or []), start=1):
        lines.append(f"{idx}. {item}")

    lines += ["", "---", "", "## 반복 패턴", ""]
    for label, key in (
        ("주요 진입 사유", "top_entry_reasons"),
        ("주요 청산 사유", "top_exit_reasons"),
        ("진입 패턴", "top_entry_pattern_types"),
        ("청산 패턴", "top_exit_pattern_types"),
        ("플레이북", "top_playbooks"),
    ):
        rows = patterns.get(key) if isinstance(patterns.get(key), list) else []
        text = ", ".join(f"{row.get('name')} ({row.get('count')})" for row in rows[:3] if isinstance(row, dict))
        lines.append(f"- {label}: {text or '없음'}")

    lines += ["", "---", "", "## 주요 종목", ""]
    if not symbols:
        lines.append("- 기간 내 종목별 요약이 없습니다.")
    for row in symbols[:8]:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"- {row.get('symbol')}: 거래 {row.get('trade_count')}건 / 완료 {row.get('closed_trade_count')}건 / "
            f"승패 {row.get('win_count')}/{row.get('loss_count')} / 평균 {float(row.get('avg_return_pct') or 0.0):.2f}%"
        )

    lines += [
        "",
        "---",
        "",
        "## 상세 분석",
        "",
        "> 기간별 운영 요약은 reports/operator_summary/symbols/*/trade_history.json 집계를 기준으로 생성됩니다.",
        "",
    ]
    return "\n".join(lines)


def render_operator_daily_summary_markdown(payload: Dict[str, Any]) -> str:
    day = str(payload.get("day") or "")
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    runtime = payload.get("runtime_activity") if isinstance(payload.get("runtime_activity"), dict) else {}
    patterns = payload.get("patterns") if isinstance(payload.get("patterns"), dict) else {}
    readout = payload.get("operator_readout") if isinstance(payload.get("operator_readout"), dict) else {}
    symbols = payload.get("symbol_summary") if isinstance(payload.get("symbol_summary"), list) else []

    lines = [
        f"# Daily Summary ({day})",
        "",
        "---",
        "",
        "## 운영 요약",
        "",
        f"- 총 거래: {_safe_int(metrics.get('trade_count'))}건",
        f"- 완료 거래: {_safe_int(metrics.get('closed_trade_count'))}건",
        f"- 성과: **승률 {float(metrics.get('win_rate') or 0.0) * 100:.2f}% / 평균 {float(metrics.get('avg_return_pct') or 0.0):.2f}%**",
        f"- 런타임 이벤트: {runtime.get('events') or 0}건",
        f"- 승인/차단: {runtime.get('approvals') or 0} / {runtime.get('blocks') or 0}",
        "",
        "### 잘된 점",
    ]
    for item in list(readout.get("good_points") or []):
        lines.append(f"- {item}")
    lines += ["", "### 문제점"]
    for idx, item in enumerate(list(readout.get("issues") or []), start=1):
        lines.append(f"{idx}. {item}")
    lines += [
        "",
        "### 원인 해석",
        f"**{readout.get('root_cause') or '-'}**",
        "",
        "### 권고 액션",
    ]
    for idx, item in enumerate(list(readout.get("recommended_actions") or []), start=1):
        lines.append(f"{idx}. {item}")

    lines += ["", "---", "", "## 핵심 패턴", ""]
    for label, key in (
        ("주요 진입 사유", "top_entry_reasons"),
        ("주요 청산 사유", "top_exit_reasons"),
        ("진입 패턴", "top_entry_pattern_types"),
        ("청산 패턴", "top_exit_pattern_types"),
    ):
        rows = patterns.get(key) if isinstance(patterns.get(key), list) else []
        text = ", ".join(f"{row.get('name')} ({row.get('count')})" for row in rows[:3] if isinstance(row, dict))
        lines.append(f"- {label}: {text or '없음'}")

    lines += ["", "---", "", "## 종목별 요약", ""]
    if not symbols:
        lines.append("- 당일 종목별 요약이 없습니다.")
    for row in symbols[:8]:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"- {row.get('symbol')}: 거래 {row.get('trade_count')}건 / 완료 {row.get('closed_trade_count')}건 / "
            f"승패 {row.get('win_count')}/{row.get('loss_count')} / 평균 {float(row.get('avg_return_pct') or 0.0):.2f}%"
        )

    lines += [
        "",
        "---",
        "",
        "## 상세 분석",
        "",
        "> 세부 거래 및 로그 기반 분석은 같은 일자의 daily_report.md와 개별 ai_trade_report.md를 참조합니다.",
        "",
    ]
    return "\n".join(lines)


def render_operator_symbol_summary_markdown(payload: Dict[str, Any]) -> str:
    symbol = str(payload.get("symbol") or "")
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    patterns = payload.get("patterns") if isinstance(payload.get("patterns"), dict) else {}
    readout = payload.get("operator_readout") if isinstance(payload.get("operator_readout"), dict) else {}
    memory = payload.get("symbol_memory") if isinstance(payload.get("symbol_memory"), dict) else {}
    risk_notes = list(payload.get("risk_notes") or [])

    lines = [
        f"# Symbol Summary ({symbol})",
        "",
        "---",
        "",
        "## 운영 요약",
        "",
        f"- 총 거래: {_safe_int(metrics.get('trade_count'))}건",
        f"- 완료 거래: {_safe_int(metrics.get('closed_trade_count'))}건",
        f"- 성과: **승률 {float(metrics.get('win_rate') or 0.0) * 100:.2f}% / 평균 {float(metrics.get('avg_return_pct') or 0.0):.2f}%**",
        "",
        "### 잘된 점",
    ]
    for item in list(readout.get("good_points") or []):
        lines.append(f"- {item}")
    lines += ["", "### 문제점"]
    for idx, item in enumerate(list(readout.get("issues") or []), start=1):
        lines.append(f"{idx}. {item}")
    lines += [
        "",
        "### 원인 해석",
        f"**{readout.get('root_cause') or '-'}**",
        "",
        "### 권고 액션",
    ]
    for idx, item in enumerate(list(readout.get("recommended_actions") or []), start=1):
        lines.append(f"{idx}. {item}")

    lines += ["", "---", "", "## 패턴 분석", ""]
    for label, key in (
        ("주요 진입 사유", "top_entry_reasons"),
        ("주요 청산 사유", "top_exit_reasons"),
        ("진입 패턴", "top_entry_pattern_types"),
        ("청산 패턴", "top_exit_pattern_types"),
        ("플레이북", "top_playbooks"),
    ):
        rows = patterns.get(key) if isinstance(patterns.get(key), list) else []
        text = ", ".join(f"{row.get('name')} ({row.get('count')})" for row in rows[:3] if isinstance(row, dict))
        lines.append(f"- {label}: {text or '없음'}")

    bias = memory.get("bias_recommendation") if isinstance(memory.get("bias_recommendation"), dict) else {}
    if bias or risk_notes:
        lines += ["", "---", "", "## 거래 특징", ""]
        if bias:
            lines.append(f"- 메모리 bias: {json.dumps(bias, ensure_ascii=False)}")
        for note in risk_notes:
            lines.append(f"- 리스크 메모: {note}")

    lines += [
        "",
        "---",
        "",
        "## 상세 분석",
        "",
        "> 개별 ai_trade_report.md와 symbol_trade_report.md를 참조합니다.",
        "",
    ]
    return "\n".join(lines)


def generate_operator_period_summary(
    *,
    reports_root: Path,
    period_type: str,
    period_key: str,
) -> Tuple[Path, Path, Dict[str, Any]]:
    payload = build_operator_period_summary(
        reports_root=reports_root,
        period_type=period_type,
        period_key=period_key,
    )
    if payload["period_type"] == "weekly":
        paths = weekly_artifact_paths(reports_root, payload["period_key"])
        json_path = paths["weekly_summary_json"]
        md_path = paths["weekly_summary_md"]
    else:
        paths = monthly_artifact_paths(reports_root, payload["period_key"])
        json_path = paths["monthly_summary_json"]
        md_path = paths["monthly_summary_md"]

    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_operator_period_summary_markdown(payload), encoding="utf-8")
    return md_path, json_path, payload


def generate_operator_daily_summary_artifact(
    *,
    reports_root: Path,
    day: str,
    daily_report_payload: Dict[str, Any] | None = None,
) -> Tuple[Path, Path, Dict[str, Any]]:
    payload = build_operator_daily_summary_artifact_payload(
        reports_root=reports_root,
        day=day,
        daily_report_payload=daily_report_payload,
    )
    paths = daily_artifact_paths(reports_root, payload["day"])
    json_path = paths["daily_summary_json"]
    md_path = paths["daily_summary_md"]
    md_path.parent.mkdir(parents=True, exist_ok=True)
    payload["performance_memory_sync"] = sync_strategy_memory_artifacts(
        reports_root=reports_root,
        day=payload["day"],
        source="operator_daily_summary",
    )
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_operator_daily_summary_markdown(payload), encoding="utf-8")
    return md_path, json_path, payload


def generate_operator_symbol_summary_artifact(
    *,
    reports_root: Path,
    symbol: str,
    symbol_trade_report_payload: Dict[str, Any] | None = None,
    symbol_memory_payload: Dict[str, Any] | None = None,
) -> Tuple[Path, Path, Dict[str, Any]]:
    payload = build_operator_symbol_summary_artifact_payload(
        reports_root=reports_root,
        symbol=symbol,
        symbol_trade_report_payload=symbol_trade_report_payload,
        symbol_memory_payload=symbol_memory_payload,
    )
    paths = symbol_artifact_paths(reports_root, payload["symbol"])
    json_path = paths["symbol_summary_json"]
    md_path = paths["symbol_summary_md"]
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_operator_symbol_summary_markdown(payload), encoding="utf-8")
    return md_path, json_path, payload
