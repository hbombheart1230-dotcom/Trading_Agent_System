from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Mapping, Sequence


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _safe_list_of_str(value: Any, *, limit: int = 64) -> List[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, (list, tuple, set)):
        return []
    out: List[str] = []
    for item in value:
        text = str(item or "").strip()
        if not text or text in out:
            continue
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _feature_name_from_spec(spec: Any) -> str:
    text = str(spec or "").strip()
    if not text:
        return ""
    if "=" in text:
        return text.split("=", 1)[0].strip()
    return text


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _build_applied_example(row: Mapping[str, Any], hint: Mapping[str, Any]) -> Dict[str, Any]:
    legacy_reason = _safe_str(row.get("legacy_entry_reason"))
    final_reason = _safe_str(row.get("reason"))
    transition = f"{legacy_reason or '-'} -> {final_reason or '-'}"
    return {
        "run_id": _safe_str(row.get("run_id")),
        "symbol": _safe_str(row.get("symbol")),
        "entry_style": _safe_str(hint.get("entry_style") or row.get("entry_style")) or "unknown",
        "mode": _safe_str(hint.get("mode")) or "none",
        "legacy_decision": _safe_str(row.get("legacy_entry_decision")).upper() or "UNKNOWN",
        "legacy_reason": legacy_reason,
        "final_decision": _safe_str(row.get("final_decision")).upper() or "UNKNOWN",
        "final_reason": final_reason,
        "reason_transition": transition,
        "blocking_features": _safe_list_of_str(hint.get("blocking_features"), limit=8),
        "matched_features": _safe_list_of_str(hint.get("matched_features"), limit=8),
    }


def build_chart_structure_decision_hint_summary(runs: Sequence[Mapping[str, Any]] | None) -> Dict[str, Any]:
    rows = [dict(row) for row in list(runs or []) if isinstance(row, Mapping)]
    run_count = len(rows)
    if run_count <= 0:
        return {
            "schema_version": "chart_structure_decision_hint_summary.v1",
            "run_count": 0,
            "available_run_count": 0,
            "applied_count": 0,
            "applied_rate": 0.0,
            "mode_counts": {},
            "blocking_feature_counts": {},
            "top_blocking_features": [],
            "applied_run_ids": [],
            "reason_counts_when_applied": {},
            "entry_style_counts_when_applied": {},
            "decision_counts_when_applied": {},
            "applied_examples": [],
            "notes": ["no_runs_available"],
        }

    available_run_count = 0
    applied_count = 0
    mode_counts: Counter[str] = Counter()
    blocking_feature_counts: Counter[str] = Counter()
    reason_counts_when_applied: Counter[str] = Counter()
    entry_style_counts_when_applied: Counter[str] = Counter()
    decision_counts_when_applied: Counter[str] = Counter()
    applied_run_ids: List[str] = []
    applied_examples: List[Dict[str, Any]] = []
    applied_non_wait_count = 0
    applied_unexpected_reason_count = 0
    allowed_reasons = {
        "breakout_continuation_structure_guard_blocked",
        "pullback_reversal_structure_guard_blocked",
    }

    for row in rows:
        hint = row.get("chart_structure_decision_hint") if isinstance(row.get("chart_structure_decision_hint"), Mapping) else {}
        if not hint:
            continue
        if not bool(hint.get("available")):
            continue
        available_run_count += 1
        mode = str(hint.get("mode") or "none").strip() or "none"
        mode_counts[mode] += 1

        if not bool(hint.get("applied")):
            continue

        applied_count += 1
        run_id = str(row.get("run_id") or "").strip()
        if run_id:
            applied_run_ids.append(run_id)
        if len(applied_examples) < 3:
            applied_examples.append(_build_applied_example(row, hint))

        final_decision = str(row.get("final_decision") or "").strip().upper() or "UNKNOWN"
        final_reason = str(row.get("reason") or "").strip()
        entry_style = str(hint.get("entry_style") or row.get("entry_style") or "").strip() or "unknown"

        decision_counts_when_applied[final_decision] += 1
        if final_reason:
            reason_counts_when_applied[final_reason] += 1
        entry_style_counts_when_applied[entry_style] += 1

        if final_decision not in {"WAIT", "NOOP", "NO_TRADE"}:
            applied_non_wait_count += 1
        if final_reason not in allowed_reasons:
            applied_unexpected_reason_count += 1

        for spec in _safe_list_of_str(hint.get("blocking_features"), limit=16):
            feature_name = _feature_name_from_spec(spec)
            if feature_name:
                blocking_feature_counts[feature_name] += 1

    notes: List[str] = []
    if available_run_count <= 0:
        notes.append("no_chart_structure_hint_runs")
    if available_run_count > 0 and applied_count <= 0:
        notes.append("no_chart_structure_guard_applications")
    if applied_count > 0 and not blocking_feature_counts:
        notes.append("blocking_features_not_recorded_on_applied_runs")
    if applied_non_wait_count > 0:
        notes.append("applied_without_wait_decision_detected")
    if applied_unexpected_reason_count > 0:
        notes.append("applied_with_unexpected_reason_detected")

    return {
        "schema_version": "chart_structure_decision_hint_summary.v1",
        "run_count": run_count,
        "available_run_count": available_run_count,
        "applied_count": applied_count,
        "applied_rate": _rate(applied_count, available_run_count),
        "mode_counts": dict(mode_counts),
        "blocking_feature_counts": dict(blocking_feature_counts),
        "top_blocking_features": [name for name, _ in blocking_feature_counts.most_common(5)],
        "applied_run_ids": applied_run_ids[:20],
        "reason_counts_when_applied": dict(reason_counts_when_applied),
        "entry_style_counts_when_applied": dict(entry_style_counts_when_applied),
        "decision_counts_when_applied": dict(decision_counts_when_applied),
        "applied_examples": applied_examples,
        "notes": notes,
    }


