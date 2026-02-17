from __future__ import annotations

import json
from pathlib import Path

from scripts.run_m24_guard_precedence_check import main as closeout_main


def test_m24_6_guard_precedence_check_passes_default(tmp_path: Path, capsys):
    log_path = tmp_path / "intents.jsonl"
    db_path = tmp_path / "intent_state.db"
    rc = closeout_main(
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

    assert rc == 0
    assert obj["ok"] is True
    assert obj["checks"]["reject_after_approved_blocked"] is True
    assert obj["checks"]["executing_state_blocked"] is True
    assert obj["checks"]["duplicate_claim_blocked"] is True
    assert obj["checks"]["preflight_denial_code_ok"] is True


def test_m24_6_guard_precedence_check_fails_when_duplicate_case_skipped(tmp_path: Path, capsys):
    log_path = tmp_path / "intents.jsonl"
    db_path = tmp_path / "intent_state.db"
    rc = closeout_main(
        [
            "--intent-log-path",
            str(log_path),
            "--state-db-path",
            str(db_path),
            "--skip-duplicate-case",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert any("duplicate_claim_not_blocked" in x for x in obj["failures"])
