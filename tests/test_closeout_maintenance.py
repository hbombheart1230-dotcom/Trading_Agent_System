import json
from pathlib import Path

from libs.reporting.closeout_maintenance import write_closeout_maintenance_report


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
