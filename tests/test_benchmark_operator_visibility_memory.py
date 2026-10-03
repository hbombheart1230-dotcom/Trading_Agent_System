from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import benchmark_operator_visibility_memory as bench


def test_gen_fixture_hits_target_sizes_and_writes_target_day(tmp_path: Path) -> None:
    out = tmp_path / "fixture.jsonl"
    result = bench.gen_fixture(out, history_mb=0.5, day_mb=0.1, day="2026-04-08")

    assert out.exists()
    actual_mb = out.stat().st_size / 1024 / 1024
    assert abs(actual_mb - result["total_mb"]) < 0.05
    assert result["total_mb"] >= 0.5
    assert result["day_mb"] >= 0.1
    assert result["target_runs"] > 0

    day_rows = 0
    distinct_run_ids = set()
    with out.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row.get("ts", "").startswith("2026-04-08"):
                day_rows += 1
                distinct_run_ids.add(row["run_id"])
    # 7 events per run (see _target_day_events_for_run) -- realistic
    # multi-event-per-run shape, not 1 row = 1 run.
    assert day_rows == result["target_runs"] * 7
    assert len(distinct_run_ids) == result["target_runs"]


def test_gen_fixture_target_day_rows_exercise_real_fold_stages(tmp_path: Path) -> None:
    out = tmp_path / "fixture.jsonl"
    bench.gen_fixture(out, history_mb=0.1, day_mb=0.05, day="2026-04-08")
    stages_seen = set()
    with out.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row.get("ts", "").startswith("2026-04-08"):
                stages_seen.add(row["stage"])
    # matches the (stage, event) pairs _build_run_contexts actually folds on
    assert {"decision", "commander_router", "scanner", "monitor", "execute_from_packet"} <= stages_seen


@pytest.mark.heavy
def test_measure_runs_isolated_child_and_returns_expected_shape(tmp_path: Path) -> None:
    out = tmp_path / "fixture.jsonl"
    bench.gen_fixture(out, history_mb=0.1, day_mb=0.02, day="2026-04-08")

    result = bench.measure(out, "2026-04-08", "decision_story", tmp_path / "out")

    assert result["func"] == "decision_story"
    assert result["day"] == "2026-04-08"
    assert result["story_total"] > 0
    assert result["elapsed_sec"] > 0
    if platform.system() == "Windows":
        assert result["peak_ws_mb"] is not None
        assert result["peak_ws_mb"] > 0


@pytest.mark.heavy
def test_measure_run_card_also_works(tmp_path: Path) -> None:
    out = tmp_path / "fixture.jsonl"
    bench.gen_fixture(out, history_mb=0.1, day_mb=0.02, day="2026-04-08")

    result = bench.measure(out, "2026-04-08", "run_card", tmp_path / "out")

    assert result["func"] == "run_card"
    assert result["elapsed_sec"] > 0
