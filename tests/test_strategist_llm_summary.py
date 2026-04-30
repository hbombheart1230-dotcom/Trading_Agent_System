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


def test_strategist_llm_summary_surfaces_canonical_memory_and_news(tmp_path: Path) -> None:
    response_path = (
        tmp_path
        / "reports"
        / "llm"
        / "2026-04-29"
        / "run-1"
        / "strategist"
        / "response.json"
    )
    response_path.parent.mkdir(parents=True)
    response_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "run_id": "run-1",
                "day": "2026-04-29",
                "response_text": json.dumps(
                    {"playbook": "defensive", "selected_themes": ["휴대폰_RF부품"]},
                    ensure_ascii=False,
                ),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    canonical_path = tmp_path / "reports" / "canonical" / "2026-04-29" / "run-1" / "strategist.json"
    canonical_path.parent.mkdir(parents=True)
    canonical_path.write_text(
        json.dumps(
            {
                "memory_usage_trace": {
                    "active_layers": ["daily", "weekly"],
                    "priority_order": ["daily", "weekly", "monthly", "symbol"],
                    "human_summary": "Active memory layers: daily, weekly",
                    "applied_to_strategy": {
                        "playbook_effect": "maintain_defensive",
                        "risk_posture_effect": "defensive",
                        "scanner_guidance_effect": "source_weight_delta",
                        "monitor_policy_effect": "memory_delta",
                    },
                    "layer_decisions": {
                        "daily": {
                            "status": "ok",
                            "active": True,
                            "used": True,
                            "effect": "primary_strategy_memory",
                            "operator_summary": {"available": True, "trade_count": 3, "win_rate": 0.33},
                        }
                    },
                },
                "news_usage_trace": {
                    "query_targets": ["휴대폰_RF부품", "코스피"],
                    "human_summary": "News was used for market/theme context.",
                    "market_effect": "context only",
                    "playbook_effect": "kept defensive",
                    "scanner_guidance_effect": "ranking context",
                    "monitor_policy_effect": "does not relax monitor gate",
                    "market_headlines_used": ["코스피 headline"],
                    "candidate_headlines_used": ["휴대폰 headline"],
                },
                "news_query_reasoning": "theme hints expanded queries",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    md_path, _json_path, payload = generate_strategist_llm_summary(response_path)
    md = md_path.read_text(encoding="utf-8")

    assert payload["memory_usage"]["active_layers"] == ["daily", "weekly"]
    assert payload["news_usage"]["query_targets"][:2] == ["휴대폰_RF부품", "코스피"]
    assert "### 메모리 사용" in md
    assert "### 뉴스 사용" in md
    assert "휴대폰_RF부품" in md
