from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from libs.research.post_reclaim_alpha.episodes import build_independent_episodes
from libs.research.post_reclaim_alpha.evaluator import (
    build_decision,
    evaluate_episodes,
    scanner_baseline_for_days,
    summarize_horizon,
)
from libs.research.post_reclaim_alpha.kiwoom_history import (
    KiwoomHistoricalMinuteReader,
)
from libs.research.post_reclaim_alpha.executable_policy import (
    apply_executable_filter,
    evaluate_executable_policy,
)


def _candidate(epoch: int, *, symbol: str = "005930") -> dict:
    return {
        "_payload_day": "2026-07-30",
        "_source_path": "fixture.json",
        "symbol": symbol,
        "shadow_role": "top_pick",
        "reason": "below_vwap_reclaim_not_ready",
        "shadow_forward_base": {
            "baseline_epoch": epoch,
            "baseline_price": 100.0,
            "baseline_raw_ts": "20260730090000",
        },
        "below_vwap_reclaim_observation": {
            "subtype_v2": "confirmed_post_reclaim_pullback"
        },
        "quant_factor_snapshot": {"factors": {"volume_ratio": 1.1}},
    }


def test_episode_builder_is_deterministic_and_uses_first_observation() -> None:
    rows = [
        _candidate(1000),
        _candidate(1000),
        _candidate(1100),
        _candidate(2000),
    ]

    result = build_independent_episodes(rows)

    assert result["raw_candidate_count"] == 4
    assert result["canonical_candidate_count"] == 3
    assert result["episode_count"] == 2
    assert [row["baseline_epoch"] for row in result["episodes"]] == [1000, 2000]


def test_forward_evaluation_applies_fixed_live_and_mock_costs() -> None:
    base = 1785369600
    episodes = [
        {
            "episode_id": "e1",
            "day": "2026-07-30",
            "symbol": "005930",
            "baseline_epoch": base,
            "baseline_price": 100.0,
        }
    ]
    candles = {
        "005930": [
            {
                "ts": base + minute * 60,
                "open": 100.0,
                "high": 101.0 + minute / 100,
                "low": 99.0,
                "close": 100.0 + minute / 10,
            }
            for minute in range(0, 91)
        ]
    }

    result = evaluate_episodes(episodes, minute_rows_by_symbol=candles)
    checkpoint = result[0]["checkpoints"]["+5m"]

    assert checkpoint["gross_return_pct"] == 0.5
    assert checkpoint["live_net_return_pct"] == 0.22
    assert checkpoint["mock_net_return_pct"] == -0.5868
    assert checkpoint["mfe_pct"] == 1.05
    assert checkpoint["mae_pct"] == -1.0


def test_forward_evaluation_carries_recent_price_across_sparse_bar() -> None:
    base = 1785369600
    episodes = [
        {
            "episode_id": "sparse",
            "day": "2026-07-30",
            "symbol": "005930",
            "baseline_epoch": base,
            "baseline_price": 100.0,
        }
    ]
    candles = {
        "005930": [
            {"ts": base, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0},
            {"ts": base + 29 * 60, "open": 101.0, "high": 101.0, "low": 101.0, "close": 101.0},
            {"ts": base + 35 * 60, "open": 102.0, "high": 102.0, "low": 102.0, "close": 102.0},
        ]
    }

    result = evaluate_episodes(episodes, minute_rows_by_symbol=candles)
    checkpoint = result[0]["checkpoints"]["+30m"]

    assert checkpoint["status"] == "observed"
    assert checkpoint["delay_sec"] == -60
    assert checkpoint["observation_method"] == "last_price_carried_forward"
    assert checkpoint["live_net_return_pct"] == 0.72


def test_scanner_baseline_filters_to_episode_days() -> None:
    review = {
        "episode_scanner_review": {
            "episodes": [
                {
                    "day": "20260730",
                    "rank_bucket": "rank1",
                    "returns": {"+30m": 1.0},
                },
                {
                    "day": "20260729",
                    "rank_bucket": "rank1",
                    "returns": {"+30m": -5.0},
                },
            ]
        }
    }

    baseline = scanner_baseline_for_days(review, days={"2026-07-30"})

    assert baseline["horizons"]["+30m"]["gross"]["count"] == 1
    assert baseline["horizons"]["+30m"]["live_net"]["expectancy_pct"] == 0.72


