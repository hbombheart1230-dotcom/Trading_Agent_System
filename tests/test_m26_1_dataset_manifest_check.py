from __future__ import annotations

import json
from pathlib import Path

from scripts.run_m26_dataset_manifest_check import main as manifest_main


def test_m26_1_dataset_manifest_check_passes_with_seed_demo(tmp_path: Path, capsys):
    root = tmp_path / "m26_dataset"
    rc = manifest_main(
        [
            "--dataset-root",
            str(root),
            "--seed-demo",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["schema_version"] == "m26.dataset_manifest.v1"
    assert obj["missing_file_total"] == 0
    assert obj["failure_total"] == 0
    assert (root / "manifest.json").exists() is True


def test_m26_1_dataset_manifest_check_fails_when_files_missing(tmp_path: Path, capsys):
    root = tmp_path / "m26_dataset_missing"
    root.mkdir(parents=True, exist_ok=True)

    rc = manifest_main(
        [
            "--dataset-root",
            str(root),
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert obj["missing_file_total"] >= 1
    assert obj["failure_total"] >= 1
    assert any("missing:manifest.json" in x for x in obj["failures"])
