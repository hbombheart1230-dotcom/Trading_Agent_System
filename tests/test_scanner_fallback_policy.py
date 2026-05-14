from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from graphs.commander_runtime import _run_integrated_chain
from graphs.nodes.scanner_node import scanner_node


_REMOVED_SCANNER_ENV_KEYS = [
    "STRICT_KIWOOM_CANDIDATES_ONLY",
    "BLOCK_STATIC_FALLBACK_WHEN_KIWOOM_EMPTY",
    "CANDIDATE_SOURCE",
    "KIWOOM_CANDIDATE_LIVE_FETCH",
    "KIWOOM_CANDIDATE_INCLUDE_CHANGE_RATE",
]


def _scanner_policy(
    *,
    source_type: str = "kiwoom",
    strict_only: bool = True,
    block_static_when_empty: bool = True,
    live_fetch: bool = True,
    include_change_rate: bool = True,
) -> Dict[str, Any]:
    return {
        "scanner": {
            "source": {"type": source_type},
            "kiwoom": {
                "strict_only": bool(strict_only),
                "live_fetch": bool(live_fetch),
                "include_change_rate": bool(include_change_rate),
            },
            "fallback": {
                "block_static_when_empty": bool(block_static_when_empty),
            },
        }
    }


def test_scanner_removed_env_keys_absent_from_env_example() -> None:
    text = Path("config/.env.example").read_text(encoding="utf-8")
    for key in _REMOVED_SCANNER_ENV_KEYS:
        assert key not in text, key


def test_commander_injects_scanner_policy_defaults_into_applied_policy(monkeypatch) -> None:
    strategist_seen: Dict[str, Any] = {}

    def fake_build_portfolio_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
        state["portfolio_snapshot"] = {"cash": 1_000_000.0, "positions": [], "_health": {"reader_ok": True}}
        return state

    def fake_build_risk_context(state: Dict[str, Any]) -> Dict[str, Any]:
        return state

    def fake_strategist(state: Dict[str, Any]) -> Dict[str, Any]:
        strategist_seen["applied_policy"] = dict(state.get("applied_policy") or {})
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

    assert (((applied.get("scanner") or {}).get("source") or {}).get("type")) == "kiwoom"
    assert (((applied.get("scanner") or {}).get("kiwoom") or {}).get("strict_only")) is True
    assert ((((applied.get("scanner") or {}).get("fallback") or {}).get("block_static_when_empty"))) is True
    assert (((applied.get("scanner") or {}).get("kiwoom") or {}).get("live_fetch")) is True
    assert (((applied.get("scanner") or {}).get("kiwoom") or {}).get("include_change_rate")) is True
    strategist_applied = strategist_seen.get("applied_policy") or {}
    assert (((strategist_applied.get("scanner") or {}).get("kiwoom") or {}).get("live_fetch")) is True
    assert (((strategist_applied.get("scanner") or {}).get("kiwoom") or {}).get("policy_source")) == "commander_applied_policy"

    commander_decision = out.get("commander_decision") or {}
    scanner_fields = (commander_decision.get("commander_applied_policy_summary") or {}).get("scanner_fields") or {}
    assert scanner_fields.get("source_type") == "kiwoom"
    assert scanner_fields.get("strict_only") is True
    assert "scanner.source.type" in list((commander_decision.get("policy_sources") or {}).get("commander_owned_scanner_fields") or [])


def test_scanner_node_uses_kiwoom_results_without_fallback_when_pool_present(monkeypatch) -> None:
    for key in _REMOVED_SCANNER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    state = {
        "applied_policy": _scanner_policy(),
        "mock_top_value_symbols": ["005930", "000660"],
        "mock_top_volume_symbols": ["005930", "000660"],
        "mock_scan_results": {
            "005930": {"score": 0.61, "risk_score": 0.2, "confidence": 0.8},
            "000660": {"score": 0.60, "risk_score": 0.2, "confidence": 0.8},
        },
    }

    out = scanner_node(state)
    scanner_output = out.get("scanner_output") or {}

    assert out.get("top_stock") == "000660"
    assert scanner_output.get("candidate_source") == "kiwoom_market_data"
    assert scanner_output.get("fallback_reason") == ""
    assert scanner_output.get("scanner_candidate_source") == "kiwoom"
    assert scanner_output.get("scanner_policy_source") == "commander_applied_policy"


def test_scanner_node_kiwoom_empty_strict_only_blocks_fallback_without_env(monkeypatch) -> None:
    for key in _REMOVED_SCANNER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    state = {
        "applied_policy": _scanner_policy(strict_only=True, block_static_when_empty=False),
        "strategist_output": {"candidates": ["123456"]},
        "mock_scan_results": {
            "123456": {"score": 0.5, "risk_score": 0.1, "confidence": 0.8},
        },
    }

    out = scanner_node(state)
    scanner_output = out.get("scanner_output") or {}

    assert out.get("top_stock") in ("", None)
    assert scanner_output.get("candidate_source") == "kiwoom"
    assert scanner_output.get("fallback_reason") == "kiwoom_candidate_pool_empty_strict_mode"
    assert scanner_output.get("scanner_fallback_mode") == "strict_kiwoom_only"
    assert scanner_output.get("scanner_strict_mode") is True


