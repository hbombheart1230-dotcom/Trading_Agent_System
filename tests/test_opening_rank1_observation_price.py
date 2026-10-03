import pytest

from libs.runtime.opening_rank1_observation_price import resolve_observation_price
from libs.reporting.trade_report_markdown_clean import _build_summary_llm_evaluation_section


@pytest.mark.parametrize("age,expected", [(60, 47250.0), (121, None), (-60, None)])
def test_missing_selected_price_uses_only_recent_observed_candle(age, expected):
    result = resolve_observation_price(
        selected={}, quote={}, rows=[{"ts": 1000 - age, "close": 47250}], now_epoch=1000,
    )
    assert result["observed_price"] == expected


def test_no_price_is_not_fabricated():
    result = resolve_observation_price(selected={}, quote={}, rows=[], now_epoch=1000)
    assert result == {"observed_price": None, "price_source": "unavailable"}


def test_fresh_quote_fallback():
    result = resolve_observation_price(
        selected={}, quote={"cur": 47300, "_observed_epoch": 990}, rows=[], now_epoch=1000,
    )
    assert result == {"observed_price": 47300.0, "price_source": "market.quote"}


def test_opening_probe_llm_causality_is_not_displayed_as_established():
    summary = {"llm_evaluation": {"root_cause": "volume blocker caused the loss", "priority_actions": ["tighten everything"]}}
    report = {"fact_payload": {"trade": {"entry_summary": {"reason_human": "opening_rank1_controlled_probe"}}}}
    text = "\n".join(_build_summary_llm_evaluation_section(summary, report=report))
    assert "volume blocker caused the loss" not in text
    assert "tighten everything" not in text
    assert "Opening Alpha" in text
    assert summary["llm_evaluation"]["root_cause"] == "volume blocker caused the loss"
