from __future__ import annotations

import json
from pathlib import Path

from scripts.check_q9_q12_readiness import _baseline_artifacts, _evaluate


def test_q10_lead_market_readiness_is_activation_aware(tmp_path: Path) -> None:
    before = _baseline_artifacts(tmp_path, "2026-08-28")
    after = _baseline_artifacts(tmp_path, "2026-08-31")
    assert "lead_market_preopen" not in before["q10"]
    assert "lead_market_preopen" in after["q10"]


def test_q10_missed_preopen_is_a_closeout_blocker(tmp_path: Path) -> None:
    day = "2026-08-31"
    root = tmp_path / "evaluation" / "baseline_samsung_hynix" / day / "q10_forward_validation"
    root.mkdir(parents=True)
    (root / "q10_preopen_signal_snapshot.json").write_text(
        json.dumps({"capture_status": "MISSED"}), encoding="utf-8"
    )
    artifacts = _baseline_artifacts(tmp_path, day)
    blockers, _warnings = _evaluate(
        phase="closeout", day=day, live={}, processes={}, q9={}, artifacts=artifacts
    )
    assert any(row["code"] == "q10_lead_market_preopen_not_captured" for row in blockers)
