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


def test_strategist_llm_summary_surfaces_strategy_detail_from_canonical(tmp_path: Path) -> None:
    response_path = tmp_path / "reports" / "llm" / "2026-05-06" / "run-2" / "strategist" / "response.json"
    response_path.parent.mkdir(parents=True)
    response_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "run_id": "run-2",
                "day": "2026-05-06",
                "response_text": json.dumps(
                    {
                        "playbook": "defensive",
                        "selected_themes": [],
                        "tactical_strategy": "defensive_observe",
                    },
                    ensure_ascii=False,
                ),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    canonical_path = tmp_path / "reports" / "canonical" / "2026-05-06" / "run-2" / "strategist.json"
    canonical_path.parent.mkdir(parents=True)
    canonical_path.write_text(
        json.dumps(
            {
                "playbook": "breakout",
                "pre_llm_playbook": "defensive",
                "llm_requested_playbook": "breakout",
                "requested_playbook": "breakout",
                "requested_playbook_source": "llm",
                "final_playbook": "breakout",
                "tactical_strategy": "opening_range_breakout",
                "strategy_scores": {
                    "opening_range_breakout": 0.82,
                    "defensive_observe": 0.18,
                },
                "rejected_strategy_reasons": {
                    "defensive_observe": "risk_on tape supports active watch",
                },
                "candidate_watch_policy": {
                    "behavior_effect": "visibility_only",
                    "max_priority_rank": 7,
                    "max_runner_ups": 4,
                    "cascade_enabled": True,
                    "reason": "breakout tape supports rank expansion",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = build_strategist_llm_summary_payload(response_path)
    md = render_strategist_llm_summary_markdown(payload)

    detail = payload["strategy_detail"]
    assert detail["pre_llm_playbook"] == "defensive"
    assert detail["llm_requested_playbook"] == "breakout"
    assert detail["final_playbook"] == "breakout"
    assert detail["tactical_strategy"] == "opening_range_breakout"
    assert detail["candidate_watch_policy"]["max_priority_rank"] == 7
    assert "### 전략 디테일" in md
    assert "전략 강화 필드: 적용됨" in md
    assert "플레이북 흐름: defensive -> breakout -> breakout (source=llm)" in md
    assert "선택 전술: opening_range_breakout" in md
    assert "opening_range_breakout" in md
    assert "후보 감시 제안: 7위까지 / 차순위 4개 / cascade 활성" in md
    assert "#### 전략 점수" in md
    assert "opening_range_breakout: 0.82 (선택)" in md
    assert "defensive_observe: 0.18" in md
    assert "#### 제외 전략 이유" in md
    assert "defensive_observe: risk_on tape supports active watch" in md
    assert "strategy_scores:" not in md
    assert "rejected_strategy_reasons:" not in md
    assert "candidate_watch_reason" not in md
    assert "breakout tape supports rank expansion" not in md


def test_strategist_llm_summary_renders_stage3_hold_review_without_market_frame_blanks(tmp_path: Path) -> None:
    run_id = "c" * 32
    response_path = (
        tmp_path
        / "reports"
        / "llm"
        / "2026-05-11"
        / "trade_executed"
        / run_id
        / "strategist_stage3_hold_review"
        / "response.json"
    )
    response_path.parent.mkdir(parents=True)
    response_path.write_text(
        json.dumps(
            {
                "status": "ok",
                "model": "test-model",
                "run_id": run_id,
                "day": "2026-05-11",
                "stage_index": 3,
                "stage_name": "stale_intraday_hold_review",
                "call_kind": "stale_intraday_hold_review",
                "stage_component": "strategist_stage3_hold_review",
                "response_text": json.dumps(
                    {
                        "hold_review_decision": "tighten_exit",
                        "exit_pressure": "medium",
                        "thesis_status": "weakened",
                        "monitor_adjustment": {
                            "tighten_stop": True,
                            "tighten_time_decay": True,
                            "allow_profit_recovery_wait": False,
                            "next_check_minutes": 5,
                        },
                        "priority_exit_triggers": ["vwap_breakdown", "time_decay"],
                        "next_check_minutes": 5,
                        "reason": "현재 포지션의 테제가 약화되어 출구 조건을 강화합니다.",
                    },
                    ensure_ascii=False,
                ),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    canonical_path = tmp_path / "reports" / "canonical" / "2026-05-11" / run_id / "strategist.json"
    canonical_path.parent.mkdir(parents=True)
    canonical_path.write_text(
        json.dumps(
            {
                "final_playbook": "pullback",
                "tactical_strategy": "vwap_reclaim_pullback",
                "candidate_watch_policy": {"max_priority_rank": 5, "max_runner_ups": 4, "cascade_enabled": True},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    md_path, _json_path, payload = generate_strategist_llm_summary(response_path)
    md = md_path.read_text(encoding="utf-8")

    assert payload["source_canonical_strategist_json"] == str(canonical_path)
    assert payload["stage_decision"]["decision"] == "tighten_exit"
    assert payload["operator_readout"]["headline"] == "stale_intraday_hold_review / decision=tighten_exit"
    assert "단계별 전략가 LLM 출력" in md
    assert "decision: **tighten_exit**" in md
    assert "priority_exit_triggers: vwap_breakdown, time_decay" in md
    assert "현재 포지션의 테제가 약화" in md
    assert "Market-frame fields" not in md
    assert "theme=none" not in md
