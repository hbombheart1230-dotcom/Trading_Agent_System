import time

from graphs.pipelines.m10_live_pipeline import run_m10_live_pipeline
from libs.read.price_reader import MockPriceReader
from libs.read.portfolio_reader import MockPortfolioReader


class StubExecutor:
    def execute(self, order: dict) -> dict:  # type: ignore
        # mimic executor result shape expected downstream
        return {"ok": True, "dry_run": True, "reason": "stub-dry-run", "order": order, "executor": "stub"}


def test_run_m10_live_pipeline_end_to_end(tmp_path, monkeypatch):
    # state store path for this test
    monkeypatch.setenv("STATE_STORE_PATH", str(tmp_path / "state.json"))

    # minimal catalog required by execute_from_packet when env is not loaded
    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"주문","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("KIWOOM_REGISTRY_APIS_JSONL", str(cat))

    # minimal decision_packet (shape compatible with execute_from_packet in project)
    decision_packet = {
        "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 70000, "order_type": "limit"},
        "risk": {"daily_pnl_ratio": 0.0, "last_order_epoch": 0, "open_positions": 0, "per_trade_risk_ratio": 0.0},
        "exec_context": {"mode": "mock", "executor": "stub"},
    }

    state = {
        "symbol": "005930",
        "decision_packet": decision_packet,
        "price_reader": MockPriceReader(prices={"005930": 71200}),
        "portfolio_reader": MockPortfolioReader(cash=10000000, positions=[]),
        # inject executor into state if execute_from_packet supports it
        "executor": StubExecutor(),
    }

    out = run_m10_live_pipeline(state)
    assert "snapshots" in out
    assert "risk_context" in out
    assert "execution" in out
    assert "persisted_state" in out
