from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from libs.reporting.quant_shadow_candidate_evaluation import (
    build_quant_shadow_candidate_evaluation,
    load_quant_shadow_candidate_payloads,
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _rows(value: Any) -> List[Dict[str, Any]]:
    return [dict(row) for row in list(value or []) if isinstance(row, Mapping)]


def _forward_rows(evaluation: Mapping[str, Any]) -> List[Dict[str, Any]]:
    forward = evaluation.get("entry_lane_forward_outcomes")
    if not isinstance(forward, Mapping):
        return []
    return _rows(forward.get("by_primary_lane"))


def _counts_by_name(rows: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in rows:
        name = _text(row.get("name"))
        if name:
            out[name] = _int(row.get("count"))
    return out


def _reason_summary(evaluation: Mapping[str, Any], *, limit: int = 6) -> str:
    parts = []
    for row in _rows(evaluation.get("by_reason"))[:limit]:
        name = _text(row.get("name"))
        if name:
            parts.append(f"{name} {row.get('count') or 0}")
    return ", ".join(parts) if parts else "-"


def _verdict(row: Mapping[str, Any]) -> Dict[str, str]:
    n = _int(row.get("candidate_count"))
    observed = _int(row.get("observed_count"))
    coverage = _float(row.get("coverage"))
    ret5 = _float(row.get("avg_return_5m_pct"))
    ret15 = _float(row.get("avg_return_15m_pct"))
    mfe5 = _float(row.get("avg_mfe_5m_pct"))
    mae5 = _float(row.get("avg_mae_5m_pct"))
    lane = _text(row.get("name"))

    if observed < 10 or coverage < 0.65:
        return {
            "verdict": "DATA_INCOMPLETE",
            "decision": "관찰 유지",
            "rationale": "표본 또는 forward coverage 부족",
        }
    if lane == "vwap_reclaim" and ret5 < 0.0 and ret15 < 0.0:
        return {
            "verdict": "GOOD_BLOCK",
            "decision": "차단 유지",
            "rationale": "VWAP 미회복 차단 후 단기/중기 수익률이 음수",
        }
    if ret5 >= 0.50 or ret15 >= 0.80 or mfe5 >= 1.50:
        risk_note = " 단, MAE가 커서 소액 probe 또는 기준 재검토만 허용." if mae5 <= -1.50 else ""
        return {
            "verdict": "MISSED_OPPORTUNITY",
            "decision": "완화 후보",
            "rationale": f"차단 후보의 forward 상승 여지가 관측됨.{risk_note}".strip(),
        }
    if ret5 <= 0.0 and ret15 <= 0.0:
        return {
            "verdict": "GOOD_BLOCK",
            "decision": "차단 유지",
            "rationale": "차단 후 forward 수익률이 부진",
        }
    return {
        "verdict": "DATA_INCOMPLETE",
        "decision": "혼합 관찰",
        "rationale": "방향성은 있으나 즉시 정책화할 정도로 선명하지 않음",
    }


def build_q8_lane_decision_table(
    *,
    reports_root: Path = Path("reports"),
    day: str,
) -> Dict[str, Any]:
    payloads = load_quant_shadow_candidate_payloads(reports_root=reports_root, days=[str(day)[:10]])
    evaluation = build_quant_shadow_candidate_evaluation(payloads)
    lane_counts = _counts_by_name(_rows(evaluation.get("entry_lane_observation", {}).get("by_primary_lane") if isinstance(evaluation.get("entry_lane_observation"), Mapping) else []))
    rows: List[Dict[str, Any]] = []
    for row in _forward_rows(evaluation):
        verdict = _verdict(row)
        lane = _text(row.get("name"))
        rows.append(
            {
                "lane": lane,
                "candidate_count": _int(row.get("candidate_count")),
                "observed_count": _int(row.get("observed_count")),
                "coverage": round(_float(row.get("coverage")), 4),
                "shadow_count": lane_counts.get(lane, _int(row.get("candidate_count"))),
                "avg_return_3m_pct": row.get("avg_return_3m_pct"),
                "avg_return_5m_pct": row.get("avg_return_5m_pct"),
                "avg_return_15m_pct": row.get("avg_return_15m_pct"),
                "avg_return_30m_pct": row.get("avg_return_30m_pct"),
                "avg_return_60m_pct": row.get("avg_return_60m_pct"),
                "avg_mfe_5m_pct": row.get("avg_mfe_5m_pct"),
                "avg_mae_5m_pct": row.get("avg_mae_5m_pct"),
                **verdict,
            }
        )
    order = {
        "MISSED_OPPORTUNITY": 0,
        "BAD_ENTRY": 1,
        "GOOD_BLOCK": 2,
        "DATA_INCOMPLETE": 3,
    }
    rows.sort(key=lambda item: (order.get(str(item.get("verdict")), 9), -_int(item.get("observed_count"))))
    return {
        "schema_version": "q8_lane_decision_table.v1",
        "day": str(day)[:10],
        "payload_count": _int(evaluation.get("payload_count")),
        "candidate_count": _int(evaluation.get("candidate_count")),
        "evaluated_count": _int(evaluation.get("evaluated_count")),
        "forward_outcome_available_count": _int(evaluation.get("forward_outcome_available_count")),
        "forward_outcome_coverage": round(_float(evaluation.get("forward_outcome_coverage")), 4),
        "would_enter_count": _int(evaluation.get("would_enter_count")),
        "reason_summary": _reason_summary(evaluation),
        "rows": rows,
    }


def _fmt_pct(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return f"{_float(value):.4f}%"


def render_q8_lane_decision_table_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        f"# Q8 Lane Decision Table - {payload.get('day')}",
        "",
        "## Summary",
        "",
        f"- payloads: {payload.get('payload_count')}",
        f"- candidates: {payload.get('candidate_count')}",
        f"- evaluated: {payload.get('evaluated_count')}",
        f"- forward observed: {payload.get('forward_outcome_available_count')} "
        f"({float(payload.get('forward_outcome_coverage') or 0.0):.1%})",
        f"- would-enter: {payload.get('would_enter_count')}",
        f"- top reasons: {payload.get('reason_summary') or '-'}",
        "",
        "## Lane Verdicts",
        "",
        "| Lane | Verdict | Decision | n | obs | +5m | +15m | +30m | MFE5 | MAE5 | Rationale |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in _rows(payload.get("rows")):
        lines.append(
            "| "
            + " | ".join(
                [
                    _text(row.get("lane")) or "-",
                    _text(row.get("verdict")) or "-",
                    _text(row.get("decision")) or "-",
                    str(row.get("candidate_count") or 0),
                    str(row.get("observed_count") or 0),
                    _fmt_pct(row.get("avg_return_5m_pct")),
                    _fmt_pct(row.get("avg_return_15m_pct")),
                    _fmt_pct(row.get("avg_return_30m_pct")),
                    _fmt_pct(row.get("avg_mfe_5m_pct")),
                    _fmt_pct(row.get("avg_mae_5m_pct")),
                    _text(row.get("rationale")) or "-",
                ]
            )
            + " |"
        )
    lines += [
        "",
        "## Operating Interpretation",
        "",
        "- `MISSED_OPPORTUNITY`: 차단 후보가 이후 의미 있게 상승했습니다. 즉시 무조건 진입이 아니라 완화 후보입니다.",
        "- `GOOD_BLOCK`: 차단 후 forward 성과가 부진했습니다. 해당 gate는 유지합니다.",
        "- `DATA_INCOMPLETE`: 표본 또는 coverage가 부족하거나 변동성이 커서 정책 변경 대상이 아닙니다.",
        "",
        "## Current Action",
        "",
        "오늘 장중에는 이 표를 기준으로 추가 행동 패치를 하지 않습니다. 장후 같은 표를 재생성해서 판정이 유지되는지 확인합니다.",
        "",
    ]
    return "\n".join(lines)


def write_q8_lane_decision_table(
    *,
    reports_root: Path = Path("reports"),
    docs_root: Path = Path("docs/tactics"),
    day: str,
) -> Dict[str, Any]:
    payload = build_q8_lane_decision_table(reports_root=reports_root, day=day)
    docs_root.mkdir(parents=True, exist_ok=True)
    md_path = docs_root / f"q8_lane_decision_table_{str(day)[:10]}.md"
    json_dir = reports_root / "dev" / "analysis" / "q8_lane_decision_table"
    json_dir.mkdir(parents=True, exist_ok=True)
    json_path = json_dir / f"q8_lane_decision_table_{str(day)[:10]}.json"
    md_path.write_text(render_q8_lane_decision_table_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {"ok": True, "payload": payload, "md_path": str(md_path), "json_path": str(json_path)}


__all__ = [
    "build_q8_lane_decision_table",
    "render_q8_lane_decision_table_markdown",
    "write_q8_lane_decision_table",
]
