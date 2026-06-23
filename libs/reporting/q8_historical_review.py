from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from libs.runtime.quant.vwap_reclaim_observation import classify_below_vwap_reclaim_observation


def _read_json(path: Path) -> Dict[str, Any]:
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            payload = json.loads(path.read_text(encoding=encoding))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            continue
    return {}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def _write_md(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text or ""), encoding="utf-8-sig", newline="\n")


def _float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        text = str(value).strip().replace("%", "").replace(",", "")
        if not text:
            return None
        return float(text)
    except Exception:
        return None


def _int(value: Any) -> int:
    try:
        if value in (None, ""):
            return 0
        return int(float(str(value).replace(",", "")))
    except Exception:
        return 0


def _pct_from_ratio(value: Any) -> float | None:
    parsed = _float(value)
    if parsed is None:
        return None
    return parsed * 100.0 if abs(parsed) <= 1.0 else parsed


def _text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"", "-", "none", "null", "unknown", "not_captured"} else text


def _avg(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _weighted_avg(total: float, weight: int) -> float:
    return round(total / weight, 4) if weight > 0 else 0.0


def _iter_days(start: str, end: str) -> Iterable[str]:
    from datetime import date, timedelta

    current = date.fromisoformat(str(start)[:10])
    last = date.fromisoformat(str(end)[:10])
    while current <= last:
        yield current.isoformat()
        current += timedelta(days=1)


def _quant_shadow_candidate_root(reports_root: Path) -> Path:
    return Path(reports_root).parent / "data" / "logs" / "quant_shadow_candidates"


def _iter_quant_shadow_candidate_rows(reports_root: Path, *, start: str, end: str) -> Iterable[Dict[str, Any]]:
    root = _quant_shadow_candidate_root(reports_root)
    for day in _iter_days(start, end):
        day_root = root / day
        if not day_root.exists():
            continue
        for path in sorted(day_root.glob("*.json")):
            if path.name == "latest.json":
                continue
            payload = _read_json(path)
            for row in list(payload.get("candidates") or []):
                if isinstance(row, Mapping):
                    yield dict(row)


def _trade_id_from_path(path: Path) -> str:
    try:
        return path.parents[1].name
    except Exception:
        return ""


@dataclass
class GroupAccumulator:
    candidate_count: int = 0
    observed_count: int = 0
    positive_latest_count: int = 0
    missed_opportunity_count: int = 0
    adverse_count: int = 0
    latest_sum: float = 0.0
    latest_weight: int = 0
    mfe_sum: float = 0.0
    mfe_weight: int = 0
    mae_sum: float = 0.0
    mae_weight: int = 0
    decisions: Counter[str] = field(default_factory=Counter)
    days: set[str] = field(default_factory=set)

    def add(self, day: str, row: Mapping[str, Any]) -> None:
        candidates = _int(row.get("candidate_count") or row.get("count"))
        observed = _int(row.get("observed_count") or row.get("observed_review_candidate_count"))
        self.candidate_count += candidates
        self.observed_count += observed
        self.positive_latest_count += _int(row.get("positive_latest_count"))
        self.missed_opportunity_count += _int(row.get("missed_opportunity_count"))
        self.adverse_count += _int(row.get("adverse_count"))
        self.days.add(day)
        decision = _text(row.get("decision"))
        if decision:
            self.decisions[decision] += 1
        latest = _float(row.get("avg_latest_return_pct"))
        if latest is not None and observed > 0:
            self.latest_sum += latest * observed
            self.latest_weight += observed
        mfe = _float(row.get("avg_max_favorable_pct"))
        if mfe is not None and observed > 0:
            self.mfe_sum += mfe * observed
            self.mfe_weight += observed
        mae = _float(row.get("avg_max_adverse_pct"))
        if mae is not None and observed > 0:
            self.mae_sum += mae * observed
            self.mae_weight += observed

    def to_dict(self, reason: str) -> Dict[str, Any]:
        coverage = self.observed_count / self.candidate_count if self.candidate_count else 0.0
        positive_rate = self.positive_latest_count / self.observed_count if self.observed_count else 0.0
        missed_rate = self.missed_opportunity_count / self.observed_count if self.observed_count else 0.0
        adverse_rate = self.adverse_count / self.observed_count if self.observed_count else 0.0
        return {
            "reason": reason,
            "day_count": len(self.days),
            "candidate_count": self.candidate_count,
            "observed_count": self.observed_count,
            "coverage": round(coverage, 4),
            "avg_latest_return_pct": _weighted_avg(self.latest_sum, self.latest_weight),
            "avg_max_favorable_pct": _weighted_avg(self.mfe_sum, self.mfe_weight),
            "avg_max_adverse_pct": _weighted_avg(self.mae_sum, self.mae_weight),
            "positive_latest_count": self.positive_latest_count,
            "positive_latest_rate": round(positive_rate, 4),
            "missed_opportunity_count": self.missed_opportunity_count,
            "missed_opportunity_rate": round(missed_rate, 4),
            "adverse_count": self.adverse_count,
            "adverse_rate": round(adverse_rate, 4),
            "dominant_decision": self.decisions.most_common(1)[0][0] if self.decisions else "",
        }


@dataclass
class ForwardAccumulator:
    candidate_count: int = 0
    observed_count: int = 0
    day_count: int = 0
    sums: Dict[str, float] = field(default_factory=lambda: defaultdict(float))
    weights: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def add(self, row: Mapping[str, Any]) -> None:
        candidates = _int(row.get("candidate_count"))
        observed = _int(row.get("observed_count"))
        self.candidate_count += candidates
        self.observed_count += observed
        self.day_count += 1
        for key in (
            "avg_return_3m_pct",
            "avg_return_5m_pct",
            "avg_return_15m_pct",
            "avg_return_30m_pct",
            "avg_return_60m_pct",
            "avg_mfe_5m_pct",
            "avg_mae_5m_pct",
        ):
            value = _float(row.get(key))
            if value is not None and observed > 0:
                self.sums[key] += float(value) * observed
                self.weights[key] += observed

    def to_dict(self, name: str) -> Dict[str, Any]:
        out = {
            "name": name,
            "day_count": int(self.day_count),
            "candidate_count": int(self.candidate_count),
            "observed_count": int(self.observed_count),
            "coverage": round(float(self.observed_count) / float(self.candidate_count), 4)
            if self.candidate_count
            else 0.0,
        }
        for key in (
            "avg_return_3m_pct",
            "avg_return_5m_pct",
            "avg_return_15m_pct",
            "avg_return_30m_pct",
            "avg_return_60m_pct",
            "avg_mfe_5m_pct",
            "avg_mae_5m_pct",
        ):
            out[key] = _weighted_avg(float(self.sums.get(key) or 0.0), int(self.weights.get(key) or 0))
        return out


def _decision_for_reclaim_subtype(row: Mapping[str, Any]) -> str:
    name = _text(row.get("name"))
    observed = _int(row.get("observed_count"))
    ret5 = _float(row.get("avg_return_5m_pct")) or 0.0
    ret15 = _float(row.get("avg_return_15m_pct")) or 0.0
    ret60 = _float(row.get("avg_return_60m_pct")) or 0.0
    mae5 = _float(row.get("avg_mae_5m_pct")) or 0.0
    if observed < 30:
        return "retain_observation_sample_small"
    if name.endswith("true_below_vwap_failure") and ret5 > 0 and ret15 > 0:
        return "review_classifier_or_label"
    if ret5 > 0 and ret15 > 0 and mae5 > -0.5:
        return "adjust_and_retest_candidate"
    if ret5 < 0 and ret15 < 0:
        return "keep_blocked"
    if ret60 > 0 and ret5 <= 0:
        return "hold_observation_longer_horizon_only"
    return "retain_under_observation"


def _extract_trade_rows(reports_root: Path, *, start: str, end: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in sorted((reports_root / "trades").glob("*/**/reports/ai_trade_summary.json")):
        try:
            day = path.parts[path.parts.index("trades") + 1]
        except Exception:
            continue
        if day < start or day > end:
            continue
        payload = _read_json(path)
        trade = payload.get("trade") if isinstance(payload.get("trade"), dict) else {}
        truth = payload.get("truth_surface") if isinstance(payload.get("truth_surface"), dict) else {}
        decision = payload.get("decision_flow") if isinstance(payload.get("decision_flow"), dict) else {}
        quant = payload.get("quant_tactic") if isinstance(payload.get("quant_tactic"), dict) else {}
        pnl_pct = _pct_from_ratio(truth.get("pnl_pct"))
        rows.append(
            {
                "day": day,
                "trade_id": _text(trade.get("trade_id")) or _trade_id_from_path(path),
                "symbol": _text(trade.get("symbol")),
                "status": _text(trade.get("status")),
                "pnl_pct": pnl_pct,
                "truth_source": _text(truth.get("truth_source")),
                "tactic": _text(
                    quant.get("tactic_id")
                    or quant.get("selected_tactic")
                    or trade.get("tactical_strategy")
                    or decision.get("tactical_strategy")
                ),
                "playbook": _text(quant.get("playbook") or trade.get("playbook") or decision.get("playbook")),
                "entry_reason": _text(decision.get("entry_reason") or decision.get("entry_trigger")),
                "exit_reason": _text(decision.get("exit_reason") or decision.get("exit_trigger")),
            }
        )
    return rows


def _aggregate_return_rows(rows: Sequence[Mapping[str, Any]], key: str, *, limit: int = 12) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[float]] = defaultdict(list)
    for row in rows:
        value = _text(row.get(key)) or "missing"
        pnl = row.get("pnl_pct")
        if isinstance(pnl, (int, float)):
            grouped[value].append(float(pnl))
    out: List[Dict[str, Any]] = []
    for name, values in grouped.items():
        if not values:
            continue
        out.append(
            {
                "name": name,
                "count": len(values),
                "win_count": sum(1 for value in values if value > 0),
                "loss_count": sum(1 for value in values if value < 0),
                "win_rate": round(sum(1 for value in values if value > 0) / len(values), 4),
                "avg_return_pct": _avg(values),
            }
        )
    out.sort(key=lambda row: (int(row["count"]), abs(float(row["avg_return_pct"]))), reverse=True)
    return out[:limit]


def _daily_summary_rows(reports_root: Path, *, start: str, end: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for day in _iter_days(start, end):
        path = reports_root / "operator_summary" / "daily" / day / "daily_summary.json"
        if not path.exists():
            continue
        payload = _read_json(path)
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        q = (
            payload.get("quant_shadow_candidate_evaluation")
            if isinstance(payload.get("quant_shadow_candidate_evaluation"), dict)
            else {}
        )
        gate = q.get("evaluation_trust_gate") if isinstance(q.get("evaluation_trust_gate"), dict) else {}
        rail = payload.get("market_regime_rail_review") if isinstance(payload.get("market_regime_rail_review"), dict) else {}
        rows.append(
            {
                "day": day,
                "trade_count": _int(metrics.get("trade_count")),
                "closed_trade_count": _int(metrics.get("closed_trade_count")),
                "return_sample_count": _int(metrics.get("return_sample_count")),
                "unavailable_return_count": _int(metrics.get("unavailable_return_count")),
                "win_rate": _float(metrics.get("win_rate")) or 0.0,
                "avg_return_pct": _float(metrics.get("avg_return_pct")) or 0.0,
                "truth_surface_count": _int(metrics.get("truth_surface_count")),
                "shadow_candidate_count": _int(q.get("candidate_count")),
                "shadow_deduped_candidate_count": _int(q.get("deduped_candidate_count")),
                "shadow_duplicate_candidate_count": _int(q.get("duplicate_candidate_count")),
                "shadow_evaluated_count": _int(q.get("evaluated_count")),
                "shadow_would_enter_count": _int(q.get("would_enter_count")),
                "shadow_forward_outcome_coverage": _float(q.get("forward_outcome_coverage")),
                "q8_trust_gate_status": _text(gate.get("status")),
                "q8_promotion_allowed": bool(gate.get("promotion_allowed")),
                "q8_trusted_forward_count": _int(gate.get("trusted_forward_count")),
                "q8_trusted_forward_coverage": _float(gate.get("trusted_forward_coverage")),
                "q8_duplicate_rate": _float(gate.get("duplicate_rate")),
                "market_regime_rail": _text(rail.get("rail_id") or rail.get("market_regime_rail")),
            }
        )
    return rows


def _aggregate_shadow_summaries(reports_root: Path, *, start: str, end: str) -> Dict[str, Any]:
    reason_counter: Counter[str] = Counter()
    role_counter: Counter[str] = Counter()
    tactic_counter: Counter[str] = Counter()
    below_vwap_subtype_counter: Counter[str] = Counter()
    below_vwap_subtype_v2_counter: Counter[str] = Counter()
    vwap_reclaim_subtype_forward: Dict[str, ForwardAccumulator] = defaultdict(ForwardAccumulator)
    vwap_reclaim_subtype_forward_days: set[str] = set()
    group_acc: Dict[str, GroupAccumulator] = defaultdict(GroupAccumulator)
    q_days = 0
    q8_group_days = 0
    for day in _iter_days(start, end):
        path = reports_root / "operator_summary" / "daily" / day / "daily_summary.json"
        if not path.exists():
            continue
        payload = _read_json(path)
        q = payload.get("quant_shadow_candidate_evaluation") if isinstance(payload.get("quant_shadow_candidate_evaluation"), dict) else {}
        if q.get("candidate_count") is not None:
            q_days += 1
        for row in list(q.get("by_reason") or []):
            if isinstance(row, Mapping):
                reason_counter[_text(row.get("name"))] += _int(row.get("count"))
        for row in list(q.get("by_role") or []):
            if isinstance(row, Mapping):
                role_counter[_text(row.get("name"))] += _int(row.get("count"))
        for row in list(q.get("by_tactic_id") or []):
            if isinstance(row, Mapping):
                tactic_counter[_text(row.get("name"))] += _int(row.get("count"))
        below_vwap = (
            q.get("below_vwap_reclaim_observation")
            if isinstance(q.get("below_vwap_reclaim_observation"), Mapping)
            else {}
        )
        for row in list(below_vwap.get("by_subtype") or []):
            if isinstance(row, Mapping):
                below_vwap_subtype_counter[_text(row.get("name"))] += _int(row.get("count"))
        for row in list(below_vwap.get("by_subtype_v2") or []):
            if isinstance(row, Mapping):
                below_vwap_subtype_v2_counter[_text(row.get("name"))] += _int(row.get("count"))
        lane_forward = (
            q.get("entry_lane_forward_outcomes")
            if isinstance(q.get("entry_lane_forward_outcomes"), Mapping)
            else {}
        )
        for row in list(lane_forward.get("by_lane_subtype") or []):
            if not isinstance(row, Mapping):
                continue
            name = _text(row.get("name"))
            if not name.startswith("vwap_reclaim:"):
                continue
            vwap_reclaim_subtype_forward[name].add(row)
            vwap_reclaim_subtype_forward_days.add(day)
        q8 = payload.get("q8_shadow_blocker_review") if isinstance(payload.get("q8_shadow_blocker_review"), dict) else {}
        groups = list(q8.get("groups") or [])
        if groups:
            q8_group_days += 1
        for row in groups:
            if not isinstance(row, Mapping):
                continue
            reason = _text(row.get("reason") or row.get("name"))
            if not reason:
                continue
            group_acc[reason].add(day, row)
    if not below_vwap_subtype_v2_counter:
        for row in _iter_quant_shadow_candidate_rows(reports_root, start=start, end=end):
            observation = classify_below_vwap_reclaim_observation(row)
            if not bool(observation.get("applies")):
                continue
            below_vwap_subtype_v2_counter[_text(observation.get("subtype_v2"))] += 1
    subtype_forward_rows = [
        acc.to_dict(name)
        for name, acc in sorted(
            vwap_reclaim_subtype_forward.items(),
            key=lambda item: (item[1].candidate_count, item[0]),
            reverse=True,
        )
    ]
    for row in subtype_forward_rows:
        row["decision"] = _decision_for_reclaim_subtype(row)
    return {
        "q_shadow_day_count": q_days,
        "q8_group_day_count": q8_group_days,
        "by_reason": [{"name": name, "count": count} for name, count in reason_counter.most_common(20) if name],
        "by_role": [{"name": name, "count": count} for name, count in role_counter.most_common(12) if name],
        "by_tactic_id": [{"name": name, "count": count} for name, count in tactic_counter.most_common(12) if name],
        "below_vwap_reclaim_by_subtype": [
            {"name": name, "count": count}
            for name, count in below_vwap_subtype_counter.most_common(12)
            if name
        ],
        "below_vwap_reclaim_by_subtype_v2": [
            {"name": name, "count": count}
            for name, count in below_vwap_subtype_v2_counter.most_common(12)
            if name
        ],
        "below_vwap_reclaim_subtype_forward_day_count": len(vwap_reclaim_subtype_forward_days),
        "below_vwap_reclaim_subtype_forward": subtype_forward_rows,
        "q8_blocker_groups": [
            acc.to_dict(reason)
            for reason, acc in sorted(group_acc.items(), key=lambda item: item[1].candidate_count, reverse=True)
        ],
    }


def _pattern_rows_from_daily_summaries(
    reports_root: Path,
    *,
    start: str,
    end: str,
    section: str,
    group_key: str,
) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "closed_or_realized_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "flat_count": 0,
            "return_sum": 0.0,
            "return_weight": 0,
            "cost_drag_loss_count": 0,
        }
    )
    for day in _iter_days(start, end):
        path = reports_root / "operator_summary" / "daily" / day / "daily_summary.json"
        if not path.exists():
            continue
        payload = _read_json(path)
        pattern = payload.get("pattern_performance") if isinstance(payload.get("pattern_performance"), dict) else {}
        section_payload = pattern.get(section) if isinstance(pattern.get(section), dict) else {}
        rows = section_payload.get(group_key) if isinstance(section_payload.get(group_key), list) else []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            name = _text(row.get("name")) or "missing"
            bucket = grouped[name]
            count = _int(row.get("count"))
            closed = _int(row.get("closed_or_realized_count") or count)
            avg = _float(row.get("avg_return_pct"))
            bucket["count"] += count
            bucket["closed_or_realized_count"] += closed
            bucket["win_count"] += _int(row.get("win_count"))
            bucket["loss_count"] += _int(row.get("loss_count"))
            bucket["flat_count"] += _int(row.get("flat_count"))
            bucket["cost_drag_loss_count"] += _int(row.get("cost_drag_loss_count"))
            if avg is not None and closed > 0:
                bucket["return_sum"] += float(avg) * closed
                bucket["return_weight"] += closed
    out: List[Dict[str, Any]] = []
    for name, bucket in grouped.items():
        closed = int(bucket.get("closed_or_realized_count") or 0)
        wins = int(bucket.get("win_count") or 0)
        out.append(
            {
                "name": name,
                "count": int(bucket.get("count") or 0),
                "closed_or_realized_count": closed,
                "win_count": wins,
                "loss_count": int(bucket.get("loss_count") or 0),
                "flat_count": int(bucket.get("flat_count") or 0),
                "win_rate": round(wins / closed, 4) if closed else 0.0,
                "avg_return_pct": _weighted_avg(float(bucket.get("return_sum") or 0.0), int(bucket.get("return_weight") or 0)),
                "cost_drag_loss_count": int(bucket.get("cost_drag_loss_count") or 0),
            }
        )
    out.sort(key=lambda row: (int(row.get("closed_or_realized_count") or 0), abs(float(row.get("avg_return_pct") or 0.0))), reverse=True)
    return out


