from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Mapping, Sequence


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


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _safe_bool(value: Any) -> bool:
    return bool(value) if isinstance(value, bool) else False


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _extract_note_reason(note: str) -> str:
    text = str(note or "").strip()
    if not text:
        return ""
    if ":" not in text:
        return text
    return text.rsplit(":", 1)[-1].strip()


def _status_label(status: str) -> str:
    text = str(status or "").strip().lower()
    if text == "good":
        return "healthy"
    if text == "watch":
        return "watch"
    if text == "degraded":
        return "degraded"
    return "unknown"


def build_policy_surface_quality_summary(runs: Sequence[Mapping[str, Any]] | None) -> Dict[str, Any]:
    rows = [dict(row) for row in list(runs or []) if isinstance(row, Mapping)]
    run_count = len(rows)
    if run_count <= 0:
        return {
            "schema_version": "policy_surface_quality_summary.v1",
            "run_count": 0,
            "schema_available_rate": 0.0,
            "normalized_policy_rate": 0.0,
            "invalid_spec_rate": 0.0,
            "total_invalid_specs": 0,
            "top_invalid_features": [],
            "top_invalid_states": [],
            "validation_notes_counts": {},
            "invalid_specs_by_selected_source": {},
            "validation_notes_by_interpretation_basis": {},
            "notes": ["no_runs_available"],
        }

    schema_available_runs = 0
    normalized_policy_runs = 0
    total_invalid_specs = 0
    total_normalized_specs = 0
    invalid_feature_counts: Counter[str] = Counter()
    invalid_state_counts: Counter[str] = Counter()
    validation_reason_counts: Counter[str] = Counter()
    invalid_specs_by_selected_source: Counter[str] = Counter()
    validation_notes_by_interpretation_basis: Counter[str] = Counter()

    for row in rows:
        if _safe_bool(row.get("policy_schema_available")):
            schema_available_runs += 1

        normalized_count = _safe_int(row.get("normalized_policy_spec_count"))
        invalid_count = _safe_int(row.get("invalid_policy_spec_count"))
        total_normalized_specs += normalized_count
        total_invalid_specs += invalid_count
        if normalized_count > 0:
            normalized_policy_runs += 1

        selected_source = str(row.get("selected_source") or "missing").strip() or "missing"
        interpretation_basis = str(row.get("interpretation_basis") or "missing").strip() or "missing"

        if invalid_count > 0:
            invalid_specs_by_selected_source[selected_source] += invalid_count

        for note in _safe_list_of_str(row.get("spec_validation_notes"), limit=128):
            reason = _extract_note_reason(note)
            if reason:
                validation_reason_counts[reason] += 1
                validation_notes_by_interpretation_basis[interpretation_basis] += 1

        for spec in list(row.get("invalid_policy_specs") or []):
            if not isinstance(spec, Mapping):
                continue
            feature_name = str(spec.get("feature_name") or "").strip()
            expected_state = str(spec.get("expected_state") or "").strip()
            note_reasons = _safe_list_of_str(spec.get("validation_notes"), limit=8)
            if feature_name:
                invalid_feature_counts[feature_name] += 1
            if expected_state:
                invalid_state_counts[expected_state] += 1
            elif "invalid_state" in note_reasons:
                invalid_state_counts["missing_or_invalid_state"] += 1

    total_specs = total_normalized_specs + total_invalid_specs
    notes: List[str] = []
    if total_invalid_specs <= 0:
        notes.append("no_invalid_policy_specs_observed")
    if schema_available_runs <= 0:
        notes.append("no_policy_schema_available_runs")
    if normalized_policy_runs <= 0:
        notes.append("no_normalized_policy_specs_observed")

    return {
        "schema_version": "policy_surface_quality_summary.v1",
        "run_count": run_count,
        "schema_available_rate": _rate(schema_available_runs, run_count),
        "normalized_policy_rate": _rate(normalized_policy_runs, run_count),
        "invalid_spec_rate": _rate(total_invalid_specs, total_specs),
        "total_invalid_specs": total_invalid_specs,
        "top_invalid_features": [name for name, _ in invalid_feature_counts.most_common(5)],
        "top_invalid_states": [name for name, _ in invalid_state_counts.most_common(5)],
        "validation_notes_counts": dict(validation_reason_counts),
        "invalid_specs_by_selected_source": dict(invalid_specs_by_selected_source),
        "validation_notes_by_interpretation_basis": dict(validation_notes_by_interpretation_basis),
        "notes": notes,
    }


def build_policy_surface_quality_executive_summary(summary: Mapping[str, Any] | None) -> Dict[str, Any]:
    payload = dict(summary or {}) if isinstance(summary, Mapping) else {}
    run_count = _safe_int(payload.get("run_count"))
    schema_available_rate = _safe_float(payload.get("schema_available_rate"))
    normalized_policy_rate = _safe_float(payload.get("normalized_policy_rate"))
    invalid_spec_rate = _safe_float(payload.get("invalid_spec_rate"))
    total_invalid_specs = _safe_int(payload.get("total_invalid_specs"))
    top_invalid_features = _safe_list_of_str(payload.get("top_invalid_features"), limit=3)
    invalid_specs_by_selected_source = (
        payload.get("invalid_specs_by_selected_source")
        if isinstance(payload.get("invalid_specs_by_selected_source"), Mapping)
        else {}
    )

    dominant_invalid_source = ""
    dominant_invalid_count = 0
    for source, raw_count in invalid_specs_by_selected_source.items():
        count = _safe_int(raw_count)
        if count > dominant_invalid_count:
            dominant_invalid_count = count
            dominant_invalid_source = str(source or "").strip()

    notes: List[str] = []
    if run_count <= 0:
        status = "unknown"
        notes.append("no_runs_available")
        headline = "Policy surface unknown: no runs available"
    else:
        if schema_available_rate >= 0.70 and invalid_spec_rate <= 0.02:
            status = "good"
        elif invalid_spec_rate >= 0.10 or schema_available_rate < 0.25:
            status = "degraded"
        else:
            status = "watch"

        if schema_available_rate < 0.50:
            notes.append("low_schema_coverage")
        if normalized_policy_rate < 0.50:
            notes.append("low_normalized_policy_coverage")
        if total_invalid_specs > 0:
            notes.append("invalid_specs_present")
        if dominant_invalid_source and total_invalid_specs > 0 and dominant_invalid_count >= max(1, int(total_invalid_specs * 0.6)):
            notes.append(f"invalid_specs_concentrated_in:{dominant_invalid_source}")

        if status == "degraded" and dominant_invalid_source and total_invalid_specs > 0:
            headline = f"Policy surface degraded: invalid spec concentrated in {dominant_invalid_source}"
        else:
            headline = (
                f"Policy surface {_status_label(status)}: "
                f"schema {schema_available_rate:.2f}, invalid spec {invalid_spec_rate:.2f}"
            )

    return {
        "schema_version": "policy_surface_quality_executive_summary.v1",
        "status": status,
        "run_count": run_count,
        "schema_available_rate": round(schema_available_rate, 4),
        "normalized_policy_rate": round(normalized_policy_rate, 4),
        "invalid_spec_rate": round(invalid_spec_rate, 4),
        "top_invalid_features": top_invalid_features,
        "headline": headline,
        "notes": notes,
    }


def build_policy_surface_quality_executive_line(summary: Mapping[str, Any] | None) -> str:
    executive = build_policy_surface_quality_executive_summary(summary)
    return str(executive.get("headline") or "").strip()
