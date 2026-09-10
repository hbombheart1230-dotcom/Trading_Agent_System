from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

from .cohorts import independent_day_symbol_rows
from .contracts import HORIZONS
from .metrics import checkpoint_return, performance


def _asset_family(value: Any) -> str:
    asset_class = str(value or "UNKNOWN")
    if asset_class == "common_stock":
        return "COMMON_STOCK"
    if "etf" in asset_class.lower():
        return "ETF"
    return asset_class.upper()


def _summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    independent = independent_day_symbol_rows(rows)
    return {
        "day_symbol_count": len(independent),
        "horizons": {
            horizon: performance(
                [
                    checkpoint_return(dict(row.get("episode", {})), horizon)
                    for row in independent
                ]
            )
            for horizon in HORIZONS
        },
    }


def _group(
    rows: Sequence[Mapping[str, Any]], dimensions: Sequence[str]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        values = {
            "asset_family": _asset_family(row.get("asset_class")),
            "lane_condition": str(
                row.get("opening_alpha_lane_condition") or "NOT_ELIGIBLE"
            ),
            "risk_band": str(row.get("risk_band") or "MISSING"),
            "candidate_setup": str(row.get("candidate_setup") or "MISSING"),
            "entry_horizon": str(row.get("entry_horizon") or "MISSING"),
        }
        grouped[tuple(values[name] for name in dimensions)].append(row)
    return [
        {
            **{name: value for name, value in zip(dimensions, key)},
            **_summarize(group_rows),
        }
        for key, group_rows in sorted(grouped.items())
    ]


def build_opening_policy_matrix(
    joined: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Observation-only comparison using the established day-symbol unit."""
    independent = independent_day_symbol_rows(joined)
    return {
        "schema_version": "opening_policy_matrix.v1",
        "behavior_effect": "NONE_OBSERVATION_ONLY",
        "behavior_change_authorized": False,
        "unit": "first_opening_episode_per_day_symbol_within_each_discriminator_cell",
        "source_episode_count": len(joined),
        "independent_day_symbol_count": len(independent),
        "asset_class": _group(joined, ("asset_family",)),
        "lane_condition": _group(joined, ("lane_condition",)),
        "risk_band": _group(joined, ("risk_band",)),
        "candidate_setup": _group(joined, ("candidate_setup",)),
        "entry_horizon": _group(joined, ("entry_horizon",)),
        "combined": _group(
            joined,
            (
                "lane_condition",
                "asset_family",
                "risk_band",
                "candidate_setup",
                "entry_horizon",
            ),
        ),
    }


def _metric(value: Mapping[str, Any] | None) -> str:
    row = dict(value or {})
    count = int(row.get("sample_count") or 0)
    if not count:
        return "-"
    return (
        f"N={count}, WR={float(row.get('win_rate') or 0) * 100:.1f}%, "
        f"avg={float(row.get('avg_net_return_pct') or 0):+.4f}%, "
        f"PF={float(row.get('profit_factor') or 0):.4f}"
    )


def render_opening_policy_matrix(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Opening Alpha Policy Matrix",
        "",
        "- Mode: `observation_only`",
        f"- Unit: `{payload.get('unit')}`",
        f"- Independent day-symbols: `{payload.get('independent_day_symbol_count', 0)}`",
        "- This report does not authorize a trading behavior change.",
        "",
        "## Combined Comparison",
        "",
        "| Lane | Asset | Risk | Setup | Horizon | N | +5m | +15m | +30m | +60m | EOD |",
        "|---|---|---|---|---|---:|---|---|---|---|---|",
    ]
    for raw in payload.get("combined") or []:
        row = dict(raw)
        horizons = dict(row.get("horizons") or {})
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                row.get("lane_condition"),
                row.get("asset_family"),
                row.get("risk_band"),
                row.get("candidate_setup"),
                row.get("entry_horizon"),
                int(row.get("day_symbol_count") or 0),
                *[_metric(horizons.get(label)) for label in HORIZONS],
            )
        )
    return "\n".join(lines) + "\n"
