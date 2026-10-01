"""Regression coverage for the P1.2 daily UEF EOD orchestrator
(libs/reporting/evaluation/daily_uef_pipeline.py) -- authority-closure
revision (Codex bounded re-audit, 2026-09-29).

Covers, in order: the retained Fix2 findings (single-capture mutation,
closeout canonical bypass, per-source freshness including a legitimate
same-day zero-event state, feature_candidates PRESENT_ONLY, diagnostic
mode never publishing, UEF-9 failure, idempotency), and the new authority-
closure findings (legacy CLI bypass removed, unknown-source fail-closed,
registered-optional-source-absent allowed, partial-bundle non-authority,
same-day replacement failure safety, a complete generation's manifest/
pointers/hashes, tampered-artifact detection, latest.md failure isolation
from machine authority, and no trading/broker/runtime side effects).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from libs.reporting.alpha_research_board import build_alpha_research_board
from libs.reporting.evaluation.daily_uef_pipeline import (
    evaluate_source_freshness_contracts,
    resolve_canonical_alpha_board,
    run_daily_uef_evaluation,
    verify_generation_manifest,
)

ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


_FEATURE_CANDIDATES_PAYLOAD = {
    "schema_version": "rank1_candidate_selection.v1",
    "behavior_effect": "NONE_OFFLINE_RESEARCH_ONLY",
    "selection_period": {"validation_start": "2026-08-01", "selection_end_day": "2026-08-11"},
    "prospective_shadow_candidates": [
        {
            "feature": "scanner.risk_band",
            "category": "HIGH",
            "target": "+30m",
            "train": {"day_symbol_count": 24, "win_rate": 0.58, "avg_net_return_pct": 1.4},
            "validation": {"day_symbol_count": 18, "win_rate": 0.5, "avg_net_return_pct": 1.2},
        },
        {
            "feature": "chart.daily_ma5_20_cross_state",
            "category": "POST_CROSS_EXTENDED",
            "target": "+15m",
            "train": {"day_symbol_count": 10, "win_rate": 0.8, "avg_net_return_pct": 3.5},
            "validation": {"day_symbol_count": 7, "win_rate": 0.71, "avg_net_return_pct": 0.88},
        },
    ],
}

_PROSPECTIVE_CANDIDATES_PAYLOAD = {
    "schema_version": "fixture",
    "candidate_summaries": [
        {
            "candidate": {
                "candidate_id": "R1_SCANNER_RISK_HIGH_30M_V1",
                "feature_path": "scanner.risk_band",
                "expected_value": "HIGH",
            },
            "branch": {"day_symbol_count": 21, "win_rate": 0.48, "avg_net_return_pct": 0.92},
            "decision": {"status": "SINGLE_BEHAVIOR_PATCH_REVIEW_ELIGIBLE"},
        },
        {
            "candidate": {
                "candidate_id": "R1_ENTRY_DAILY_MA5_20_EXTENDED_15M_V1",
                "feature_path": "chart.daily_ma5_20_cross_state",
                "expected_value": "POST_CROSS_EXTENDED",
            },
            "branch": {"day_symbol_count": 8, "win_rate": 0.25, "avg_net_return_pct": -1.62},
            "decision": {"status": "RETAIN_SHADOW_INSUFFICIENT_BRANCH_SAMPLE"},
        },
    ],
}


def _required_sources(tmp_path: Path, *, target_day: str, daily_sources_day: str | None) -> Path:
    """The smallest reports/ tree satisfying every REQUIRED
    _SOURCE_FRESHNESS_CONTRACTS entry: feature_candidates (never day-
    stamped, by design) and large_cap_daily (via a real daily-review
    artifact) as PRESENT_ONLY, plus the four UPDATED_THROUGH_TARGET_DAY
    sources stamped with `daily_sources_day` (None omits through_day
    entirely). Also gives build_alpha_research_board two real candidates
    so UEF-8 has a non-empty pair to compare.
    """
    root = tmp_path / "reports"
    _write(root / "evaluation/feature_mart/opening_rank1/candidate_selection.json", _FEATURE_CANDIDATES_PAYLOAD)

    def _stamped(payload: dict) -> dict:
        payload = dict(payload)
        if daily_sources_day is not None:
            payload["through_day"] = daily_sources_day
        return payload

    _write(
        root / "evaluation/feature_mart/opening_rank1/prospective/rank1_candidate_shadow_cumulative.json",
        _stamped(_PROSPECTIVE_CANDIDATES_PAYLOAD),
    )
    # prospective_contract is deliberately NOT written here -- it is
    # registered OPTIONAL/PRESENT_ONLY, and build_alpha_research_board
    # itself tolerates its absence (defaults first_eligible_day), so
    # leaving it out doubles as evidence for that contract (see
    # test_registered_optional_source_absent_does_not_block).
    _write(
        root / "evaluation/feature_mart/opening_rank1/fresh_change_activation/fresh_change_activation_cumulative.json",
        _stamped({"schema_version": "fixture"}),
    )
    _write(
        root / "evaluation/opening_rank1_shadow/opening_rank1_shadow_cumulative.json",
        _stamped({"schema_version": "fixture"}),
    )
    _write(
        root / "evaluation/opening_rank1_shadow/latent_watch/latent_reactivation_forward.json",
        _stamped({"schema_version": "fixture"}),
    )
    # large_cap_daily is REQUIRED + PRESENT_ONLY, driven by
    # build_large_cap_daily_review's own source_count (= number of matching
    # dated files found, from collect_large_cap_daily_rows), not a stamped
    # date field here -- give it a real, minimal daily artifact at the
    # exact path/filename that function globs for
    # (evaluation/baseline_samsung_hynix/<day>/
    # baseline_samsung_hynix_forward_returns.json) so `available` is True
    # regardless of `daily_sources_day` (its own through_day field is a
    # vacuous echo per this module's own contract-table docstring).
    _write(
        root / "evaluation/baseline_samsung_hynix" / target_day / "baseline_samsung_hynix_forward_returns.json",
        {
            "schema_version": "fixture",
            "summary": {"horizons": {"+180m": {"top1_gross": {"average_return_pct": 0.5, "count": 1}}}},
        },
    )
    return root


def _write_tied_prospective_daily_sources(reports_root: Path) -> None:
    root = reports_root / "evaluation/feature_mart/opening_rank1/prospective"
    for day, symbols in {
        "2026-08-20": ("000001", "000002"),
        "2026-09-14": ("000003", "000004"),
    }.items():
        _write(
            root / day / "rank1_candidate_shadow_daily.json",
            {
                "observations": [
                    {"matched": True, "candidate_id": "R1", "day": day, "symbol": symbol}
                    for symbol in symbols
                ]
            },
        )


# ============================================================================
# Retained Fix2 coverage (updated for the generation/manifest/pointer model)
# ============================================================================


def test_prospective_concentration_ties_use_canonical_key_order(tmp_path: Path) -> None:
    from libs.reporting.alpha_research_board.builder import _prospective_concentrations

    reports_root = tmp_path / "reports"
    _write_tied_prospective_daily_sources(reports_root)
    result = _prospective_concentrations(
        reports_root=reports_root, first_day="2026-08-01", through_day="2026-09-30"
    )

    assert result["R1"]["largest_day"] == "2026-08-20"
    assert result["R1"]["largest_symbol"] == "000001"
    assert result["R1"]["largest_day_share"] == 0.5


def test_prospective_concentration_is_stable_across_python_hash_seeds(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    _write_tied_prospective_daily_sources(reports_root)
    code = (
        "import json; from pathlib import Path; "
        "from libs.reporting.alpha_research_board.builder import _prospective_concentrations; "
        f"print(json.dumps(_prospective_concentrations(reports_root=Path(r'{reports_root}'), "
        "first_day='2026-08-01', through_day='2026-09-30'), sort_keys=True))"
    )
    outputs = []
    for seed in ("1", "777"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=str(ROOT))
        completed = subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT, env=env, text=True, capture_output=True, check=True
        )
        outputs.append(completed.stdout)

    assert outputs[0] == outputs[1]


def test_stale_required_source_rejected(tmp_path: Path) -> None:
    _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-25")

    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    assert result.ok is False
    assert result.stage_failed == "freshness_guard"
    assert any("2026-09-25" in f for f in result.freshness_findings)
    assert not (tmp_path / "reports" / "evaluation" / "alpha_research_board" / "latest.json").exists()


def test_same_day_zero_event_state_is_accepted_as_fresh(tmp_path: Path) -> None:
    root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")
    _write(
        root / "evaluation/opening_rank1_shadow/opening_rank1_shadow_cumulative.json",
        {"schema_version": "fixture", "through_day": "2026-09-29", "summary": {"status": "NO_OPENING_RANK1"}},
    )
    _write(
        root / "evaluation/opening_rank1_shadow/latent_watch/latent_reactivation_forward.json",
        {"schema_version": "fixture", "through_day": "2026-09-29", "summary": {"status": "VALID_NO_EPISODES"}},
    )

    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    assert result.ok is True
    assert result.published is True
    assert result.freshness_findings == []


def test_feature_candidates_never_rejected_for_its_own_fixed_old_selection_window(tmp_path: Path) -> None:
    root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")
    board = build_alpha_research_board(reports_root=root, through_day="2026-09-29")
    assert board["sources"]["feature_candidates"]["through_day"] is None
    findings = evaluate_source_freshness_contracts(board, "2026-09-29")
    assert findings == []

    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    assert result.ok is True
    assert result.published is True


def test_feature_candidates_missing_is_still_rejected_required_present(tmp_path: Path) -> None:
    root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")
    (root / "evaluation/feature_mart/opening_rank1/candidate_selection.json").unlink()

    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    assert result.ok is False
    assert result.stage_failed == "freshness_guard"
    assert any("feature_candidates" in f and "MISSING_ARTIFACT" in f for f in result.freshness_findings)


def test_persisted_board_matches_captured_board_not_a_later_mutation(tmp_path: Path, monkeypatch) -> None:
    root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")

    call_count = {"n": 0}
    _orig_build = build_alpha_research_board

    def _mutating_build(*, reports_root, through_day):
        call_count["n"] += 1
        board = _orig_build(reports_root=reports_root, through_day=through_day)
        if call_count["n"] == 1:
            _write(
                root / "evaluation/opening_rank1_shadow/opening_rank1_shadow_cumulative.json",
                {"schema_version": "fixture", "through_day": "2026-09-30", "summary": {"MUTATED": True}},
            )
        return board

    monkeypatch.setattr(
        "libs.reporting.evaluation.daily_uef_pipeline.build_alpha_research_board", _mutating_build
    )

    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    assert result.ok is True
    assert result.published is True
    assert call_count["n"] == 1

    persisted = json.loads(Path(result.manifest_path).parent.joinpath("alpha_research_board.json").read_text(encoding="utf-8"))
    assert persisted["through_day"] == "2026-09-29"
    opening_source = persisted["sources"].get("opening_cumulative") or {}
    assert opening_source.get("through_day") != "2026-09-30"


def test_closeout_maintenance_cannot_advance_canonical_board_or_latest(tmp_path: Path, monkeypatch) -> None:
    from libs.reporting.closeout_maintenance import write_closeout_maintenance_report

    reports_root = tmp_path / "reports"

    def fake_build_q9_evaluation(*, reports_root, day, recover_forward=False):
        out = reports_root / "evaluation" / "daily" / day
        out.mkdir(parents=True, exist_ok=True)
        (out / "artifact_inventory.json").write_text("{}", encoding="utf-8")
        (out / "q9_day_validity.json").write_text("{}", encoding="utf-8")
        (out / "daily_scorecard.json").write_text("{}", encoding="utf-8")
        return {"q9_day_validity": str(out / "q9_day_validity.json"), "daily_scorecard": str(out / "daily_scorecard.json")}

    monkeypatch.setattr(
        "libs.reporting.evaluation.pipeline.build_q9_evaluation", fake_build_q9_evaluation
    )

    write_closeout_maintenance_report(
        {
            "schema_version": "closeout_maintenance.v1",
            "day": "2026-09-29",
            "trigger": "test",
            "steps": {"account_snapshot": {"ok": True}},
            "ok": True,
        },
        reports_root=reports_root,
    )

    assert not (reports_root / "evaluation" / "alpha_research_board" / "2026-09-29").exists()
    assert not (reports_root / "evaluation" / "alpha_research_board" / "latest.json").exists()
    assert not (reports_root / "evaluation" / "alpha_research_board" / "latest.md").exists()
    assert (reports_root / "evaluation" / "closeout_alpha_board_snapshot" / "2026-09-29" / "alpha_research_board_snapshot.json").exists()


def test_diagnostic_mode_never_writes_canonical_files_even_on_success(tmp_path: Path) -> None:
    root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-25")

    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29", canonical=False)

    assert result.canonical is False
    assert result.ok is True
    assert result.published is False
    assert not (root / "evaluation" / "alpha_research_board" / "2026-09-29").exists()
    assert not (root / "evaluation" / "alpha_research_board" / "latest.json").exists()
    assert result.output_dirs == {}


def test_uef9_failure_does_not_advance_latest(tmp_path: Path, monkeypatch) -> None:
    reports_root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")

    def _boom(*_args, **_kwargs):
        raise RuntimeError("simulated UEF-9 contradiction")

    monkeypatch.setattr(
        "libs.reporting.evaluation.daily_uef_pipeline.verify_formal_evaluation_authority", _boom
    )

    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    assert result.ok is False
    assert result.stage_failed == "uef9"
    assert result.uef7_run_id and result.uef8_run_id
    assert not (reports_root / "evaluation" / "alpha_research_board" / "latest.json").exists()
    assert not (reports_root / "evaluation" / "alpha_research_board" / "2026-09-29").exists()


def test_rerun_against_unchanged_input_is_idempotent(tmp_path: Path) -> None:
    reports_root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")

    first = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    second = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    assert first.ok is True and second.ok is True
    assert first.published is True
    assert second.published is False
    assert second.idempotency_status == "ALREADY_COMPLETE"
    assert first.uef7_run_id == second.uef7_run_id
    assert first.uef8_run_id == second.uef8_run_id
    assert first.uef9_run_id == second.uef9_run_id
    assert first.authority_id == second.authority_id
    assert second.manifest_path == first.manifest_path

    board_json_1 = Path(first.manifest_path).parent.joinpath("alpha_research_board.json").read_text(encoding="utf-8")
    third = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    board_json_2 = Path(third.manifest_path).parent.joinpath("alpha_research_board.json").read_text(encoding="utf-8")
    assert board_json_1 == board_json_2
    assert third.uef9_run_id == first.uef9_run_id


def test_same_complete_preflight_keeps_pointers_and_registry_unchanged(tmp_path: Path) -> None:
    reports_root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")
    first = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    assert first.published is True
    board_root = reports_root / "evaluation" / "alpha_research_board"
    registry = Path(first.observation_registry_path)
    before = {
        "current": (board_root / "2026-09-29" / "current.json").read_bytes(),
        "latest": (board_root / "latest.json").read_bytes(),
        "registry": registry.read_bytes(),
        "generations": sorted(p.name for p in (board_root / "2026-09-29" / "generations").iterdir()),
    }

    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    assert result.ok is True
    assert result.idempotency_status == "ALREADY_COMPLETE"
    assert (board_root / "2026-09-29" / "current.json").read_bytes() == before["current"]
    assert (board_root / "latest.json").read_bytes() == before["latest"]
    assert registry.read_bytes() == before["registry"]
    assert sorted(p.name for p in (board_root / "2026-09-29" / "generations").iterdir()) == before["generations"]


def test_different_complete_preflight_fails_closed_before_uef_writes(tmp_path: Path, monkeypatch) -> None:
    reports_root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")
    first = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    assert first.published is True
    board_root = reports_root / "evaluation" / "alpha_research_board"
    registry = Path(first.observation_registry_path)
    before = {
        "current": (board_root / "2026-09-29" / "current.json").read_bytes(),
        "latest": (board_root / "latest.json").read_bytes(),
        "registry": registry.read_bytes(),
        "generations": sorted(p.name for p in (board_root / "2026-09-29" / "generations").iterdir()),
    }
    original_build = build_alpha_research_board

    def _different_board(*, reports_root, through_day):
        board = original_build(reports_root=reports_root, through_day=through_day)
        board["candidates"][0]["decision"] = "SOURCE_CHANGED"
        return board

    monkeypatch.setattr("libs.reporting.evaluation.daily_uef_pipeline.build_alpha_research_board", _different_board)
    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    assert result.ok is False
    assert result.idempotency_status == "CANONICAL_SOURCE_CONFLICT"
    assert (board_root / "2026-09-29" / "current.json").read_bytes() == before["current"]
    assert (board_root / "latest.json").read_bytes() == before["latest"]
    assert registry.read_bytes() == before["registry"]
    assert sorted(p.name for p in (board_root / "2026-09-29" / "generations").iterdir()) == before["generations"]


def test_multiple_complete_preflight_fails_closed_without_writes(tmp_path: Path) -> None:
    reports_root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")
    first = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    assert first.published is True
    board_root = reports_root / "evaluation" / "alpha_research_board"
    day_root = board_root / "2026-09-29"
    generation_root = day_root / "generations"
    source_generation = Path(first.manifest_path).parent
    shutil.copytree(source_generation, generation_root / "forensic-second-complete")
    registry = Path(first.observation_registry_path)
    before_current = (day_root / "current.json").read_bytes()
    before_latest = (board_root / "latest.json").read_bytes()
    before_registry = registry.read_bytes()

    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    assert result.ok is False
    assert result.idempotency_status == "MULTIPLE_COMPLETE_CONFLICT"
    assert (day_root / "current.json").read_bytes() == before_current
    assert (board_root / "latest.json").read_bytes() == before_latest
    assert registry.read_bytes() == before_registry


def test_completed_day_creates_one_derived_p1_2_observation_record(tmp_path: Path) -> None:
    reports_root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")

    first = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    second = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    registry_path = reports_root / "evaluation" / "alpha_research_board" / "p1_2_daily_observation_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert list(registry["observations"]) == ["2026-09-29"]
    assert registry["observations"]["2026-09-29"]["authority_id"] == first.authority_id == second.authority_id
    assert first.observation_registry_path == second.observation_registry_path == str(registry_path)


def test_atomic_write_never_leaves_partial_file_on_failure(tmp_path: Path) -> None:
    from libs.reporting.evaluation.daily_uef_pipeline import _atomic_write_text

    target = tmp_path / "sub" / "file.json"

    class _Boom:
        def write(self, *_a, **_k):
            raise OSError("disk full")

    import libs.reporting.evaluation.daily_uef_pipeline as mod

    orig_fdopen = mod.os.fdopen

    def _boom_fdopen(fd, *a, **k):
        real = orig_fdopen(fd, *a, **k)
        real.write = _Boom().write
        return real

    mod.os.fdopen = _boom_fdopen
    try:
        with pytest.raises(OSError):
            _atomic_write_text(target, "content")
    finally:
        mod.os.fdopen = orig_fdopen

    assert not target.exists()
    assert list(target.parent.glob("*.tmp")) == []


def test_missing_sources_fail_closed(tmp_path: Path) -> None:
    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    assert result.ok is False
    assert result.stage_failed == "freshness_guard"
    assert result.freshness_findings
    assert not (tmp_path / "reports" / "evaluation" / "alpha_research_board" / "latest.json").exists()


def test_pipeline_never_imports_execution_or_runtime_modules() -> None:
    import ast
    import inspect

    import libs.reporting.evaluation.daily_uef_pipeline as mod

    forbidden_prefixes = ("libs.execution", "libs.runtime", "libs.kiwoom")
    tree = ast.parse(inspect.getsource(mod))
    imported_modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    for name in imported_modules:
        assert not name.startswith(forbidden_prefixes), (
            f"daily_uef_pipeline.py must never import from {name!r}"
        )


def test_no_state_files_written_outside_reports_evaluation(tmp_path: Path) -> None:
    reports_root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    before = sorted(p.relative_to(tmp_path) for p in data_dir.rglob("*") if p.is_file())

    run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    after = sorted(p.relative_to(tmp_path) for p in data_dir.rglob("*") if p.is_file())
    assert before == after == []


# ============================================================================
# Authority-closure coverage (Codex bounded re-audit findings)
# ============================================================================


# --- A: legacy CLI cannot canonical-publish ---------------------------------


def test_legacy_cli_cannot_write_canonical_board_or_latest(tmp_path: Path) -> None:
    reports_root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_alpha_research_board.py"),
         "--through-day", "2026-09-29", "--reports-root", str(reports_root)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (reports_root / "evaluation" / "alpha_research_board" / "2026-09-29").exists()
    assert not (reports_root / "evaluation" / "alpha_research_board" / "latest.json").exists()


def test_legacy_cli_rejects_output_dir_equal_to_canonical_path(tmp_path: Path) -> None:
    reports_root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")
    canonical = reports_root / "evaluation" / "alpha_research_board" / "2026-09-29"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_alpha_research_board.py"),
         "--through-day", "2026-09-29", "--reports-root", str(reports_root), "--output-dir", str(canonical)],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0
    assert not canonical.exists()


def test_daily_uef_pipeline_is_the_sole_canonical_writer_by_source_search() -> None:
    """Repository-wide check: the generation/current/latest writer
    functions are only ever called from within this module itself (and its
    own tests) -- no other module directly writes a generation, current.json,
    or the global latest.json."""
    import subprocess as sp

    out = sp.run(
        ["git", "grep", "-l", "-E", "write_generation\\(|advance_current_pointer\\(|advance_latest_pointer\\(",
         "--", "*.py"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    matched_files = {
        line.strip() for line in out.stdout.splitlines() if line.strip()
    }
    allowed = {
        "libs/reporting/evaluation/daily_uef_pipeline.py",
        "tests/test_daily_uef_pipeline.py",
    }
    unexpected = {f for f in matched_files if f.replace("\\", "/") not in allowed}
    assert unexpected == set(), f"unexpected canonical-writer callers found: {unexpected}"


# --- B / I: unknown source -> fail closed -----------------------------------


def test_unknown_board_source_rejects_canonical_run(tmp_path: Path) -> None:
    board = {
        "through_day": "2026-09-29",
        "candidate_count": 0,
        "sources": {
            "prospective_candidates": {"available": True, "through_day": "2026-09-29"},
            "fresh_change": {"available": True, "through_day": "2026-09-29"},
            "opening_cumulative": {"available": True, "through_day": "2026-09-29"},
            "latent_reactivation": {"available": True, "through_day": "2026-09-29"},
            "feature_candidates": {"available": True, "through_day": None},
            "large_cap_daily": {"available": True, "through_day": "2026-09-29"},
            "a_brand_new_source_nobody_reviewed_yet": {"available": True, "through_day": "2026-09-29"},
        },
    }
    findings = evaluate_source_freshness_contracts(board, "2026-09-29")
    assert any("a_brand_new_source_nobody_reviewed_yet" in f and "UNKNOWN_SOURCE" in f for f in findings)


# --- C: registered optional source absent -> allowed ------------------------


def test_registered_optional_source_absent_does_not_block(tmp_path: Path) -> None:
    root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")
    # prospective_contract and btc_woori_history are registered OPTIONAL,
    # PRESENT_ONLY -- neither file was ever written by _required_sources.
    board = build_alpha_research_board(reports_root=root, through_day="2026-09-29")
    assert board["sources"]["prospective_contract"]["available"] is False
    assert board["sources"].get("btc_woori_history", {}).get("available", False) is False
    findings = evaluate_source_freshness_contracts(board, "2026-09-29")
    assert findings == []

    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    assert result.ok is True
    assert result.published is True


# --- D: partial bundle -> not authoritative ---------------------------------


def test_partial_bundle_before_complete_manifest_is_not_authoritative(tmp_path: Path, monkeypatch) -> None:
    reports_root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")

    import libs.reporting.evaluation.daily_uef_pipeline as mod

    orig_write_generation = mod.write_generation

    def _boom_after_board_write(board, **kwargs):
        # Let the board file itself get written (simulating a crash between
        # the board write and the COMPLETE.json write), then fail.
        day_dir = kwargs["day_dir"]
        generation_dir = day_dir / "generations" / kwargs["authority_id"]
        generation_dir.mkdir(parents=True, exist_ok=True)
        (generation_dir / "alpha_research_board.json").write_text(json.dumps(board), encoding="utf-8")
        raise OSError("simulated crash before COMPLETE.json")

    monkeypatch.setattr(mod, "write_generation", _boom_after_board_write)

    with pytest.raises(OSError):
        run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    assert not (reports_root / "evaluation" / "alpha_research_board" / "2026-09-29" / "current.json").exists()
    assert not (reports_root / "evaluation" / "alpha_research_board" / "latest.json").exists()
    # The partial generation dir may physically exist, but nothing points at it.
    ok, board, manifest, reason = resolve_canonical_alpha_board(tmp_path, day="2026-09-29")
    assert ok is False


# --- E: same-day source replacement fails before any new generation exists ---


def test_same_day_source_conflict_leaves_prior_generation_current(tmp_path: Path) -> None:
    reports_root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")

    first = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    assert first.ok is True and first.published is True
    current_before = (reports_root / "evaluation" / "alpha_research_board" / "2026-09-29" / "current.json").read_text(encoding="utf-8")
    latest_before = (reports_root / "evaluation" / "alpha_research_board" / "latest.json").read_text(encoding="utf-8")

    # Mutate a required source so the current Board has a genuinely
    # different identity. The preflight must reject it before UEF/pointer
    # output is attempted.
    changed_feature_source = json.loads(json.dumps(_FEATURE_CANDIDATES_PAYLOAD))
    changed_feature_source["prospective_shadow_candidates"][0]["train"]["avg_net_return_pct"] = 9.99
    _write(
        reports_root / "evaluation/feature_mart/opening_rank1/candidate_selection.json",
        changed_feature_source,
    )

    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    assert result.ok is False
    assert result.idempotency_status == "CANONICAL_SOURCE_CONFLICT"

    current_after = (reports_root / "evaluation" / "alpha_research_board" / "2026-09-29" / "current.json").read_text(encoding="utf-8")
    latest_after = (reports_root / "evaluation" / "alpha_research_board" / "latest.json").read_text(encoding="utf-8")
    assert current_after == current_before
    assert latest_after == latest_before

    ok, board, manifest, reason = resolve_canonical_alpha_board(tmp_path)
    assert ok is True
    assert manifest["authority_id"] == first.authority_id


# --- F: a complete generation's manifest/pointers/hashes are all correct ---


def test_complete_generation_manifest_current_and_latest_all_validate(tmp_path: Path) -> None:
    reports_root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")

    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    assert result.ok is True and result.published is True

    manifest_path = Path(result.manifest_path)
    ok, reason, manifest = verify_generation_manifest(manifest_path)
    assert ok is True, reason
    assert manifest["authority_id"] == result.authority_id
    assert manifest["uef7_run_id"] == result.uef7_run_id
    assert manifest["uef8_run_id"] == result.uef8_run_id
    assert manifest["uef9_run_id"] == result.uef9_run_id
    assert manifest["uef9_authority_status"] == "VALID"
    assert manifest["status"] == "COMPLETE"

    current = json.loads((reports_root / "evaluation" / "alpha_research_board" / "2026-09-29" / "current.json").read_text(encoding="utf-8"))
    assert current["authority_id"] == result.authority_id
    latest = json.loads((reports_root / "evaluation" / "alpha_research_board" / "latest.json").read_text(encoding="utf-8"))
    assert latest["authority_id"] == result.authority_id
    assert latest["day"] == "2026-09-29"

    ok2, board, manifest2, reason2 = resolve_canonical_alpha_board(tmp_path)
    assert ok2 is True
    assert board["through_day"] == "2026-09-29"

    # legacy-compat view exists and matches, explicitly non-authoritative
    legacy = json.loads((reports_root / "evaluation" / "alpha_research_board" / "2026-09-29" / "alpha_research_board.json").read_text(encoding="utf-8"))
    assert legacy == board


# --- G: tampered completed artifact -> manifest validation FAIL ------------


def test_tampered_artifact_fails_manifest_verification(tmp_path: Path) -> None:
    _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")
    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    assert result.ok is True

    board_path = Path(result.manifest_path).parent / "alpha_research_board.json"
    original = board_path.read_text(encoding="utf-8")
    board_path.write_text(original + " ", encoding="utf-8")  # tamper: single byte appended

    ok, reason, manifest = verify_generation_manifest(Path(result.manifest_path))
    assert ok is False
    assert "digest_mismatch" in reason

    ok2, board, manifest2, reason2 = resolve_canonical_alpha_board(tmp_path)
    assert ok2 is False


# --- H: latest.md failure never invalidates machine authority --------------


def test_latest_md_failure_does_not_invalidate_latest_json(tmp_path: Path, monkeypatch) -> None:
    _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")

    import libs.reporting.evaluation.daily_uef_pipeline as mod

    orig_render = mod.render_alpha_research_board
    call_count = {"n": 0}

    def _fail_on_second_call(board):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            # First call is write_generation()'s own generation .md;
            # only the SECOND call (write_latest_presentation(), the
            # presentation-only step) is made to fail here.
            raise RuntimeError("boom")
        return orig_render(board)

    monkeypatch.setattr(mod, "render_alpha_research_board", _fail_on_second_call)

    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    assert result.ok is True
    assert result.published is True
    assert result.latest_presentation_path is None  # presentation failed
    assert result.latest_pointer_path is not None  # machine authority unaffected

    ok, board, manifest, reason = resolve_canonical_alpha_board(tmp_path)
    assert ok is True, reason
