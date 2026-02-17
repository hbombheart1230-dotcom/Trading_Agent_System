from __future__ import annotations

import json
from pathlib import Path

from libs.supervisor.intent_state_store import (
    INTENT_STATE_APPROVED,
    INTENT_STATE_EXECUTED,
    INTENT_STATE_REJECTED,
    SQLiteIntentStateStore,
)
from scripts.reconcile_intent_state_store import main as reconcile_main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _seed_dataset(log_path: Path, db_path: Path) -> None:
    _write_jsonl(
        log_path,
        [
            {"ts": 1, "intent_id": "i1", "intent": {"intent_id": "i1"}},
            {"ts": 2, "intent_id": "i1", "status": "approved", "intent": {"intent_id": "i1"}},
            {"ts": 3, "intent_id": "i1", "status": "executed", "intent": {"intent_id": "i1"}},
            {"ts": 4, "intent_id": "i2", "intent": {"intent_id": "i2"}},
            {"ts": 5, "intent_id": "i2", "status": "rejected", "intent": {"intent_id": "i2"}},
        ],
    )

    st = SQLiteIntentStateStore(str(db_path))
    # i1 mismatch: expected executed but sqlite is approved.
    st.ensure_intent("i1")
    st.transition(intent_id="i1", to_state=INTENT_STATE_APPROVED, expected_from_state="pending_approval")
    # i3 orphan: exists only in sqlite.
    st.ensure_intent("i3")


def test_m24_4_reconcile_reports_missing_mismatch_and_orphan(tmp_path: Path, capsys):
    log_path = tmp_path / "intents.jsonl"
    db_path = tmp_path / "intent_state.db"
    _seed_dataset(log_path, db_path)

    rc = reconcile_main(
        [
            "--intent-log-path",
            str(log_path),
            "--state-db-path",
            str(db_path),
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert obj["missing_total_before"] == 1
    assert obj["mismatch_total_before"] == 1
    assert obj["orphan_total_before"] == 1
    assert "i2" in obj["details"]["missing_before"]
    assert "i1" in obj["details"]["mismatch_before"]
    assert "i3" in obj["details"]["orphan_before"]


def test_m24_4_reconcile_repair_fixes_missing_and_mismatch(tmp_path: Path, capsys):
    log_path = tmp_path / "intents.jsonl"
    db_path = tmp_path / "intent_state.db"
    _seed_dataset(log_path, db_path)

    rc = reconcile_main(
        [
            "--intent-log-path",
            str(log_path),
            "--state-db-path",
            str(db_path),
            "--repair",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["missing_total_after"] == 0
    assert obj["mismatch_total_after"] == 0
    assert obj["repaired_total"] >= 2

    st = SQLiteIntentStateStore(str(db_path))
    assert st.get_state("i1")["state"] == INTENT_STATE_EXECUTED
    assert st.get_state("i2")["state"] == INTENT_STATE_REJECTED
