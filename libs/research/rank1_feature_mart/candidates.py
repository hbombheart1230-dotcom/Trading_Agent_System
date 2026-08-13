from __future__ import annotations

from statistics import mean
from typing import Any, Mapping, Sequence

from .integrity import value_at
from .trees import ENTRY_FEATURES, HORIZON_FEATURES, SCANNER_FEATURES


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _category(value: Any) -> str:
    return "MISSING" if value in (None, "", "MISSING", "INSUFFICIENT_HISTORY") else str(value)


def _branch_rows(rows: Sequence[Mapping[str, Any]], feature: str, category: str) -> list[Mapping[str, Any]]:
    return [row for row in rows if _category(value_at(row, feature)) == category]


def _metrics(rows: Sequence[Mapping[str, Any]], target: str) -> dict[str, Any]:
    values = [value for row in rows if (value := _number(value_at(row, f"outcomes.checkpoints.{target}.net_return_pct"))) is not None]
    first_by_day_symbol: dict[tuple[str, str], float] = {}
    for row in sorted(rows, key=lambda item: int(value_at(item, "identity.decision_epoch") or 0)):
        value = _number(value_at(row, f"outcomes.checkpoints.{target}.net_return_pct"))
        if value is None:
            continue
        key = (str(value_at(row, "identity.day") or ""), str(value_at(row, "identity.symbol") or ""))
        first_by_day_symbol.setdefault(key, value)
    independent = list(first_by_day_symbol.values())
    return {
        "sample_count": len(values),
        "day_symbol_count": len(independent),
        "win_rate": round(sum(value > 0.0 for value in values) / len(values), 4) if values else None,
        "avg_net_return_pct": round(mean(values), 4) if values else None,
        "day_symbol_win_rate": round(sum(value > 0.0 for value in independent) / len(independent), 4) if independent else None,
        "day_symbol_avg_net_return_pct": round(mean(independent), 4) if independent else None,
    }


def select_candidates(
    rows: Sequence[Mapping[str, Any]],
    *,
    validation_start: str = "2026-08-01",
    selection_end_day: str = "2026-08-11",
    limit: int = 2,
) -> dict[str, Any]:
    selection_rows = [row for row in rows if str(value_at(row, "identity.day") or "") <= selection_end_day]
    train = [row for row in selection_rows if str(value_at(row, "identity.day") or "") < validation_start]
    validation = [row for row in selection_rows if str(value_at(row, "identity.day") or "") >= validation_start]
    definitions = {
        "SCANNER": (SCANNER_FEATURES, "+30m"),
        "ENTRY": (ENTRY_FEATURES, "+15m"),
        "HORIZON": (HORIZON_FEATURES, "EOD"),
    }
    evaluated = []
    eligible = []
    for responsibility, (features, target) in definitions.items():
        for feature in features:
            categories = sorted({_category(value_at(row, feature)) for row in rows} - {"MISSING"})
            for category in categories:
                train_metrics = _metrics(_branch_rows(train, feature, category), target)
                validation_metrics = _metrics(_branch_rows(validation, feature, category), target)
                train_avg = train_metrics["avg_net_return_pct"]
                validation_avg = validation_metrics["avg_net_return_pct"]
                same_direction = bool(
                    train_avg is not None
                    and validation_avg is not None
                    and train_avg != 0.0
                    and validation_avg != 0.0
                    and (train_avg > 0.0) == (validation_avg > 0.0)
                )
                evidence_ready = (
                    train_metrics["sample_count"] >= 5
                    and validation_metrics["sample_count"] >= 3
                    and train_metrics["day_symbol_count"] >= 5
                    and validation_metrics["day_symbol_count"] >= 3
                )
                item = {
                    "responsibility": responsibility,
                    "feature": feature,
                    "category": category,
                    "target": target,
                    "train": train_metrics,
                    "validation": validation_metrics,
                    "same_direction": same_direction,
                    "evidence_ready": evidence_ready,
                    "decision": "ELIGIBLE_FOR_PROSPECTIVE_SHADOW" if same_direction and evidence_ready else "RETAIN_RESEARCH_ONLY",
                }
                evaluated.append(item)
                if item["decision"] == "ELIGIBLE_FOR_PROSPECTIVE_SHADOW":
                    eligible.append(item)
    eligible.sort(
        key=lambda item: (
            min(abs(item["train"]["avg_net_return_pct"]), abs(item["validation"]["avg_net_return_pct"])),
            item["train"]["sample_count"] + item["validation"]["sample_count"],
        ),
        reverse=True,
    )
    return {
        "schema_version": "rank1_candidate_selection.v1",
        "behavior_effect": "NONE_OFFLINE_RESEARCH_ONLY",
        "selection_period": {"validation_start": validation_start, "selection_end_day": selection_end_day},
        "eligibility_rule": "train episodes/day-symbols >=5, validation episodes/day-symbols >=3, same non-zero return direction",
        "evaluated_branch_count": len(evaluated),
        "eligible_branch_count": len(eligible),
        "prospective_shadow_candidates": eligible[:limit],
        "all_branch_evaluations": evaluated,
    }
