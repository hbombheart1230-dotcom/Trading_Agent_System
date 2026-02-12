from __future__ import annotations

from libs.storage.state_store import StateStore
from libs.core.settings import Settings


def save_state(state: dict) -> dict:
    """M10-1 node: save persisted state.

    Expects:
      - state['persisted_state']
    """
    s = Settings.from_env()
    store = StateStore(s.state_store_path)
    store.save(state.get("persisted_state") or {})
    return state
