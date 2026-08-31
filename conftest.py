import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _isolate_unknown_quarantine_guard(monkeypatch, tmp_path):
    """Phase 1 Step 5B: the UNKNOWN-outcome quarantine guard
    (graphs/nodes/execute_from_packet.py::_evaluate_unknown_quarantine_guard)
    runs unconditionally for every BUY/SELL/CANCEL/MODIFY -- unlike the
    opt-in recent_buy/sell guard, it has no "disabled unless configured"
    default. Without a project-wide isolation fixture here, any test that
    exercises an UNKNOWN broker outcome would write a real quarantine record
    to data/state/execution_unknown_quarantine.json, silently blocking
    unrelated tests (and any other process) that later touch the same
    symbol. Global + autouse so no test file has to remember to opt in.
    """
    monkeypatch.setenv("UNKNOWN_QUARANTINE_GUARD_PATH", str(tmp_path / "unknown_quarantine.json"))