def test_missing_forward_history_retains_shadow_instead_of_fabricating_edge() -> None:
    episodes = [
        {
            "episode_id": f"e{index}",
            "day": f"2026-07-{index + 1:02d}",
            "symbol": f"{index:06d}",
            "baseline_epoch": 1000 + index,
            "baseline_price": 100.0,
            "checkpoints": {},
        }
        for index in range(20)
    ]
    summaries = [
        summarize_horizon(episodes, horizon)
        for horizon in ("+15m", "+30m")
    ]

    decision = build_decision(
        episodes=episodes,
        summaries=summaries,
        scanner_baseline={},
    )

    assert decision["decision"] == "RETAIN_SHADOW"
    assert decision["evidence_gates"]["forward_coverage_30m"] is False


def test_kiwoom_history_retries_global_rate_limit(monkeypatch) -> None:
    class FakeToken:
        def ensure_token(self, *, dry_run: bool):
            assert dry_run is False
            return SimpleNamespace(token="token", action="ok", reason="")

        def auth_headers(self, token: str):
            assert token == "token"
            return {"Authorization": "Bearer token"}

    class FakeHttp:
        def __init__(self):
            self.calls = 0

        def request(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                payload = {
                    "return_code": 5,
                    "return_msg": (
                        "허용된 요청 개수를 초과하였습니다"
                        "[1700:허용된 API 요청 개수를 초과하였습니다.]"
                    ),
                }
            else:
                payload = {
                    "return_code": 0,
                    "stk_min_pole_chart_qry": [
                        {
                            "cntr_tm": "20260730100000",
                            "cur_prc": "100",
                            "open_pric": "99",
                            "high_pric": "101",
                            "low_pric": "98",
                            "trde_qty": "10",
                        }
                    ],
                }
            return "url", SimpleNamespace(
                text=json.dumps(payload),
                headers={"cont-yn": "N"},
            )

    ticks = iter([0.0, 2.0, 4.0, 6.0])
    monkeypatch.setattr(
        "libs.research.post_reclaim_alpha.kiwoom_history.time.monotonic",
        lambda: next(ticks),
    )
    monkeypatch.setattr(
        "libs.research.post_reclaim_alpha.kiwoom_history.time.sleep",
        lambda _seconds: None,
    )
    http = FakeHttp()
    reader = KiwoomHistoricalMinuteReader(
        settings=SimpleNamespace(
            kiwoom_app_key="",
            kiwoom_app_secret="",
        ),
        http=http,
        token=FakeToken(),
    )

    rows, meta = reader.fetch_until(
        symbol="005930",
        minimum_epoch=9999999999,
        max_pages=1,
    )

    assert http.calls == 2
    assert len(rows) == 1
    assert meta["page_count"] == 1
    assert meta["error"] == ""


def test_executable_filter_uses_only_pre_entry_prints() -> None:
    base = 1785369600
    episodes = [
        {
            "episode_id": "e1",
            "day": "2026-07-30",
            "symbol": "005930",
            "baseline_epoch": base,
        }
    ]
    candles = {
        "005930": [
            {"ts": base - minute * 60}
            for minute in range(1, 13)
        ]
        + [{"ts": base + minute * 60} for minute in range(0, 20)]
    }

    result = apply_executable_filter(
        episodes,
        minute_rows_by_symbol=candles,
    )

    policy = result[0]["executable_policy"]
    assert policy["prior_print_minutes"] == 12
    assert policy["eligible"] is True


def test_executable_policy_decision_is_deterministic() -> None:
    kst = timezone(timedelta(hours=9))
    episodes = []
    candles: dict[str, list[dict]] = {}
    for index in range(25):
        day = "2026-06-10" if index < 8 else "2026-07-10"
        symbol = f"{index:06d}"
        epoch = int(
            datetime.fromisoformat(f"{day}T10:{index:02d}:00").replace(
                tzinfo=kst
            ).timestamp()
        )
        episodes.append(
            {
                "episode_id": f"e{index}",
                "day": day,
                "symbol": symbol,
                "baseline_epoch": epoch,
                "checkpoints": {
                    "+30m": {
                        "status": "observed",
                        "live_net_return_pct": 0.5,
                    }
                },
            }
        )
        candles[symbol] = [
            {"ts": epoch - minute * 60}
            for minute in range(1, 13)
        ]

    first = evaluate_executable_policy(
        episodes,
        minute_rows_by_symbol=candles,
    )
    second = evaluate_executable_policy(
        episodes,
        minute_rows_by_symbol=candles,
    )

    assert first == second
    assert first["decision"] == "REJECT"
    assert first["gate_results"]["validation_day_concentration"] is False


def test_executable_policy_rejects_insufficient_samples() -> None:
    payload = evaluate_executable_policy([], minute_rows_by_symbol={})

    assert payload["decision"] == "REJECT"
    assert payload["gate_results"]["train_observed_count"] is False
    assert payload["gate_results"]["validation_observed_count"] is False
