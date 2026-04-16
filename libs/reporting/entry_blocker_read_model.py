from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")

_RAW_BLOCKER_EXPLANATIONS: Dict[str, str] = {
    "pullback_not_mature": "눌림이 아직 충분히 성숙하지 않음",
    "pullback_mature": "눌림 성숙 조건을 계속 확인 중",
    "pullback_ok": "눌림 기본 조건은 통과 상태",
    "pullback_structure_ok": "눌림 구조는 유지 중",
    "pullback_volume_path_ok": "눌림 경로는 허용 범위이나 추가 확인 필요",
    "breakout_not_ready": "돌파 확인 조건 미충족",
    "breakout_ok": "돌파 기본 조건은 충족 방향",
    "breakout_path_ok": "돌파 경로는 허용 범위",
    "breakout_volume_gate_ok": "돌파 경로 추가 거래량 게이트는 충족 방향",
    "wait_for_confirmation": "추가 확인 신호를 대기 중",
    "volume_confirmation_missing": "거래량 확인 부족",
    "volume_ok": "거래량 기본 조건은 충족 방향",
    "below_vwap_reclaim_not_ready": "VWAP 회복 확인 미충족",
    "vwap_reclaim_ok": "VWAP 회복 조건은 충족 방향",
    "reclaim_gate_ok": "재회복 게이트는 충족 방향",
    "vwap_hold_ok": "VWAP 지지 유지 조건은 충족 방향",
    "rebound_ok": "반등 확인 조건은 충족 방향",
    "buy_blocked_open_position": "기존 포지션 보유 중이라 신규 매수 차단",
    "post_exit_cooldown": "직전 청산 후 재진입 대기",
    "too_extended_from_vwap": "VWAP 대비 과열/이격이 과도함",
    "extension_ok": "이격 조건은 관찰 중",
    "confidence_gate_ok": "신뢰도 게이트는 충족 방향",
    "risk_blocked": "리스크 보호 조건이 진입을 차단",
    "data_insufficient": "판단에 필요한 데이터가 부족함",
}

_BLOCKER_FAMILY_EXPLANATIONS: Dict[str, str] = {
    "pullback_timing": "눌림이 성숙 단계에 도달했는지와 눌림 경로 품질을 확인하는 축",
    "breakout_confirmation": "돌파/확인 신호가 충분히 확정되었는지 보는 축",
    "volume_confirmation": "거래량 확인과 체결 강도 관련 축",
    "reclaim_readiness": "VWAP 또는 재회복 확인이 충분한지 보는 축",
    "open_position_guard": "기존 포지션 보유로 신규 진입을 막는 구조적 가드",
    "cooldown_guard": "직전 청산 후 재진입 대기 가드",
    "rebound_confirmation": "반등 확인이 충분한지 보는 축",
    "confidence_gate": "종합 confidence 문턱과 근접도를 보는 축",
    "structure_confirmation": "차트 구조 유지 여부를 보는 축",
    "overextension_guard": "과도한 이격/과열 진입을 막는 축",
    "risk_guard": "리스크 보호 성격의 진입 차단 축",
    "other": "기타 보조 blocker 축",
    "unknown": "분류되지 않은 blocker 축",
}


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _to_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    if out != out:
        return None
    return out


def _to_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except Exception:
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list_text(values: Any, *, limit: int = 8) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in list(values or []):
        text = _text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= int(limit):
            break
    return out


def _normalize_blocker_family(value: Any) -> str:
    text = _text(value).lower()
    if not text:
        return ""
    if text in {"buy_blocked_open_position", "open_position_blocked"}:
        return "open_position_guard"
    if text.startswith("entry_guard_cooldown") or "cooldown" in text:
        return "cooldown_guard"
    if text in {
        "pullback_not_mature",
        "pullback_mature",
        "pullback_ok",
        "pullback_structure_ok",
        "pullback_volume_path_ok",
        "pullback_below_vwap_reclaim_not_ready",
    } or "pullback" in text:
        return "pullback_timing"
    if text in {
        "below_vwap_reclaim_not_ready",
        "vwap_reclaim_ok",
        "reclaim_gate_ok",
        "vwap_hold_ok",
    } or "reclaim" in text or "vwap" in text:
        return "reclaim_readiness"
    if text in {
        "volume_confirmation_missing",
        "volume_ok",
    } or "volume" in text:
        return "volume_confirmation"
    if text in {
        "breakout_not_ready",
        "breakout_ok",
        "breakout_path_ok",
        "wait_for_confirmation",
    } or "breakout" in text or "confirmation" in text:
        return "breakout_confirmation"
    if text in {"rebound_ok"} or "rebound" in text:
        return "rebound_confirmation"
    if text in {"structure_hh_hl", "chart_structure_guard"} or "structure" in text:
        return "structure_confirmation"
    if text in {"confidence_gate_ok"} or "confidence" in text:
        return "confidence_gate"
    if "extend" in text or "overextended" in text:
        return "overextension_guard"
    if text.startswith("risk_") or text == "risk_blocked":
        return "risk_guard"
    if text == "unknown":
        return "unknown"
    return "other"


