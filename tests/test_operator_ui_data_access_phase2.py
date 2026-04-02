import json
from pathlib import Path

import apps.operator_ui.data_access as data_access
import apps.operator_ui.data_access_reports as data_access_reports
import libs.reporting.trade_read_model as trade_read_model
from apps.operator_ui.data_access_reports import load_trade_report_payloads
from libs.reporting.trade_read_model import load_trade_report_payloads as load_trade_report_payloads_read_model
from libs.reporting.trade_read_model import (
    brief_collect_top_headlines,
    brief_top_numeric_drivers,
    build_operator_brief_detail_view,
    build_linked_trade_report_card,
    build_trade_report_detail_view,
    build_unlinked_trade_report_card,
    extract_labeled_bullet,
    extract_labeled_int,
    load_operator_brief_detail_payloads,
    load_reporter_snippet_for_run,
    load_trade_report_detail_payloads,
    normalize_canonical_monitor_snapshot,
    normalize_trade_report_detail_sections,
    normalize_trade_report_detail_meta,
    normalize_operator_brief_detail_payload,
    normalize_trade_report_section,
    parse_canonical_filter_bullets,
    prefer_richer_trade_report_section,
    trade_report_artifact_payload,
    trade_report_section_bullets,
    trade_report_section_summary,
)


def test_data_access_facade_uses_phase2_status_semantics() -> None:
    assert data_access._report_status_label("available") == "AI Report Available"
    assert data_access._report_status_label("pending") == "AI Report Pending"
    assert data_access._report_status_badge_class("failed").endswith("--critical")

    diag = data_access._normalize_ai_report_diagnostics(
        {
            "report_status": "pending",
            "report_reason_code": "awaiting_exit_for_full_report",
        },
        report_exists=False,
        lifecycle_status="open",
        story_type="simulation",
        model_hint="openrouter/free",
    )
    assert diag["report_status"] == "pending"
    assert "exit" in str(diag["next_expected_step"]).lower()


def test_data_access_facade_trade_paths_include_phase2_metadata(tmp_path: Path) -> None:
    bundle_path = tmp_path / "reports" / "trades" / "2026-03-18" / "TRD_TEST" / "lifecycle" / "aggregated_execution_bundle.json"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text("{}", encoding="utf-8")

    paths = data_access._trade_paths_from_bundle(
        bundle_path,
        day_hint="2026-03-18",
        trade_id_hint="TRD_TEST",
    )
    assert str(paths["trade_root"]).endswith("TRD_TEST")
    assert paths["trade_provenance_json"].name == "_provenance.json"
    assert paths["trade_health_json"].name == "_health.json"
    assert paths["trade_artifact_links_json"].name == "_artifact_links.json"


