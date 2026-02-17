from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from libs.supervisor.intent_state_store import (
    INTENT_STATE_APPROVED,
    INTENT_STATE_EXECUTED,
    INTENT_STATE_EXECUTING,
    INTENT_STATE_PENDING,
    INTENT_STATE_REJECTED,
    SQLiteIntentStateStore,
)
from scripts.query_intent_state_store import main as query_main


def _seed_base_states(db_path: Path) -> None:
    st = SQLiteIntentStateStore(str(db_path))
    st.ensure_intent("i1", initial_state=INTENT_STATE_PENDING)
    st.transition(intent_id="i1", to_state=INTENT_STATE_APPROVED, expected_from_state=INTENT_STATE_PENDING)
    st.transition(intent_id="i1", to_state=INTENT_STATE_EXECUTING, expected_from_state=INTENT_STATE_APPROVED)
    st.transition(intent_id="i1", to_state=INTENT_STATE_EXECUTED, expected_from_state=INTENT_STATE_EXECUTING)

    st.ensure_intent("i2", initial_state=INTENT_STATE_PENDING)
    st.transition(intent_id="i2", to_state=INTENT_STATE_REJECTED, expected_from_state=INTENT_STATE_PENDING)


def test_m24_7_query_intent_state_summary_json(tmp_path: Path, capsys):
    db_path = tmp_path / "intent_state.db"
    _seed_base_states(db_path)

    rc = query_main(["--state-db-path", str(db_path), "--json", "--limit", "10"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    summary = obj["summary"]

    assert rc == 0
    assert obj["ok"] is True
    assert summary["total"] == 2
    assert summary["current_state_total"]["executed"] == 1
    assert summary["current_state_total"]["rejected"] == 1
    assert summary["journal_transition_total"]["approved->executing"] == 1
    assert summary["journal_transition_total"]["executing->executed"] == 1
    assert len(obj["recent_journal"]) >= 1


def test_m24_7_query_intent_state_filter_by_state(tmp_path: Path, capsys):
    db_path = tmp_path / "intent_state.db"
    _seed_base_states(db_path)

    rc = query_main(["--state-db-path", str(db_path), "--state", "executed", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    summary = obj["summary"]

    assert rc == 0
    assert summary["total"] == 1
    assert summary["current_state_total"] == {"executed": 1}
    assert summary["journal_transition_total"] == {"executing->executed": 1}


def test_m24_7_query_intent_state_require_no_stuck_returns_3(tmp_path: Path, capsys):
    db_path = tmp_path / "intent_state.db"
    st = SQLiteIntentStateStore(str(db_path))
    st.ensure_intent("i3", initial_state=INTENT_STATE_PENDING)
    st.transition(intent_id="i3", to_state=INTENT_STATE_APPROVED, expected_from_state=INTENT_STATE_PENDING)
    st.transition(intent_id="i3", to_state=INTENT_STATE_EXECUTING, expected_from_state=INTENT_STATE_APPROVED)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("UPDATE intent_state SET updated_ts = ? WHERE intent_id = ?", (1, "i3"))
        conn.commit()

    rc = query_main(
        [
            "--state-db-path",
            str(db_path),
            "--stuck-executing-sec",
            "300",
            "--require-no-stuck",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    summary = obj["summary"]

    assert rc == 3
    assert summary["stuck_executing_total"] == 1
    assert summary["stuck_executing"][0]["intent_id"] == "i3"


def test_m24_7_query_intent_state_missing_db_returns_2(tmp_path: Path):
    missing = tmp_path / "missing.db"
    rc = query_main(["--state-db-path", str(missing)])
    assert rc == 2