def explain_raw_blocker(value: Any) -> str:
    text = _text(value)
    key = text.lower()
    if not key:
        return ""
    if key.startswith("entry_guard_cooldown"):
        return "엔트리 가드 쿨다운으로 잠시 재진입 대기"
    if key in _RAW_BLOCKER_EXPLANATIONS:
        return _RAW_BLOCKER_EXPLANATIONS[key]
    return f"{text} 관련 확인/차단 조건"


def explain_blocker_family(value: Any) -> str:
    key = _text(value)
    if not key:
        return ""
    return _BLOCKER_FAMILY_EXPLANATIONS.get(key, f"{key} 관련 blocker 묶음")


def _build_blocker_families(
    primary_blockers: Any,
    *,
    no_trade_code: Any = None,
    limit: int = 6,
) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    values = list(primary_blockers or [])
    if no_trade_code not in (None, ""):
        values = [no_trade_code] + values
    for value in values:
        family = _normalize_blocker_family(value)
        if not family or family in seen:
            continue
        seen.add(family)
        out.append(family)
        if len(out) >= int(limit):
            break
    return out


def _build_family_raw_breakdown(
    primary_blockers: Any,
    *,
    no_trade_code: Any = None,
    limit_per_family: int = 10,
) -> Dict[str, List[str]]:
    breakdown: Dict[str, List[str]] = {}
    values = _list_text(([no_trade_code] if no_trade_code not in (None, "") else []) + list(primary_blockers or []), limit=20)
    for raw in values:
        family = _normalize_blocker_family(raw)
        if not family:
            continue
        breakdown.setdefault(family, [])
        if raw not in breakdown[family]:
            breakdown[family].append(raw)
            if len(breakdown[family]) > int(limit_per_family):
                breakdown[family] = breakdown[family][: int(limit_per_family)]
    return breakdown


def _infer_scanner_quality_suspected(
    *,
    no_trade_code: str,
    primary_blockers: Sequence[str],
    scanner_selected_summary: Mapping[str, Any],
    scanner_score_total: float | None,
) -> tuple[bool, str, List[str]]:
    reasons: List[str] = []
    raw = {_text(item) for item in list(primary_blockers or []) if _text(item)}
    if _text(no_trade_code):
        raw.add(_text(no_trade_code))
    selected_confidence = _to_float(scanner_selected_summary.get("confidence"))
    selected_score = _to_float(scanner_selected_summary.get("score_total"))
    effective_score = selected_score if selected_score is not None else scanner_score_total

    if "too_extended_from_vwap" in raw:
        reasons.append("selected_candidate_extended")
    if "volume_confirmation_missing" in raw and effective_score is not None and effective_score < 0.8:
        reasons.append("volume_confirmation_missing_low_score")
    if selected_confidence is not None and selected_confidence < 0.72:
        reasons.append("low_candidate_confidence")

    return bool(reasons), (reasons[0] if reasons else ""), reasons


def _scanner_quality_reason_explanation(value: Any) -> str:
    key = _text(value)
    mapping = {
        "selected_candidate_extended": "선정 종목이 이미 VWAP 대비 과열/이격 상태로 보임",
        "volume_confirmation_missing_low_score": "거래량 확인 부족과 낮은 scanner 점수가 함께 나타남",
        "low_candidate_confidence": "selected candidate confidence가 낮은 편",
    }
    return mapping.get(key, "")


def _nested_counter_to_dict(counter_map: Mapping[str, Counter[str]]) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
    for key, counter in dict(counter_map or {}).items():
        out[str(key)] = _counter_to_dict(Counter(dict(counter.most_common(12))))
    return out


