from __future__ import annotations

from typing import Any, Dict

import pytest

from graphs.commander_runtime import _run_integrated_chain
from graphs.nodes.execute_from_packet import execute_from_packet
from graphs.nodes.scanner_node import scanner_node
from libs.contracts.agent_outputs import build_scanner_output_artifact
import libs.runtime.asset_universe_policy as asset_universe_policy


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


def test_commander_injects_all_tradable_universe_policy(monkeypatch) -> None:
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

    assert ((applied.get("universe") or {}).get("asset_type")) == "all_tradable"
    assert "universe.asset_type" in list((commander_decision.get("policy_sources") or {}).get("commander_owned_universe_fields") or [])
    assert (((commander_decision.get("commander_applied_policy_summary") or {}).get("universe_fields") or {}).get("asset_type")) == "all_tradable"


def test_scanner_allows_etf_when_universe_is_all_tradable() -> None:
    policy = _scanner_policy()
    policy["universe"]["asset_type"] = "all_tradable"
    state = {
        "applied_policy": policy,
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

    assert out.get("top_stock") == "069500"
    assert int(scanner_output.get("excluded_candidate_count_by_asset_policy") or 0) == 0
    assert [str(row.get("symbol") or "") for row in list(out.get("ranked_candidates") or [])] == [
        "069500",
        "005930",
    ]
    assert (out.get("selected") or {}).get("asset_class_detected") == "etf"


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
    assert len(excluded) == int(scanner_output.get("excluded_candidate_count_by_asset_policy") or 0)
    assert excluded and excluded[0]["symbol"] == "069500"
    assert excluded[0]["exclusion_reason"] == "etf_or_etn_not_allowed"
    assert excluded[0]["asset_class_detected"] == "etf"
    assert excluded[0]["detection_source"] == "name_heuristic_extended"
    assert scanner_output.get("unknown_asset_candidate_count") == 0
    assert (scanner_output.get("asset_detection_stats") or {}).get("by_asset_class", {}).get("etf") == 1
    assert (scanner_output.get("asset_detection_stats") or {}).get("by_asset_class", {}).get("common_stock") == 1
    assert [str(row.get("symbol") or "") for row in list(out.get("ranked_candidates") or [])] == ["005930"]
    assert artifact["candidate_pool_snapshot"]["excluded_candidate_count_by_asset_policy"] == 1
    assert artifact["candidate_pool_snapshot"]["total_candidates_before_filter"] == 2
    assert artifact["candidate_pool_snapshot"]["total_candidates_after_filter"] == 1
    assert artifact["candidate_pool_snapshot"]["excluded_candidates_by_asset_policy"][0]["symbol"] == "069500"
    assert artifact["selected_candidate"]["asset_class_detected"] == "common_stock"
    assert artifact["selected_candidate"]["detection_source"] == "name_heuristic"


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
    assert (out.get("selected") or {}).get("detection_source") == "name_heuristic"


def test_scanner_classifies_symbol_only_common_stock_candidates_via_remote_profile(monkeypatch) -> None:
    profiles = {
        "000660": {"stk_cd": "000660", "stk_nm": "SK\ud558\uc774\ub2c9\uc2a4", "mkt_tp_nm": "\ucf54\uc2a4\ud53c"},
        "005930": {"stk_cd": "005930", "stk_nm": "\uc0bc\uc131\uc804\uc790", "mkt_tp_nm": "\ucf54\uc2a4\ud53c"},
    }
    monkeypatch.setattr(
        asset_universe_policy,
        "_lookup_remote_symbol_profile",
        lambda symbol: dict(profiles.get(str(symbol), {})),
    )

    state = {
        "applied_policy": _scanner_policy(),
        "candidates": [
            {"symbol": "000660", "why": "strategist_manual", "sources": ["strategist_manual"]},
            {"symbol": "005930", "why": "strategist_manual", "sources": ["strategist_manual"]},
        ],
        "mock_scan_results": {
            "000660": {"score": 0.74, "risk_score": 0.2, "confidence": 0.86},
            "005930": {"score": 0.61, "risk_score": 0.2, "confidence": 0.8},
        },
    }

    out = scanner_node(state)
    scanner_output = out.get("scanner_output") or {}
    ranked = list(out.get("ranked_candidates") or [])

    assert out.get("top_stock") == "000660"
    assert scanner_output.get("unknown_asset_candidate_count") == 0
    assert scanner_output.get("selected_asset_class_detected") == "common_stock"
    assert scanner_output.get("selected_asset_detection_source") == "name_heuristic"
    assert {row.get("symbol"): row for row in ranked}["000660"]["asset_class_detected"] == "common_stock"
    assert {row.get("symbol"): row for row in ranked}["005930"]["asset_class_detected"] == "common_stock"


@pytest.mark.parametrize(
    ("name", "expected_asset_class"),
    [
        ("KODEX 200", "etf"),
        ("TIGER \ubc18\ub3c4\uccb4TOP10", "etf"),
        ("KBSTAR \ubbf8\uad6d\ub098\uc2a4\ub2e5100", "etf"),
        ("ARIRANG \uace0\ubc30\ub2f9\uc8fc", "etf"),
        ("HANARO \uc6d0\uc790\ub825iSelect", "etf"),
        ("SOL \ubc18\ub3c4\uccb4TOP3\ud50c\ub7ec\uc2a4", "etf"),
        ("ACE US S&P500", "etf"),
        ("KOSEF \uad6d\uace0\ucc4410\ub144", "etf"),
        ("\uc0bc\uc131 \ub808\ubc84\ub9ac\uc9c0", "leveraged_etf"),
        ("\uc0bc\uc131 \uc778\ubc84\uc2a4", "inverse_etf"),
        ("TIMEFOLIO \ucf54\ub9ac\uc544\ud50c\ub7ec\uc2a4\uc561\ud2f0\ube0c", "active_etf"),
        ("KODEX \ubbf8\uad6d\ucc44\uc6b8\ud2b8\ub77c30\ub144\uc120\ubb3c", "futures_etf"),
        ("PLUS \uace0\ubc30\ub2f9\uc8fcTR", "tr_index_product"),
        ("KODEX \ubbf8\uad6d\ubc30\ub2f9\ucee4\ubc84\ub4dc\ucf5c\uc561\ud2f0\ube0c", "covered_call_etf"),
    ],
)
def test_asset_resolver_classifies_korean_etf_family_names(name: str, expected_asset_class: str) -> None:
    inspection = asset_universe_policy.inspect_asset_universe_candidate(
        symbol="999999",
        candidate={"symbol": "999999", "name": name},
        state={"applied_policy": _scanner_policy()},
        policy={},
    )

    assert inspection["asset_class_detected"] == expected_asset_class
    assert inspection["detection_source"] in {"name_heuristic", "name_heuristic_extended"}


def test_scanner_and_executor_share_asset_resolver_results(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setattr(
        asset_universe_policy,
        "_lookup_remote_symbol_profile",
        lambda symbol: {"stk_cd": str(symbol), "stk_nm": "TIGER \ubc18\ub3c4\uccb4TOP10"},
    )

    state = {
        "applied_policy": _scanner_policy(),
        "candidates": [
            {"symbol": "396500", "why": "strategist_manual", "sources": ["strategist_manual"]},
        ],
        "mock_scan_results": {
            "396500": {"score": 0.91, "risk_score": 0.2, "confidence": 0.82},
        },
    }
    scanner_out = scanner_node(state)
    scanner_output = scanner_out.get("scanner_output") or {}
    excluded = list(scanner_output.get("excluded_candidates_by_asset_policy") or [])
    assert excluded

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )
    exec_state = {
        "catalog_path": str(cat),
        "applied_policy": _scanner_policy(),
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "396500", "qty": 1, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }
    exec_out = execute_from_packet(exec_state)
    guard = exec_out["execution"]["asset_universe_guard"]

    assert guard["asset_class_detected"] == excluded[0]["asset_class_detected"]
    assert guard["detection_source"] == excluded[0]["detection_source"]
    assert guard["detection_field"] == excluded[0]["detection_field"]