def test_load_trade_report_payloads_prefers_normalized_trade_paths(tmp_path: Path) -> None:
    trade_root = tmp_path / "reports" / "trades" / "2026-03-18" / "TRD_TEST"
    normalized_story = trade_root / "ai_trade_report_input.json"
    normalized_lifecycle = trade_root / "lifecycle_bundle.json"
    normalized_report = trade_root / "reports" / "ai_trade_report.json"
    for path, payload in (
        (normalized_story, {"source": "normalized_story"}),
        (normalized_lifecycle, {"source": "normalized_lifecycle"}),
        (normalized_report, {"source": "normalized_report"}),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    meta_story = tmp_path / "meta_story.json"
    meta_story.write_text('{"source":"meta_story"}', encoding="utf-8")
    meta_lifecycle = tmp_path / "meta_lifecycle.json"
    meta_lifecycle.write_text('{"source":"meta_lifecycle"}', encoding="utf-8")
    meta_report = tmp_path / "meta_report.json"
    meta_report.write_text('{"source":"meta_report"}', encoding="utf-8")

    out = load_trade_report_payloads(
        {
            "trade_root_path": str(trade_root),
            "trade_story_input_path": str(meta_story),
            "trade_lifecycle_json_path": str(meta_lifecycle),
            "trade_report_json_path": str(meta_report),
        },
        read_json=lambda p: data_access._read_json(Path(p)),
    )
    assert out["story_input_data"]["source"] == "normalized_story"
    assert out["lifecycle_data"]["source"] == "normalized_lifecycle"
    assert out["report_data"]["source"] == "normalized_report"
    assert out["payload_sources"]["story_input"] == "normalized_trade_artifact"


def test_operator_ui_data_access_reports_remains_compatibility_wrapper() -> None:
    assert load_trade_report_payloads is load_trade_report_payloads_read_model


def test_trade_read_model_explicit_public_surface_includes_detail_builders() -> None:
    exported = set(getattr(trade_read_model, "__all__", []))
    assert "load_trade_report_payloads" in exported
    assert "build_trade_report_detail_view" in exported
    assert "build_operator_brief_detail_view" in exported
    assert data_access_reports.__all__ == ["load_trade_report_payloads"]


def test_trade_read_model_section_helpers_choose_richer_payload_and_normalize_output() -> None:
    sparse = {"summary": "", "bullets": [], "status": "unknown"}
    rich = {"summary": "selected from canonical report", "bullets": ["one", "two"], "status": "ok"}

    chosen = prefer_richer_trade_report_section(sparse, rich)
    assert chosen["summary"] == "selected from canonical report"
    assert trade_report_section_summary(chosen) == "selected from canonical report"
    assert trade_report_section_bullets(chosen, limit=1) == ["one"]


def test_trade_read_model_artifact_payload_is_null_safe() -> None:
    assert trade_report_artifact_payload({}, "story_input_data") == {}
    assert trade_report_artifact_payload({"story_input_data": {"a": 1}}, "story_input_data") == {"a": 1}
    assert trade_report_artifact_payload({"story_input_data": []}, "story_input_data") == {}


def test_trade_read_model_load_trade_report_detail_payloads_reads_report_bundle_and_lifecycle(tmp_path: Path) -> None:
    trade_root = tmp_path / "reports" / "trades" / "2026-03-18" / "TRD_TEST"
    report_path = trade_root / "reports" / "ai_trade_report.json"
    bundle_path = trade_root / "lifecycle_bundle.json"
    lifecycle_path = trade_root / "trade_lifecycle.json"
    report_md_path = trade_root / "reports" / "ai_trade_report.md"
    for path, payload in (
        (report_path, {"kind": "report"}),
        (bundle_path, {"kind": "bundle"}),
        (lifecycle_path, {"kind": "lifecycle"}),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    report_md_path.write_text("# report", encoding="utf-8")

    out = load_trade_report_detail_payloads(
        {
            "trade_report_json_path": str(report_path),
            "aggregated_bundle_path": str(bundle_path),
            "trade_lifecycle_json_path": str(lifecycle_path),
            "trade_report_md_path": str(report_md_path),
        },
        read_json=lambda p: data_access._read_json(Path(p)),
    )
    assert out["report_data"]["kind"] == "report"
    assert out["bundle_data"]["kind"] == "bundle"
    assert out["lifecycle_data"]["kind"] == "lifecycle"
    assert out["report_exists"] is True


def test_trade_read_model_normalize_trade_report_section_is_trimmed_and_null_safe() -> None:
    section = normalize_trade_report_section(
        {
            "entry_decision": {
                "summary": "entry summary",
                "bullets": ["a", "", "b"],
                "status": "ok",
                "grade": "A",
            }
        },
        "entry_decision",
        trim_text=lambda value, **_: str(value or "").strip(),
        clean_str_list=lambda values, **_: [str(v).strip() for v in list(values or []) if str(v).strip()],
    )
    assert section == {
        "summary": "entry summary",
        "bullets": ["a", "b"],
        "status": "ok",
        "grade": "A",
    }


def test_trade_read_model_load_operator_brief_detail_payloads_respects_saved_brief_flag(tmp_path: Path) -> None:
    trade_root = tmp_path / "reports" / "trades" / "2026-03-18" / "TRD_TEST"
    brief_json = trade_root / "reports" / "operator_brief.json"
    brief_md = trade_root / "reports" / "operator_brief.md"
    brief_json.parent.mkdir(parents=True, exist_ok=True)
    brief_json.write_text(json.dumps({"headline": "saved brief"}), encoding="utf-8")
    brief_md.write_text("# brief", encoding="utf-8")

    allowed = load_operator_brief_detail_payloads(
        {
            "operator_brief_json_path": str(brief_json),
            "operator_brief_md_path": str(brief_md),
        },
        read_json=lambda p: data_access._read_json(Path(p)),
        allow_saved_brief=True,
    )
    blocked = load_operator_brief_detail_payloads(
        {
            "operator_brief_json_path": str(brief_json),
            "operator_brief_md_path": str(brief_md),
        },
        read_json=lambda p: data_access._read_json(Path(p)),
        allow_saved_brief=False,
    )
    assert allowed["brief_data"]["headline"] == "saved brief"
    assert blocked["brief_data"] == {}
    assert allowed["paths"]["operator_brief_json"].endswith("operator_brief.json")
    assert allowed["paths"]["operator_brief_md"].endswith("operator_brief.md")


def test_trade_read_model_normalize_operator_brief_detail_payload_extracts_sections_and_lists() -> None:
    normalized = normalize_operator_brief_detail_payload(
        {
            "headline": "brief headline",
            "status": "ok",
            "model": "gpt",
            "saved_at": "2026-04-02T10:00:00+09:00",
            "operator_takeaways": ["one", "", "two"],
            "sections": {
                "executive_decision": {"action": "BUY", "symbol": "005930"},
                "ai_trade_report": {"status_label": "AI Report Available"},
                "operator_conclusion": {
                    "watch_next": ["a", "", "b"],
                    "thesis_invalidation": ["x"],
                },
            },
        },
        clean_str_list=lambda values, **_: [str(v).strip() for v in list(values or []) if str(v).strip()],
    )
    assert normalized["headline"] == "brief headline"
    assert normalized["operator_takeaways"] == ["one", "two"]
    assert normalized["executive"]["action"] == "BUY"
    assert normalized["ai_trade"]["status_label"] == "AI Report Available"
    assert normalized["watch_next"] == ["a", "b"]
    assert normalized["thesis_invalidation"] == ["x"]


def test_trade_read_model_normalize_trade_report_detail_sections_builds_review_focus() -> None:
    normalized = normalize_trade_report_detail_sections(
        {
            "entry_decision": {"summary": "entered on breakout"},
            "holding_monitoring_story": {"summary": "held above VWAP"},
            "exit_decision": {"summary": "exited on peak drawdown"},
            "execution_quality": {"summary": "fills were acceptable"},
            "errors_weaknesses_improvement_points": {"summary": "avoid late entries"},
        },
        fallback_summaries={
            "executive_summary": "exec fallback",
            "market_context_at_entry": "market fallback",
            "why_this_symbol_was_chosen": "symbol fallback",
            "scanner_filters": "filters fallback",
            "entry_decision": "entry fallback",
            "holding_monitoring_story": "holding fallback",
            "exit_decision": "exit fallback",
            "execution_quality": "execution fallback",
            "guard_approval_result": "guard fallback",
            "reporter_evaluation": "reporter fallback",
            "errors_weaknesses_improvement_points": "weakness fallback",
        },
        trim_text=lambda value, **_: str(value or "").strip(),
        clean_str_list=lambda values, **_: [str(v).strip() for v in list(values or []) if str(v).strip()],
    )
    assert normalized["executive_summary"]["summary"] == "exec fallback"
    assert normalized["market_context"]["summary"] == "market fallback"
    assert normalized["review_focus"] == {
        "why_entered": "entered on breakout",
        "why_held": "held above VWAP",
        "why_exited": "exited on peak drawdown",
        "execution_quality": "fills were acceptable",
        "improvement_focus": "avoid late entries",
    }


def test_trade_read_model_normalize_trade_report_detail_meta_builds_final_conclusion_and_generation() -> None:
    normalized = normalize_trade_report_detail_meta(
        {
            "final_operator_conclusion": {
                "summary": "close monitoring remains important",
                "current_action": "HOLD",
                "watch_next": ["VWAP hold", ""],
                "thesis_invalidation": ["lose support"],
            },
            "generation": {
                "status": "ok",
                "mode": "llm",
                "model": "gpt-5",
                "reason": "generated successfully",
            },
        },
        operator_conclusion_human={"summary": "fallback summary"},
        action="WAIT",
        trim_text=lambda value, **_: str(value or "").strip(),
        clean_str_list=lambda values, **_: [str(v).strip() for v in list(values or []) if str(v).strip()],
    )
    assert normalized["final_operator_conclusion"] == {
        "summary": "close monitoring remains important",
        "current_action": "HOLD",
        "watch_next": ["VWAP hold"],
        "thesis_invalidation": ["lose support"],
    }
    assert normalized["generation"] == {
        "status": "ok",
        "mode": "llm",
        "model": "gpt-5",
        "reason": "generated successfully",
    }


def test_trade_read_model_load_reporter_snippet_for_run_reads_same_day_report_and_matches_run() -> None:
    root = Path("C:/repo")
    expected_path = root / "dev" / "analysis" / "reporter_analysis" / "reporter_analysis_2026-04-02.json"

    def _fake_read_json(path: Path) -> dict:
        assert path == expected_path
        return {
            "ai_summary": "same-day reporter summary",
            "ai_run_grade": "A",
            "decision_trace_chain_summary": {
                "chains": [
                    {"run_id": "run-1", "headline": "linked"},
                    {"run_id": "run-2", "headline": "other"},
                ]
            },
        }

    out = load_reporter_snippet_for_run(root, "run-1", "2026-04-02", read_json=_fake_read_json)
    assert out["found"] is True
    assert out["ai_summary"] == "same-day reporter summary"
    assert out["ai_run_grade"] == "A"
    assert out["chain"]["headline"] == "linked"


def test_trade_read_model_build_linked_trade_report_card_keeps_paths_and_payloads() -> None:
    card = build_linked_trade_report_card(
        {
            "report_available": True,
            "trade_id": "TRD_TEST",
            "story_id": "TRD_TEST",
            "story_type": "simulation",
            "story_type_label": "Simulation",
            "story_type_badge_class": "status-badge",
            "lifecycle_status": "closed",
            "lifecycle_summary": "closed trade",
            "execution_mode_label": "simulation",
            "report_status": "available",
            "report_status_label": "AI Report Available",
            "report_status_badge_class": "status-badge status-badge--ok",
            "report_summary": "report summary",
            "operator_brief_available": True,
            "trade_report_json_path": "report.json",
        },
        {
            "story_input_data": {"a": 1},
            "lifecycle_data": {"b": 2},
            "report_data": {"c": 3},
            "payload_sources": {"story_input": "normalized_trade_artifact"},
            "paths": {"report_path": "report.json"},
        },
        primary_symbol="005930",
        execution_action="BUY",
        normalize_ai_report_diagnostics=lambda *args, **kwargs: {"report_status": "available"},
    )
    assert card["trade_id"] == "TRD_TEST"
    assert card["symbol"] == "005930"
    assert card["action"] == "BUY"
    assert card["story_input_data"] == {"a": 1}
    assert card["report_payload_sources"]["story_input"] == "normalized_trade_artifact"


def test_trade_read_model_build_unlinked_trade_report_card_marks_missing_report_linkage() -> None:
    card = build_unlinked_trade_report_card(
        execution_action="BUY",
        monitor_reason_text="hold",
        symbol="005930",
        normalize_ai_report_diagnostics=lambda payload, **kwargs: {
            **payload,
            "report_status_label": "AI Report Failed",
            "report_status_badge_class": "status-badge status-badge--critical",
            "llm_provider": "OpenRouter",
            "llm_model_used": "",
        },
        report_reason_human=lambda code: f"human:{code}",
        report_next_step=lambda code: f"next:{code}",
    )
    assert card["report_available"] is False
    assert card["report_reason_code"] == "missing_report_linkage"
    assert card["report_reason_human"] == "human:missing_report_linkage"
    assert card["symbol"] == "005930"
    assert card["action"] == "BUY"


def test_trade_read_model_build_trade_report_detail_view_returns_normalized_detail() -> None:
    detail = build_trade_report_detail_view(
        {
            "trade_id": "TRD_TEST",
            "story_id": "TRD_TEST",
            "run_id": "run-1",
            "symbol": "005930",
            "story_type": "simulation",
            "lifecycle_status": "closed",
            "report_summary": "meta summary",
            "trade_report_json_path": "report.json",
        },
        {
            "report_data": {
                "symbol": "005930",
                "action": "BUY",
                "story_type": "simulation",
                "entry_decision": {"summary": "entered on reclaim"},
                "holding_monitoring_story": {"summary": "held above VWAP"},
                "exit_decision": {"summary": "exited on weakness"},
                "execution_quality": {"summary": "fills ok"},
                "reporter_evaluation": {"summary": "solid"},
                "errors_weaknesses_improvement_points": {"summary": "avoid late chase"},
                "generation": {"status": "ok", "mode": "llm", "model": "gpt-5"},
            },
            "bundle_data": {
                "operator_conclusion_human": {"summary": "stay disciplined"},
            },
            "lifecycle_data": {"status": "closed", "summary": {"lifecycle_summary_human": "closed cleanly"}},
            "report_exists": True,
        },
        trim_text=lambda value, **_: str(value or "").strip(),
        clean_str_list=lambda values, **_: [str(v).strip() for v in list(values or []) if str(v).strip()],
        normalize_symbol=lambda value, **_: str(value or "").strip(),
        story_type_label=lambda value: f"label:{value}",
        story_type_badge_class=lambda value: f"badge:{value}",
        normalize_ai_report_diagnostics=lambda payload, **_: {"report_status": "available", **payload},
    )
    assert detail["found"] is True
    assert detail["trade_id"] == "TRD_TEST"
    assert detail["symbol"] == "005930"
    assert detail["review_focus"]["why_entered"] == "entered on reclaim"
    assert detail["generation"]["model"] == "gpt-5"


def test_trade_read_model_build_operator_brief_detail_view_returns_normalized_detail() -> None:
    detail = build_operator_brief_detail_view(
        {
            "trade_id": "TRD_TEST",
            "story_id": "TRD_TEST",
            "run_id": "run-1",
            "symbol": "005930",
            "report_summary": "summary",
            "story_type_label": "Simulation",
            "story_type_badge_class": "status-badge",
            "execution_mode_label": "simulation",
        },
        {
            "headline": "brief headline",
            "status": "ok",
            "operator_takeaways": ["watch reclaim"],
            "sections": {
                "executive_decision": {"action": "BUY", "symbol": "005930"},
                "ai_trade_report": {"status_label": "AI Report Available", "status_badge_class": "ok"},
                "operator_conclusion": {"watch_next": ["VWAP hold"], "thesis_invalidation": ["lose VWAP"]},
            },
        },
        json_path="brief.json",
        md_path="brief.md",
        normalize_symbol=lambda value, **_: str(value or "").strip(),
        clean_str_list=lambda values, **_: [str(v).strip() for v in list(values or []) if str(v).strip()],
    )
    assert detail["found"] is True
    assert detail["trade_id"] == "TRD_TEST"
    assert detail["executive_action"] == "BUY"
    assert detail["ai_trade_status_label"] == "AI Report Available"
    assert detail["paths"]["operator_brief_json"] == "brief.json"


def test_trade_read_model_canonical_brief_helpers_parse_labels_filters_headlines_and_snapshot() -> None:
    bullets = [
        "Market regime: defensive",
        "Selected rank: #2",
        "Liquidity: PASS - strong participation",
    ]
    headlines = [
        {"title": "005930 rallies on earnings", "symbol": "005930"},
        {"title": "Macro headline", "symbol": "KOSPI"},
    ]
    snapshot = normalize_canonical_monitor_snapshot(
        {"posture": "HOLD", "trigger_type": "trend_breakdown", "current_price": 1000, "vwap_distance": -0.012},
        {"bullets": ["watch reclaim"]},
        format_duration=lambda value: f"{value}s",
        format_percent=lambda value, digits: f"{float(value) * 100:.{digits}f}%",
        format_float=lambda value, digits: f"{float(value):.{digits}f}",
        friendly_exit_reason=lambda value: str(value).replace("_", " ").title(),
    )

    assert extract_labeled_bullet(bullets, ["market regime"]) == "defensive"
    assert extract_labeled_int(bullets, ["selected rank"]) == 2
    assert parse_canonical_filter_bullets([bullets[2]]) == [
        {"name": "Liquidity", "status": "PASS", "note": "strong participation"}
    ]
    assert brief_collect_top_headlines(
        headlines,
        limit=2,
        symbol="005930",
        trim_text=lambda value, **_: str(value or "").strip(),
        normalize_symbol=lambda value, **_: str(value or "").strip().upper(),
    ) == ["005930 rallies on earnings"]
    assert brief_top_numeric_drivers({"a": 0.1, "b": -0.4, "c": 0.0}, limit=2) == {"b": -0.4, "a": 0.1}
    assert snapshot["active_exit_axis"] == "Trend Breakdown"
    assert snapshot["current_price"] == "1000.00"
