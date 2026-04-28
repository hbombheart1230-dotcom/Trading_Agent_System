from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.strategist_llm_summary import (
    build_strategist_llm_summary_payload,
    generate_strategist_llm_summary,
    render_strategist_llm_summary_markdown,
)


def test_strategist_llm_summary_surfaces_theme_fallback(tmp_path: Path) -> None:
    response_path = tmp_path / "response.json"
    response_path.write_text(
        json.dumps(
            {
                "stage": "strategist",
                "provider": "OpenRouter",
                "model": "test-model",
                "status": "ok",
                "run_id": "run-1",
                "day": "2026-04-28",
                "saved_at": "2026-04-28T00:00:00+00:00",
                "response_text": json.dumps(
                    {
                        "playbook": "defensive",
                        "selected_themes": [],
                        "theme_strategy": {
                            "selection_mode": "fallback",
                            "fallback_reason": "available_themes empty",
                        },
                        "rationale": "defensive best 및 worst overlap",
                        "strategy_adjustment_directives": {
                            "entry_policy_action": {
                                "action": "tighten",
                                "target_fields": ["volume_ratio_min"],
                                "reason": "loss-heavy",
                            },
                            "selected_symbol_bias_action": {"action": "none", "reason": "no memory"},
                        },
                        "monitor_entry_policy": {"enabled": True, "volume_ratio_min": 0.75},
                    },
                    ensure_ascii=False,
                ),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = build_strategist_llm_summary_payload(response_path)
    md = render_strategist_llm_summary_markdown(payload)

    assert payload["schema_version"] == "strategist_llm_summary.v1"
    assert payload["strategy_frame"]["theme_selection_mode"] == "fallback"
    assert payload["strategy_frame"]["selected_themes"] == []
    assert "selected_themes가 비어" in payload["operator_readout"]["issues"][0]
    assert "Strategist LLM Summary" in md
    assert "available_themes empty" in md


def test_generate_strategist_llm_summary_writes_md_and_json(tmp_path: Path) -> None:
    response_path = tmp_path / "response.json"
    response_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "response_text": json.dumps({"playbook": "trend", "selected_themes": ["반도체"]}, ensure_ascii=False),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    md_path, json_path, payload = generate_strategist_llm_summary(response_path)

    assert md_path == tmp_path / "strategist_summary.md"
    assert json_path == tmp_path / "strategist_summary.json"
    assert md_path.exists()
    assert json_path.exists()
    assert payload["strategy_frame"]["selected_themes"] == ["반도체"]