def _promotion_recommendations(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    groups = {str(row.get("reason")): dict(row) for row in list(payload.get("q8_blocker_groups") or []) if isinstance(row, Mapping)}
    recs: List[Dict[str, Any]] = []
    defensive = next(
        (
            row
            for row in list(payload.get("trade_by_tactic") or [])
            if str(row.get("name") or "") == "defensive_observe"
        ),
        {},
    )
    if defensive and int(defensive.get("count") or 0) >= 5 and float(defensive.get("avg_return_pct") or 0.0) < 0:
        recs.append(
            {
                "candidate": "risk_off_defensive_observe_no_entry_policy",
                "decision": "promoted_keep",
                "reason": "defensive_observe live trades are negative and 2026-06-08 showed severe risk-off misuse.",
            }
        )
    for reason, label in (
        ("below_vwap_reclaim_not_ready", "subtype_adjust_review"),
        ("breakout_not_ready", "adjust_and_retest"),
        ("pullback_not_mature", "adjust_and_retest"),
        ("volume_confirmation_missing", "retain_strict_or_observe"),
        ("human_chart_sanity_guard_blocked", "retain_veto_review_missed"),
    ):
        row = groups.get(reason) or {}
        if not row:
            continue
        recs.append(
            {
                "candidate": reason,
                "decision": label,
                "candidate_count": row.get("candidate_count"),
                "observed_count": row.get("observed_count"),
                "avg_latest_return_pct": row.get("avg_latest_return_pct"),
                "missed_opportunity_rate": row.get("missed_opportunity_rate"),
                "adverse_rate": row.get("adverse_rate"),
            }
        )
    subtype_rows = list(payload.get("below_vwap_reclaim_subtype_forward") or [])
    if subtype_rows:
        strongest = max(
            subtype_rows,
            key=lambda row: (
                float(row.get("avg_return_15m_pct") or 0.0),
                float(row.get("avg_return_5m_pct") or 0.0),
                int(row.get("observed_count") or 0),
            ),
        )
        recs.append(
            {
                "candidate": "below_vwap_reclaim_subtype_policy",
                "decision": "do_not_relax_globally",
                "reason": (
                    f"Subtype forward evidence is mixed; strongest={strongest.get('name')} "
                    f"5m={float(strongest.get('avg_return_5m_pct') or 0.0):.4f}%, "
                    f"15m={float(strongest.get('avg_return_15m_pct') or 0.0):.4f}%. "
                    "Review classifier labels before behavior promotion."
                ),
            }
        )
    return recs


def build_q8_historical_review_payload(
    *,
    reports_root: Path = Path("reports"),
    start: str,
    end: str,
) -> Dict[str, Any]:
    daily_rows = _daily_summary_rows(reports_root, start=start, end=end)
    trade_rows = _extract_trade_rows(reports_root, start=start, end=end)
    return_rows = [row for row in trade_rows if isinstance(row.get("pnl_pct"), (int, float))]
    shadow = _aggregate_shadow_summaries(reports_root, start=start, end=end)
    pattern_by_tactic = _pattern_rows_from_daily_summaries(
        reports_root,
        start=start,
        end=end,
        section="strategist",
        group_key="by_tactical_strategy",
    )
    pattern_by_exit = _pattern_rows_from_daily_summaries(
        reports_root,
        start=start,
        end=end,
        section="monitor_exit",
        group_key="by_exit_reason",
    )
    payload: Dict[str, Any] = {
        "schema_version": "q8_historical_review.v1",
        "behavior_effect": "evaluation_only",
        "start": str(start)[:10],
        "end": str(end)[:10],
        "daily_count": len(daily_rows),
        "daily_rows": daily_rows,
        "q8_promotion_eligibility": {
            "promotion_allowed_day_count": sum(1 for row in daily_rows if bool(row.get("q8_promotion_allowed"))),
            "trusted_gate_day_count": sum(1 for row in daily_rows if _text(row.get("q8_trust_gate_status"))),
            "status": (
                "promotion_review_possible"
                if any(bool(row.get("q8_promotion_allowed")) for row in daily_rows)
                else "promotion_blocked_by_trust_gate_or_legacy_data"
            ),
            "rule": "Historical conclusions require daily evaluation_trust_gate.promotion_allowed=true. Legacy daily summaries without trust gate are observation-only.",
        },
        "trade_summary": {
            "trade_report_count": len(trade_rows),
            "return_sample_count": len(return_rows),
            "avg_return_pct": _avg([float(row["pnl_pct"]) for row in return_rows]),
            "win_rate": round(sum(1 for row in return_rows if float(row["pnl_pct"]) > 0) / len(return_rows), 4)
            if return_rows
            else 0.0,
            "truth_sources": [
                {"name": name, "count": count}
                for name, count in Counter(_text(row.get("truth_source")) or "missing" for row in trade_rows).most_common(12)
            ],
        },
        "trade_by_tactic": pattern_by_tactic or _aggregate_return_rows(return_rows, "tactic"),
        "trade_by_entry_reason": _aggregate_return_rows(return_rows, "entry_reason"),
        "trade_by_exit_reason": pattern_by_exit or _aggregate_return_rows(return_rows, "exit_reason"),
        **shadow,
    }
    eligibility = payload.get("q8_promotion_eligibility") if isinstance(payload.get("q8_promotion_eligibility"), Mapping) else {}
    if int(eligibility.get("promotion_allowed_day_count") or 0) <= 0:
        payload["promotion_recommendations"] = [
            {
                "candidate": "all_q8_candidates",
                "decision": "retain_under_observation",
                "reason": "no historical day passed the Q8 evaluation trust gate",
            }
        ]
    else:
        payload["promotion_recommendations"] = _promotion_recommendations(payload)
    return payload


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> List[str]:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(item) for item in row) + " |")
    return out