def build_chart_structure_decision_hint_executive_summary(summary: Mapping[str, Any] | None) -> Dict[str, Any]:
    payload = dict(summary or {}) if isinstance(summary, Mapping) else {}
    run_count = _safe_int(payload.get("run_count"))
    available_run_count = _safe_int(payload.get("available_run_count"))
    applied_count = _safe_int(payload.get("applied_count"))
    applied_rate = _safe_float(payload.get("applied_rate"))
    top_blocking_features = _safe_list_of_str(payload.get("top_blocking_features"), limit=3)
    notes = _safe_list_of_str(payload.get("notes"), limit=8)

    decision_counts_when_applied = (
        payload.get("decision_counts_when_applied")
        if isinstance(payload.get("decision_counts_when_applied"), Mapping)
        else {}
    )
    non_wait_when_applied = sum(
        _safe_int(count)
        for decision, count in decision_counts_when_applied.items()
        if str(decision or "").strip().upper() not in {"WAIT", "NOOP", "NO_TRADE"}
    )

    if run_count <= 0:
        status = "unknown"
        headline = "Chart structure guard unknown: no runs available"
    elif available_run_count <= 0:
        status = "inactive"
        headline = "Chart structure guard inactive: no eligible breakout continuation runs"
    elif applied_count <= 0:
        status = "inactive"
        headline = f"Chart structure guard inactive: evaluated {available_run_count} runs, applied 0"
    elif non_wait_when_applied > 0:
        status = "watch"
        headline = (
            f"Chart structure guard watch: applied {applied_count} times with "
            f"{non_wait_when_applied} non-WAIT outcomes"
        )
    else:
        status = "active"
        blocker_text = ", ".join(top_blocking_features) if top_blocking_features else "none"
        headline = (
            f"Chart structure guard active: applied {applied_count} times "
            f"(rate {applied_rate:.2f}), top blockers: {blocker_text}"
        )

    return {
        "schema_version": "chart_structure_decision_hint_executive_summary.v1",
        "status": status,
        "run_count": run_count,
        "available_run_count": available_run_count,
        "applied_count": applied_count,
        "applied_rate": round(applied_rate, 4),
        "top_blocking_features": top_blocking_features,
        "headline": headline,
        "notes": notes,
    }


def build_chart_structure_decision_hint_executive_line(summary: Mapping[str, Any] | None) -> str:
    executive = build_chart_structure_decision_hint_executive_summary(summary)
    return str(executive.get("headline") or "").strip()
