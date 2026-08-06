from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .analysis import analyze_horizon_revision
from .loaders import load_latest_q16_review, load_stage_review_inventory, load_trade_observations
from .report import render_report


def run_horizon_revision_backtest(
    *,
    reports_root: Path,
    start_day: str,
    end_day: str,
    output_dir: Path,
    live_cost_pct: float = 0.28,
    mock_cost_pct: float = 1.086849,
) -> dict[str, Any]:
    observations = load_trade_observations(
        reports_root,
        start_day=start_day,
        end_day=end_day,
    )
    payload = analyze_horizon_revision(
        observations,
        live_cost_pct=live_cost_pct,
        mock_cost_pct=mock_cost_pct,
        stage_inventory=load_stage_review_inventory(
            reports_root,
            start_day=start_day,
            end_day=end_day,
        ),
        q16_review=load_latest_q16_review(reports_root, end_day=end_day),
    )
    payload["range"] = {"start": start_day, "end": end_day}
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "horizon_revision_historical_comparison.json"
    markdown_path = output_dir / "horizon_revision_historical_comparison.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(
        render_report(payload, start_day=start_day, end_day=end_day),
        encoding="utf-8",
    )
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "trade_count": len(payload.get("trade_rows") or []),
    }
