from __future__ import annotations

import json
from pathlib import Path

from scripts.run_m23_resilience_closeout_check import main as closeout_main


def test_m23_8_closeout_check_passes_default(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    rc = closeout_main(
        [
            "--event-log-path",
            str(events),
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["query_summary"]["cooldown_transition_total"] >= 1
    assert obj["query_summary"]["intervention_total"] >= 1
    assert obj["query_summary"]["error_total"] >= 1


def test_m23_8_closeout_check_fails_when_error_case_skipped(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    rc = closeout_main(
        [
            "--event-log-path",
            str(events),
            "--skip-error-case",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert any("error_total < 1" in x for x in obj["failures"])
