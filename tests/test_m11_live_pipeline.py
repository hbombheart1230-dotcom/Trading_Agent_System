from graphs.pipelines.m11_live_pipeline import run_m11_live_pipeline
from libs.read.price_reader import MockPriceReader
from libs.read.portfolio_reader import MockPortfolioReader


class StubExecutor:
    def execute(self, order):  # type: ignore
        return {"ok": True, "dry_run": True, "reason": "stub", "order": order, "executor": "stub"}


def test_run_m11_live_pipeline_builds_decision_and_executes(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_STORE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    # minimal catalog required by execute_from_packet when env is not loaded
    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"주문","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("KIWOOM_REGISTRY_APIS_JSONL", str(cat))

    state = {
        "symbol": "005930",
        "price_reader": MockPriceReader(prices={"005930": 71200}),
        "portfolio_reader": MockPortfolioReader(cash=10_000_000, positions=[]),
        "executor": StubExecutor(),
    }

    out = run_m11_live_pipeline(state)

    assert "decision_packet" in out
    assert out["decision_packet"]["intent"]["action"] in ("BUY", "NOOP")
    assert "execution" in out
    assert "persisted_state" in out
