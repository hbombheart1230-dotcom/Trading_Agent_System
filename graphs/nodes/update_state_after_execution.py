from __future__ import annotations

import time


def update_state_after_execution(state: dict) -> dict:
    """M10-3 node: update persisted_state after an execution attempt.

    Inputs:
      - state['execution'] (dict-like), may include:
          - ok: bool
          - blocked: bool
          - reason: str
          - executor: str
          - order: dict
      - state['persisted_state'] (dict)

    Produces:
      - state['persisted_state'] updated:
          - last_order_epoch (only when execution ok == True OR order was actually sent)
          - last_execution_ok
          - last_execution_reason
    """
    ps = state.get("persisted_state") or {}
    ex = state.get("execution") or {}

    ok = bool(ex.get("ok", False))
    blocked = bool(ex.get("blocked", False))

    # update audit info always
    ps["last_execution_ok"] = ok
    ps["last_execution_reason"] = ex.get("reason") or ex.get("error") or ("blocked" if blocked else "")

    # Only set last_order_epoch when an order was actually sent.
    # Convention:
    # - In dry-run mode, execution should NOT be treated as "order sent"
    # - In real mode, ok=True implies it was sent
    order_sent = ok and not bool(ex.get("dry_run", False))

    if order_sent:
        ps["last_order_epoch"] = int(time.time())

    state["persisted_state"] = ps
    return state
