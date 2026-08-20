from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from libs.reporting.quant_shadow_candidate_evaluation import (
    load_quant_shadow_candidate_payloads_for_range,
)
from libs.reporting.q9_forward_candles import (
    FORWARD_DATA_SOURCE,
    load_q9_forward_candles,
)
from libs.runtime.broker_cost_profile import load_broker_cost_profile

from .scanner_quality import (
    build_scanner_quality_review,
    extract_pre_strategist_candidate_rows,
)


DEFAULT_EVALUATION_SLIPPAGE_PCT = 0.05
LIVE_BUY_FEE_RATE = 0.00015
LIVE_SELL_FEE_RATE = 0.00015
LIVE_EQUITY_SELL_TAX_RATE_2026 = 0.002


def _pct(value: float) -> float:
    return round(float(value) * 100.0, 6)


def build_evaluation_cost_bases(
    profile: Mapping[str, Any] | None,
    *,
    slippage_pct: float = DEFAULT_EVALUATION_SLIPPAGE_PCT,
) -> dict[str, Any]:
    observed = dict(profile or {})
    mock_ratio = float(
        observed.get("conservative_round_trip_cost_pct")
        or observed.get("ema_round_trip_cost_pct")
        or 0.009
    )
    live_ratio = LIVE_BUY_FEE_RATE + LIVE_SELL_FEE_RATE + LIVE_EQUITY_SELL_TAX_RATE_2026
    return {
        "schema_version": "evaluation_cost_bases.v1",
        "primary_interpretation": "show_both_no_automatic_policy_change",
        "slippage_pct": round(float(slippage_pct), 6),
        "mock_observed": {
            "purpose": "mock_broker_pnl_and_mock_cash_truth",
            "source": str(observed.get("source") or "fallback"),
            "sample_count": int(observed.get("sample_count") or 0),
            "round_trip_cost_pct": _pct(mock_ratio),
            "total_drag_with_slippage_pct": round(_pct(mock_ratio) + float(slippage_pct), 6),
        },
        "live_deployment_equity": {
            "purpose": "real_account_strategy_evaluation",
            "source": "kiwoom_openapi_standard_equity_assumption_2026",
            "buy_fee_pct": _pct(LIVE_BUY_FEE_RATE),
            "sell_fee_pct": _pct(LIVE_SELL_FEE_RATE),
            "sell_tax_pct": _pct(LIVE_EQUITY_SELL_TAX_RATE_2026),
            "round_trip_cost_pct": _pct(live_ratio),
            "total_drag_with_slippage_pct": round(_pct(live_ratio) + float(slippage_pct), 6),
            "scope": "KRX listed equities; ETF/ETN tax treatment must be resolved by instrument type",
        },
    }


def _topk_rows(review: Mapping[str, Any]) -> dict[tuple[int, str], dict[str, Any]]:
    topk = review.get("topk_forward_performance")
    topk = topk if isinstance(topk, Mapping) else {}
    return {
        (int(row.get("top_k") or 0), str(row.get("horizon") or "")): dict(row)
        for row in topk.get("rows") or []
        if isinstance(row, Mapping)
    }


def build_cost_basis_comparison(
    *,
    reports_root: Path,
    start: str,
    end: str,
    cost_profile_path: Path | None = None,
    slippage_pct: float = DEFAULT_EVALUATION_SLIPPAGE_PCT,
) -> dict[str, Any]:
    payloads = load_quant_shadow_candidate_payloads_for_range(
        reports_root=Path(reports_root),
        start=start,
        end=end,
    )
    profile = load_broker_cost_profile(cost_profile_path)
    bases = build_evaluation_cost_bases(profile, slippage_pct=slippage_pct)
    pre_strategist_rows = extract_pre_strategist_candidate_rows(payloads)
    forward_candles = load_q9_forward_candles(
        pre_strategist_rows,
        allow_fresh_fetch=start[:10] == end[:10],
        run_id_prefix="q9_cost_basis_forward_recovery",
    )
    mock_cost = float(bases["mock_observed"]["round_trip_cost_pct"])
    live_cost = float(bases["live_deployment_equity"]["round_trip_cost_pct"])
    mock_review = build_scanner_quality_review(
        payloads,
        cost_pct=mock_cost,
        slippage_pct=slippage_pct,
        minute_rows_by_symbol=forward_candles,
    )
    live_review = build_scanner_quality_review(
        payloads,
        cost_pct=live_cost,
        slippage_pct=slippage_pct,
        minute_rows_by_symbol=forward_candles,
    )
    mock_rows = _topk_rows(mock_review)
    live_rows = _topk_rows(live_review)
    rows: list[dict[str, Any]] = []
    for key in sorted(mock_rows, key=lambda item: (item[1], item[0])):
        mock_row = mock_rows[key]
        live_row = live_rows.get(key, {})
        gross = mock_row.get("gross") if isinstance(mock_row.get("gross"), Mapping) else {}
        mock_net = mock_row.get("net") if isinstance(mock_row.get("net"), Mapping) else {}
        live_net = live_row.get("net") if isinstance(live_row.get("net"), Mapping) else {}
        rows.append({
            "top_k": key[0],
            "horizon": key[1],
            "window_count": int(mock_row.get("window_count") or 0),
            "observed_day_count": int(mock_row.get("observed_day_count") or 0),
            "gross": dict(gross),
            "mock_net": dict(mock_net),
            "live_net": dict(live_net),
            "expectancy_delta_live_minus_mock_pct": round(
                float(live_net.get("expectancy_pct") or 0.0)
                - float(mock_net.get("expectancy_pct") or 0.0),
                4,
            ),
        })
    return {
        "schema_version": "q9_cost_basis_comparison.v1",
        "behavior_effect": "evaluation_only",
        "cohort_scope": "all_pre_strategist_windows_with_observed_horizon",
        "forward_data_source": FORWARD_DATA_SOURCE,
        "range": {"start": start[:10], "end": end[:10]},
        "cost_bases": bases,
        "pre_strategist_universe_available": bool(
            mock_review.get("pre_strategist_universe_available")
        ),
        "rows": rows,
        "interpretation": {
            "mock_net": "Can the signal overcome Kiwoom mock-account friction?",
            "live_net": "Could the signal overcome the stated real-account equity assumptions?",
            "policy_change_authorized": False,
        },
    }