def test_scanner_node_kiwoom_empty_allows_static_fallback_when_policy_permits(monkeypatch) -> None:
    for key in _REMOVED_SCANNER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    state = {
        "applied_policy": _scanner_policy(strict_only=False, block_static_when_empty=False),
        "candidates": [
            {"symbol": "005930", "why": "fallback_static", "fallback_source": "static_default"},
            {"symbol": "000660", "why": "fallback_static", "fallback_source": "static_default"},
        ],
        "mock_scan_results": {
            "005930": {"score": 0.6, "risk_score": 0.2, "confidence": 0.8},
            "000660": {"score": 0.5, "risk_score": 0.2, "confidence": 0.8},
        },
    }

    out = scanner_node(state)
    scanner_output = out.get("scanner_output") or {}

    assert out.get("top_stock") == "005930"
    assert scanner_output.get("candidate_source") == "strategist_fallback"
    assert scanner_output.get("scanner_fallback_mode") == "allow_static_fallback"
    assert scanner_output.get("scanner_strict_mode") is False


def test_scanner_candidate_count_regression_stays_at_top_pool_without_env(monkeypatch) -> None:
    monkeypatch.delenv("TOP_N_CANDIDATES", raising=False)
    for key in _REMOVED_SCANNER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    state = {
        "applied_policy": {
            **_scanner_policy(),
            "scanner": {
                **_scanner_policy().get("scanner", {}),
                "candidate": {"top_pool": 6},
                "kiwoom": {
                    **((_scanner_policy().get("scanner") or {}).get("kiwoom") or {}),
                    "condition_limit": 6,
                },
            },
        },
        "mock_top_value_symbols": ["A01", "A02", "A03", "A04", "A05", "A06", "A07"],
        "mock_scan_results": {
            "A01": {"score": 0.61, "risk_score": 0.2, "confidence": 0.8},
            "A02": {"score": 0.60, "risk_score": 0.2, "confidence": 0.8},
            "A03": {"score": 0.59, "risk_score": 0.2, "confidence": 0.8},
            "A04": {"score": 0.58, "risk_score": 0.2, "confidence": 0.8},
            "A05": {"score": 0.57, "risk_score": 0.2, "confidence": 0.8},
            "A06": {"score": 0.56, "risk_score": 0.2, "confidence": 0.8},
        },
    }

    out = scanner_node(state)
    scanner_output = out.get("scanner_output") or {}
    assert int(scanner_output.get("candidate_count") or 0) == 6
    assert int(scanner_output.get("candidate_pool_size") or 0) == 6


def test_scanner_node_relaxes_strict_mode_backfill_when_scan_aggressiveness_active(monkeypatch) -> None:
    for key in _REMOVED_SCANNER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    state = {
        "applied_policy": _scanner_policy(strict_only=True, block_static_when_empty=True),
        "commander_decision": {
            "scanner_policy": {
                "scan_aggressiveness": 0.05,
            }
        },
        "strategist_output": {
            "candidates": [
                {"symbol": "000660", "why": "strategist_backfill"},
            ]
        },
        "mock_top_value_symbols": ["005930"],
        "mock_scan_results": {
            "005930": {"score": 0.61, "risk_score": 0.2, "confidence": 0.8},
            "000660": {"score": 0.60, "risk_score": 0.2, "confidence": 0.8},
        },
    }

    out = scanner_node(state)
    scanner_output = out.get("scanner_output") or {}

    assert scanner_output.get("candidate_source") == "kiwoom_market_data"
    assert scanner_output.get("backfill_used") is True
    assert scanner_output.get("backfill_count") == 1
    assert scanner_output.get("strict_mode_relaxed_by_scan_aggressiveness") is True
    assert scanner_output.get("scan_aggressiveness") == 0.05
    assert int(scanner_output.get("candidate_count") or 0) == 2


def test_scanner_node_expands_sources_when_scan_aggressiveness_active(monkeypatch) -> None:
    for key in _REMOVED_SCANNER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    state = {
        "applied_policy": {
            **_scanner_policy(strict_only=True, block_static_when_empty=True, include_change_rate=False),
            "scanner": {
                **_scanner_policy(strict_only=True, block_static_when_empty=True, include_change_rate=False).get("scanner", {}),
                "candidate": {"top_pool": 2},
                "kiwoom": {
                    **((_scanner_policy(strict_only=True, block_static_when_empty=True, include_change_rate=False).get("scanner") or {}).get("kiwoom") or {}),
                    "condition_limit": 1,
                },
            },
        },
        "commander_decision": {
            "scanner_policy": {
                "scan_aggressiveness": 0.05,
            }
        },
        "strategist_output": {
            "candidates": [
                {"symbol": "051910", "why": "strategist_backfill"},
            ]
        },
        "mock_top_value_symbols": ["005930"],
        "mock_top_volume_symbols": ["005930"],
        "mock_condition_symbols": ["000660"],
        "operator_watchlist": ["035420"],
        "mock_scan_results": {
            "005930": {"score": 0.65, "risk_score": 0.2, "confidence": 0.8},
            "000660": {"score": 0.63, "risk_score": 0.2, "confidence": 0.8},
            "035420": {"score": 0.62, "risk_score": 0.2, "confidence": 0.8},
            "051910": {"score": 0.61, "risk_score": 0.2, "confidence": 0.8},
        },
    }

    out = scanner_node(state)
    scanner_output = out.get("scanner_output") or {}
    source_mix = scanner_output.get("source_mix") or {}

    assert scanner_output.get("aggressive_source_expansion_used") is True
    assert scanner_output.get("candidate_limit_base") == 2
    assert int(scanner_output.get("candidate_limit_effective") or 0) > 2
    assert "condition_search" in list(scanner_output.get("aggressive_source_expansion_sources") or [])
    assert "operator_watchlist" in list(scanner_output.get("aggressive_source_expansion_sources") or [])
    assert source_mix.get("condition_search") == 1
    assert source_mix.get("operator_watchlist") == 1
    assert scanner_output.get("backfill_used") is True
    assert int(scanner_output.get("candidate_count") or 0) >= 4