def render_q8_historical_review_markdown(payload: Mapping[str, Any]) -> str:
    trade = payload.get("trade_summary") if isinstance(payload.get("trade_summary"), Mapping) else {}
    lines: List[str] = [
        f"# Q8 Historical Review: {payload.get('start')} to {payload.get('end')}",
        "",
        "Purpose: reuse prior live and shadow evidence without mixing incompatible artifact eras.",
        "",
        "This review is evaluation-only. It does not change entry, exit, scanner, Strategist, or execution behavior.",
        "",
        "## Data Windows",
        "",
        "- Live trade performance: usable from 2026-05-18 onward when truth-surface PnL exists.",
        "- Q8 shadow evaluation: most useful from 2026-05-26 onward when candidate shadow summaries are populated.",
        "- Market regime rail: most useful from 2026-06-02 onward when rail IDs are attached to daily summaries.",
        "- Broker truth reconciliation: strongest from 2026-06-08 onward after post-close order-pair repair.",
        "",
        "## Live Trade Summary",
        "",
        f"- Trade report files: **{trade.get('trade_report_count', 0)}**",
        f"- Return samples: **{trade.get('return_sample_count', 0)}**",
        f"- Win rate: **{float(trade.get('win_rate') or 0.0) * 100:.2f}%**",
        f"- Average return: **{float(trade.get('avg_return_pct') or 0.0):.4f}%**",
        "",
    ]
    daily_rows = list(payload.get("daily_rows") or [])
    if daily_rows:
        lines.extend(
            _md_table(
                ["Day", "Trades", "Closed", "Returns", "Missing", "Win", "Avg", "Raw", "Deduped", "Trusted", "Gate", "Allowed", "Rail"],
                [
                    [
                        row.get("day"),
                        row.get("trade_count"),
                        row.get("closed_trade_count"),
                        row.get("return_sample_count"),
                        row.get("unavailable_return_count"),
                        f"{float(row.get('win_rate') or 0.0) * 100:.1f}%",
                        f"{float(row.get('avg_return_pct') or 0.0):.2f}%",
                        row.get("shadow_candidate_count") or 0,
                        row.get("shadow_deduped_candidate_count") or 0,
                        row.get("q8_trusted_forward_count") or 0,
                        row.get("q8_trust_gate_status") or "legacy/no_gate",
                        bool(row.get("q8_promotion_allowed")),
                        row.get("market_regime_rail") or "-",
                    ]
                    for row in daily_rows
                ],
            )
        )
        lines.append("")
    eligibility = payload.get("q8_promotion_eligibility") if isinstance(payload.get("q8_promotion_eligibility"), Mapping) else {}
    lines.extend(
        [
            "## Q8 Promotion Eligibility",
            "",
            f"- status: `{eligibility.get('status') or 'unknown'}`",
            f"- trusted gate days: **{eligibility.get('trusted_gate_day_count') or 0}**",
            f"- promotion allowed days: **{eligibility.get('promotion_allowed_day_count') or 0}**",
            f"- rule: {eligibility.get('rule') or '-'}",
            "",
        ]
    )
    lines.extend(["## Trade Pattern Evidence", ""])
    for title, key in (
        ("By Tactic", "trade_by_tactic"),
        ("By Entry Reason", "trade_by_entry_reason"),
        ("By Exit Reason", "trade_by_exit_reason"),
    ):
        rows = list(payload.get(key) or [])
        lines.extend([f"### {title}", ""])
        lines.extend(
            _md_table(
                ["Name", "Count", "Win", "Avg"],
                [
                    [
                        row.get("name"),
                        row.get("count"),
                        f"{float(row.get('win_rate') or 0.0) * 100:.1f}%",
                        f"{float(row.get('avg_return_pct') or 0.0):.3f}%",
                    ]
                    for row in rows[:10]
                ],
            )
        )
        lines.append("")
    lines.extend(
        [
            "## Q8 Shadow Summary",
            "",
            f"- Q8 shadow summary days: **{payload.get('q_shadow_day_count', 0)}**",
            f"- Q8 blocker forward-review days: **{payload.get('q8_group_day_count', 0)}**",
            "",
            "### Top Shadow Reasons",
            "",
        ]
    )
    lines.extend(
        _md_table(
            ["Reason", "Count"],
            [[row.get("name"), row.get("count")] for row in list(payload.get("by_reason") or [])[:15]],
        )
    )
    lines.extend(["", "### Forward Blocker Review", ""])
    lines.extend(
        _md_table(
            ["Reason", "n", "obs", "Latest", "MFE", "MAE", "Missed", "Adverse", "Decision"],
            [
                [
                    row.get("reason"),
                    row.get("candidate_count"),
                    row.get("observed_count"),
                    f"{float(row.get('avg_latest_return_pct') or 0.0):.4f}%",
                    f"{float(row.get('avg_max_favorable_pct') or 0.0):.4f}%",
                    f"{float(row.get('avg_max_adverse_pct') or 0.0):.4f}%",
                    f"{float(row.get('missed_opportunity_rate') or 0.0) * 100:.1f}%",
                    f"{float(row.get('adverse_rate') or 0.0) * 100:.1f}%",
                    row.get("dominant_decision") or "-",
                ]
                for row in list(payload.get("q8_blocker_groups") or [])[:10]
            ],
        )
    )
    subtype_rows = list(payload.get("below_vwap_reclaim_by_subtype") or [])
    subtype_v2_rows = list(payload.get("below_vwap_reclaim_by_subtype_v2") or [])
    subtype_forward_rows = list(payload.get("below_vwap_reclaim_subtype_forward") or [])
    lines.extend(
        [
            "",
            "## Below-VWAP Reclaim Subtype Review",
            "",
            f"- Subtype count days: **{payload.get('q_shadow_day_count', 0)}**",
            f"- Subtype forward days: **{payload.get('below_vwap_reclaim_subtype_forward_day_count', 0)}**",
            "- Note: subtype forward evidence is available only after the entry-lane observation fields were added.",
            "",
            "### Subtype Counts",
            "",
        ]
    )
    lines.extend(
        _md_table(
            ["Subtype", "Count"],
            [[row.get("name"), row.get("count")] for row in subtype_rows[:10]],
        )
    )
    lines.extend(["", "### Subtype V2 Counts", ""])
    lines.extend(
        _md_table(
            ["Subtype V2", "Count"],
            [[row.get("name"), row.get("count")] for row in subtype_v2_rows[:12]],
        )
    )
    lines.extend(["", "### Subtype Forward Outcomes", ""])
    lines.extend(
        _md_table(
            ["Subtype", "n", "obs", "3m", "5m", "15m", "30m", "60m", "MFE5", "MAE5", "Decision"],
            [
                [
                    row.get("name"),
                    row.get("candidate_count"),
                    row.get("observed_count"),
                    f"{float(row.get('avg_return_3m_pct') or 0.0):.4f}%",
                    f"{float(row.get('avg_return_5m_pct') or 0.0):.4f}%",
                    f"{float(row.get('avg_return_15m_pct') or 0.0):.4f}%",
                    f"{float(row.get('avg_return_30m_pct') or 0.0):.4f}%",
                    f"{float(row.get('avg_return_60m_pct') or 0.0):.4f}%",
                    f"{float(row.get('avg_mfe_5m_pct') or 0.0):.4f}%",
                    f"{float(row.get('avg_mae_5m_pct') or 0.0):.4f}%",
                    row.get("decision") or "-",
                ]
                for row in subtype_forward_rows[:10]
            ],
        )
    )
    lines.extend(["", "## Recommendations", ""])
    lines.extend(
        _md_table(
            ["Candidate", "Decision", "Evidence"],
            [
                [
                    row.get("candidate"),
                    row.get("decision"),
                    row.get("reason")
                    or (
                        f"n={row.get('candidate_count')}, obs={row.get('observed_count')}, "
                        f"latest={float(row.get('avg_latest_return_pct') or 0.0):.4f}%, "
                        f"missed={float(row.get('missed_opportunity_rate') or 0.0) * 100:.1f}%, "
                        f"adverse={float(row.get('adverse_rate') or 0.0) * 100:.1f}%"
                    ),
                ]
                for row in list(payload.get("promotion_recommendations") or [])
            ],
        )
    )
    lines.extend(
        [
            "",
            "## Operator Conclusion",
            "",
            "- Prior data is useful, but it must be sliced by artifact era.",
            "- Live trade PnL already shows persistent negative expectancy in stop/trend-break/low-break exits.",
            "- Q8 shadow raw sample size alone is not promotion evidence.",
            "- Promotion review requires trusted same-day forward outcomes, canonical dedupe, and evaluation_trust_gate.promotion_allowed=true.",
            "- Historical reports generated before the trust gate are legacy observation material, not policy-promotion evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def write_q8_historical_review(
    *,
    reports_root: Path = Path("reports"),
    docs_root: Path = Path("docs/tactics"),
    start: str,
    end: str,
) -> Dict[str, Any]:
    payload = build_q8_historical_review_payload(reports_root=reports_root, start=start, end=end)
    stem = f"q8_historical_review_{str(start)[:10]}_to_{str(end)[:10]}"
    md_path = docs_root / f"{stem}.md"
    json_path = reports_root / "dev" / "analysis" / "q8_historical_review" / f"{stem}.json"
    _write_json(json_path, payload)
    _write_md(md_path, render_q8_historical_review_markdown(payload))
    return {"ok": True, "payload": payload, "md_path": str(md_path), "json_path": str(json_path)}


__all__ = [
    "build_q8_historical_review_payload",
    "render_q8_historical_review_markdown",
    "write_q8_historical_review",
]
