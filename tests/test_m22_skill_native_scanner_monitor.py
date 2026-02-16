from __future__ import annotations

import json

from graphs.nodes.monitor_node import monitor_node
from graphs.nodes.scanner_node import scanner_node
from scripts.demo_m22_skill_flow import main as demo_main


def test_m22_scanner_uses_skill_account_orders_for_penalty():
    state = {
        "candidates": [{"symbol": "AAA"}, {"symbol": "BBB"}],
        "mock_scan_results": {
            "AAA": {"score": 0.50, "risk_score": 0.20, "confidence": 0.80},
            "BBB": {"score": 0.50, "risk_score": 0.20, "confidence": 0.80},
        },
        "skill_results": {
            "market.quote": {
                "AAA": {"symbol": "AAA", "cur": 1000},
                "BBB": {"symbol": "BBB", "cur": 1000},
            },
            "account.orders": {
                "rows": [
                    {"symbol": "AAA", "order_id": "x-1"},
                ]
            },
        },
        "policy": {"max_risk": 1.0, "min_confidence": 0.0},
    }

    out = scanner_node(state)
    assert out["selected"]["symbol"] == "BBB"
    assert out["scanner_skill"]["contract_version"] == "m22.skill.v1"
    assert out["scanner_skill"]["used"] is True
    assert out["scanner_skill"]["account_order_rows"] == 1
    assert out["scanner_skill"]["fallback"] is False

    rows = {str(r.get("symbol")): r for r in out.get("scan_results", []) if isinstance(r, dict)}
    assert rows["AAA"]["features"]["skill_open_orders"] == 1
    assert rows["BBB"]["features"]["skill_open_orders"] == 0
    assert rows["AAA"]["risk_score"] > rows["BBB"]["risk_score"]


def test_m22_monitor_reads_order_status_dto_without_changing_intent_shape():
    state = {
        "plan": {"thesis": "demo"},
        "selected": {"symbol": "AAA", "score": 0.9, "risk_score": 0.2, "confidence": 0.8},
        "skill_results": {
            "order.status": {
                "ord_no": "ord-1",
                "symbol": "AAA",
                "status": "PARTIAL",
                "filled_qty": 1,
                "order_qty": 2,
            }
        },
    }

    out = monitor_node(state)
    assert isinstance(out.get("intents"), list) and len(out["intents"]) == 1
    assert out["intents"][0]["symbol"] == "AAA"
    assert out["monitor"]["skill_contract_version"] == "m22.skill.v1"
    assert out["monitor"]["order_status_loaded"] is True
    assert out["monitor"]["order_status"]["status"] == "PARTIAL"
    assert out["monitor"]["order_status"]["ord_no"] == "ord-1"
    assert out["monitor"]["order_status_fallback"] is False
    assert out["monitor"]["order_lifecycle_loaded"] is True
    assert out["monitor"]["order_lifecycle"]["stage"] == "partial_fill"
    assert out["monitor"]["order_lifecycle"]["terminal"] is False
    assert out["monitor"]["order_lifecycle"]["progress"] == 0.5


def test_m22_monitor_maps_filled_lifecycle_from_qty_progress():
    state = {
        "selected": {"symbol": "AAA"},
        "order_status": {
            "ord_no": "ord-2",
            "symbol": "AAA",
            "status": "OPEN",
            "filled_qty": 2,
            "order_qty": 2,
        },
    }

    out = monitor_node(state)
    life = out["monitor"]["order_lifecycle"]
    assert life["stage"] == "filled"
    assert life["terminal"] is True
    assert life["progress"] == 1.0


def test_m22_monitor_maps_cancelled_lifecycle_from_status_text():
    state = {
        "selected": {"symbol": "AAA"},
        "order_status": {
            "ord_no": "ord-3",
            "symbol": "AAA",
            "status": "CANCELLED",
            "filled_qty": 0,
            "order_qty": 2,
        },
    }

    out = monitor_node(state)
    life = out["monitor"]["order_lifecycle"]
    assert life["stage"] == "cancelled"
    assert life["terminal"] is True
    assert life["progress"] == 0.0


def test_m22_scanner_falls_back_safely_on_skill_timeout_errors():
    state = {
        "candidates": [{"symbol": "AAA"}, {"symbol": "BBB"}],
        "mock_scan_results": {
            "AAA": {"score": 0.20, "risk_score": 0.20, "confidence": 0.80},
            "BBB": {"score": 0.80, "risk_score": 0.20, "confidence": 0.80},
        },
        "skill_results": {
            "market.quote": {"action": "error", "meta": {"error_type": "TimeoutError"}},
            "account.orders": {"result": {"action": "ask", "question": "symbol required"}},
        },
    }

    out = scanner_node(state)
    assert out["selected"]["symbol"] == "BBB"  # baseline scoring still works
    assert out["scanner_skill"]["fallback"] is True
    assert out["scanner_skill"]["error_count"] == 2
    reasons = out["scanner_skill"]["fallback_reasons"]
    assert any("market.quote:error:TimeoutError" in x for x in reasons)
    assert any("account.orders:ask" in x for x in reasons)


def test_m22_monitor_falls_back_safely_on_order_status_timeout():
    state = {
        "selected": {"symbol": "AAA"},
        "skill_results": {
            "order.status": {"result": {"action": "error", "meta": {"error_type": "TimeoutError"}}}
        },
    }

    out = monitor_node(state)
    assert out["monitor"]["order_status_loaded"] is False
    assert out["monitor"]["order_lifecycle_loaded"] is False
    assert out["monitor"]["order_status_fallback"] is True
    assert out["monitor"]["order_status_error_count"] == 1
    assert out["monitor"]["order_status_fallback_reasons"][0].startswith("order.status:error:TimeoutError")


def test_m22_demo_script_outputs_skill_visible_summary(capsys):
    rc = demo_main(["--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["skill_contract_version"]["scanner"] == "m22.skill.v1"
    assert obj["skill_contract_version"]["monitor"] == "m22.skill.v1"
    assert obj["scanner_skill"]["used"] is True
    assert obj["selected"]["symbol"] in ("005930", "000660", "035420")
    assert isinstance(obj["top"], list) and len(obj["top"]) >= 1
    assert obj["monitor"]["order_status_loaded"] is True
    assert obj["order_lifecycle"]["stage"] == "partial_fill"


def test_m22_demo_script_simulate_timeout_shows_fallbacks(capsys):
    rc = demo_main(["--simulate-timeout", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["scanner_skill"]["fallback"] is True
    assert obj["scanner_skill"]["error_count"] >= 1
    assert obj["monitor"]["order_status_fallback"] is True
    assert obj["monitor"]["order_status_loaded"] is False
    assert obj["order_lifecycle"] is None
