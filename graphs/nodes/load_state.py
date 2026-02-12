from __future__ import annotations

from libs.storage.state_store import StateStore
from libs.core.settings import Settings


def load_state(state: dict) -> dict:
    """M10-1 node: load persisted state into pipeline state.

    Produces:
      - state['persisted_state']
    """
    s = Settings.from_env()
    store = StateStore(s.state_store_path)
    state["persisted_state"] = store.load()
    return state
