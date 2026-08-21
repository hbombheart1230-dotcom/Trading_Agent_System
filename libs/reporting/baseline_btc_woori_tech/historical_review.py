from __future__ import annotations

import json
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from libs.reporting.evaluation.metrics import performance_metrics

from .contracts import HORIZONS
from .data_provider import evaluate_multihorizon_leading_signal


KST = timezone(timedelta(hours=9))
POLICY_V1 = "q12_btc_5m_leading_signal.v1"
POLICY_V2 = "q12_btc_multihorizon_leading_signal.v2"
REAL_ACCOUNT_TOTAL_DRAG_PCT = 0.28


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _direct_observation(decision: Mapping[str, Any]) -> dict[str, Any] | None:
    observations = (decision.get("btc_signal") or {}).get("observations") or []
    for preferred in ("btc_usd", "btc_krw"):
        for row in observations:
            if row.get("name") == preferred and not row.get("stale") and float(row.get("price") or 0.0) > 0.0:
                return dict(row)
    return None


def _pct(current: float, prior: float | None) -> float | None:
    if current <= 0.0 or prior is None or prior <= 0.0:
        return None
    return round(((current / prior) - 1.0) * 100.0, 6)


def _prior_price(
    *,
    epochs: list[int],
    prices: list[float],
    epoch: int,
    seconds: int,
    tolerance_sec: int = 5 * 60,
) -> float | None:
    target = epoch - seconds
    index = bisect_right(epochs, target) - 1
    if index < 0 or target - epochs[index] > tolerance_sec:
        return None
    return prices[index]


def _krx_open_price(*, epochs: list[int], prices: list[float], epoch: int) -> float | None:
    current = datetime.fromtimestamp(epoch, tz=KST)
    opening = current.replace(hour=9, minute=0, second=0, microsecond=0)
    index = bisect_left(epochs, int(opening.timestamp()))
    if index >= len(epochs) or epochs[index] > epoch:
        return None
    observed = datetime.fromtimestamp(epochs[index], tz=KST)
    return prices[index] if observed.date() == current.date() else None


def _metric(values: Iterable[float]) -> dict[str, Any]:
    raw = performance_metrics(values)
    return {
        "trade_count": int(raw.get("count") or 0),
        "win_rate": float(raw.get("win_rate") or 0.0),
        "avg_return_pct": float(raw.get("average_return_pct") or 0.0),
        "profit_factor": float(raw.get("profit_factor") or 0.0),
        "max_drawdown_pct": float(raw.get("maximum_drawdown_pct") or 0.0),
    }


