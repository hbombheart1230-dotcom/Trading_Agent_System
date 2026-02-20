from __future__ import annotations

from typing import Any, Dict

from graphs.nodes.scanner_node import scanner_node


def _trend_up_candles(n: int = 40) -> list[dict]:
    rows: list[dict] = []
    px = 100.0
    for _ in range(n):
        op = px
        cl = px + 1.0
        rows.append(
            {
                "open": op,
                "high": cl + 0.5,
                "low": op - 0.5,
                "close": cl,
                "volume": 1000,
            }
        )
        px = cl
    return rows


def _trend_down_candles(n: int = 40) -> list[dict]:
    rows: list[dict] = []
    px = 140.0
    for _ in range(n):
        op = px
        cl = max(1.0, px - 1.0)
        rows.append(
            {
                "open": op,
                "high": op + 0.5,
                "low": cl - 0.5,
                "close": cl,
                "volume": 1000,
            }
        )
        px = cl
    return rows


def test_m29_2_scanner_uses_feature_engine_map_from_ohlcv():
    state: Dict[str, Any] = {
        "candidates": [{"symbol": "AAA"}, {"symbol": "BBB"}],
        "mock_scan_results": {
            "AAA": {"score": 0.50, "risk_score": 0.20, "confidence": 0.80},
            "BBB": {"score": 0.50, "risk_score": 0.20, "confidence": 0.80},
        },
        "ohlcv_by_symbol": {
            "AAA": _trend_up_candles(),
            "BBB": _trend_down_candles(),
        },
        "policy": {
            "weight_news": 0.0,
            "weight_global": 0.0,
            "risk_news_penalty": 0.0,
            "risk_global_penalty": 0.0,
            "confidence_news_boost": 0.0,
            "feature_score_weight": 0.5,
            "feature_risk_penalty": 0.0,
            "high_vol_risk_penalty": 0.0,
        },
    }

    out = scanner_node(state)
    assert out["selected"]["symbol"] == "AAA"
    assert out["scanner_feature"]["used"] is True
    assert out["scanner_feature"]["source"] == "state.ohlcv_by_symbol"

    rows = {str(r.get("symbol")): r for r in out.get("scan_results", []) if isinstance(r, dict)}
    assert rows["AAA"]["features"]["engine_regime"] in ("trend", "range", "high_volatility")
    assert rows["BBB"]["features"]["engine_regime"] in ("trend", "range", "high_volatility")
    assert float(rows["AAA"]["components"]["feature_signal"]) >= float(rows["BBB"]["components"]["feature_signal"])
