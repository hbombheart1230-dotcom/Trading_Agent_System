from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from libs.market.opening_macro_snapshot_collector import (
    KST,
    capture_slot,
    mark_missed_slots,
    scheduled_slots,
)


def test_schedule_is_fixed_to_opening_window() -> None:
    slots = scheduled_slots("2026-08-27")
    assert [row.strftime("%H:%M") for row in slots[:3]] == ["08:55", "08:58", "08:59"]
    assert slots[3].strftime("%H:%M") == "09:00"
    assert slots[-1].strftime("%H:%M") == "09:20"
    assert len(slots) == 24


def test_capture_is_idempotent_and_records_created_artifact(tmp_path: Path) -> None:
    day = "2026-08-27"
    macro_root = tmp_path / "macro"
    manifest = macro_root / day / "opening_capture_manifest.json"
    scheduled = datetime(2026, 8, 27, 9, 0, tzinfo=KST)
    now_values = iter([scheduled + timedelta(seconds=5), scheduled + timedelta(seconds=7)])
    calls = []

    def fake_capture(**_kwargs):
        calls.append(1)
        target = macro_root / day / "090005_macro_indicators.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")
        return {"status": "ok", "source": "fixture"}

    first = capture_slot(
        day=day,
        scheduled_at=scheduled,
        manifest_path=manifest,
        macro_root=macro_root,
        now_fn=lambda: next(now_values),
        capture=fake_capture,
    )
    second = capture_slot(
        day=day,
        scheduled_at=scheduled,
        manifest_path=manifest,
        macro_root=macro_root,
        capture=fake_capture,
    )

    assert first["status"] == "CAPTURED"
    assert first["start_delay_sec"] == 5
    assert second == first
    assert len(calls) == 1


def test_missed_slots_are_not_backfilled_as_observed(tmp_path: Path) -> None:
    day = "2026-08-27"
    manifest = tmp_path / "opening_capture_manifest.json"
    now = datetime(2026, 8, 27, 9, 2, 5, tzinfo=KST)

    rows = mark_missed_slots(day=day, now=now, manifest_path=manifest)
    payload = json.loads(manifest.read_text(encoding="utf-8"))

    assert any(row["slot"] == "09:01" and row["status"] == "MISSED" for row in rows)
    assert not any(row["slot"] == "09:02" for row in payload["slots"])
    assert all(row["status"] == "MISSED" for row in rows)
