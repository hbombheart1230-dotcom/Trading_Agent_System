from __future__ import annotations

from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any, Mapping, Sequence

from .loaders import load_json, mapping


CANDIDATE_ID = "R1_SCANNER_RISK_HIGH_30M_V1"
MIN_SAMPLE = 10
MIN_PROFIT_FACTOR = 1.20


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    values = [value for row in rows if (value := _number(row.get("net_return_pct"))) is not None]
    wins = [value for value in values if value > 0.0]
    losses = [value for value in values if value < 0.0]
    gross_loss = abs(sum(losses))
    equity = peak = max_drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    return {
        "sample_count": len(values),
        "win_rate": round(len(wins) / len(values), 4) if values else None,
        "avg_net_return_pct": round(mean(values), 4) if values else None,
        "median_net_return_pct": round(median(values), 4) if values else None,
        "profit_factor": (
            round(sum(wins) / gross_loss, 4)
            if gross_loss
            else 999.0 if wins else 0.0
        ),
        "max_drawdown_pct": round(max_drawdown, 4) if values else None,
        "total_gain_pct": round(sum(wins), 4),
        "total_loss_pct": round(sum(losses), 4),
    }


def _passes(metrics: Mapping[str, Any]) -> bool:
    avg = _number(metrics.get("avg_net_return_pct"))
    pf = _number(metrics.get("profit_factor"))
    return bool(avg is not None and avg > 0.0 and pf is not None and pf >= MIN_PROFIT_FACTOR)


def _market_regime(kospi_pct: Any) -> str:
    value = _number(kospi_pct)
    if value is None:
        return "UNKNOWN"
    if value >= 1.0:
        return "STRONG_POSITIVE"
    if value >= 0.0:
        return "NON_NEGATIVE"
    if value > -1.0:
        return "MILD_NEGATIVE"
    return "SHARP_NEGATIVE"


def _group_metrics(rows: Sequence[Mapping[str, Any]], field: str) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row.get(field) or "UNKNOWN"), []).append(row)
    return [{field: key, **_metrics(values)} for key, values in sorted(groups.items())]


def _leave_one_out(rows: Sequence[Mapping[str, Any]], field: str) -> list[dict[str, Any]]:
    result = []
    for value in sorted({str(row.get(field) or "UNKNOWN") for row in rows}):
        metrics = _metrics([row for row in rows if str(row.get(field) or "UNKNOWN") != value])
        result.append({f"excluded_{field}": value, **metrics, "passes": _passes(metrics)})
    return sorted(
        result,
        key=lambda item: (
            float(item.get("avg_net_return_pct") or -999.0),
            float(item.get("profit_factor") or -999.0),
        ),
    )


def performance_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return _metrics(rows)


def performance_passes(metrics: Mapping[str, Any]) -> bool:
    return _passes(metrics)


def leave_one_out(rows: Sequence[Mapping[str, Any]], field: str) -> list[dict[str, Any]]:
    return _leave_one_out(rows, field)


