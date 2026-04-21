from __future__ import annotations

from pathlib import Path

from libs.reporting.trade_bundle_assembly import (
    apply_live_trade_context,
    build_execution_details_from_bundle,
    build_live_run_bundle,
    hydrate_live_run_bundle_context,
)


def test_build_live_run_bundle_builds_story_contract_and_human_sections(tmp_path: Path) -> None:
    out = build_live_run_bundle(
        day="2026-04-17",
        run_id="run-1",
        merged_execution={"action": "BUY", "symbol": "005930", "qty": 1, "status": "filled"},
        commander_payload={"decision": "BUY"},
        strategist_payload={"playbook": "pullback", "themes": ["semiconductor"]},
        scanner_payload={"selected_symbol": "005930", "selected_rank": 1, "universe_size": 5},
        monitor_payload={"monitor_reason": "entry confirmed"},
        supervisor_payload={"risk_state": "normal"},
        executor_payload={"execution_mode": "mock"},
        reporter_trace_payload={"status_human": "linked"},
        reporter_obj={"ai_summary": "steady", "ai_run_grade": "B"},
        trade_obj={"execution_summary": {"executions_total": 2}},
        trace_json_path=tmp_path / "trace.json",
        trace_md_path=tmp_path / "trace.md",
        trade_json_path=tmp_path / "trade.json",
        trade_md_path=tmp_path / "trade.md",
        reporter_json_path=tmp_path / "reporter.json",
        reporter_md_path=tmp_path / "reporter.md",
        operator_summary_json_path=tmp_path / "operator_summary.json",
        operator_summary_md_path=tmp_path / "operator_summary.md",
        commander_path="commander.json",
        strategist_path="strategist.json",
        scanner_path="scanner.json",
        monitor_path="monitor.json",
        supervisor_path="supervisor.json",
        executor_path="executor.json",
        canonical_sources={"artifacts": {"strategist": {"playbook": "pullback"}}},
    )

    bundle = out["bundle_out"]
    assert out["story_type"]
    assert out["story_id"]
    assert bundle["run_id"] == "run-1"
    assert bundle["reporter"]["reporter_analysis_summary"] == "steady"
    assert bundle["artifacts"]["canonical_scanner_json"] == "scanner.json"
    assert bundle["market_context_human"]
    assert bundle["scanner_reason_human"]
    assert bundle["operator_conclusion_human"]
    assert bundle["story_contract"]["warnings"] == bundle["warnings"]


def test_hydrate_live_run_bundle_context_prefers_canonical_payloads(tmp_path: Path, monkeypatch) -> None:
    canonical_root = tmp_path / "reports"
    commander_path = canonical_root / "canonical" / "2026-04-17" / "run-1" / "commander.json"
    strategist_path = canonical_root / "canonical" / "2026-04-17" / "run-1" / "strategist.json"
    scanner_path = canonical_root / "canonical" / "2026-04-17" / "run-1" / "scanner.json"
    monitor_path = canonical_root / "canonical" / "2026-04-17" / "run-1" / "monitor.json"
    supervisor_path = canonical_root / "canonical" / "2026-04-17" / "run-1" / "supervisor.json"
    executor_path = canonical_root / "canonical" / "2026-04-17" / "run-1" / "executor.json"
    monkeypatch.setattr(
        "libs.reporting.trade_bundle_assembly.load_run_canonical_artifacts",
        lambda reports_root, run_id, day_hint: {
            "artifacts": {
                "commander": {"decision": "BUY"},
                "strategist": {"playbook": "pullback"},
                "scanner": {"selected_symbol": "005930", "selected_rank": 1, "universe_size": 4},
                "monitor": {"monitor_reason": "good"},
                "supervisor": {"allowed": True},
                "executor": {"execution_mode": "mock"},
            },
            "paths": {
                "commander": str(commander_path),
                "strategist": str(strategist_path),
                "scanner": str(scanner_path),
                "monitor": str(monitor_path),
                "supervisor": str(supervisor_path),
                "executor": str(executor_path),
            },
        },
    )
    out = hydrate_live_run_bundle_context(
        reports_root=canonical_root,
        day="2026-04-17",
        run_id="run-1",
        execution_row={"run_id": "run-1", "ts": "2026-04-17T00:00:00+00:00", "action": "BUY", "symbol": "005930"},
        trace_out={"reporter": {"status_human": "linked"}},
        reporter_obj={"ai_summary": "stable", "ai_run_grade": "A"},
        trade_obj={},
        trace_json_path=tmp_path / "trace.json",
        trace_md_path=tmp_path / "trace.md",
        trade_json_path=tmp_path / "trade.json",
        trade_md_path=tmp_path / "trade.md",
        reporter_json_path=tmp_path / "reporter.json",
        reporter_md_path=tmp_path / "reporter.md",
        operator_summary_json_path=tmp_path / "operator_summary.json",
        operator_summary_md_path=tmp_path / "operator_summary.md",
        bundle_ts="2026-04-17T00:00:01+00:00",
    )
    bundle = out["bundle_out"]
    assert bundle["ts"] == "2026-04-17T00:00:01+00:00"
    assert bundle["strategist"]["playbook"] == "pullback"
    assert bundle["artifacts"]["canonical_scanner_json"] == str(scanner_path)
    assert bundle["evidence_provenance"]["scanner"] == "canonical"
    assert out["story_type"]


