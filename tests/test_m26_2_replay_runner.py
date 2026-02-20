from __future__ import annotations

import json
from pathlib import Path

from scripts.run_m26_dataset_manifest_check import main as manifest_main
from scripts.run_m26_replay_runner import main as replay_main


def test_m26_2_replay_runner_passes_with_seeded_dataset(tmp_path: Path, capsys):
    root = tmp_path / "m26_dataset"

    rc_seed = manifest_main(["--dataset-root", str(root), "--seed-demo", "--json"])
    out_seed = capsys.readouterr().out.strip()
    obj_seed = json.loads(out_seed)
    assert rc_seed == 0
    assert obj_seed["ok"] is True

    rc = replay_main(["--dataset-root", str(root), "--day", "2026-02-17", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["missing_file_total"] == 0
    assert obj["replayed_intent_total"] >= 1
    assert obj["executed_intent_total"] >= 1
    assert obj["fill_qty_total"] >= 1
    assert obj["fill_notional_total"] > 0.0


def test_m26_2_replay_runner_fails_when_day_filter_excludes_events(tmp_path: Path, capsys):
    root = tmp_path / "m26_dataset"
    rc_seed = manifest_main(["--dataset-root", str(root), "--seed-demo", "--json"])
    _ = capsys.readouterr().out.strip()
    assert rc_seed == 0

    rc = replay_main(["--dataset-root", str(root), "--day", "2099-01-01", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert obj["replayed_intent_total"] == 0
    assert any("replayed_intent_total < 1" in x for x in obj["failures"])


def test_m26_2_replay_runner_fails_when_required_files_missing(tmp_path: Path, capsys):
    root = tmp_path / "missing"
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps({"schema_version": "m26.dataset_manifest.v1", "dataset_id": "x", "components": {}}, ensure_ascii=False),
        encoding="utf-8",
    )

    rc = replay_main(["--dataset-root", str(root), "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert obj["missing_file_total"] >= 1
    assert any("missing_required_files" in x for x in obj["failures"])