def evaluate_risk_high_sensitivity(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    first: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in sorted(rows, key=lambda item: int(item.get("decision_epoch") or 0)):
        key = (str(row.get("day") or ""), str(row.get("symbol") or ""))
        if key[0] and key[1] and _number(row.get("net_return_pct")) is not None:
            first.setdefault(key, row)
    independent = [dict(row) for row in first.values()]
    day_counts = Counter(str(row.get("day")) for row in independent)
    symbol_counts = Counter(str(row.get("symbol")) for row in independent)
    largest_day = day_counts.most_common(1)[0][0] if day_counts else None
    largest_symbol = symbol_counts.most_common(1)[0][0] if symbol_counts else None

    base = _metrics(independent)
    without_largest_symbol = _metrics([row for row in independent if row.get("symbol") != largest_symbol])
    without_largest_day = _metrics([row for row in independent if row.get("day") != largest_day])
    without_both = _metrics(
        [row for row in independent if row.get("symbol") != largest_symbol and row.get("day") != largest_day]
    )
    best_row = max(independent, key=lambda row: float(row["net_return_pct"])) if independent else None
    without_best_observation = _metrics([row for row in independent if row is not best_row])
    symbol_loo = _leave_one_out(independent, "symbol")
    day_loo = _leave_one_out(independent, "day")
    worst_symbol = symbol_loo[0] if symbol_loo else {}
    worst_day = day_loo[0] if day_loo else {}

    positive_by_symbol: Counter[str] = Counter()
    for row in independent:
        value = float(row["net_return_pct"])
        if value > 0:
            positive_by_symbol[str(row.get("symbol"))] += value
    total_positive = sum(positive_by_symbol.values())
    top_positive_symbol, top_positive_gain = positive_by_symbol.most_common(1)[0] if positive_by_symbol else (None, 0.0)

    asset_known = sum(str(row.get("asset_class") or "UNKNOWN") != "UNKNOWN" for row in independent)
    market_known = sum(str(row.get("market_regime") or "UNKNOWN") != "UNKNOWN" for row in independent)
    checks = {
        "base": _passes(base),
        "without_largest_symbol": _passes(without_largest_symbol),
        "without_largest_day": _passes(without_largest_day),
        "without_both": _passes(without_both),
        "without_best_observation": _passes(without_best_observation),
        "all_symbol_leave_one_out": bool(symbol_loo) and all(bool(row["passes"]) for row in symbol_loo),
        "all_day_leave_one_out": bool(day_loo) and all(bool(row["passes"]) for row in day_loo),
    }
    if len(independent) < MIN_SAMPLE:
        decision = "INSUFFICIENT_EVIDENCE"
        rationale = f"독립 표본 {len(independent)}건으로 최소 {MIN_SAMPLE}건에 미달함."
    elif not checks["base"]:
        decision = "REJECT_BASE_EFFECT"
        rationale = "기본 prospective 성과가 고정 기대값/PF 기준을 통과하지 못함."
    elif not checks["all_symbol_leave_one_out"]:
        decision = "REJECT_CONTRIBUTOR_DEPENDENCE"
        rationale = "특정 수익 기여 종목 제외 시 PF 기준이 무너져 일반 risk-band 구분자로 볼 수 없음."
    elif not all(checks.values()):
        decision = "REJECT_CONCENTRATION_SENSITIVITY"
        rationale = "일자·종목·최대 관측 제거 민감도 중 하나 이상이 고정 기준을 통과하지 못함."
    elif market_known / len(independent) < 0.8 or asset_known / len(independent) < 0.8:
        decision = "CONDITIONAL_NOT_PROMOTABLE_METADATA_GAP"
        rationale = "성과는 견고하지만 자산군/시장 regime point-in-time coverage가 80% 미만임."
    else:
        decision = "PROMOTION_REVIEW_PASS"
        rationale = "고정 민감도와 metadata coverage 기준을 모두 통과함."

    return {
        "schema_version": "risk_high_30m_sensitivity.v1",
        "behavior_effect": "evaluation_only",
        "candidate_id": CANDIDATE_ID,
        "evaluation_unit": "first_observed_day_symbol",
        "target_horizon": "+30m",
        "thresholds": {
            "minimum_independent_sample": MIN_SAMPLE,
            "minimum_avg_net_return_pct": 0.0,
            "minimum_profit_factor": MIN_PROFIT_FACTOR,
            "minimum_asset_metadata_coverage": 0.8,
            "minimum_market_metadata_coverage": 0.8,
        },
        "base": base,
        "largest_frequency_exposure": {
            "day": largest_day,
            "day_share": round(day_counts[largest_day] / len(independent), 4) if largest_day else None,
            "symbol": largest_symbol,
            "symbol_share": round(symbol_counts[largest_symbol] / len(independent), 4) if largest_symbol else None,
        },
        "sensitivity": {
            "without_largest_symbol": without_largest_symbol,
            "without_largest_day": without_largest_day,
            "without_both": without_both,
            "without_best_observation": without_best_observation,
            "worst_symbol_leave_one_out": worst_symbol,
            "worst_day_leave_one_out": worst_day,
        },
        "positive_contribution": {
            "top_symbol": top_positive_symbol,
            "top_symbol_gain_pct": round(top_positive_gain, 4),
            "top_symbol_share_of_positive_gain": round(top_positive_gain / total_positive, 4) if total_positive else None,
        },
        "metadata_coverage": {
            "asset_class": round(asset_known / len(independent), 4) if independent else 0.0,
            "market_regime": round(market_known / len(independent), 4) if independent else 0.0,
        },
        "by_asset_class": _group_metrics(independent, "asset_class"),
        "by_market_regime": _group_metrics(independent, "market_regime"),
        "checks": checks,
        "decision": decision,
        "rationale": rationale,
        "behavior_change_authorized": False,
        "rows": independent,
    }


def build_risk_high_sensitivity(*, reports_root: Path, first_day: str, through_day: str) -> dict[str, Any]:
    opening, opening_source = load_json(
        reports_root / "evaluation" / "opening_rank1_shadow" / "opening_rank1_shadow_cumulative.json"
    )
    episode_by_id = {
        str(row.get("episode_id")): mapping(row)
        for row in opening.get("episodes") or []
        if isinstance(row, Mapping)
    }
    observations = []
    source_errors = []
    prospective_root = reports_root / "evaluation" / "feature_mart" / "opening_rank1" / "prospective"
    for path in sorted(prospective_root.glob("20??-??-??/rank1_candidate_shadow_daily.json")):
        day = path.parent.name
        if day < first_day or day > through_day:
            continue
        payload, source = load_json(path)
        if source.get("error"):
            source_errors.append(str(path))
            continue
        if str(payload.get("status")) not in {"VALID", "VALID_NO_EPISODES"}:
            continue
        for value in payload.get("observations") or []:
            row = mapping(value)
            if row.get("candidate_id") != CANDIDATE_ID or not row.get("matched"):
                continue
            episode = episode_by_id.get(str(row.get("episode_id")), {})
            observability = mapping(episode.get("opening_observability"))
            asset = mapping(observability.get("asset_observation"))
            market = mapping(observability.get("market_snapshot"))
            enriched = dict(row)
            enriched["asset_class"] = asset.get("asset_class") or "UNKNOWN"
            enriched["kospi_pct"] = market.get("kospi_pct")
            enriched["market_regime"] = _market_regime(market.get("kospi_pct"))
            observations.append(enriched)
    result = evaluate_risk_high_sensitivity(observations)
    result["range"] = {"start": first_day, "end": through_day}
    result["source_integrity"] = {
        "opening_source_error": opening_source.get("error"),
        "daily_source_errors": source_errors,
    }
    return result


def render_risk_high_sensitivity(payload: Mapping[str, Any]) -> str:
    def cell(metrics: Any) -> str:
        row = mapping(metrics)
        if not row.get("sample_count"):
            return "-"
        wr = _number(row.get("win_rate"))
        profit_factor = _number(row.get("profit_factor"))
        pf_text = "-" if profit_factor is None else f"{profit_factor:.4f}"
        return (
            f"N={row['sample_count']}, WR {wr * 100:.1f}%, "
            f"avg {float(row.get('avg_net_return_pct') or 0):+.4f}%, "
            f"median {float(row.get('median_net_return_pct') or 0):+.4f}%, "
            f"PF {pf_text}"
        )

    exposure = mapping(payload.get("largest_frequency_exposure"))
    sensitivity = mapping(payload.get("sensitivity"))
    contribution = mapping(payload.get("positive_contribution"))
    coverage = mapping(payload.get("metadata_coverage"))
    checks = mapping(payload.get("checks"))
    lines = [
        "# Risk HIGH +30m Sensitivity Review",
        "",
        "기존 prospective 자료의 첫 day-symbol 관측만 사용한 read-only 검토입니다.",
        "",
        f"## 결론: `{payload.get('decision')}`",
        "",
        str(payload.get("rationale") or ""),
        "",
        "## 민감도",
        "",
        "| 조건 | 결과 | 통과 |",
        "|---|---|---|",
        f"| 전체 | {cell(payload.get('base'))} | `{checks.get('base')}` |",
        f"| 최대 빈도 종목 `{exposure.get('symbol')}` 제외 | {cell(sensitivity.get('without_largest_symbol'))} | `{checks.get('without_largest_symbol')}` |",
        f"| 최대 빈도 일자 `{exposure.get('day')}` 제외 | {cell(sensitivity.get('without_largest_day'))} | `{checks.get('without_largest_day')}` |",
        f"| 둘 다 제외 | {cell(sensitivity.get('without_both'))} | `{checks.get('without_both')}` |",
        f"| 최대 단일 수익 관측 제외 | {cell(sensitivity.get('without_best_observation'))} | `{checks.get('without_best_observation')}` |",
        f"| 최악의 종목 leave-one-out `{mapping(sensitivity.get('worst_symbol_leave_one_out')).get('excluded_symbol')}` | {cell(sensitivity.get('worst_symbol_leave_one_out'))} | `{mapping(sensitivity.get('worst_symbol_leave_one_out')).get('passes')}` |",
        f"| 최악의 일자 leave-one-out `{mapping(sensitivity.get('worst_day_leave_one_out')).get('excluded_day')}` | {cell(sensitivity.get('worst_day_leave_one_out'))} | `{mapping(sensitivity.get('worst_day_leave_one_out')).get('passes')}` |",
        "",
        "## 집중도 해석",
        "",
        f"- 최대 빈도 종목: `{exposure.get('symbol')}` / {float(exposure.get('symbol_share') or 0) * 100:.1f}%",
        f"- 최대 빈도 일자: `{exposure.get('day')}` / {float(exposure.get('day_share') or 0) * 100:.1f}%",
        f"- 양수 기여 1위 종목: `{contribution.get('top_symbol')}` / 전체 양수 수익의 {float(contribution.get('top_symbol_share_of_positive_gain') or 0) * 100:.1f}%",
        f"- 자산군 metadata coverage: {float(coverage.get('asset_class') or 0) * 100:.1f}%",
        f"- 시장 regime metadata coverage: {float(coverage.get('market_regime') or 0) * 100:.1f}%",
        "",
        "## 자산군",
        "",
        "| 자산군 | 결과 |",
        "|---|---|",
    ]
    for row in payload.get("by_asset_class") or []:
        item = mapping(row)
        lines.append(f"| `{item.get('asset_class')}` | {cell(item)} |")
    lines.extend(["", "## 시장 regime", "", "| Regime | 결과 |", "|---|---|"])
    for row in payload.get("by_market_regime") or []:
        item = mapping(row)
        lines.append(f"| `{item.get('market_regime')}` | {cell(item)} |")
    lines.extend(
        [
            "",
            "이 검토는 `risk_band=HIGH` 자체가 일반 승패 구분자인지만 판정합니다. 결과를 보고 threshold를 재튜닝하지 않습니다.",
            "",
        ]
    )
    return "\n".join(lines)
