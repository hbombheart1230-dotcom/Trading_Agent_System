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

    # Backward/forward compatible success shape:
    # - legacy: execution["ok"]
    # - current: execution["allowed"]
    if "ok" in ex:
        ok = bool(ex.get("ok", False))
    else:
        ok = bool(ex.get("allowed", False))

    if "blocked" in ex:
        blocked = bool(ex.get("blocked", False))
    else:
        blocked = not bool(ex.get("allowed", False))

    # update audit info always
    ps["last_execution_ok"] = ok
    ps["last_execution_reason"] = ex.get("reason") or ex.get("error") or ("blocked" if blocked else "")

    # Only set last_order_epoch when an order was actually sent.
    # Convention:
    # - In dry-run/mock mode, execution should NOT be treated as "order sent"
    # - In real mode, success implies it was sent
    payload = ex.get("payload") if isinstance(ex.get("payload"), dict) else {}
    mode = str(payload.get("mode") or "").strip().lower()
    is_dry = bool(ex.get("dry_run", False)) or (mode == "mock")
    order_sent = ok and not is_dry

    if order_sent:
        ps["last_order_epoch"] = int(time.time())

    state["persisted_state"] = ps
    return state
