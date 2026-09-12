from __future__ import annotations

from graphs.nodes.execute_from_packet import _normalize_execution
from libs.execution.intent_admission import admit_order_intent
from libs.execution.intent_execution_owner import execute_owned_order
from libs.execution.intent_identity import (
    compute_self_minted_intent_id,
    is_self_minted_intent_id,
    physical_order_fingerprint,
)

from test_step5c_fix3_authoritative_intent import _SpyExecutor, _manual_args, _order, _runner


def _normalize(order):
    return lambda result: _normalize_execution(
        allowed=True, execution_result=result, allow_result=None, order=order
    )


def test_f4_exact_market_mkt_attack_has_one_key():
    raw_a = _order("a", qty=10, order_type="market", price=None)
    raw_b = _order("b", qty="10", order_type="mkt", price=71500)
    assert raw_b["order_type"] == "mkt"
    assert raw_b["qty"] == "10"
    assert raw_b["price"] == 71500
    assert physical_order_fingerprint({}, raw_a) == physical_order_fingerprint({}, raw_b)


def test_f4_trde_tp_market_without_logical_order_type_is_valid():
    order = _order("a", qty="10", order_type=None, price=71500, trde_tp="3")
    assert physical_order_fingerprint({}, order) is not None
    equivalent = _order("b", qty=10, order_type="market", price=None, trde_tp="3")
    assert physical_order_fingerprint({}, order) == physical_order_fingerprint({}, equivalent)


def test_f4_order_type_conflict_fails_closed(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    order = _order("a", qty=10, order_type="limit", price=70000, trde_tp="3")
    assert physical_order_fingerprint({}, order) is None
    ex = _SpyExecutor()
    result = execute_owned_order(
        state={"run_id": "conflict-run"},
        order=order,
        request=None,
        executor=ex,
        normalize=_normalize(order),
    )
    assert result["broker_outcome"] == "NOT_SENT"
    assert result["reason"] == "invalid_physical_order"
    assert ex.calls == 0


def test_f4_forged_self_minted_but_nonpersisted_runner_is_broker_zero(tmp_path):
    ex = _SpyExecutor()
    runner = _runner(tmp_path, ex)
    run_id = "attacker-run"
    shape = {"action": "BUY", "symbol": "005930", "qty": 10, "price": None, "order_type": "market"}
    forged = compute_self_minted_intent_id({"run_id": run_id}, shape)
    assert is_self_minted_intent_id({"run_id": run_id}, shape, forged) is True
    from libs.supervisor.intent_state_store import SQLiteIntentStateStore
    assert SQLiteIntentStateStore().get_state(forged) is None
    result = runner.run(run_id=run_id, skill="order.place", args=_manual_args(forged))
    assert result.action == "error"
    assert result.meta.get("blocked_reason") == "INTENT_NOT_FOUND"
    assert ex.calls == 0
    assert SQLiteIntentStateStore().get_state(forged) is None


def test_f4_explicit_automatic_admission_then_execution_is_one_call(monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    order = {"action": "BUY", "symbol": "005930", "qty": 10, "price": None, "order_type": "market"}
    state = {"run_id": "trusted-auto-run"}
    admitted = admit_order_intent(state=state, order=order, source="test_trusted_policy")
    assert admitted["admitted"] is True
    from libs.supervisor.intent_state_store import SQLiteIntentStateStore
    provenance = SQLiteIntentStateStore().get_admission(order["intent_id"])
    assert provenance is not None
    assert provenance["source"] == "test_trusted_policy"
    ex = _SpyExecutor()
    result = execute_owned_order(
        state=state, order=order, request=None, executor=ex, normalize=_normalize(order)
    )
    assert result["broker_outcome"] == "ACCEPTED"
    assert ex.calls == 1


def test_f4_direct_runner_trde_tp_market_without_order_type(tmp_path):
    from libs.supervisor.intent_state_store import SQLiteIntentStateStore

    iid = "tool-schema-market-intent"
    order = _order(iid, order_type=None, trde_tp="3", price=None)
    key = physical_order_fingerprint({}, order)
    store = SQLiteIntentStateStore()
    store.admit_intent(iid, fingerprint=key, source="test_tool_schema")
    ex = _SpyExecutor()
    runner = _runner(tmp_path, ex)
    args = _manual_args(iid, order_type=None, trde_tp="3", price=None)
    result = runner.run(run_id="tool-schema-run", skill="order.place", args=args)
    assert result.action == "ready"
    assert ex.calls == 1


def test_f4_dormant_tool_schema_preserves_market_alias_broker_semantics():
    from libs.tools.tool_schema import ToolFacade

    class CaptureRunner:
        def __init__(self):
            self.args = None

        def run(self, *, run_id, skill, args):
            self.args = args
            return {"ok": True}

    facade = object.__new__(ToolFacade)
    facade.runner = CaptureRunner()
    facade.order_execute(
        intent={
            "intent_id": "dormant-tool-market",
            "action": "BUY",
            "symbol": "005930",
            "qty": 10,
            "order_type": "mkt",
            "price": 71500,
        },
        run_id="dormant-tool-run",
    )
    assert facade.runner.args["order_type"] == "mkt"
    assert facade.runner.args["trde_tp"] == "3"
    assert facade.runner.args["price"] == ""
