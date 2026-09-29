"""Regression coverage for the P1.2 daily UEF EOD orchestrator
(libs/reporting/evaluation/daily_uef_pipeline.py).

Covers exactly the cases enumerated for the P1.2 operational-prerequisite
task: missing board sources fail closed, a stale-dated source is rejected
even though the board's own top-level through_day field always echoes the
request, a fully successful run chains Board -> UEF-7 -> UEF-8 -> UEF-9 and
only then advances latest.json/.md, a downstream UEF-9 failure never
advances latest, a repeat run against unchanged input is idempotent, and no
call in this path touches any execution/runtime module.
"""

from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.evaluation.daily_uef_pipeline import (
    check_board_source_freshness,
    run_daily_uef_evaluation,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _minimal_two_candidate_reports(tmp_path: Path, *, source_through_day: str | None) -> Path:
    """The smallest reports/ tree that gives build_alpha_research_board two
    real candidates (enough for UEF-8 to have a non-empty pair to compare),
    optionally stamping every populated source with an explicit
    through_day so the freshness guard has something concrete to check.
    """
    root = tmp_path / "reports"

    def _stamped(payload: dict) -> dict:
        if source_through_day is not None:
            payload = dict(payload)
            payload["through_day"] = source_through_day
        return payload

    _write(
        root / "evaluation/feature_mart/opening_rank1/candidate_selection.json",
        _stamped({
            "schema_version": "fixture",
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
        }),
    )
    _write(
        root / "evaluation/feature_mart/opening_rank1/prospective/rank1_candidate_shadow_cumulative.json",
        _stamped({
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
        }),
    )
    _write(
        root / "evaluation/feature_mart/opening_rank1/prospective/frozen_candidate_contract.json",
        _stamped({"schema_version": "fixture", "first_eligible_day": "2026-08-12"}),
    )
    return root


# --- A: target day Board missing -> FAIL CLOSED -----------------------------


def test_missing_sources_fail_closed(tmp_path: Path) -> None:
    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    assert result.ok is False
    assert result.stage_failed == "freshness_guard"
    assert result.stale_sources
    assert all("MISSING_ARTIFACT" in s for s in result.stale_sources)
    # A failed run must never leave a latest pointer behind.
    assert not (tmp_path / "reports" / "evaluation" / "alpha_research_board" / "latest.json").exists()


# --- B: stale canonical Board (target=09-29, source dated 09-25) -> REJECT --


def test_stale_source_is_rejected_even_though_board_through_day_always_echoes_request(tmp_path: Path) -> None:
    reports_root = _minimal_two_candidate_reports(tmp_path, source_through_day="2026-09-25")

    # Direct proof that the vacuous top-level check would NOT have caught this.
    from libs.reporting.alpha_research_board import build_alpha_research_board

    board = build_alpha_research_board(reports_root=reports_root, through_day="2026-09-29")
    assert board["through_day"] == "2026-09-29"  # echoes the request, as documented
    findings = check_board_source_freshness(board, "2026-09-29")
    assert findings and any("2026-09-25" in f for f in findings)

    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    assert result.ok is False
    assert result.stage_failed == "freshness_guard"
    assert any("2026-09-25" in s for s in result.stale_sources)
    assert not (reports_root / "evaluation" / "alpha_research_board" / "latest.json").exists()
    assert not (reports_root / "evaluation" / "alpha_research_board" / "2026-09-29").exists()


# --- C: successful canonical Board: Board -> UEF7 -> UEF8 -> UEF9 VALID ----


def test_successful_chain_persists_and_advances_latest(tmp_path: Path) -> None:
    reports_root = _minimal_two_candidate_reports(tmp_path, source_through_day=None)

    result = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    assert result.ok is True
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


# --- D: UEF-9 invalid/failure -> pipeline fails, latest not falsely advanced -


def test_uef9_failure_does_not_advance_latest(tmp_path: Path, monkeypatch) -> None:
    reports_root = _minimal_two_candidate_reports(tmp_path, source_through_day=None)

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


# --- E: same finalized input rerun -> deterministic / idempotent -----------


def test_rerun_against_unchanged_input_is_idempotent(tmp_path: Path) -> None:
    reports_root = _minimal_two_candidate_reports(tmp_path, source_through_day=None)

    first = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    second = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    assert first.ok is True and second.ok is True
    assert first.uef7_run_id == second.uef7_run_id
    assert first.uef8_run_id == second.uef8_run_id
    assert first.uef9_run_id == second.uef9_run_id
    assert first.to_dict() == second.to_dict()

    board_json_1 = (reports_root / "evaluation" / "alpha_research_board" / "2026-09-29" / "alpha_research_board.json").read_text(encoding="utf-8")
    # Re-run again a third time explicitly to prove no accumulation/duplication.
    third = run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")
    board_json_2 = (reports_root / "evaluation" / "alpha_research_board" / "2026-09-29" / "alpha_research_board.json").read_text(encoding="utf-8")
    assert board_json_1 == board_json_2
    assert third.uef9_run_id == first.uef9_run_id


# --- F: no broker/runtime state writes --------------------------------------


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
    reports_root = _minimal_two_candidate_reports(tmp_path, source_through_day=None)
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    before = sorted(p.relative_to(tmp_path) for p in data_dir.rglob("*") if p.is_file())

    run_daily_uef_evaluation(repo_root=tmp_path, through_day="2026-09-29")

    after = sorted(p.relative_to(tmp_path) for p in data_dir.rglob("*") if p.is_file())
    assert before == after == []