def test_build_execution_details_from_bundle_fetches_broker_order_status() -> None:
    class _FakeReader:
        def get_order_status(self, *, ord_no: str, symbol: str, ord_dt: str, side: str = "all"):
            assert ord_no == "A2"
            assert symbol == "005930"
            assert ord_dt == "20260420"

            class _Dto:
                ord_no = "A2"
                symbol = "005930"
                status = "filled"
                filled_qty = 1
                filled_price = 70200
                order_qty = 1
                order_price = 70100
                side = "SELL"
                raw = {"matched_summary": {"ord_no": "A2"}}

            return _Dto()

    class _FakeDayPnlReader:
        def get_day_realized_details(self, *, symbol: str = ""):
            assert symbol == "005930"
            return {
                "rows": [
                    {
                        "symbol": "005930",
                        "filled_qty": 1,
                        "filled_price": 70200,
                        "buy_price": 70100,
                        "realized_pnl": 100,
                        "pnl_ratio": 0.0014,
                        "fee": 11,
                        "tax": 7,
                    }
                ]
            }

    res = build_execution_details_from_bundle(
        {
            "execution": {
                "action": "SELL",
                "symbol": "005930",
                "qty": 1,
                "ord_no": "A2",
                "ts": "2026-04-20T06:00:00+00:00",
            },
            "monitor": {"current_price": 70100.0},
        },
        context={
            "execution_context": {"order_id": "A2", "ts": "2026-04-20T06:00:00+00:00"},
            "broker_fill_reader": _FakeReader(),
            "broker_day_pnl_reader": _FakeDayPnlReader(),
            "broker_fill_lookup_enabled": True,
            "broker_day_truth_lookup_enabled": True,
        },
    )

    assert res["order_id"] == "A2"
    assert res["filled_price"] == 70200
    assert res["avg_price"] == 70200.0
    assert res["fill_status"] == "filled"
    assert res["broker_truth_source"] == "kiwoom.order_status"
    assert res["broker_realized_pnl"] == 100.0
    assert res["broker_fee"] == 11
    assert res["broker_tax"] == 7
    assert res["pnl_truth_source"] == "kiwoom.ka10077"


