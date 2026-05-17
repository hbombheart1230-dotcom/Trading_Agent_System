import json
from pathlib import Path

import libs.reporting.daily_report_generator as daily_generator
from libs.reporting.llm_artifacts import daily_artifact_paths
from libs.reporting.daily_report import generate_daily_report as compat_generate_daily_report
from scripts.generate_daily_report import generate_daily_report


def test_daily_artifact_paths_use_single_canonical_root(tmp_path: Path) -> None:
    paths = daily_artifact_paths(tmp_path / "reports", "2026-03-20")
    assert paths["root_dir"] == tmp_path / "reports" / "operator_summary" / "daily" / "2026-03-20"
    assert paths["daily_report_json"] == tmp_path / "reports" / "operator_summary" / "daily" / "2026-03-20" / "daily_report.json"
    assert paths["operator_summary_json"] == tmp_path / "reports" / "operator_summary" / "daily" / "2026-03-20" / "operator_summary.json"
    assert "legacy_operator_summary_json" not in paths
    assert "legacy_operator_summary_md" not in paths


def test_generate_daily_report(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text(
        "\n".join([
            json.dumps({"ts": 1700000000, "run_id": "r1", "stage": "decision", "event": "trace", "payload": {"decision_packet": {"intent": {"action": "BUY", "symbol": "005930"}}}}),
            json.dumps({"ts": 1700000001, "run_id": "r1", "stage": "execute_from_packet", "event": "verdict", "payload": {"allowed": True}}),
        ]) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "reports"
    lifecycle = out_dir / "trades" / "2023-11-14" / "TRD_20231114_005930_01" / "lifecycle" / "trade_lifecycle.json"
    lifecycle.parent.mkdir(parents=True, exist_ok=True)
    lifecycle.write_text(
        json.dumps(
            {
                "trade_id": "TRD_20231114_005930_01",
                "symbol": "005930",
                "day": "2023-11-14",
                "status": "closed",
                "entry": {"run_id": "r1", "ts": "2023-11-14T00:00:00+00:00", "price": 100.0, "strategist_context": {"playbook": "pullback"}},
                "exit": {"run_id": "r2", "ts": "2023-11-14T00:05:00+00:00", "price": 103.0},
                "summary": {"entry_reason_human": "눌림목 이후 재상승 진입", "exit_reason_human": "목표 수익 실현"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    # 1700000000 is 2023-11-14 in UTC
    md, js = generate_daily_report(events, out_dir, day="2023-11-14")
    assert md.exists() and js.exists()
    assert md == out_dir / "operator_summary" / "daily" / "2023-11-14" / "daily_report.md"
    assert js == out_dir / "operator_summary" / "daily" / "2023-11-14" / "daily_report.json"
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["approvals"] == 1
    assert (out_dir / "operator_summary" / "daily" / "2023-11-14" / "daily_report.json").exists()
    assert (out_dir / "operator_summary" / "daily" / "2023-11-14" / "daily_report.md").exists()
    assert (out_dir / "operator_summary" / "daily" / "2023-11-14" / "daily_summary.json").exists()
    assert (out_dir / "operator_summary" / "daily" / "2023-11-14" / "daily_summary.md").exists()
    assert (out_dir / "operator_summary" / "daily" / "2023-11-14" / "trade_index.json").exists()
    assert (out_dir / "operator_summary" / "symbols" / "005930" / "symbol_trade_report.json").exists()
    assert not (out_dir / "daily_2023-11-14.json").exists()
    assert not (out_dir / "daily_2023-11-14.md").exists()
    assert not (out_dir / "daily" / "daily_2023-11-14.json").exists()
    assert not (out_dir / "daily" / "daily_2023-11-14.md").exists()
    assert not (out_dir / "daily" / "2023-11-14" / "daily_report.json").exists()
    assert not (out_dir / "symbols" / "005930" / "symbol_trade_report.json").exists()


def test_generate_daily_report_surfaces_residual_positions(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("STATE_STORE_PATH", raising=False)
    events = tmp_path / "events.jsonl"
    events.write_text("", encoding="utf-8")
    out_dir = tmp_path / "reports"
    state_path = tmp_path / "data" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "mock_positions": [
                    {"symbol": "005930", "qty": 5, "avg_price": 264500.0, "current_price": 268500.0},
                    {"symbol": "078890", "qty": 338, "avg_price": 8770.0, "current_price": 8700.0},
                ],
                "overnight_decision_by_symbol": {
                    "005930": {
                        "approved": True,
                        "action": "carry_overnight",
                        "reason": "carry_overnight_approved",
                        "decided_at_epoch": 1778221320,
                        "positive_signals": ["pnl_ok:0.0098"],
                    }
                },
                "closeout_backup_liquidation": {
                    "mode": "broker_truth_unresolved_positions_retained",
                    "reason": "closeout_broker_truth_unresolved_positions_retained",
                    "carry_forward_symbols": ["005930"],
                    "unresolved_flatten_symbols": ["078890"],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    md, js = generate_daily_report(events, out_dir, day="2026-05-08")
    data = json.loads(js.read_text(encoding="utf-8"))
    text = md.read_text(encoding="utf-8")

    assert data["residual_positions"]["position_count"] == 2
    assert "## 장마감 잔여 보유 종목" in text
    assert "005930: 주말 오버나이트 승인(주의)" in text
    assert "주말보유 3일" in text
    assert "078890: 정리 필요" in text
    assert "오버나이트 판단: 미수행(모니터 상태 기록 없음)" in text
    assert "판단 기록 근거: 모니터 상태 기록 없음; EOD 전체 보유 종목 재점검 필요" in text


def test_compat_daily_report_delegates_to_canonical_generator(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text(
        "\n".join([
            json.dumps({"ts": "2026-03-23T06:24:32+00:00", "run_id": "r1", "stage": "strategist", "event": "summary", "payload": {}}),
            json.dumps({"ts": "2026-03-23T06:25:32+00:00", "run_id": "r1", "stage": "execute_from_packet", "event": "verdict", "payload": {"allowed": True}}),
        ]) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "reports"
    md, js = compat_generate_daily_report(events, out_dir, day="2026-03-23")
    data = json.loads(js.read_text(encoding="utf-8"))
    assert md == out_dir / "operator_summary" / "daily" / "2026-03-23" / "daily_report.md"
    assert data["events"] == 2
    assert data["approvals"] == 1
    assert "stage_counts" in data


def test_generate_daily_report_uses_lifecycle_bundle_for_trade_index(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps({"ts": "2026-03-23T06:24:32+00:00", "run_id": "r1", "stage": "monitor", "event": "summary", "payload": {"symbol": "005930"}}) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "reports"
    bundle = out_dir / "trades" / "2026-03-23" / "TRD_20260323_005930_01" / "lifecycle_bundle.json"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text(
        json.dumps(
            {
                "schema_version": "lifecycle_bundle.v1",
                "day": "2026-03-23",
                "trade_id": "TRD_20260323_005930_01",
                "symbol": "005930",
                "trade_lifecycle_status": "closed",
                "lifecycle": {
                    "entry": {"run_id": "r1", "ts": "2026-03-23T06:20:00+00:00", "price": 100.0, "reason_human": "entry reason"},
                    "exit": {"run_id": "r2", "ts": "2026-03-23T06:30:00+00:00", "price": 103.0, "reason_human": "exit reason"},
                },
                "trade_outcome": {"exit_reason": "exit reason"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    _md, js = generate_daily_report(events, out_dir, day="2026-03-23")
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["trade_index"]
    assert data["trade_index"][0]["trade_id"] == "TRD_20260323_005930_01"
    assert data["symbols_observed"] == ["005930"]


def test_generate_daily_report_surfaces_operator_summary_snapshot(tmp_path: Path, monkeypatch) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps({"ts": "2026-04-02T01:00:00+00:00", "run_id": "r1", "stage": "execute_from_packet", "event": "verdict", "payload": {"allowed": True}}) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "reports"
    daily_root = out_dir / "operator_summary" / "daily" / "2026-04-02"
    daily_root.mkdir(parents=True, exist_ok=True)
    (daily_root / "operator_summary.json").write_text(json.dumps({"junk": True}), encoding="utf-8")

    def fake_operator_payload(*args, **kwargs):
        return {
            "schema_version": "operator_summary.v1",
            "generated_at": "2026-04-02T00:59:59+00:00",
            "source_run_count": 12,
            "latest_run_id": "r-prev",
            "latest_run_ts": "2026-04-02T00:59:59+00:00",
            "executive_summary": {
                "system_status": "GREEN",
                "summary_lines": [
                    "runs=12, executions=2 (ok=2, fail=0), blocks=1.",
                    "Top guard block: noop_intent_skipped (1)",
                ],
            },
            "system_health_status": {
                "system_health_level": "GREEN",
                "reasoning": ["no critical or warning issues detected"],
                "recommended_action": ["Continue current configuration."],
            },
            "trading_activity_summary": {
                "run_total": 12,
                "decision_action_counts": {"BUY": 1, "SELL": 1},
                "strategy_counts": {"defensive": 2},
                "executions_total": 2,
                "executions_ok_total": 2,
                "executions_fail_total": 0,
                "blocked_total": 1,
            },
            "route_summary": {
                "route_source": "canonical_commander_preferred",
                "route_source_run_count": 12,
                "route_source_missing_count": 0,
                "route_selected_total": {"monitor_only": 10, "full_cycle": 2},
                "strategy_generation_mode_total": {"cached": 10, "live_llm": 2},
            },
            "top_issues": [{"code": "none", "severity": "GREEN", "detail": "no critical or warning issues detected"}],
            "recommended_operator_actions": ["Continue current configuration."],
        }

    def fake_policy_snapshot(*args, **kwargs):
        return {
            "summary": {"schema_version": "policy_surface_quality_summary.v1", "run_count": 8},
            "executive_summary": {"schema_version": "policy_surface_quality_executive_summary.v1", "status": "good", "headline": "Policy surface healthy"},
            "chart_structure_summary": {"schema_version": "chart_structure_decision_hint_summary.v1", "run_count": 8},
            "chart_structure_executive_summary": {"schema_version": "chart_structure_decision_hint_executive_summary.v1", "status": "inactive", "headline": "Chart structure guard inactive"},
            "source": {"run_count": 8, "source": "daily_monitor_artifacts"},
        }

    monkeypatch.setattr(daily_generator, "build_operator_daily_summary_payload", fake_operator_payload)
    monkeypatch.setattr(daily_generator, "build_policy_surface_quality_snapshot", fake_policy_snapshot)

    md, js = generate_daily_report(events, out_dir, day="2026-04-02")

    data = json.loads(js.read_text(encoding="utf-8"))
    snapshot = data["operator_summary_snapshot"]
    assert snapshot["available"] is True
    assert snapshot["generated_at"] == "2026-04-02T00:59:59+00:00"
    assert snapshot["executive_summary"]["system_status"] == "GREEN"
    assert snapshot["executive_summary"]["summary_lines"][0].startswith("runs=12")
    assert snapshot["route_summary"]["route_source"] == "canonical_commander_preferred"
    assert snapshot["data_freshness"]["freshness_status"] == "fresh"
    assert data["report_freshness"]["source_run_count"] == 1
    assert data["data_freshness"]["freshness_status"] == "fresh"
    assert data["route_provenance"]["route_source"] == "canonical_commander_preferred"
    assert data["operator_summary_snapshot_freshness"]["stale"] is True
    assert data["policy_surface_quality_summary"]["schema_version"] == "policy_surface_quality_summary.v1"
    assert data["policy_surface_quality_executive_summary"]["schema_version"] == "policy_surface_quality_executive_summary.v1"
    assert data["chart_structure_decision_hint_summary"]["schema_version"] == "chart_structure_decision_hint_summary.v1"
    assert data["chart_structure_decision_hint_executive_summary"]["schema_version"] == "chart_structure_decision_hint_executive_summary.v1"
    assert "policy_surface_quality_source" in data
    assert "chart_structure_decision_hint_source" in data
    md_text = md.read_text(encoding="utf-8")
    assert "## Data Freshness" in md_text
    assert "## Operator Summary Snapshot" in md_text
    assert "## Route Provenance" in md_text
    assert "## Policy Surface Executive Summary" in md_text
    assert "## Policy Surface Quality" in md_text
    assert "## Chart Structure Decision Hint Executive Summary" in md_text
    assert "## Chart Structure Decision Hint" in md_text
    assert "## Top Issues" in md_text
    assert "## Recommended Operator Actions" in md_text


def test_generate_daily_report_keeps_working_when_policy_surface_summary_unavailable(tmp_path: Path, monkeypatch) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps({"ts": "2026-04-03T01:00:00+00:00", "run_id": "r1", "stage": "monitor", "event": "summary", "payload": {}}) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "reports"

    monkeypatch.setattr(daily_generator, "build_policy_surface_quality_snapshot", lambda *args, **kwargs: {
        "summary": {"schema_version": "policy_surface_quality_summary.v1", "run_count": 0},
        "executive_summary": {"schema_version": "policy_surface_quality_executive_summary.v1", "status": "unknown"},
        "chart_structure_summary": {"schema_version": "chart_structure_decision_hint_summary.v1", "run_count": 0},
        "chart_structure_executive_summary": {"schema_version": "chart_structure_decision_hint_executive_summary.v1", "status": "unknown"},
        "source": {"run_count": 0, "notes": ["no_canonical_monitor_runs_found"]},
    })

    md, js = generate_daily_report(events, out_dir, day="2026-04-03")

    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["policy_surface_quality_summary"]["schema_version"] == "policy_surface_quality_summary.v1"
    assert data["policy_surface_quality_executive_summary"]["status"] == "unknown"
    assert data["chart_structure_decision_hint_summary"]["schema_version"] == "chart_structure_decision_hint_summary.v1"
    assert data["chart_structure_decision_hint_executive_summary"]["status"] == "unknown"
    assert data["policy_surface_quality_summary"]["run_count"] == 0
    assert data["policy_surface_quality_source"]["run_count"] == 0
    assert data["report_freshness"]["source_run_count"] == 1
    assert data["data_freshness"]["freshness_status"] == "fresh"
    assert "no_canonical_monitor_runs_found" in list(data["policy_surface_quality_source"]["notes"])
    md_text = md.read_text(encoding="utf-8")
    assert "## Data Freshness" in md_text
    assert "## Policy Surface Executive Summary" in md_text
    assert "## Policy Surface Quality" in md_text
    assert "## Chart Structure Decision Hint Executive Summary" in md_text
    assert "## Chart Structure Decision Hint" in md_text


def test_generate_daily_report_renders_chart_structure_applied_examples(tmp_path: Path, monkeypatch) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps({"ts": "2026-04-03T01:00:00+00:00", "run_id": "r1", "stage": "monitor", "event": "summary", "payload": {}}) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "reports"

    def fake_policy_snapshot(*args, **kwargs):
        return {
            "summary": {
                "schema_version": "policy_surface_quality_summary.v1",
                "run_count": 3,
                "schema_available_rate": 1.0,
                "normalized_policy_rate": 1.0,
                "invalid_spec_rate": 0.0,
                "total_invalid_specs": 0,
                "top_invalid_features": [],
                "top_invalid_states": [],
                "validation_notes_counts": {},
                "invalid_specs_by_selected_source": {},
                "validation_notes_by_interpretation_basis": {},
                "notes": [],
            },
            "executive_summary": {
                "schema_version": "policy_surface_quality_executive_summary.v1",
                "status": "good",
                "headline": "Policy surface healthy: schema 1.00, invalid spec 0.00",
            },
            "chart_structure_summary": {
                "schema_version": "chart_structure_decision_hint_summary.v1",
                "run_count": 3,
                "available_run_count": 2,
                "applied_count": 1,
                "applied_rate": 0.5,
                "mode_counts": {"block": 1, "none": 1},
                "blocking_feature_counts": {"support_holding": 1},
                "top_blocking_features": ["support_holding"],
                "applied_run_ids": ["run-pullback-guard"],
                "reason_counts_when_applied": {"pullback_reversal_structure_guard_blocked": 1},
                "entry_style_counts_when_applied": {"pullback": 1},
                "decision_counts_when_applied": {"WAIT": 1},
                "applied_examples": [
                    {
                        "run_id": "run-pullback-guard",
                        "symbol": "005930",
                        "entry_style": "pullback",
                        "mode": "block",
                        "legacy_decision": "BUY",
                        "legacy_reason": "pullback_volume_path_ready",
                        "final_decision": "WAIT",
                        "final_reason": "pullback_reversal_structure_guard_blocked",
                        "reason_transition": "pullback_volume_path_ready -> pullback_reversal_structure_guard_blocked",
                        "blocking_features": ["support_holding=lost"],
                        "matched_features": [],
                    }
                ],
                "notes": [],
            },
            "chart_structure_executive_summary": {
                "schema_version": "chart_structure_decision_hint_executive_summary.v1",
                "status": "active",
                "headline": "Chart structure guard active: applied 1 times",
                "applied_examples": [
                    {
                        "run_id": "run-pullback-guard",
                        "reason_transition": "pullback_volume_path_ready -> pullback_reversal_structure_guard_blocked",
                        "blocking_features": ["support_holding=lost"],
                        "entry_style": "pullback",
                    }
                ],
            },
            "source": {"run_count": 3, "source": "daily_monitor_artifacts"},
        }

    monkeypatch.setattr(daily_generator, "build_policy_surface_quality_snapshot", fake_policy_snapshot)

    md, js = generate_daily_report(events, out_dir, day="2026-04-03")

    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["chart_structure_decision_hint_summary"]["applied_examples"][0]["run_id"] == "run-pullback-guard"
    md_text = md.read_text(encoding="utf-8")
    assert "## Chart Structure Decision Hint Applied Examples" in md_text
    assert "pullback_volume_path_ready -> pullback_reversal_structure_guard_blocked" in md_text


def test_generate_daily_report_does_not_read_operator_summary_file(tmp_path: Path, monkeypatch) -> None:
    day = "2026-04-08"
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps({"ts": f"{day}T01:00:00+00:00", "run_id": "r1", "stage": "execute_from_packet", "event": "verdict", "payload": {"allowed": True}}) + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "reports"
    daily_root = out_dir / "operator_summary" / "daily" / day
    daily_root.mkdir(parents=True, exist_ok=True)
    (daily_root / "operator_summary.json").write_text(
        json.dumps({"executive_summary": {"summary_lines": ["stale-file-should-not-be-read"]}}, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(daily_generator, "build_operator_daily_summary_payload", lambda *args, **kwargs: {
        "generated_at": "2026-04-08T01:00:00+00:00",
        "source_run_count": 1,
        "latest_run_id": "r1",
        "latest_run_ts": "2026-04-08T01:00:00+00:00",
        "executive_summary": {"system_status": "GREEN", "summary_lines": ["fresh-source-line"]},
        "system_health_status": {"system_health_level": "GREEN", "reasoning": [], "recommended_action": []},
        "trading_activity_summary": {"run_total": 1, "decision_action_counts": {}, "strategy_counts": {}, "executions_total": 0, "executions_ok_total": 0, "executions_fail_total": 0, "blocked_total": 0},
        "route_summary": {"route_source": "canonical_commander_preferred", "route_source_run_count": 1, "route_source_missing_count": 0, "route_selected_total": {"monitor_only": 1}, "strategy_generation_mode_total": {}},
        "top_issues": [],
        "recommended_operator_actions": [],
    })
    monkeypatch.setattr(daily_generator, "build_policy_surface_quality_snapshot", lambda *args, **kwargs: {
        "summary": {"schema_version": "policy_surface_quality_summary.v1", "run_count": 0},
        "executive_summary": {"schema_version": "policy_surface_quality_executive_summary.v1", "status": "unknown"},
        "chart_structure_summary": {"schema_version": "chart_structure_decision_hint_summary.v1", "run_count": 0},
        "chart_structure_executive_summary": {"schema_version": "chart_structure_decision_hint_executive_summary.v1", "status": "unknown"},
        "source": {"run_count": 0},
    })

    _md, js = generate_daily_report(events, out_dir, day=day)
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["operator_summary_snapshot"]["executive_summary"]["summary_lines"] == ["fresh-source-line"]
    assert data["narrative_axis_policy"]["entry_primary_for"] == ["BUY", "WAIT", "NOOP", "NO_TRADE"]
    assert data["narrative_axis_policy"]["exit_primary_for"] == ["SELL", "EXIT"]
