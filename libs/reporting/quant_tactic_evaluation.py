from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Mapping


_REQUIRED_FIELDS = (
    "quant_tactic_id",
    "entry_quant_decision",
    "exit_quant_decision",
    "tactic_suitability_tier",
    "entry_quant_cost_floor_state",
)
_MIN_REVIEW_SAMPLE = 8
_TARGET_PROMOTION_SAMPLE = 20
_FIELD_COVERAGE_FLOOR = 0.90


def _text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"", "-", "none", "null", "unknown", "not_captured"} else text


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _closed_or_realized(row: Mapping[str, Any]) -> bool:
    status = str(row.get("status") or row.get("last_status") or "").strip().lower()
    action = str(row.get("last_action") or row.get("action") or "").strip().upper()
    origin = str(row.get("trade_origin") or "").strip().lower()
    partial = status == "partial" or origin == "recovered_partial"
    return bool(
        row.get("is_closed_trade")
        or row.get("is_realized_nonclosed_exit")
        or (status == "closed" and not partial)
        or (action == "SELL" and partial)
    )


def _evaluation_rows(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return [dict(row) for row in rows if isinstance(row, Mapping) and _closed_or_realized(row)]


def _invalid_sample_reason(row: Mapping[str, Any]) -> str:
    status = _text(row.get("broker_alignment_status")).lower()
    if status and status not in {"ok"}:
        return f"broker_alignment_{status}"
    if _int(row.get("broker_alignment_missing_in_local_total")) > 0:
        return "broker_missing_in_local"
    if _int(row.get("broker_alignment_missing_in_broker_total")) > 0:
        return "broker_missing_in_broker"
    snapshot_status = _text(row.get("broker_account_snapshot_status")).lower()
    if snapshot_status and snapshot_status not in {"ok"}:
        return f"account_snapshot_{snapshot_status}"
    if _int(row.get("broker_alignment_account_snapshot_error_count")) > 0:
        return "account_snapshot_partial_errors"
    return ""


def _valid_evaluation_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if not _invalid_sample_reason(row)]


