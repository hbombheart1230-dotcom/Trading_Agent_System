import json
from pathlib import Path

from libs.reporting.closeout_residual_positions import reconcile_closeout_residual_positions
from libs.reporting.operator_period_summary import generate_operator_daily_summary_artifact
from libs.reporting.symbol_trade_report import build_daily_trade_index


def _snapshot(day: str) -> dict:
    return {
        "schema_version": "kiwoom_account_snapshot.v1",
        "day": day,
        "generated_at": f"{day}T07:08:19+00:00",
        "path": f"data/logs/kiwoom_account_snapshots/{day}/snapshot.json",
        "summary": {"api_call_count": 19, "ok_count": 19, "error_count": 0},
        "calls": [
            {
                "api_id": "ka10170",
                "status": "ok",
                "payload": {
                    "tdy_trde_diary": [
                        {
                            "stk_cd": "396500",
                            "stk_nm": "TIGER 반도체TOP10",
                            "buy_avg_pric": "53241",
                            "buy_qty": "56",
                            "sel_avg_pric": "0",
                            "sell_qty": "0",
                            "cmsn_alm_tax": "10430",
                            "pl_amt": "0",
                            "prft_rt": "0.00",
                        }
                    ]
                },
            },
            {
                "api_id": "kt00018",
                "status": "ok",
                "payload": {
                    "acnt_evlt_remn_indv_tot": [
                        {
                            "stk_cd": "A396500",
                            "stk_nm": "TIGER 반도체TOP10",
                            "rmnd_qty": "000000000000056",
                            "pur_pric": "000000000053241",
                            "cur_prc": "000000053000",
                            "evltv_prft": "-00000000034280",
                            "prft_rt": "-00000001.15",
                        }
                    ]
                },
            },
            {
                "api_id": "kt00007",
                "status": "ok",
                "payload": {
                    "acnt_ord_cntr_prps_dtl": [
                        {
                            "ord_no": "0078938",
                            "stk_cd": "A396500",
                            "io_tp_nm": "현금매수",
                            "ord_tm": "10:31:22",
                            "cntr_qty": "0000000056",
                            "cntr_uv": "0000053241",
                        }
                    ]
                },
            },
        ],
    }


def test_reconcile_closeout_residual_positions_marks_state_and_backfills_open_lifecycle(tmp_path: Path) -> None:
    day = "2026-06-12"
    reports = tmp_path / "reports"
    state_path = tmp_path / "data" / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"mock_positions": [], "open_positions": 0}), encoding="utf-8")

    out = reconcile_closeout_residual_positions(
        reports_root=reports,
        day=day,
        snapshot=_snapshot(day),
        state_path=state_path,
        trigger="test_closeout",
    )

    assert out["ok"] is False
    assert out["unresolved_symbols"] == ["396500"]
    assert out["requires_next_open_flatten"] is True
    created = out["lifecycle_backfill"]["created"]
    assert len(created) == 1
    trade_root = Path(created[0]["trade_root_path"])
    bundle = json.loads((trade_root / "lifecycle_bundle.json").read_text(encoding="utf-8"))
    assert bundle["symbol"] == "396500"
    assert bundle["trade_lifecycle_status"] == "open"
    assert bundle["entry"]["qty"] == 56
    assert bundle["lifecycle"]["entry"]["qty"] == 56
    assert bundle["lifecycle"]["holding"]["status"] == "open"
    assert bundle["closeout_residual_recovery"]["requires_next_open_flatten"] is True

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["open_positions"] == 1
    assert state["mock_positions"][0]["symbol"] == "396500"
    assert state["closeout_backup_liquidation"]["requires_next_open_flatten"] is True
    assert state["closeout_unresolved_flatten_by_symbol"]["396500"]["requires_next_open_flatten"] is True
    assert state["broker_truth_position_reconciliation"]["authoritative"] is True
    assert state["broker_truth_position_reconciliation"]["position_count"] == 1
    assert state["broker_truth_position_reconciliation"]["symbols"] == ["396500"]


def test_operator_daily_summary_surfaces_critical_closeout_risk(tmp_path: Path) -> None:
    day = "2026-06-12"
    reports = tmp_path / "reports"
    data_dir = tmp_path / "data"
    state_path = data_dir / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "mock_positions": [{"symbol": "396500", "qty": 56, "avg_price": 53241.0}],
                "open_positions": 1,
                "closeout_backup_liquidation": {
                    "mode": "broker_truth_unresolved_positions_retained",
                    "reason": "closeout_broker_truth_unresolved_positions_retained",
                    "unresolved_flatten_symbols": ["396500"],
                    "unresolved_flatten_requires_next_open_symbols": ["396500"],
                    "requires_next_open_flatten": True,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    snapshot_dir = data_dir / "logs" / "kiwoom_account_snapshots" / day
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "latest.json").write_text(json.dumps(_snapshot(day), ensure_ascii=False), encoding="utf-8")

    md, _json, payload = generate_operator_daily_summary_artifact(reports_root=reports, day=day)

    risk = payload["residual_positions"]["closeout_operational_risk"]
    assert risk["severity"] == "critical"
    assert risk["unresolved_symbols"] == ["396500"]
    assert payload["operator_readout"]["recommended_actions"][0].startswith("Next open: flatten")
    text = md.read_text(encoding="utf-8-sig")
    assert "CRITICAL: broker truth shows unclosed position" in text
    assert "unresolved_symbols: `396500`" in text


def test_operator_daily_summary_keeps_residual_open_trade_out_of_closed_metrics(tmp_path: Path) -> None:
    day = "2026-06-12"
    reports = tmp_path / "reports"
    state_path = tmp_path / "data" / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"mock_positions": [], "open_positions": 0}), encoding="utf-8")

    reconcile_closeout_residual_positions(
        reports_root=reports,
        day=day,
        snapshot=_snapshot(day),
        state_path=state_path,
        trigger="test_closeout",
    )
    trade_index = build_daily_trade_index(reports, day)

    _md, _json, payload = generate_operator_daily_summary_artifact(
        reports_root=reports,
        day=day,
        daily_report_payload={"day": day, "trade_index": trade_index},
    )

    metrics = payload["metrics"]
    assert metrics["trade_count"] == 1
    assert metrics["closed_trade_count"] == 0
    assert metrics["return_sample_count"] == 0
    assert payload["residual_positions"]["closeout_operational_risk"]["severity"] == "critical"