def test_build_execution_details_from_bundle_uses_existing_execution_details_for_broker_truth() -> None:
    class _FakeReader:
        def get_order_status(self, *, ord_no: str, symbol: str, ord_dt: str, side: str = "all"):
            assert ord_no == "0174131"
            assert symbol == "010820"
            assert ord_dt == "20260420"
            assert side == "sell"

            class _Dto:
                ord_no = "0174131"
                symbol = "010820"
                status = "filled"
                filled_qty = 1
                filled_price = 15610
                order_qty = 1
                order_price = 15610
                side = "SELL"
                raw = {}

            return _Dto()

    class _FakeDayPnlReader:
        def get_day_realized_details(self, *, symbol: str = ""):
            assert symbol == "010820"
            return {
                "rows": [
                    {
                        "symbol": "010820",
                        "filled_qty": 1,
                        "filled_price": 15610,
                        "buy_price": 15850,
                        "realized_pnl": -240,
                        "pnl_ratio": -0.0151,
                        "fee": 12,
                        "tax": 8,
                    }
                ]
            }

    res = build_execution_details_from_bundle(
        {
            "monitor": {"current_price": 15740.0},
            "execution_details": {
                "order_id": "0174131",
                "filled_qty": 1,
            },
        },
        context={
            "trade_day": "2026-04-20",
            "action": "SELL",
            "symbol": "010820",
            "ts": "2026-04-20T06:25:18+00:00",
            "execution_details": {
                "order_id": "0174131",
                "filled_qty": 1,
            },
            "broker_fill_reader": _FakeReader(),
            "broker_day_pnl_reader": _FakeDayPnlReader(),
            "broker_fill_lookup_enabled": True,
            "broker_day_truth_lookup_enabled": True,
        },
    )

    assert res["order_id"] == "0174131"
    assert res["filled_price"] == 15610
    assert res["broker_truth_source"] == "kiwoom.order_status"
    assert res["broker_realized_pnl"] == -240.0
    assert res["broker_fee"] == 12
    assert res["broker_tax"] == 8


def test_build_execution_details_from_bundle_does_not_promote_sparse_order_status_to_broker_truth() -> None:
    class _SparseReader:
        def get_order_status(self, *, ord_no: str, symbol: str, ord_dt: str, side: str = "all"):
            class _Dto:
                ord_no = "0101795"
                symbol = None
                status = None
                filled_qty = None
                filled_price = None
                order_qty = None
                order_price = None
                side = None
                raw = {}

            return _Dto()

    res = build_execution_details_from_bundle(
        {
            "execution_details": {
                "order_id": "0101795",
                "filled_qty": 1,
            },
            "monitor": {"current_price": 17660.0},
        },
        context={
            "trade_day": "2026-04-20",
            "action": "SELL",
            "symbol": "356680",
            "ts": "2026-04-20T02:29:27+00:00",
            "execution_details": {
                "order_id": "0101795",
                "filled_qty": 1,
            },
            "broker_fill_reader": _SparseReader(),
            "broker_fill_lookup_enabled": True,
        },
    )

    assert res["broker_truth_source"] is None
    assert res["filled_price"] is None


def test_apply_live_trade_context_enables_broker_truth_lookup_for_live_bundle() -> None:
    class _FakeReader:
        def get_order_status(self, *, ord_no: str, symbol: str, ord_dt: str, side: str = "all"):
            assert ord_no == "0056037"
            assert symbol == "000660"
            assert ord_dt == "20260421"
            assert side == "sell"

            class _Dto:
                ord_no = "0056037"
                symbol = "000660"
                status = "주문완료"
                filled_qty = 1
                filled_price = 1218000
                order_qty = 1
                order_price = 1218000
                side = "SELL"
                raw = {}

            return _Dto()

    class _FakeDayPnlReader:
        def get_day_realized_details(self, *, symbol: str = ""):
            assert symbol == "000660"
            return {"rows": []}

    out = apply_live_trade_context(
        lifecycle={"entry": {}, "exit": {}, "holding": {}},
        lifecycle_bundle={"day": "2026-04-21"},
        summary_obj={},
        status="closed",
        monitor_timeline={},
        reporter_obj={},
        reporter_js=Path("reporter.json"),
        reporter_md=Path("reporter.md"),
        entry_run_id="run-entry",
        exit_run_id="run-exit",
        entry_ctx_live={"action": "BUY", "symbol": "000660", "ts": "2026-04-21T00:05:26+00:00"},
        exit_ctx_live={
            "action": "SELL",
            "symbol": "000660",
            "ts": "2026-04-21T00:44:10+00:00",
            "broker_fill_reader": _FakeReader(),
            "broker_day_pnl_reader": _FakeDayPnlReader(),
        },
        entry_bundle={},
        exit_bundle={
            "execution_details": {
                "order_id": "0056037",
                "filled_qty": 1,
            },
            "monitor": {"current_price": 1219000.0},
        },
    )

    assert out["exit_execution_details"]["order_id"] == "0056037"
    assert out["exit_execution_details"]["filled_price"] == 1218000
    assert out["exit_execution_details"]["broker_truth_source"] == "kiwoom.order_status"