def _invalid_sample_examples(rows: List[Dict[str, Any]], *, limit: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        reason = _invalid_sample_reason(row)
        if not reason:
            continue
        out.append(
            {
                "trade_id": _text(row.get("trade_id")),
                "symbol": _text(row.get("symbol")),
                "reason": reason,
            }
        )
        if len(out) >= limit:
            break
    return out


def _field_gap_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    count = len(rows)
    out: List[Dict[str, Any]] = []
    for field in _REQUIRED_FIELDS:
        captured = sum(1 for row in rows if _text(row.get(field)))
        coverage = float(captured) / float(count) if count else 0.0
        out.append(
            {
                "field": field,
                "captured_count": captured,
                "missing_count": max(0, count - captured),
                "coverage": coverage,
                "coverage_ok": coverage >= _FIELD_COVERAGE_FLOOR,
            }
        )
    return out


def _mismatch_examples(rows: List[Dict[str, Any]], *, limit: int = 4) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        count = _int(row.get("quant_tactic_mismatch_count"))
        if count <= 0:
            continue
        out.append(
            {
                "trade_id": _text(row.get("trade_id")),
                "symbol": _text(row.get("symbol")),
                "tactic_id": _text(row.get("quant_tactic_id")),
                "mismatch_count": count,
            }
        )
        if len(out) >= limit:
            break
    return out


def build_quant_tactic_evaluation(rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    all_evaluation_rows = _evaluation_rows(rows)
    invalid_examples = _invalid_sample_examples(all_evaluation_rows)
    evaluation_rows = _valid_evaluation_rows(all_evaluation_rows)
    field_gaps = _field_gap_rows(evaluation_rows)
    gap_fields = [row["field"] for row in field_gaps if not bool(row.get("coverage_ok"))]
    mismatch_count = sum(_int(row.get("quant_tactic_mismatch_count")) for row in evaluation_rows)
    mismatch_trade_count = sum(1 for row in evaluation_rows if _int(row.get("quant_tactic_mismatch_count")) > 0)
    exit_drift_count = sum(_int(row.get("quant_exit_tactic_drift_count")) for row in evaluation_rows)
    exit_drift_trade_count = sum(1 for row in evaluation_rows if _int(row.get("quant_exit_tactic_drift_count")) > 0)
    source_counts = Counter(_text(row.get("quant_tactic_id_source")) for row in evaluation_rows)
    source_counts.pop("", None)

    if invalid_examples:
        status = "hold_invalid_truth_samples"
    elif len(evaluation_rows) < _MIN_REVIEW_SAMPLE:
        status = "hold_sample_insufficient"
    elif mismatch_trade_count > 0:
        status = "hold_tactic_id_mismatch"
    elif gap_fields:
        status = "hold_field_gaps"
    elif len(evaluation_rows) < _TARGET_PROMOTION_SAMPLE:
        status = "review_sample_building"
    else:
        status = "promotion_review_ready"

    return {
        "schema_version": "quant_tactic_evaluation.v1",
        "behavior_effect": "evaluation_only",
        "status": status,
        "promotion_action": "hold" if status.startswith("hold_") else "manual_review",
        "closed_or_realized_sample_count": len(evaluation_rows),
        "raw_closed_or_realized_sample_count": len(all_evaluation_rows),
        "invalid_sample_count": max(0, len(all_evaluation_rows) - len(evaluation_rows)),
        "invalid_sample_examples": invalid_examples,
        "review_sample_floor": _MIN_REVIEW_SAMPLE,
        "promotion_sample_target": _TARGET_PROMOTION_SAMPLE,
        "required_fields": list(_REQUIRED_FIELDS),
        "field_coverage_floor": _FIELD_COVERAGE_FLOOR,
        "field_gaps": field_gaps,
        "missing_required_fields": gap_fields,
        "tactic_id_mismatch_trade_count": mismatch_trade_count,
        "tactic_id_mismatch_count": mismatch_count,
        "tactic_id_mismatch_examples": _mismatch_examples(evaluation_rows),
        "exit_tactic_drift_trade_count": exit_drift_trade_count,
        "exit_tactic_drift_count": exit_drift_count,
        "tactic_id_source_counts": dict(source_counts),
    }


def render_quant_tactic_evaluation_lines(payload: Mapping[str, Any] | None) -> List[str]:
    evaluation = dict(payload or {})
    if not evaluation:
        return []
    missing = list(evaluation.get("missing_required_fields") or [])
    missing_text = ", ".join(str(field) for field in missing) if missing else "none"
    source_counts = dict(evaluation.get("tactic_id_source_counts") or {})
    source_text = ", ".join(f"{key}={value}" for key, value in source_counts.items()) if source_counts else "none"
    lines = [
        "- Quant Q8 readiness: "
        f"`{evaluation.get('status') or 'not_available'}` / action `{evaluation.get('promotion_action') or 'hold'}` "
        f"/ sample {evaluation.get('closed_or_realized_sample_count') or 0}"
        f" valid, invalid {evaluation.get('invalid_sample_count') or 0}"
        f"/{evaluation.get('promotion_sample_target') or _TARGET_PROMOTION_SAMPLE}",
        f"- Quant Q8 missing fields: {missing_text}",
        "- Quant Q8 tactic ID integrity: "
        f"mismatch trades {evaluation.get('tactic_id_mismatch_trade_count') or 0}, "
        f"mismatch rows {evaluation.get('tactic_id_mismatch_count') or 0}, "
        f"exit drift trades {evaluation.get('exit_tactic_drift_trade_count') or 0}, "
        f"exit drift rows {evaluation.get('exit_tactic_drift_count') or 0}, "
        f"sources {source_text}",
    ]
    invalid_examples = [row for row in list(evaluation.get("invalid_sample_examples") or []) if isinstance(row, Mapping)]
    if invalid_examples:
        rendered = []
        for row in invalid_examples[:5]:
            trade_id = _text(row.get("trade_id")) or "-"
            symbol = _text(row.get("symbol")) or "-"
            reason = _text(row.get("reason")) or "unknown"
            rendered.append(f"{trade_id}/{symbol}:{reason}")
        lines.append(f"- Quant Q8 invalid samples: {', '.join(rendered)}")
    mismatch_examples = [row for row in list(evaluation.get("tactic_id_mismatch_examples") or []) if isinstance(row, Mapping)]
    if mismatch_examples:
        rendered = []
        for row in mismatch_examples[:4]:
            trade_id = _text(row.get("trade_id")) or "-"
            symbol = _text(row.get("symbol")) or "-"
            count = _int(row.get("mismatch_count"))
            rendered.append(f"{trade_id}/{symbol}:{count}")
        lines.append(f"- Quant Q8 tactic mismatch examples: {', '.join(rendered)}")
    return lines
