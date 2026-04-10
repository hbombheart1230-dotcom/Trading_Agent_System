from __future__ import annotations

from typing import Any, Dict

from graphs.commander_runtime import _run_integrated_chain
from graphs.nodes.scanner_node import scanner_node
from libs.contracts.agent_outputs import build_scanner_output_artifact


def _scanner_policy(source_type: str = "strategist") -> Dict[str, Any]:
    return {
        "universe": {
            "asset_type": "common_stock_only",
        },
        "scanner": {
            "source": {"type": source_type},
            "kiwoom": {
                "strict_only": True,
                "condition_limit": 30,
                "live_fetch": False,
                "include_change_rate": True,
            },
            "fallback": {"block_static_when_empty": True},
            "candidate": {"top_pool": 10},
        },
    }


def test_commander_injects_common_stock_only_universe_policy(monkeypatch) -> None:
    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        state["portfolio_snapshot"] = {"cash": 1_000_000.0, "positions": [], "_health": {"reader_ok": True}}
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        return state

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        state["strategist_output"] = {"playbook": "pullback"}
        return state

    def fake_scanner(state: Dict[str, Any]) -> Dict[str, Any]:
        state["selected"] = {"symbol": "005930"}
        return state

    def fake_monitor(state: Dict[str, Any]) -> Dict[str, Any]:
        state["intents"] = []
        return state

    def fake_decision(state: Dict[str, Any]) -> Dict[str, Any]:
        state["decision"] = "hold"
        return state

    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain({}, execute_fn=lambda state: state)
    applied = out.get("applied_policy") or {}
    commander_decision = out.get("commander_decision") or {}

    assert ((applied.get("universe") or {}).get("asset_type")) == "common_stock_only"
    assert "universe.asset_type" in list((commander_decision.get("policy_sources") or {}).get("commander_owned_universe_fields") or [])
    assert (((commander_decision.get("commander_applied_policy_summary") or {}).get("universe_fields") or {}).get("asset_type")) == "common_stock_only"


def test_scanner_excludes_etf_candidates_and_records_observability() -> None:
    state = {
        "applied_policy": _scanner_policy(),
        "candidates": [
            {
                "symbol": "069500",
                "name": "KODEX 200 ETF",
                "why": "strategist_manual",
                "sources": ["strategist_manual"],
            },
            {
                "symbol": "005930",
                "name": "\uc0bc\uc131\uc804\uc790",
                "why": "strategist_manual",
                "sources": ["strategist_manual"],
            },
        ],
        "mock_scan_results": {
            "069500": {"score": 0.99, "risk_score": 0.2, "confidence": 0.8},
            "005930": {"score": 0.61, "risk_score": 0.2, "confidence": 0.8},
        },
    }

    out = scanner_node(state)
    scanner_output = out.get("scanner_output") or {}
    artifact = build_scanner_output_artifact(out)

    assert out.get("top_stock") == "005930"
    assert int(scanner_output.get("excluded_candidate_count_by_asset_policy") or 0) == 1
    excluded = list(scanner_output.get("excluded_candidates_by_asset_policy") or [])
    assert excluded and excluded[0]["symbol"] == "069500"
    assert excluded[0]["exclusion_reason"] == "etf_or_etn_not_allowed"
    assert excluded[0]["asset_class_detected"] == "etf"
    assert excluded[0]["detection_source"] == "name_heuristic"
    assert [str(row.get("symbol") or "") for row in list(out.get("ranked_candidates") or [])] == ["005930"]
    assert artifact["candidate_pool_snapshot"]["excluded_candidate_count_by_asset_policy"] == 1
    assert artifact["candidate_pool_snapshot"]["excluded_candidates_by_asset_policy"][0]["symbol"] == "069500"
    assert artifact["selected_candidate"]["asset_class_detected"] == "common_stock"


def test_scanner_allows_common_stock_candidates() -> None:
    state = {
        "applied_policy": _scanner_policy(),
        "candidates": [
            {
                "symbol": "000660",
                "name": "SK\ud558\uc774\ub2c9\uc2a4",
                "why": "strategist_manual",
                "sources": ["strategist_manual"],
            }
        ],
        "mock_scan_results": {
            "000660": {"score": 0.74, "risk_score": 0.2, "confidence": 0.86},
        },
    }

    out = scanner_node(state)
    scanner_output = out.get("scanner_output") or {}

    assert out.get("top_stock") == "000660"
    assert int(scanner_output.get("candidate_count") or 0) == 1
    assert int(scanner_output.get("excluded_candidate_count_by_asset_policy") or 0) == 0
    assert (out.get("selected") or {}).get("asset_class_detected") == "common_stock"
