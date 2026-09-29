"""Guards the Patch Notes UI against silently going stale.

docs/daily_patch/ is the canonical technical patch-history archive.
docs/trading_agent_patch_notes_detailed_update/patch_notes.json is the
structured data the Patch Notes UI and /api/v1/patch-notes actually read
(see apps/api/adapters/patch_notes.py::RELATIVE_PATH). These are two
separate files by design (one technical audit trail, one human-facing
changelog) -- but the UI file's own latest date must never fall behind the
technical archive's latest date.

This is the exact failure mode discovered on 2026-09-29: patch_notes.json's
latest entry silently stalled at 2026-09-14 while docs/daily_patch/ kept
accumulating new dated files for two more weeks of frozen UEF-6..UEF-9 work,
and nothing caught the drift until a user noticed the UI looked stale.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAILY_PATCH_DIR = ROOT / "docs" / "daily_patch"
PATCH_NOTES_JSON = ROOT / "docs" / "trading_agent_patch_notes_detailed_update" / "patch_notes.json"

_DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})_")

_REQUIRED_ENTRY_FIELDS = {
    "date", "version", "title", "stage", "types", "summary", "details", "impact", "sources", "status",
}


def _load_patch_notes() -> dict:
    return json.loads(PATCH_NOTES_JSON.read_text(encoding="utf-8"))


def _latest_daily_patch_date() -> str:
    dates = []
    for path in DAILY_PATCH_DIR.glob("*.md"):
        match = _DATE_PREFIX.match(path.name)
        if match:
            dates.append(match.group(1))
    assert dates, "docs/daily_patch/ contains no dated entries -- cannot verify freshness"
    return max(dates)


def test_patch_notes_json_parses_and_is_internally_consistent():
    payload = _load_patch_notes()
    entries = payload["entries"]
    assert payload["entry_count"] == len(entries), (
        f"entry_count={payload['entry_count']} != len(entries)={len(entries)} -- "
        "the API reports this as PARTIAL, not AVAILABLE"
    )
    for entry in entries:
        missing = _REQUIRED_ENTRY_FIELDS - set(entry.keys())
        assert not missing, f"patch_notes.json entry missing required fields {missing}: {entry.get('title')!r}"
        assert entry["status"] in ("current", "historical"), f"unexpected status {entry['status']!r} on {entry.get('title')!r}"
        # A handful of pre-existing entries use a date RANGE (e.g. "2026-02-07 ~
        # 2026-02-10"); only the leading YYYY-MM-DD is required to be well-formed,
        # since that is what freshness comparisons below actually rely on.
        assert re.match(r"^\d{4}-\d{2}-\d{2}", entry["date"]), f"non-ISO date {entry['date']!r} on {entry.get('title')!r}"


def test_patch_notes_json_not_older_than_canonical_daily_patch_history():
    payload = _load_patch_notes()
    entries = payload["entries"]
    latest_ui_date = max(entry["date"] for entry in entries)
    latest_daily_patch_date = _latest_daily_patch_date()
    assert latest_ui_date >= latest_daily_patch_date, (
        f"docs/daily_patch/ has a newer dated entry ({latest_daily_patch_date}) than the Patch Notes UI's "
        f"own data file docs/trading_agent_patch_notes_detailed_update/patch_notes.json "
        f"(latest entry date={latest_ui_date}) -- the UI has gone stale relative to the canonical "
        "technical history. Add the missing milestone(s) to patch_notes.json and patch_notes.md "
        "(append-only; see docs/trading_agent_patch_notes_detailed_update/README.md)."
    )
