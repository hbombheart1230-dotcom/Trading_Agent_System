"""Regression coverage for the P1.2 daily UEF EOD orchestrator
(libs/reporting/evaluation/daily_uef_pipeline.py), Fix2.

Covers the Codex independent-audit findings and their required test
additions (T1-T10 in the Fix2 task spec): single-capture authority under
concurrent source mutation, the closeout canonical-publication bypass being
removed, per-source freshness contracts (including a legitimate same-day
zero-event state and a source whose own contract is not daily-dated),
diagnostic mode never being able to publish canonical output, atomic
publication surviving a mid-write failure, idempotency, and no trading
side effects anywhere in the call graph.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from libs.reporting.alpha_research_board import build_alpha_research_board
from libs.reporting.evaluation.daily_uef_pipeline import (
    evaluate_source_freshness_contracts,
    run_daily_uef_evaluation,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


_FEATURE_CANDIDATES_PAYLOAD = {
    # Confirmed shape of the real file: no through_day/day field, a fixed
    # one-time selection_period instead (see daily_uef_pipeline.py's own
    # contract-table docstring) -- deliberately NOT stamped with a day.
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
    """The smallest reports/ tree satisfying every _SOURCE_FRESHNESS_CONTRACTS
    entry: feature_candidates (never day-stamped, by design) plus the four
    daily-advancing sources stamped with `daily_sources_day` (None omits the
    through_day field entirely, i.e. simulates a source that legitimately
    carries no date -- used only where a test needs that; the four required
    daily sources are normally always given an explicit day by their real
    producer). Also gives build_alpha_research_board two real candidates so
    UEF-8 has a non-empty pair to compare.
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
    _write(
        root / "evaluation/feature_mart/opening_rank1/prospective/frozen_candidate_contract.json",
        {"schema_version": "fixture", "first_eligible_day": "2026-08-12"},
    )
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
    return root


# --- T3: source-specific freshness (four required daily sources) -----------


def test_stale_required_source_rejected(tmp_path: Path) -> None:
    _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-25")

    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    assert result.ok is False
    assert result.stage_failed == "freshness_guard"
    assert any("2026-09-25" in f for f in result.freshness_findings)
    assert not (tmp_path / "reports" / "evaluation" / "alpha_research_board" / "latest.json").exists()


def test_same_day_zero_event_state_is_accepted_as_fresh(tmp_path: Path) -> None:
    root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")
    # Overwrite two of the four with an explicit, legitimate zero-event
    # shape -- freshness must be judged purely by the date stamp, not by
    # whether any rows/episodes are present.
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


# --- T5 / feature_candidates freshness (PRESENT_ONLY, never date-compared) -


def test_feature_candidates_never_rejected_for_its_own_fixed_old_selection_window(tmp_path: Path) -> None:
    root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")
    board = build_alpha_research_board(reports_root=root, through_day="2026-09-29")
    # feature_candidates carries no through_day at all (fixed 2026-08-01..
    # 2026-08-11 selection_period instead) -- must never appear as "stale".
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


# --- T1: single-capture authority under source mutation after capture ------


def test_persisted_board_matches_captured_board_not_a_later_mutation(tmp_path: Path, monkeypatch) -> None:
    root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")

    call_count = {"n": 0}
    _orig_build = build_alpha_research_board

    def _mutating_build(*, reports_root, through_day):
        call_count["n"] += 1
        board = _orig_build(reports_root=reports_root, through_day=through_day)
        if call_count["n"] == 1:
            # Simulate a source mutating on disk AFTER the orchestrator's
            # own single capture -- a second (hypothetical) rebuild must
            # never be allowed to observe this.
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
    # Exactly one build call for the whole run -- if persistence rebuilt
    # internally, this would be 2+ and the persisted file would reflect the
    # mutated (MUTATED=True) source instead of the originally captured one.
    assert call_count["n"] == 1

    persisted = json.loads(
        (root / "evaluation" / "alpha_research_board" / "2026-09-29" / "alpha_research_board.json").read_text(
            encoding="utf-8"
        )
    )
    assert persisted["through_day"] == "2026-09-29"
    opening_source = persisted["sources"].get("opening_cumulative") or {}
    assert opening_source.get("through_day") != "2026-09-30"


# --- T2: closeout can no longer publish canonical authority -----------------


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
    # Closeout's own diagnostic snapshot IS still produced, just non-canonically.
    assert (reports_root / "evaluation" / "closeout_alpha_board_snapshot" / "2026-09-29" / "alpha_research_board_snapshot.json").exists()


# --- T6: diagnostic mode can never publish canonical output -----------------


def test_diagnostic_mode_never_writes_canonical_files_even_on_success(tmp_path: Path) -> None:
    # Stale sources -- would be rejected in canonical mode.
    root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-25")

    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29", canonical=False)

    assert result.canonical is False
    assert result.ok is True  # the chain itself succeeds -- freshness is not enforced in diagnostic mode
    assert result.published is False
    assert not (root / "evaluation" / "alpha_research_board" / "2026-09-29").exists()
    assert not (root / "evaluation" / "alpha_research_board" / "latest.json").exists()
    assert result.output_dirs == {}


