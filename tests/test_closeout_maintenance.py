import json
from pathlib import Path

from libs.reporting.closeout_maintenance import (
    _build_opening_rank1_closeout_with_offline_fallback,
    write_closeout_maintenance_report,
)


def test_opening_rank1_closeout_falls_back_to_local_evidence_on_network_failure(
    tmp_path,
) -> None:
    calls = []

    def builder(**kwargs):
        calls.append(kwargs["allow_fresh_fetch"])
        if kwargs["allow_fresh_fetch"]:
            raise ConnectionError("mockapi unavailable")
        return {"ok": True, "day_status": "FORWARD_INCOMPLETE"}

    result = _build_opening_rank1_closeout_with_offline_fallback(
        day="2026-09-01",
        reports_root=tmp_path / "reports",
        state_path=tmp_path / "state.json",
        builder=builder,
    )

    assert calls == [True, False]
    assert result["ok"] is True
    assert result["degraded_offline_fallback"] is True
    assert result["fresh_fetch_error"] == "mockapi unavailable"


def test_write_closeout_maintenance_refreshes_q9_artifacts_after_json_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[dict] = []

    def fake_build_q9_evaluation(*, reports_root: Path, day: str):
        closeout_path = reports_root / "operator_summary" / "daily" / day / "closeout_maintenance.json"
        assert closeout_path.exists()
        calls.append({"reports_root": reports_root, "day": day})
        out = reports_root / "evaluation" / "daily" / day
        out.mkdir(parents=True, exist_ok=True)
        (out / "artifact_inventory.json").write_text(
            json.dumps({"daily_artifacts": {"closeout_maintenance": {"exists": True}}}),
            encoding="utf-8",
        )
        (out / "q9_day_validity.json").write_text("{}", encoding="utf-8")
        (out / "daily_scorecard.json").write_text("{}", encoding="utf-8")
        return {
            "q9_day_validity": str(out / "q9_day_validity.json"),
            "daily_scorecard": str(out / "daily_scorecard.json"),
        }

    monkeypatch.setattr(
        "libs.reporting.evaluation.pipeline.build_q9_evaluation",
        fake_build_q9_evaluation,
    )

    reports_root = tmp_path / "reports"
    paths = write_closeout_maintenance_report(
        {
            "schema_version": "closeout_maintenance.v1",
            "day": "2026-07-13",
            "trigger": "test",
            "steps": {"account_snapshot": {"ok": True}},
            "ok": True,
        },
        reports_root=reports_root,
    )

    payload = json.loads(Path(paths["report_json_path"]).read_text(encoding="utf-8"))
    refresh = payload["steps"]["q9_evaluation_post_close_refresh"]
    assert calls == [{"reports_root": reports_root, "day": "2026-07-13"}]
    assert refresh["ok"] is True
    assert Path(refresh["artifact_inventory_path"]).exists()
    board = payload["steps"]["alpha_research_board_final"]
    assert board["ok"] is True
    assert board["explanation_authority"] == "alpha_research_board_only"
    assert Path(board["report_json_path"]).exists()
    assert Path(board["report_md_path"]).exists()
    assert Path(board["latest_json_path"]).exists()
    assert list(payload["steps"])[-1] == "alpha_research_board_final"
