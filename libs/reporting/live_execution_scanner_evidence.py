from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from libs.core.symbols import normalize_symbol
from libs.reporting.trade_story_pipeline import safe_int


def _safe_float(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except Exception:
        return default


def normalized_feature_coverage_from_scanner_evidence(
    scanner_evidence: Dict[str, Any],
    *,
    selected_symbol: str,
) -> Dict[str, Any]:
    symbol = normalize_symbol(selected_symbol or "", allow_test_symbols=True)
    if not symbol:
        return {}
    ranking_sources: List[Dict[str, Any]] = []
    for row in list((scanner_evidence or {}).get("candidate_ranking_tables") or []):
        payload = row.get("payload") if isinstance(row, dict) and isinstance(row.get("payload"), dict) else {}
        for ranking_row in list(payload.get("rows") or []):
            if isinstance(ranking_row, dict):
                ranking_sources.append(ranking_row)
    for row in list((scanner_evidence or {}).get("selection_outputs") or []):
        payload = row.get("payload") if isinstance(row, dict) and isinstance(row.get("payload"), dict) else {}
        for ranking_row in list(payload.get("ranking_top_n") or []):
            if isinstance(ranking_row, dict):
                ranking_sources.append(ranking_row)
        selected_candidate = payload.get("selected_candidate") if isinstance(payload.get("selected_candidate"), dict) else {}
        if selected_candidate:
            ranking_sources.append(selected_candidate)

    matched_row: Dict[str, Any] = {}
    for row in ranking_sources:
        row_symbol = normalize_symbol(row.get("symbol") or "", allow_test_symbols=True)
        if row_symbol == symbol:
            matched_row = row
            break
    if not matched_row:
        return {}

    reported = matched_row.get("feature_coverage") if isinstance(matched_row.get("feature_coverage"), dict) else {}
    snapshot = matched_row.get("compact_feature_snapshot") if isinstance(matched_row.get("compact_feature_snapshot"), dict) else {}
    if not snapshot:
        snapshot = matched_row.get("feature_snapshot") if isinstance(matched_row.get("feature_snapshot"), dict) else {}
    if not snapshot and not reported:
        return {}

    keys = [
        "engine_ma20_gap",
        "engine_ma60",
        "engine_ma120",
        "engine_adx14",
        "engine_trend_strength",
        "engine_atr14",
        "engine_volume_spike20",
        "engine_volatility20",
        "engine_vwap_distance",
        "engine_sector_relative_strength",
        "engine_cross_section_rank",
        "engine_regime",
        "engine_signal_score",
    ]
    computed_present_keys = [key for key in keys if snapshot.get(key) is not None]
    computed_missing_keys = [key for key in keys if snapshot.get(key) is None]
    computed_total = len(keys)
    computed_present = len(computed_present_keys)
    present = safe_int(reported.get("present"), computed_present)
    total = safe_int(reported.get("total"), computed_total)
    coverage_ratio = _safe_float(reported.get("coverage_ratio"), float(present) / float(total) if total else 0.0) or 0.0
    quality = str(reported.get("quality") or "").strip().lower()
    if not quality:
        if coverage_ratio >= 0.75:
            quality = "strong"
        elif coverage_ratio >= 0.5:
            quality = "partial"
        else:
            quality = "weak"
    reported_present_keys = [str(x or "") for x in list(reported.get("present_keys") or []) if str(x or "").strip()]
    reported_missing_keys = [str(x or "") for x in list(reported.get("missing_keys") or []) if str(x or "").strip()]
    reported_key_counts_match = bool(
        reported_present_keys
        and len(reported_present_keys) == present
        and len(reported_present_keys) + len(reported_missing_keys) == total
    )
    computed_key_counts_match = computed_present == present and computed_total == total
    present_keys = reported_present_keys if reported_key_counts_match else (computed_present_keys if computed_key_counts_match else [])
    missing_keys = reported_missing_keys if reported_key_counts_match else (computed_missing_keys if computed_key_counts_match else [])
    coverage_source = "feature_coverage_reported" if reported else "snapshot_derived"
    return {
        "present": present,
        "total": total,
        "coverage_ratio": coverage_ratio,
        "quality": quality,
        "present_keys": present_keys,
        "missing_keys": missing_keys,
        "source": coverage_source,
    }


def enrich_scanner_reason_from_evidence(
    scanner_reason_human: Dict[str, Any],
    scanner_evidence: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(scanner_reason_human or {})
    selected_symbol = normalize_symbol(
        out.get("selected_symbol") or "",
        allow_test_symbols=True,
    )
    selection_rows = [
        dict(row)
        for row in list((scanner_evidence or {}).get("candidate_selection_reasons") or [])
        if isinstance(row, dict)
    ]
    payload = (
        selection_rows[0].get("payload")
        if selection_rows and isinstance(selection_rows[0].get("payload"), dict)
        else {}
    )
    if not isinstance(payload, dict):
        payload = {}

    why_selected = [str(x or "") for x in list(payload.get("why_selected") or []) if str(x or "").strip()][:4]
    selection_basis = str(payload.get("final_decision_basis") or "").strip()
    tie_break_rule = str(payload.get("tie_break_rule") or "").strip()
    runner_ups_lost: List[Dict[str, Any]] = []
    for row in list(payload.get("runner_ups_lost") or payload.get("runner_up_reasons") or []):
        if not isinstance(row, dict):
            continue
        symbol = normalize_symbol(row.get("symbol") or "", allow_test_symbols=True)
        why_lost = [
            str(x or "")
            for x in list(row.get("why_lost") or row.get("lost_because") or [])
            if str(x or "").strip()
        ][:4]
        if not symbol and not why_lost:
            continue
        runner_ups_lost.append(
            {
                "symbol": symbol,
                "why_lost": why_lost,
                "summary": "; ".join(why_lost),
            }
        )
        if len(runner_ups_lost) >= 3:
            break

    coverage = normalized_feature_coverage_from_scanner_evidence(scanner_evidence, selected_symbol=selected_symbol)
    if coverage:
        out["feature_coverage"] = dict(coverage)
        present = safe_int(coverage.get("present"), 0)
        total = safe_int(coverage.get("total"), 0)
        if present > 0 and total > 0:
            top_reasons = [str(x or "") for x in list(out.get("top_reasons") or []) if str(x or "").strip()]
            replaced_top_reason = False
            for idx, reason in enumerate(top_reasons):
                if reason.lower().startswith("chart feature coverage "):
                    top_reasons[idx] = f"chart feature coverage {present}/{total}"
                    replaced_top_reason = True
                    break
            if not replaced_top_reason:
                top_reasons.append(f"chart feature coverage {present}/{total}")
            out["top_reasons"] = top_reasons[:6]

            selection_reason = str(out.get("selection_reason") or "").strip()
            if selection_reason:
                if "chart feature coverage " in selection_reason.lower():
                    selection_reason = re.sub(
                        r"chart feature coverage\s+\d+/\d+",
                        f"chart feature coverage {present}/{total}",
                        selection_reason,
                        flags=re.IGNORECASE,
                    )
                else:
                    selection_reason = f"{selection_reason}; chart feature coverage {present}/{total}"
            else:
                selection_reason = f"chart feature coverage {present}/{total}"
            out["selection_reason"] = selection_reason[:260]

            bullets = [str(x or "") for x in list(out.get("bullets") or []) if str(x or "").strip()]
            updated_bullets: List[str] = []
            replaced_chart_bullet = False
            coverage_detail_inserted = False
            present_keys = [str(x or "") for x in list(coverage.get("present_keys") or []) if str(x or "").strip()]
            missing_keys = [str(x or "") for x in list(coverage.get("missing_keys") or []) if str(x or "").strip()]
            coverage_source = str(coverage.get("source") or "").strip()

            def _append_coverage_details(target: List[str]) -> None:
                nonlocal coverage_detail_inserted
                if coverage_detail_inserted:
                    return
                if present_keys:
                    target.append(
                        "Chart features present: " + ", ".join(present_keys[:8]) + (", ..." if len(present_keys) > 8 else "")
                    )
                if missing_keys:
                    target.append(
                        "Chart features missing: " + ", ".join(missing_keys[:8]) + (", ..." if len(missing_keys) > 8 else "")
                    )
                if coverage_source:
                    target.append(f"Chart feature coverage source: {coverage_source}")
                coverage_detail_inserted = True

            for bullet in bullets:
                if bullet.lower().startswith("chart / feature coverage:"):
                    updated_bullets.append(f"Chart / feature coverage: {present}/{total}")
                    replaced_chart_bullet = True
                    _append_coverage_details(updated_bullets)
                else:
                    updated_bullets.append(bullet)
            if not replaced_chart_bullet:
                updated_bullets.append(f"Chart / feature coverage: {present}/{total}")
                _append_coverage_details(updated_bullets)
            out["bullets"] = updated_bullets[:12]

    if why_selected:
        out["why_selected"] = why_selected
    if selection_basis:
        out["selection_basis"] = selection_basis
    if tie_break_rule:
        out["tie_break_rule"] = tie_break_rule
    if runner_ups_lost:
        out["runner_ups_lost"] = runner_ups_lost

    bullets = [str(x or "") for x in list(out.get("bullets") or []) if str(x or "").strip()]
    if why_selected:
        selection_text = "Selection decision: " + "; ".join(why_selected)
        if selection_text not in bullets:
            bullets.append(selection_text)
    if selection_basis:
        basis_text = f"Final decision basis: {selection_basis}"
        if basis_text not in bullets:
            bullets.append(basis_text)
    if tie_break_rule:
        tie_text = f"Tie-break rule: {tie_break_rule}"
        if tie_text not in bullets:
            bullets.append(tie_text)
    if runner_ups_lost:
        runner_text = "Runner-ups lost because: " + "; ".join(
            f"{row.get('symbol')}: {row.get('summary')}" for row in runner_ups_lost if row.get("symbol")
        )
        if runner_text not in bullets:
            bullets.append(runner_text)
    if bullets:
        out["bullets"] = bullets[:12]
    trace = out.get("scanner_selection_trace") if isinstance(out.get("scanner_selection_trace"), dict) else {}
    if trace and coverage:
        trace["chart_feature_coverage"] = dict(coverage)
        out["scanner_selection_trace"] = trace
    return out


def enrich_filters_from_evidence(
    filters_human: Dict[str, Any],
    scanner_evidence: Dict[str, Any],
    *,
    selected_symbol: str,
    monitor_evidence: Optional[Dict[str, Any]] = None,
    entry_execution_details: Optional[Dict[str, Any]] = None,
    exit_execution_details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    out = dict(filters_human or {})
    coverage = normalized_feature_coverage_from_scanner_evidence(scanner_evidence, selected_symbol=selected_symbol)
    price_anomaly_check: Optional[Dict[str, str]] = None
    execution_spread_check: Optional[Dict[str, str]] = None

    def _visit_monitor_payload(node: Any) -> None:
        nonlocal price_anomaly_check
        if price_anomaly_check is not None:
            return
        if isinstance(node, dict):
            if "price_anomaly_flag" in node:
                flagged = bool(node.get("price_anomaly_flag"))
                reason = str(node.get("price_anomaly_reason") or "").strip()
                price_anomaly_check = {
                    "name": "price anomaly filter",
                    "status": "FAIL" if flagged else "PASS",
                    "detail": reason if flagged and reason else ("monitor price cross-check flagged an anomaly" if flagged else "monitor price cross-check found no anomaly"),
                }
                return
            for value in node.values():
                _visit_monitor_payload(value)
                if price_anomaly_check is not None:
                    return
        elif isinstance(node, list):
            for value in node:
                _visit_monitor_payload(value)
                if price_anomaly_check is not None:
                    return

    _visit_monitor_payload(monitor_evidence)

    def _resolve_execution_spread_check() -> Optional[Dict[str, str]]:
        spread_threshold_bps = 50.0
        for details in (entry_execution_details, exit_execution_details):
            if not isinstance(details, dict):
                continue
            quote_snapshot = details.get("quote_snapshot") if isinstance(details.get("quote_snapshot"), dict) else {}
            spread_bps = details.get("spread_bps")
            if spread_bps in (None, ""):
                spread_bps = quote_snapshot.get("spread_bps")
            if spread_bps in (None, ""):
                continue
            try:
                spread_value = float(spread_bps)
            except Exception:
                continue
            return {
                "name": "spread/slippage filter",
                "status": "PASS" if spread_value <= spread_threshold_bps else "FAIL",
                "detail": f"execution quote snapshot spread was {spread_value:.1f} bps",
            }
        return None

    execution_spread_check = _resolve_execution_spread_check()
    present = 0
    total = 0
    ratio = 0.0
    chart_status = "NOT_AVAILABLE"
    chart_note = "feature snapshot not available"
    coverage_quality = "missing"
    chart_available = bool(coverage)
    if coverage:
        present = safe_int(coverage.get("present"), 0)
        total = safe_int(coverage.get("total"), 0)
        ratio = _safe_float(coverage.get("coverage_ratio"), 0.0) or 0.0
        coverage_quality = str(coverage.get("quality") or "").strip().lower() or chart_status.lower()
        if total <= 0:
            chart_status = "NOT_AVAILABLE"
            chart_note = "feature snapshot not available"
        elif ratio >= 0.75:
            chart_status = "PASS"
            chart_note = f"{present}/{total} captured chart features"
        elif ratio >= 0.5:
            chart_status = "PARTIAL"
            chart_note = f"{present}/{total} captured chart features"
        else:
            chart_status = "FAIL"
            chart_note = f"{present}/{total} captured chart features"

    summary = str(out.get("summary") or "").strip()
    if chart_available:
        if summary:
            summary = re.sub(
                r"Chart completeness was [^.]*(?:\.)?",
                f"Chart completeness was {coverage_quality} with {present}/{total} captured features.",
                summary,
                flags=re.IGNORECASE,
            )
        else:
            summary = f"Scanner and guard checks were captured. Chart completeness was {coverage_quality} with {present}/{total} captured features."
        out["summary"] = summary

    checks = [dict(x) for x in list(out.get("checks") or []) if isinstance(x, dict)]
    updated_checks: List[Dict[str, Any]] = []
    replaced_check = False
    replaced_price_anomaly = False
    replaced_spread_check = False
    for check in checks:
        check_name = str(check.get("name") or "").strip().lower()
        if check_name == "chart completeness filter" and chart_available:
            check["status"] = chart_status
            check["detail"] = chart_note
            replaced_check = True
        elif check_name == "price anomaly filter" and price_anomaly_check is not None:
            check["status"] = str(price_anomaly_check.get("status") or check.get("status") or "")
            check["detail"] = str(price_anomaly_check.get("detail") or check.get("detail") or "")
            replaced_price_anomaly = True
        elif check_name == "spread/slippage filter" and execution_spread_check is not None:
            current_status = str(check.get("status") or "").strip().upper()
            if current_status in {"", "NOT_AVAILABLE", "UNKNOWN"}:
                check["status"] = str(execution_spread_check.get("status") or check.get("status") or "")
                check["detail"] = str(execution_spread_check.get("detail") or check.get("detail") or "")
                replaced_spread_check = True
        updated_checks.append(check)
    if chart_available and not replaced_check:
        updated_checks.append(
            {
                "name": "chart completeness filter",
                "status": chart_status,
                "detail": chart_note,
            }
        )
    if price_anomaly_check is not None and not replaced_price_anomaly:
        updated_checks.append(dict(price_anomaly_check))
    if execution_spread_check is not None and not replaced_spread_check:
        updated_checks.append(dict(execution_spread_check))
    if updated_checks:
        out["checks"] = updated_checks

    bullets = [str(x or "") for x in list(out.get("bullets") or []) if str(x or "").strip()]
    updated_bullets: List[str] = []
    replaced = False
    replaced_price_bullet = False
    replaced_spread_bullet = False
    for bullet in bullets:
        if bullet.lower().startswith("chart completeness filter:") and chart_available:
            updated_bullets.append(f"chart completeness filter: {chart_status} - {chart_note}")
            replaced = True
        elif bullet.lower().startswith("price anomaly filter:") and price_anomaly_check is not None:
            updated_bullets.append(
                f"price anomaly filter: {price_anomaly_check['status']} - {price_anomaly_check['detail']}"
            )
            replaced_price_bullet = True
        elif bullet.lower().startswith("spread/slippage filter:") and execution_spread_check is not None:
            current_status = ""
            match = re.match(r"spread/slippage filter:\s*([A-Z_]+)\s*-", bullet, flags=re.IGNORECASE)
            if match:
                current_status = str(match.group(1) or "").strip().upper()
            if current_status in {"", "NOT_AVAILABLE", "UNKNOWN"}:
                updated_bullets.append(
                    f"spread/slippage filter: {execution_spread_check['status']} - {execution_spread_check['detail']}"
                )
                replaced_spread_bullet = True
            else:
                updated_bullets.append(bullet)
        else:
            updated_bullets.append(bullet)
    if chart_available and not replaced:
        updated_bullets.append(f"chart completeness filter: {chart_status} - {chart_note}")
    if price_anomaly_check is not None and not replaced_price_bullet:
        updated_bullets.append(
            f"price anomaly filter: {price_anomaly_check['status']} - {price_anomaly_check['detail']}"
        )
    if execution_spread_check is not None and not replaced_spread_bullet:
        updated_bullets.append(
            f"spread/slippage filter: {execution_spread_check['status']} - {execution_spread_check['detail']}"
        )
    out["bullets"] = updated_bullets[:8]
    if coverage:
        out["feature_coverage"] = dict(coverage)
    return out