def render_cost_basis_comparison(payload: Mapping[str, Any]) -> str:
    date_range = payload.get("range") or {}
    bases = payload.get("cost_bases") or {}
    mock = bases.get("mock_observed") or {}
    live = bases.get("live_deployment_equity") or {}
    lines = [
        f"# Cost Basis Comparison ({date_range.get('start')} ~ {date_range.get('end')})",
        "",
        "Evaluation-only. Runtime entry, exit, and broker accounting are unchanged.",
        f"Forward data source: `{payload.get('forward_data_source') or 'unknown'}`.",
        f"Cohort scope: `{payload.get('cohort_scope') or 'unknown'}`.",
        "",
        "## Cost Assumptions",
        "",
        "| Basis | Round Trip | Slippage | Total Drag | Purpose |",
        "|---|---:|---:|---:|---|",
        f"| Mock observed | {float(mock.get('round_trip_cost_pct') or 0):.4f}% | "
        f"{float(bases.get('slippage_pct') or 0):.4f}% | "
        f"{float(mock.get('total_drag_with_slippage_pct') or 0):.4f}% | Mock PnL/cash truth |",
        f"| Live equity assumption | {float(live.get('round_trip_cost_pct') or 0):.4f}% | "
        f"{float(bases.get('slippage_pct') or 0):.4f}% | "
        f"{float(live.get('total_drag_with_slippage_pct') or 0):.4f}% | Deployment evaluation |",
        "",
        "## Pre-Strategist Scanner Top-K",
        "",
        "| Top-K | Horizon | Windows/Days | Gross | Mock Net | Live Net | Live-Mock Delta |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in payload.get("rows") or []:
        gross = row.get("gross") or {}
        mock_net = row.get("mock_net") or {}
        live_net = row.get("live_net") or {}
        lines.append(
            f"| {row.get('top_k')} | {row.get('horizon')} | "
            f"{row.get('window_count')}/{row.get('observed_day_count')} | "
            f"{float(gross.get('expectancy_pct') or 0):.4f}% | "
            f"{float(mock_net.get('expectancy_pct') or 0):.4f}% | "
            f"{float(live_net.get('expectancy_pct') or 0):.4f}% | "
            f"{float(row.get('expectancy_delta_live_minus_mock_pct') or 0):+.4f}% |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- Mock net answers whether the signal beats the mock account's observed friction.",
        "- Live net answers whether it beats the explicit 2026 KRX equity assumption.",
        "- ETF/ETN tax treatment requires instrument classification and is not inferred here.",
        "- This report does not authorize a trading-policy change.",
    ]
    return "\n".join(lines) + "\n"


def write_cost_basis_comparison(
    *,
    reports_root: Path,
    start: str,
    end: str,
    output_dir: Path,
    cost_profile_path: Path | None = None,
) -> dict[str, str]:
    payload = build_cost_basis_comparison(
        reports_root=reports_root,
        start=start,
        end=end,
        cost_profile_path=cost_profile_path,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "cost_basis_comparison.json"
    markdown_path = output_dir / "cost_basis_comparison.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_cost_basis_comparison(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


__all__ = [
    "build_cost_basis_comparison",
    "build_evaluation_cost_bases",
    "render_cost_basis_comparison",
    "write_cost_basis_comparison",
]