def build_historical_review(
    *,
    reports_root: Path = Path("reports"),
    output_dir: Path | None = None,
) -> dict[str, str]:
    source_root = reports_root / "evaluation" / "baseline_btc_woori_tech"
    source_days: list[dict[str, Any]] = []
    decisions_by_id: dict[str, dict[str, Any]] = {}
    forward_by_id: dict[str, dict[str, Any]] = {}
    drag_by_id: dict[str, float] = {}
    observations_by_id: dict[str, dict[str, Any]] = {}

    for day_dir in sorted(path for path in source_root.iterdir() if path.is_dir() and path.name[:4].isdigit()):
        decisions_payload = _read(day_dir / "baseline_btc_woori_decisions.json")
        forward_payload = _read(day_dir / "baseline_btc_woori_forward_returns.json")
        decisions = [row for row in decisions_payload.get("decisions") or [] if isinstance(row, dict)]
        forward_rows = [row for row in forward_payload.get("rows") or [] if isinstance(row, dict)]
        if not decisions:
            continue
        source_days.append({"day": day_dir.name, "decision_count": len(decisions)})
        drag = float((forward_payload.get("cost_model") or {}).get("round_trip_cost_pct") or 0.0) + float(
            (forward_payload.get("cost_model") or {}).get("slippage_pct") or 0.0
        )
        for row in decisions:
            decision_id = str(row.get("decision_id") or "")
            if not decision_id:
                continue
            decisions_by_id[decision_id] = row
            observation = _direct_observation(row)
            if observation is not None:
                observations_by_id[decision_id] = observation
            drag_by_id[decision_id] = drag
        for row in forward_rows:
            decision_id = str(row.get("baseline_decision_id") or "")
            if decision_id:
                forward_by_id[decision_id] = row

    series = sorted(
        (
            int(row.get("ts") or 0),
            float(row.get("price") or 0.0),
        )
        for row in observations_by_id.values()
        if int(row.get("ts") or 0) > 0 and float(row.get("price") or 0.0) > 0.0
    )
    deduped = {epoch: price for epoch, price in series}
    epochs = sorted(deduped)
    prices = [deduped[epoch] for epoch in epochs]

    rows: list[dict[str, Any]] = []
    for decision_id, decision in sorted(decisions_by_id.items(), key=lambda item: int(item[1].get("as_of_epoch") or 0)):
        observation = observations_by_id.get(decision_id)
        forward = forward_by_id.get(decision_id)
        if observation is None or forward is None:
            continue
        epoch = int(observation.get("ts") or decision.get("as_of_epoch") or 0)
        price = float(observation.get("price") or 0.0)
        momentum_5m = (decision.get("btc_signal") or {}).get("momentum_5m_pct")
        momentum_5m = float(momentum_5m) if momentum_5m is not None else None
        momentum_15m = _pct(price, _prior_price(epochs=epochs, prices=prices, epoch=epoch, seconds=15 * 60))
        momentum_60m = _pct(price, _prior_price(epochs=epochs, prices=prices, epoch=epoch, seconds=60 * 60))
        momentum_24h = _pct(price, _prior_price(epochs=epochs, prices=prices, epoch=epoch, seconds=24 * 60 * 60))
        momentum_krx = _pct(price, _krx_open_price(epochs=epochs, prices=prices, epoch=epoch))
        leading = evaluate_multihorizon_leading_signal(
            momentum_5m=momentum_5m,
            momentum_15m=momentum_15m,
            momentum_60m=momentum_60m,
            momentum_24h=momentum_24h,
        )
        local = decision.get("local_features") or {}
        local_confirmation = bool(
            local.get("available")
            and (float(local.get("volume_ratio") or 0.0) >= 1.2 or bool(local.get("breakout_confirmed")))
        )
        trend_confirmation = bool(local.get("price_above_vwap_or_short_ma"))
        v1_eligible = bool(
            local.get("available")
            and momentum_5m is not None
            and momentum_5m > 0.0
            and local_confirmation
            and trend_confirmation
        )
        v2_eligible = bool(local.get("available") and leading["leading_positive"] and local_confirmation and trend_confirmation)
        rows.append(
            {
                "decision_id": decision_id,
                "day": str(decision.get("day") or ""),
                "as_of_epoch": int(decision.get("as_of_epoch") or epoch),
                "btc": {
                    "source": observation.get("name"),
                    "price": price,
                    "momentum_5m_pct": momentum_5m,
                    "momentum_15m_pct": momentum_15m,
                    "momentum_60m_pct": momentum_60m,
                    "momentum_24h_pct": momentum_24h,
                    "momentum_since_krx_open_pct": momentum_krx,
                    **leading,
                },
                "conditions": {
                    "local_confirmation": local_confirmation,
                    "trend_confirmation": trend_confirmation,
                },
                "v1_eligible": v1_eligible,
                "v2_eligible": v2_eligible,
                "v2_only": bool(v2_eligible and not v1_eligible),
                "round_trip_drag_pct": drag_by_id.get(decision_id, 0.0),
                "returns": forward.get("returns") or {},
            }
        )

    horizons: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        def values(key: str, *, cost_basis: str) -> list[float]:
            output: list[float] = []
            for row in rows:
                checkpoint = (row.get("returns") or {}).get(horizon) or {}
                if not row.get(key) or checkpoint.get("status") != "observed":
                    continue
                value = float(checkpoint.get("return_pct") or 0.0)
                if cost_basis == "artifact_mock":
                    value -= float(row.get("round_trip_drag_pct") or 0.0)
                elif cost_basis == "real_account":
                    value -= REAL_ACCOUNT_TOTAL_DRAG_PCT
                output.append(value)
            return output

        v1_gross = _metric(values("v1_eligible", cost_basis="gross"))
        v1_net = _metric(values("v1_eligible", cost_basis="artifact_mock"))
        v1_real_net = _metric(values("v1_eligible", cost_basis="real_account"))
        v2_gross = _metric(values("v2_eligible", cost_basis="gross"))
        v2_net = _metric(values("v2_eligible", cost_basis="artifact_mock"))
        v2_real_net = _metric(values("v2_eligible", cost_basis="real_account"))
        v2_only_gross = _metric(values("v2_only", cost_basis="gross"))
        v2_only_net = _metric(values("v2_only", cost_basis="artifact_mock"))
        v2_only_real_net = _metric(values("v2_only", cost_basis="real_account"))
        horizons.append(
            {
                "horizon": horizon,
                "v1_gross": v1_gross,
                "v1_net": v1_net,
                "v1_real_net": v1_real_net,
                "v2_gross": v2_gross,
                "v2_net": v2_net,
                "v2_real_net": v2_real_net,
                "v2_only_gross": v2_only_gross,
                "v2_only_net": v2_only_net,
                "v2_only_real_net": v2_only_real_net,
                "v2_minus_v1": {
                    "trade_count": v2_net["trade_count"] - v1_net["trade_count"],
                    "win_rate": round(v2_net["win_rate"] - v1_net["win_rate"], 6),
                    "avg_return_pct": round(v2_net["avg_return_pct"] - v1_net["avg_return_pct"], 6),
                },
                "v2_minus_v1_gross": {
                    "trade_count": v2_gross["trade_count"] - v1_gross["trade_count"],
                    "win_rate": round(v2_gross["win_rate"] - v1_gross["win_rate"], 6),
                    "avg_return_pct": round(v2_gross["avg_return_pct"] - v1_gross["avg_return_pct"], 6),
                },
                "v2_minus_v1_real": {
                    "trade_count": v2_real_net["trade_count"] - v1_real_net["trade_count"],
                    "win_rate": round(v2_real_net["win_rate"] - v1_real_net["win_rate"], 6),
                    "avg_return_pct": round(v2_real_net["avg_return_pct"] - v1_real_net["avg_return_pct"], 6),
                },
            }
        )

    complete = sum(
        1
        for row in rows
        if all((row.get("btc") or {}).get(field) is not None for field in ("momentum_15m_pct", "momentum_60m_pct", "momentum_24h_pct"))
    )
    episodes: list[dict[str, Any]] = []
    for row in (item for item in rows if item.get("v2_only")):
        if (
            episodes
            and episodes[-1]["day"] == row["day"]
            and int(row["as_of_epoch"]) - int(episodes[-1]["last_epoch"]) <= 30 * 60
        ):
            episodes[-1]["last_epoch"] = row["as_of_epoch"]
            episodes[-1]["decision_ids"].append(row["decision_id"])
            continue
        episodes.append(
            {
                "episode_id": f"Q12V2_{row['day'].replace('-', '')}_{row['as_of_epoch']}",
                "day": row["day"],
                "start_epoch": row["as_of_epoch"],
                "last_epoch": row["as_of_epoch"],
                "decision_ids": [row["decision_id"]],
                "btc": row["btc"],
                "round_trip_drag_pct": row["round_trip_drag_pct"],
                "returns": row["returns"],
            }
        )
    episode_horizons: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        gross: list[float] = []
        real_net: list[float] = []
        artifact_net: list[float] = []
        for episode in episodes:
            checkpoint = (episode.get("returns") or {}).get(horizon) or {}
            if checkpoint.get("status") != "observed":
                continue
            value = float(checkpoint.get("return_pct") or 0.0)
            gross.append(value)
            real_net.append(value - REAL_ACCOUNT_TOTAL_DRAG_PCT)
            artifact_net.append(value - float(episode.get("round_trip_drag_pct") or 0.0))
        episode_horizons.append(
            {
                "horizon": horizon,
                "gross": _metric(gross),
                "real_net": _metric(real_net),
                "artifact_mock_net": _metric(artifact_net),
            }
        )
    episode_30m = next((row for row in episode_horizons if row.get("horizon") == "+30m"), {})
    episode_30m_real = episode_30m.get("real_net") or {}
    conclusion = (
        "PROMISING_SUBSET_PROSPECTIVE_SHADOW_REQUIRED"
        if int(episode_30m_real.get("trade_count") or 0) >= 10
        and float(episode_30m_real.get("avg_return_pct") or 0.0) > 0.0
        else "INSUFFICIENT_OR_NONPOSITIVE_EPISODE_EVIDENCE"
    )
    payload = {
        "schema_version": "q12_v1_v2_historical_review.v1",
        "behavior_effect": "evaluation_only",
        "source": "existing_q12_decisions_and_forward_returns",
        "policies": {"v1": POLICY_V1, "v2": POLICY_V2},
        "cost_bases": {
            "gross": 0.0,
            "artifact_mock": "per-day stored cost profile plus slippage",
            "real_account_total_drag_pct": REAL_ACCOUNT_TOTAL_DRAG_PCT,
        },
        "source_days": source_days,
        "coverage": {
            "day_count": len(source_days),
            "decision_count": len(rows),
            "multihorizon_complete_count": complete,
            "multihorizon_complete_rate": round(complete / len(rows), 6) if rows else 0.0,
            "limitation": "24h requires a stored observation within five minutes of the same time on the prior calendar day.",
        },
        "eligibility": {
            "v1_count": sum(bool(row.get("v1_eligible")) for row in rows),
            "v2_count": sum(bool(row.get("v2_eligible")) for row in rows),
            "v2_only_count": sum(bool(row.get("v2_only")) for row in rows),
        },
        "episode_policy": {
            "scope": "v2_only",
            "merge_gap_sec": 1800,
            "representative": "first_decision_in_episode",
        },
        "episode_count": len(episodes),
        "episode_horizons": episode_horizons,
        "conclusion": conclusion,
        "horizons": horizons,
        "episodes": episodes,
        "rows": rows,
    }
    target = output_dir or source_root / "historical"
    json_path = target / "q12_v1_v2_historical_review.json"
    markdown_path = target / "q12_v1_v2_historical_review.md"
    _write(json_path, payload)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_historical_review(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


def render_historical_review(payload: Mapping[str, Any]) -> str:
    coverage = payload.get("coverage") or {}
    eligibility = payload.get("eligibility") or {}
    lines = [
        "# Q12 v1 vs v2 Historical Review",
        "",
        "- Mode: `evaluation_only`",
        f"- Source days: {coverage.get('day_count')} ({coverage.get('decision_count')} decisions)",
        f"- Complete multi-horizon coverage: {float(coverage.get('multihorizon_complete_rate') or 0):.1%}",
        f"- Eligible: v1={eligibility.get('v1_count')}, v2={eligibility.get('v2_count')}, v2-only={eligibility.get('v2_only_count')}",
        f"- Independent v2-only episodes: {payload.get('episode_count')}",
        f"- Conclusion: `{payload.get('conclusion')}`",
        "- Main execution impact: none",
        "",
        "## Gross Performance",
        "",
        "| Horizon | v1 Trades | v1 Win | v1 Avg | v2 Trades | v2 Win | v2 Avg | Delta Avg | v2-only Avg |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload.get("horizons") or []:
        v1 = row.get("v1_gross") or {}
        v2 = row.get("v2_gross") or {}
        delta = row.get("v2_minus_v1_gross") or {}
        only = row.get("v2_only_gross") or {}
        lines.append(
            f"| {row.get('horizon')} | {v1.get('trade_count')} | {float(v1.get('win_rate') or 0):.1%} | "
            f"{float(v1.get('avg_return_pct') or 0):.4f}% | {v2.get('trade_count')} | "
            f"{float(v2.get('win_rate') or 0):.1%} | {float(v2.get('avg_return_pct') or 0):.4f}% | "
            f"{float(delta.get('avg_return_pct') or 0):+.4f}% | {float(only.get('avg_return_pct') or 0):.4f}% |"
        )
    lines += [
        "",
        "## Independent v2-only Episodes",
        "",
        "Consecutive v2-only decisions within 30 minutes are counted once using the first decision.",
        "",
        "| Horizon | Episodes | Gross Win | Gross Avg | Real-cost Win | Real-cost Avg |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in payload.get("episode_horizons") or []:
        gross = row.get("gross") or {}
        real = row.get("real_net") or {}
        lines.append(
            f"| {row.get('horizon')} | {gross.get('trade_count')} | {float(gross.get('win_rate') or 0):.1%} | "
            f"{float(gross.get('avg_return_pct') or 0):.4f}% | {float(real.get('win_rate') or 0):.1%} | "
            f"{float(real.get('avg_return_pct') or 0):.4f}% |"
        )
    lines += [
        "",
        "## Real Account Cost Performance",
        "",
        f"- Total assumed drag: `{REAL_ACCOUNT_TOTAL_DRAG_PCT:.2f}%`",
        "",
        "| Horizon | v1 Trades | v1 Win | v1 Avg Net | v2 Trades | v2 Win | v2 Avg Net | Delta Avg | v2-only Avg Net |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload.get("horizons") or []:
        v1 = row.get("v1_real_net") or {}
        v2 = row.get("v2_real_net") or {}
        delta = row.get("v2_minus_v1_real") or {}
        only = row.get("v2_only_real_net") or {}
        lines.append(
            f"| {row.get('horizon')} | {v1.get('trade_count')} | {float(v1.get('win_rate') or 0):.1%} | "
            f"{float(v1.get('avg_return_pct') or 0):.4f}% | {v2.get('trade_count')} | "
            f"{float(v2.get('win_rate') or 0):.1%} | {float(v2.get('avg_return_pct') or 0):.4f}% | "
            f"{float(delta.get('avg_return_pct') or 0):+.4f}% | {float(only.get('avg_return_pct') or 0):.4f}% |"
        )
    lines += [
        "",
        "## Artifact Mock Cost Performance",
        "",
        "| Horizon | v1 Avg Net | v2 Avg Net | v2-only Avg Net |",
        "|---|---:|---:|---:|",
    ]
    for row in payload.get("horizons") or []:
        lines.append(
            f"| {row.get('horizon')} | {float((row.get('v1_net') or {}).get('avg_return_pct') or 0):.4f}% | "
            f"{float((row.get('v2_net') or {}).get('avg_return_pct') or 0):.4f}% | "
            f"{float((row.get('v2_only_net') or {}).get('avg_return_pct') or 0):.4f}% |"
        )
    lines += [
        "",
        "## Interpretation Boundary",
        "",
        "- This is a deterministic replay of stored Q12 evidence, not a new market-data backfill.",
        "- Missing 24-hour observations are reported as missing and are not inferred.",
        "- Promotion requires prospective v2 evidence in addition to this historical comparison.",
    ]
    return "\n".join(lines) + "\n"