def _parse_ts(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def classify_entry_time_bucket(value: Any) -> str:
    dt = _parse_ts(value)
    if dt is None:
        return "unknown"
    dt_kst = dt.astimezone(KST)
    minutes = dt_kst.hour * 60 + dt_kst.minute
    if minutes < (10 * 60 + 30):
        return "open_window"
    if minutes < (14 * 60 + 30):
        return "mid_session"
    return "late_session"


def _resolve_structure_state(monitor: Mapping[str, Any], blocker_surface: Mapping[str, Any]) -> str:
    state = _text(blocker_surface.get("structure_hh_hl"))
    if state:
        return state
    chart_features = monitor.get("entry_chart_structure_features")
    if isinstance(chart_features, Mapping):
        structure = chart_features.get("structure")
        if isinstance(structure, Mapping):
            state = _text(structure.get("structure_hh_hl"))
            if state:
                return state
        state = _text(chart_features.get("structure_hh_hl"))
        if state:
            return state
    return ""


def _resolve_threshold_actual(threshold_snapshot: Mapping[str, Any], field: str) -> Any:
    margins = threshold_snapshot.get("entry_threshold_margins")
    if isinstance(margins, Mapping):
        row = margins.get(field)
        if isinstance(row, Mapping) and row.get("actual") not in (None, ""):
            return row.get("actual")
    return threshold_snapshot.get(field)


def build_entry_blocker_row(
    run_id: str,
    *,
    monitor: Mapping[str, Any],
    scanner: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    scanner_row = dict(scanner or {}) if isinstance(scanner, Mapping) else {}
    blocker_surface = (
        dict(monitor.get("entry_blocker_surface") or {})
        if isinstance(monitor.get("entry_blocker_surface"), Mapping)
        else {}
    )
    no_trade_surface = (
        dict(monitor.get("no_trade_surface") or {})
        if isinstance(monitor.get("no_trade_surface"), Mapping)
        else {}
    )
    threshold_snapshot = (
        dict(monitor.get("threshold_snapshot") or {})
        if isinstance(monitor.get("threshold_snapshot"), Mapping)
        else {}
    )
    scanner_selected = (
        dict(scanner_row.get("selected_candidate") or {})
        if isinstance(scanner_row.get("selected_candidate"), Mapping)
        else {}
    )
    scanner_pool = (
        dict(scanner_row.get("candidate_pool_snapshot") or {})
        if isinstance(scanner_row.get("candidate_pool_snapshot"), Mapping)
        else {}
    )

    ts = _text(monitor.get("ts"))
    dt = _parse_ts(ts)
    ts_kst = dt.astimezone(KST).isoformat() if dt is not None else ""
    decision_raw = _text(monitor.get("decision") or monitor.get("decision_action") or "NOOP").upper()
    if decision_raw == "BUY":
        final_decision = "BUY"
    elif decision_raw == "SELL":
        final_decision = "SELL"
    else:
        final_decision = "WAIT"

    no_trade_code = _text(
        blocker_surface.get("no_trade_code")
        or monitor.get("no_trade_reason_code")
        or no_trade_surface.get("no_trade_reason_code")
    )
    dominant_blocker = _text(
        blocker_surface.get("dominant_blocker")
        or monitor.get("dominant_blocker")
        or no_trade_surface.get("dominant_blocker")
        or no_trade_code
    )
    primary_blockers = _list_text(
        blocker_surface.get("primary_blockers")
        or monitor.get("entry_blockers")
        or [dominant_blocker, no_trade_code]
    )
    raw_entry_blockers = _list_text(
        blocker_surface.get("raw_entry_blockers")
        or monitor.get("entry_blockers")
    )

    confidence_score = blocker_surface.get("confidence_score")
    if confidence_score in (None, ""):
        confidence_score = (
            (monitor.get("evidence_snapshot") or {}).get("confidence_score")
            if isinstance(monitor.get("evidence_snapshot"), Mapping)
            else None
        )
    if confidence_score in (None, "") and isinstance(monitor.get("entry_condition_scores"), Mapping):
        confidence_score = monitor.get("entry_condition_scores", {}).get("confidence_score")
    confidence_threshold = blocker_surface.get("confidence_threshold")
    if confidence_threshold in (None, "") and isinstance(monitor.get("evidence_snapshot"), Mapping):
        confidence_threshold = monitor.get("evidence_snapshot", {}).get("confidence_threshold")
    if confidence_threshold in (None, "") and isinstance(monitor.get("entry_condition_scores"), Mapping):
        confidence_threshold = monitor.get("entry_condition_scores", {}).get("confidence_threshold")

    symbol = _text(
        monitor.get("symbol")
        or monitor.get("scanner_selected_symbol")
        or scanner_selected.get("symbol")
    )
    volume_ratio = blocker_surface.get("volume_ratio")
    if volume_ratio in (None, ""):
        volume_ratio = _resolve_threshold_actual(threshold_snapshot, "entry_volume_ratio")
    pullback_depth_pct = blocker_surface.get("pullback_depth_pct")
    if pullback_depth_pct in (None, ""):
        pullback_depth_pct = _resolve_threshold_actual(threshold_snapshot, "entry_pullback_depth_pct")

    selected_summary = {
        "symbol": _text(scanner_selected.get("symbol") or symbol),
        "why": _text(scanner_selected.get("why")),
        "asset_class_detected": _text(scanner_selected.get("asset_class_detected")),
        "detection_source": _text(scanner_selected.get("detection_source")),
        "score_total": scanner_selected.get("score_total", monitor.get("scanner_score_total")),
        "confidence": scanner_selected.get("confidence"),
        "sources": _list_text(scanner_selected.get("sources"), limit=6),
    }
    blocker_families = _build_blocker_families(primary_blockers, no_trade_code=no_trade_code)
    blocker_family_raw_breakdown = _build_family_raw_breakdown(primary_blockers, no_trade_code=no_trade_code)
    scanner_score_total = _to_float(monitor.get("scanner_score_total"))
    scanner_quality_suspected, scanner_quality_reason, scanner_quality_reasons = _infer_scanner_quality_suspected(
        no_trade_code=no_trade_code,
        primary_blockers=primary_blockers,
        scanner_selected_summary=selected_summary,
        scanner_score_total=scanner_score_total,
    )
    blocker_family_explanations = {
        family: explain_blocker_family(family)
        for family in blocker_families
        if explain_blocker_family(family)
    }
    raw_blocker_explanations = {
        raw: explain_raw_blocker(raw)
        for raw in _list_text(([no_trade_code] if no_trade_code else []) + primary_blockers, limit=12)
        if explain_raw_blocker(raw)
    }

    return {
        "run_id": _text(run_id),
        "ts": ts,
        "ts_kst": ts_kst,
        "time_bucket": classify_entry_time_bucket(ts),
        "symbol": symbol,
        "final_decision": final_decision,
        "decision_raw": decision_raw,
        "primary_blockers": primary_blockers,
        "blocker_families": blocker_families,
        "blocker_family_raw_breakdown": blocker_family_raw_breakdown,
        "blocker_family_explanations": blocker_family_explanations,
        "raw_entry_blockers": raw_entry_blockers,
        "raw_blocker_explanations": raw_blocker_explanations,
        "dominant_blocker": dominant_blocker,
        "no_trade_code": no_trade_code,
        "entry_style": _text(blocker_surface.get("entry_style") or ((monitor.get("evidence_snapshot") or {}).get("entry_style") if isinstance(monitor.get("evidence_snapshot"), Mapping) else "")),
        "confidence_score": _to_float(confidence_score),
        "confidence_threshold": _to_float(confidence_threshold),
        "pullback_depth_pct": _to_float(pullback_depth_pct),
        "rebound_ok": blocker_surface.get("rebound_ok"),
        "rebound_progress": _to_float(blocker_surface.get("rebound_progress")),
        "pullback_ok": blocker_surface.get("pullback_ok"),
        "pullback_not_mature": bool(blocker_surface.get("pullback_not_mature") or no_trade_code == "pullback_not_mature"),
        "volume_ok": blocker_surface.get("volume_ok"),
        "volume_ratio": _to_float(volume_ratio),
        "volume_confirmation_missing": bool(blocker_surface.get("volume_confirmation_missing") or no_trade_code == "volume_confirmation_missing"),
        "structure_hh_hl": _resolve_structure_state(monitor, blocker_surface),
        "below_vwap_reclaim_not_ready": bool(blocker_surface.get("below_vwap_reclaim_not_ready") or no_trade_code == "below_vwap_reclaim_not_ready"),
        "reclaim_gate_ok": blocker_surface.get("reclaim_gate_ok"),
        "vwap_hold_ok": blocker_surface.get("vwap_hold_ok"),
        "vwap_reclaim_ok": blocker_surface.get("vwap_reclaim_ok"),
        "reclaim_distance_to_ready": blocker_surface.get("reclaim_distance_to_ready"),
        "reclaim_readiness_tuned": bool(blocker_surface.get("reclaim_readiness_tuned")),
        "reclaim_tuning_version": _text(blocker_surface.get("reclaim_tuning_version")),
        "reclaim_tuning_scope": _text(blocker_surface.get("reclaim_tuning_scope")),
        "reclaim_tuning_band_used": _text(blocker_surface.get("reclaim_tuning_band_used")),
        "entry_tuning_flags": _list_text(blocker_surface.get("entry_tuning_flags"), limit=6),
        "reclaim_evidence_explanation": _text(blocker_surface.get("reclaim_evidence_explanation")),
        "open_position_blocked": bool(blocker_surface.get("open_position_blocked") or monitor.get("buy_blocked_open_position")),
        "cooldown_blocked": bool(blocker_surface.get("cooldown_blocked") or monitor.get("buy_blocked_post_exit_cooldown")),
        "cooldown_remaining_sec": _to_int(blocker_surface.get("post_exit_cooldown_remaining_sec") or monitor.get("post_exit_cooldown_remaining_sec")),
        "scanner_rank": _to_int(monitor.get("scanner_rank")),
        "scanner_score_total": scanner_score_total,
        "scanner_selected_summary": selected_summary,
        "scanner_candidate_count_after_filter": _to_int(scanner_pool.get("total_candidates_after_filter") or scanner_row.get("candidate_pool_after_filter")),
        "unknown_asset_candidate_count": _to_int(scanner_pool.get("unknown_asset_candidate_count") or scanner_row.get("unknown_asset_candidate_count")),
        "scanner_quality_suspected": scanner_quality_suspected,
        "scanner_quality_reason": scanner_quality_reason,
        "scanner_quality_reasons": scanner_quality_reasons,
        "scanner_quality_reason_explanation": _scanner_quality_reason_explanation(scanner_quality_reason),
    }


def load_entry_blocker_rows(
    canonical_root: str | Path,
    *,
    day: str,
    symbol: str = "",
    family: str = "",
    limit: int | None = None,
) -> List[Dict[str, Any]]:
    root = Path(canonical_root)
    day_root = root / day
    if not day_root.exists():
        return []
    rows: List[Dict[str, Any]] = []
    symbol_filter = _text(symbol).upper()
    family_filter = _text(family)
    for run_dir in sorted(path for path in day_root.iterdir() if path.is_dir()):
        monitor = _read_json(run_dir / "monitor.json")
        if not monitor:
            continue
        scanner = _read_json(run_dir / "scanner.json")
        row = build_entry_blocker_row(run_dir.name, monitor=monitor, scanner=scanner)
        if symbol_filter and _text(row.get("symbol")).upper() != symbol_filter:
            continue
        if family_filter and family_filter not in set(_list_text(row.get("blocker_families"), limit=12)):
            continue
        rows.append(row)
    rows.sort(key=lambda row: (_text(row.get("ts")), _text(row.get("run_id"))))
    if limit and int(limit) > 0:
        rows = rows[-int(limit) :]
    return rows


def build_symbol_entry_blocker_sequence(
    rows: Sequence[Mapping[str, Any]],
    *,
    symbol: str,
) -> List[Dict[str, Any]]:
    target = _text(symbol).upper()
    out: List[Dict[str, Any]] = []
    for row in rows:
        if _text(row.get("symbol")).upper() != target:
            continue
        out.append(
            {
                "run_id": _text(row.get("run_id")),
                "ts_kst": _text(row.get("ts_kst")),
                "final_decision": _text(row.get("final_decision")),
                "no_trade_code": _text(row.get("no_trade_code")),
                "primary_blockers": _list_text(row.get("primary_blockers")),
                "blocker_families": _list_text(row.get("blocker_families")),
                "family_explanations": dict(row.get("blocker_family_explanations") or {}),
                "raw_blocker_explanations": dict(row.get("raw_blocker_explanations") or {}),
                "scanner_quality_suspected": bool(row.get("scanner_quality_suspected")),
                "scanner_quality_reason": _text(row.get("scanner_quality_reason")),
                "scanner_quality_reason_explanation": _text(row.get("scanner_quality_reason_explanation")),
                "scanner_selected_summary": dict(row.get("scanner_selected_summary") or {}),
            }
        )
    out.sort(key=lambda row: (_text(row.get("ts_kst")), _text(row.get("run_id"))))
    return out


def _counter_to_dict(counter: Any) -> Dict[str, int]:
    if isinstance(counter, Mapping):
        items = counter.items()
    else:
        items = list(counter or [])
    return {str(key): int(value) for key, value in items}


def summarize_entry_blocker_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    symbol: str = "",
    family: str = "",
) -> Dict[str, Any]:
    blocker_frequency: Counter[str] = Counter()
    blocker_family_frequency: Counter[str] = Counter()
    blocker_family_raw_breakdown: Dict[str, Counter[str]] = defaultdict(Counter)
    no_trade_frequency: Counter[str] = Counter()
    decision_frequency: Counter[str] = Counter()
    by_symbol_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    by_time_bucket: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "blockers": Counter(),
            "blocker_families": Counter(),
            "family_raw_breakdown": defaultdict(Counter),
            "no_trade_codes": Counter(),
            "decisions": Counter(),
        }
    )
    by_decision: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "blockers": Counter(),
            "blocker_families": Counter(),
            "family_raw_breakdown": defaultdict(Counter),
            "no_trade_codes": Counter(),
            "symbols": Counter(),
        }
    )
    by_symbol_family_raw_breakdown: Dict[str, Dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    scanner_quality_reason_frequency: Counter[str] = Counter()
    scanner_quality_top_symbols: Counter[str] = Counter()
    scanner_quality_suspected_count = 0

    for row in rows:
        final_decision = _text(row.get("final_decision") or "WAIT") or "WAIT"
        decision_frequency[final_decision] += 1
        symbol_value = _text(row.get("symbol") or "UNKNOWN") or "UNKNOWN"
        bucket = _text(row.get("time_bucket") or "unknown") or "unknown"
        no_trade_code = _text(row.get("no_trade_code"))
        primary_blockers = _list_text(row.get("primary_blockers"))
        blocker_families = _list_text(row.get("blocker_families")) or _build_blocker_families(primary_blockers, no_trade_code=no_trade_code)
        family_raw_breakdown = dict(row.get("blocker_family_raw_breakdown") or {}) if isinstance(row.get("blocker_family_raw_breakdown"), Mapping) else _build_family_raw_breakdown(primary_blockers, no_trade_code=no_trade_code)
        scanner_quality_suspected = bool(row.get("scanner_quality_suspected"))
        scanner_quality_reason = _text(row.get("scanner_quality_reason"))

        by_time_bucket[bucket]["decisions"][final_decision] += 1
        by_decision[final_decision]["symbols"][symbol_value] += 1

        if no_trade_code:
            by_decision[final_decision]["no_trade_codes"][no_trade_code] += 1
        for blocker in primary_blockers:
            by_decision[final_decision]["blockers"][blocker] += 1
        for family_name in blocker_families:
            by_decision[final_decision]["blocker_families"][family_name] += 1
        for family_name, raw_values in family_raw_breakdown.items():
            for raw in _list_text(raw_values, limit=20):
                by_decision[final_decision]["family_raw_breakdown"][family_name][raw] += 1

        if scanner_quality_suspected:
            scanner_quality_suspected_count += 1
            scanner_quality_top_symbols[symbol_value] += 1
            if scanner_quality_reason:
                scanner_quality_reason_frequency[scanner_quality_reason] += 1

        if final_decision != "WAIT":
            continue

        if no_trade_code:
            no_trade_frequency[no_trade_code] += 1
            by_symbol_counts[symbol_value][no_trade_code] += 1
            by_time_bucket[bucket]["no_trade_codes"][no_trade_code] += 1

        for blocker in primary_blockers:
            blocker_frequency[blocker] += 1
            by_time_bucket[bucket]["blockers"][blocker] += 1
        for family_name in blocker_families:
            blocker_family_frequency[family_name] += 1
            by_time_bucket[bucket]["blocker_families"][family_name] += 1
        for family_name, raw_values in family_raw_breakdown.items():
            for raw in _list_text(raw_values, limit=20):
                blocker_family_raw_breakdown[family_name][raw] += 1
                by_time_bucket[bucket]["family_raw_breakdown"][family_name][raw] += 1
                by_symbol_family_raw_breakdown[symbol_value][family_name][raw] += 1

    symbol_summary = {}
    for symbol_value, no_trade_counter in by_symbol_counts.items():
        symbol_rows = [
            row
            for row in rows
            if _text(row.get("symbol")) == symbol_value and _text(row.get("final_decision") or "WAIT") == "WAIT"
        ]
        symbol_summary[symbol_value] = {
            "run_count": len(symbol_rows),
            "decision_frequency": _counter_to_dict(Counter(_text(row.get("final_decision") or "WAIT") or "WAIT" for row in symbol_rows)),
            "no_trade_code_frequency": _counter_to_dict(no_trade_counter),
            "top_blocker_families": _counter_to_dict(
                Counter(
                    family
                    for row in symbol_rows
                    for family_name in (_list_text(row.get("blocker_families")) or _build_blocker_families(row.get("primary_blockers"), no_trade_code=row.get("no_trade_code")))
                    for family in [family_name]
                ).most_common(8)
            ),
            "blocker_family_raw_breakdown": _nested_counter_to_dict(by_symbol_family_raw_breakdown[symbol_value]),
            "top_blockers": _counter_to_dict(Counter(blocker for row in symbol_rows for blocker in _list_text(row.get("primary_blockers"))).most_common(8)),
            "scanner_quality_suspected_count": int(sum(1 for row in symbol_rows if bool(row.get("scanner_quality_suspected")))),
        }

    return {
        "row_count": len(rows),
        "symbol_filter": _text(symbol).upper(),
        "family_filter": _text(family),
        "blocker_family_frequency": _counter_to_dict(Counter(dict(blocker_family_frequency.most_common(12)))),
        "blocker_family_raw_breakdown": _nested_counter_to_dict(blocker_family_raw_breakdown),
        "blocker_frequency": _counter_to_dict(Counter(dict(blocker_frequency.most_common(16)))),
        "no_trade_code_frequency": _counter_to_dict(Counter(dict(no_trade_frequency.most_common(16)))),
        "decision_frequency": _counter_to_dict(decision_frequency),
        "scanner_quality_suspected_count": int(scanner_quality_suspected_count),
        "scanner_quality_reason_frequency": _counter_to_dict(Counter(dict(scanner_quality_reason_frequency.most_common(8)))),
        "scanner_quality_top_symbols": _counter_to_dict(Counter(dict(scanner_quality_top_symbols.most_common(8)))),
        "by_symbol": symbol_summary,
        "by_time_bucket": {
            bucket: {
                "decision_frequency": _counter_to_dict(payload["decisions"]),
                "blocker_family_frequency": _counter_to_dict(Counter(dict(payload["blocker_families"].most_common(8)))),
                "blocker_family_raw_breakdown": _nested_counter_to_dict(payload["family_raw_breakdown"]),
                "blocker_frequency": _counter_to_dict(Counter(dict(payload["blockers"].most_common(12)))),
                "no_trade_code_frequency": _counter_to_dict(Counter(dict(payload["no_trade_codes"].most_common(12)))),
            }
            for bucket, payload in by_time_bucket.items()
        },
        "by_final_decision": {
            decision: {
                "blocker_family_frequency": _counter_to_dict(Counter(dict(payload["blocker_families"].most_common(8)))),
                "blocker_family_raw_breakdown": _nested_counter_to_dict(payload["family_raw_breakdown"]),
                "blocker_frequency": _counter_to_dict(Counter(dict(payload["blockers"].most_common(12)))),
                "no_trade_code_frequency": _counter_to_dict(Counter(dict(payload["no_trade_codes"].most_common(12)))),
                "top_symbols": _counter_to_dict(Counter(dict(payload["symbols"].most_common(8)))),
            }
            for decision, payload in by_decision.items()
        },
        "symbol_sequence": build_symbol_entry_blocker_sequence(rows, symbol=symbol) if symbol else [],
    }


def build_entry_blocker_day_summary(
    canonical_root: str | Path,
    *,
    day: str,
    symbol: str = "",
    family: str = "",
    limit: int | None = None,
) -> Dict[str, Any]:
    rows = load_entry_blocker_rows(canonical_root, day=day, symbol=symbol, family=family, limit=limit)
    summary = summarize_entry_blocker_rows(rows, symbol=symbol, family=family)
    summary.update(
        {
            "date": _text(day),
            "canonical_root": str(Path(canonical_root)),
            "rows": list(rows),
            "limit": int(limit or 0),
        }
    )
    return summary


def render_entry_blocker_summary_markdown(summary: Mapping[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# Entry Blocker Summary ({_text(summary.get('date'))})")
    lines.append("")
    lines.append(f"- rows: {int(summary.get('row_count') or 0)}")
    if _text(summary.get("symbol_filter")):
        lines.append(f"- symbol: `{_text(summary.get('symbol_filter'))}`")
    if _text(summary.get("family_filter")):
        family = _text(summary.get("family_filter"))
        lines.append(f"- family: `{family}`")
        lines.append(f"- family explanation: {explain_blocker_family(family)}")
    if int(summary.get("limit") or 0) > 0:
        lines.append(f"- limit: {int(summary.get('limit') or 0)}")
    lines.append("")
    lines.append("## Decision Frequency")
    for key, value in dict(summary.get("decision_frequency") or {}).items():
        lines.append(f"- `{key}`: {int(value)}")
    lines.append("")
    lines.append("## Blocker Families")
    for key, value in dict(summary.get("blocker_family_frequency") or {}).items():
        lines.append(f"- `{key}`: {int(value)}")
    lines.append("")
    lines.append("## Blocker Frequency")
    for key, value in dict(summary.get("blocker_frequency") or {}).items():
        lines.append(f"- `{key}`: {int(value)}")
    lines.append("")
    lines.append("## Family -> Raw Blocker Breakdown")
    for family, raw_counts in dict(summary.get("blocker_family_raw_breakdown") or {}).items():
        explanation = explain_blocker_family(family)
        lines.append(f"- `{family}`: {explanation}")
        for raw, value in dict(raw_counts or {}).items():
            lines.append(f"  - `{raw}`: {int(value)} | {explain_raw_blocker(raw)}")
    lines.append("")
    family_filter = _text(summary.get("family_filter"))
    if family_filter:
        focused_global = dict((summary.get("blocker_family_raw_breakdown") or {}).get(family_filter) or {})
        lines.append("## Focused Family Raw Blockers")
        for raw, value in focused_global.items():
            lines.append(f"- `{raw}`: {int(value)} | {explain_raw_blocker(raw)}")
        lines.append("")
        lines.append("## Focused Family by Symbol")
        for symbol_value, payload in dict(summary.get("by_symbol") or {}).items():
            raw_counts = dict((payload.get("blocker_family_raw_breakdown") or {}).get(family_filter) or {})
            if not raw_counts:
                continue
            lines.append(f"- `{symbol_value}`: {raw_counts}")
        lines.append("")
        lines.append("## Focused Family by Time Bucket")
        for bucket, payload in dict(summary.get("by_time_bucket") or {}).items():
            raw_counts = dict((payload.get("blocker_family_raw_breakdown") or {}).get(family_filter) or {})
            if not raw_counts:
                continue
            lines.append(f"- `{bucket}`: {raw_counts}")
        lines.append("")
        lines.append("## Focused Family by Final Decision")
        for decision, payload in dict(summary.get("by_final_decision") or {}).items():
            raw_counts = dict((payload.get("blocker_family_raw_breakdown") or {}).get(family_filter) or {})
            if not raw_counts:
                continue
            lines.append(f"- `{decision}`: {raw_counts}")
        lines.append("")
    lines.append("## No-Trade Codes")
    for key, value in dict(summary.get("no_trade_code_frequency") or {}).items():
        lines.append(f"- `{key}`: {int(value)}")
    lines.append("")
    lines.append("## Scanner Quality Suspected")
    lines.append(f"- count: {int(summary.get('scanner_quality_suspected_count') or 0)}")
    if dict(summary.get("scanner_quality_reason_frequency") or {}):
        lines.append(f"- reasons: {dict(summary.get('scanner_quality_reason_frequency') or {})}")
    if dict(summary.get("scanner_quality_top_symbols") or {}):
        lines.append(f"- top_symbols: {dict(summary.get('scanner_quality_top_symbols') or {})}")
    lines.append("")
    lines.append("## Time Buckets")
    for bucket, payload in dict(summary.get("by_time_bucket") or {}).items():
        lines.append(
            f"- `{bucket}`: decisions={dict(payload.get('decision_frequency') or {})}, "
            + f"families={dict(payload.get('blocker_family_frequency') or {})}, "
            + f"blockers={dict(payload.get('blocker_frequency') or {})}"
        )
        family_raw = dict(payload.get("blocker_family_raw_breakdown") or {})
        if family_raw:
            lines.append(f"  - family_raw_breakdown={family_raw}")
    if list(summary.get("symbol_sequence") or []):
        lines.append("")
        lines.append("## Symbol Sequence")
        for row in list(summary.get("symbol_sequence") or [])[:30]:
            family_explanations = dict(row.get("family_explanations") or {})
            raw_explanations = dict(row.get("raw_blocker_explanations") or {})
            lines.append(
                "- "
                + f"{_text(row.get('ts_kst'))} "
                + f"`{_text(row.get('run_id'))}` "
                + f"{_text(row.get('final_decision'))} "
                + f"reason=`{_text(row.get('no_trade_code'))}` "
                + f"families={list(row.get('blocker_families') or [])} "
                + f"blockers={list(row.get('primary_blockers') or [])}"
            )
            if family_explanations:
                lines.append(f"  - family_explanations={family_explanations}")
            if raw_explanations:
                lines.append(f"  - raw_blocker_explanations={raw_explanations}")
            if _text(row.get("reclaim_evidence_explanation")):
                lines.append(
                    "  - reclaim="
                    + f"{_text(row.get('reclaim_evidence_explanation'))} "
                    + f"distance={_text(row.get('reclaim_distance_to_ready'))} "
                    + f"tuned={str(bool(row.get('reclaim_readiness_tuned'))).lower()} "
                    + f"band={_text(row.get('reclaim_tuning_band_used'))}"
                )
            if bool(row.get("scanner_quality_suspected")):
                lines.append(
                    "  - scanner_quality_suspected="
                    + f"true reason=`{_text(row.get('scanner_quality_reason'))}` "
                    + f"explanation={_text(row.get('scanner_quality_reason_explanation'))}"
                )
    return "\n".join(lines).strip() + "\n"


__all__ = [
    "build_entry_blocker_day_summary",
    "build_entry_blocker_row",
    "build_symbol_entry_blocker_sequence",
    "classify_entry_time_bucket",
    "explain_blocker_family",
    "explain_raw_blocker",
    "load_entry_blocker_rows",
    "render_entry_blocker_summary_markdown",
    "summarize_entry_blocker_rows",
]
