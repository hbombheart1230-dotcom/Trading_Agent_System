from __future__ import annotations

from scripts.smoke_m20_llm import main


def test_smoke_m20_llm_script_rule_mode_returns_zero(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "rule")
    rc = main(["--symbol", "005930", "--price", "70000", "--cash", "2000000"])
    assert rc == 0


def test_smoke_m20_llm_script_require_openai_fails_when_not_openai(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "rule")
    rc = main(["--require-openai"])
    assert rc == 2
