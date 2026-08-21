from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from libs.reporting.baseline_btc_woori_tech.historical_review import build_historical_review


KST = timezone(timedelta(hours=9))


def _epoch(day: str, hour: int, minute: int) -> int:
    return int(datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00+09:00").timestamp())


def _write_day(root: Path, day: str, prices: list[float], five_minute: list[float]) -> None:
    day_dir = root / "evaluation" / "baseline_btc_woori_tech" / day
    day_dir.mkdir(parents=True)
    decisions = []
    forwards = []
    for index, (price, momentum) in enumerate(zip(prices, five_minute)):
        minute = index * 5
        epoch = _epoch(day, 9, minute)
        decision_id = f"BTW_{day.replace('-', '')}_{epoch}"
        eligible = momentum > 0.0
        decisions.append(
            {
                "decision_id": decision_id,
                "day": day,
                "as_of_epoch": epoch,
                "eligible": eligible,
                "btc_signal": {
                    "momentum_5m_pct": momentum,
                    "observations": [
                        {
                            "name": "btc_usd",
                            "ts": epoch,
                            "price": price,
                            "stale": False,
                        }
                    ],
                },
                "local_features": {
                    "available": True,
                    "volume_ratio": 1.5,
                    "breakout_confirmed": False,
                    "price_above_vwap_or_short_ma": True,
                },
            }
        )
        forwards.append(
            {
                "baseline_decision_id": decision_id,
                "returns": {
                    horizon: {"status": "observed", "return_pct": 1.0}
                    for horizon in ("+5m", "+15m", "+30m", "EOD")
                },
            }
        )
    (day_dir / "baseline_btc_woori_decisions.json").write_text(
        json.dumps({"decisions": decisions}), encoding="utf-8"
    )
    (day_dir / "baseline_btc_woori_forward_returns.json").write_text(
        json.dumps(
            {
                "cost_model": {"round_trip_cost_pct": 0.2, "slippage_pct": 0.05},
                "rows": forwards,
            }
        ),
        encoding="utf-8",
    )


def test_historical_review_replays_v2_without_execution(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write_day(reports, "2026-08-20", [100.0, 100.0, 100.0, 100.0, 100.0], [0.1] * 5)
    _write_day(reports, "2026-08-21", [104.0, 105.0, 106.0, 107.0, 106.8], [0.1, 0.1, 0.1, 0.1, -0.19])

    first = build_historical_review(reports_root=reports)
    first_payload = json.loads(Path(first["json"]).read_text(encoding="utf-8"))
    second = build_historical_review(reports_root=reports)
    second_payload = json.loads(Path(second["json"]).read_text(encoding="utf-8"))

    assert first_payload == second_payload
    assert first_payload["behavior_effect"] == "evaluation_only"
    assert first_payload["eligibility"]["v2_count"] == first_payload["eligibility"]["v1_count"] + 1
    assert first_payload["eligibility"]["v2_only_count"] == 1
    assert first_payload["episode_count"] == 1
    assert first_payload["horizons"][0]["v2_only_net"]["avg_return_pct"] == 0.75
    assert first_payload["horizons"][0]["v2_only_real_net"]["avg_return_pct"] == 0.72
    assert "order_intent" not in first_payload
