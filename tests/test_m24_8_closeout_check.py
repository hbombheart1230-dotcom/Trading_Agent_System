from __future__ import annotations

import json
from pathlib import Path

from scripts.run_m24_closeout_check import main as closeout_main


def test_m24_8_closeout_check_passes_default(tmp_path: Path, capsys):
    intent_log_path = tmp_path / "intents.jsonl"
    state_db_path = tmp_path / "intent_state.db"

    rc = closeout_main(
        [
            "--intent-log-path",
            str(intent_log_path),
            "--state-db-path",
            str(state_db_path),
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["guard"]["rc"] == 0
    assert obj["query"]["rc"] == 0
    assert obj["state_summary"]["total"] >= 3
    assert obj["state_summary"]["journal_transition_total"]["approved->executing"] >= 1
    assert obj["state_summary"]["journal_transition_total"]["executing->executed"] >= 1
    assert obj["state_summary"]["stuck_executing_total"] == 0


def test_m24_8_closeout_check_fails_when_stuck_injected(tmp_path: Path, capsys):
    intent_log_path = tmp_path / "intents.jsonl"
    state_db_path = tmp_path / "intent_state.db"

    rc = closeout_main(
        [
            "--intent-log-path",
            str(intent_log_path),
            "--state-db-path",
            str(state_db_path),
            "--inject-stuck-case",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert obj["query"]["rc"] == 3
    assert obj["state_summary"]["stuck_executing_total"] >= 1
    assert any("stuck_executing_total" in x for x in obj["failures"])