# --- C (retained from Fix1): successful canonical chain ---------------------


def test_successful_chain_persists_and_advances_latest(tmp_path: Path) -> None:
    reports_root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")

    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    assert result.ok is True
    assert result.published is True
    assert result.stage_failed is None
    assert result.board_candidate_count and result.board_candidate_count >= 2
    assert result.uef7_run_id and result.uef8_run_id and result.uef9_run_id
    assert result.authority_status == "VALID"
    n = result.board_candidate_count
    assert result.uef8_pair_count == n * (n - 1) // 2

    board_dir = reports_root / "evaluation" / "alpha_research_board" / "2026-09-29"
    assert (board_dir / "alpha_research_board.json").exists()
    latest = json.loads((reports_root / "evaluation" / "alpha_research_board" / "latest.json").read_text(encoding="utf-8"))
    assert latest["through_day"] == "2026-09-29"

    uef9_payload = json.loads(
        (Path(result.output_dirs["uef9"]) / "formal_evaluation_authority.json").read_text(encoding="utf-8")
    )
    assert uef9_payload["authority_status"] == "VALID"
    assert uef9_payload["source_uef7_run_id"] == result.uef7_run_id
    assert uef9_payload["source_uef8_run_id"] == result.uef8_run_id


# --- T8 (retained): UEF-9 failure -> no canonical advancement ---------------


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


# --- T7: publication failure leaves previous latest authoritative ----------


def test_publication_failure_leaves_previous_latest_unchanged(tmp_path: Path, monkeypatch) -> None:
    reports_root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")

    # Establish a prior, genuinely-published latest (a different day).
    root2 = tmp_path  # reuse same repo_root; run once for an earlier day first.
    _required_sources(tmp_path, target_day="2026-09-28", daily_sources_day="2026-09-28")
    # _required_sources overwrote the shared fixture files with 09-28-dated
    # content for this call; run once to publish 2026-09-28 as "previous".
    first = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-28")
    assert first.ok is True and first.published is True
    previous_latest = (reports_root / "evaluation" / "alpha_research_board" / "latest.json").read_text(encoding="utf-8")

    # Now re-stamp sources fresh for 09-29 and simulate a failure during
    # the final publish step.
    _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")

    def _boom(board, *, output_dir):
        raise OSError("simulated disk failure during canonical publish")

    monkeypatch.setattr(
        "libs.reporting.evaluation.daily_uef_pipeline.persist_canonical_alpha_board", _boom
    )

    with pytest.raises(OSError):
        run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    # previous canonical latest (2026-09-28) must remain exactly as it was.
    assert (reports_root / "evaluation" / "alpha_research_board" / "latest.json").read_text(encoding="utf-8") == previous_latest
    assert not (reports_root / "evaluation" / "alpha_research_board" / "2026-09-29").exists()


def test_atomic_write_never_leaves_partial_file_on_failure(tmp_path: Path) -> None:
    from libs.reporting.evaluation.daily_uef_pipeline import _atomic_write_text

    target = tmp_path / "sub" / "file.json"

    class _Boom:
        def write(self, *_a, **_k):
            raise OSError("disk full")

    import libs.reporting.evaluation.daily_uef_pipeline as mod

    # Directly exercise the failure branch: os.fdopen wrapped write raises,
    # the temp file must be cleaned up and the real target never created.
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


# --- T9 (retained): idempotency ---------------------------------------------


def test_rerun_against_unchanged_input_is_idempotent(tmp_path: Path) -> None:
    reports_root = _required_sources(tmp_path, target_day="2026-09-29", daily_sources_day="2026-09-29")

    first = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    second = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    assert first.ok is True and second.ok is True
    assert first.uef7_run_id == second.uef7_run_id
    assert first.uef8_run_id == second.uef8_run_id
    assert first.uef9_run_id == second.uef9_run_id
    assert first.to_dict() == second.to_dict()

    board_json_1 = (reports_root / "evaluation" / "alpha_research_board" / "2026-09-29" / "alpha_research_board.json").read_text(encoding="utf-8")
    third = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    board_json_2 = (reports_root / "evaluation" / "alpha_research_board" / "2026-09-29" / "alpha_research_board.json").read_text(encoding="utf-8")
    assert board_json_1 == board_json_2
    assert third.uef9_run_id == first.uef9_run_id


# --- A/B (retained from Fix1): missing sources fail closed ------------------


def test_missing_sources_fail_closed(tmp_path: Path) -> None:
    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    assert result.ok is False
    assert result.stage_failed == "freshness_guard"
    assert result.freshness_findings
    assert not (tmp_path / "reports" / "evaluation" / "alpha_research_board" / "latest.json").exists()


# --- T10: no trading/execution side effects ---------------------------------


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
