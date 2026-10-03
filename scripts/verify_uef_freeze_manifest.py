"""Read-only integrity check for docs/research/uef_freeze_manifest.md.

Recomputes the SHA256 of every file the manifest lists and reports MATCH/
MISMATCH per file. Never modifies the manifest or any tracked file --
on mismatch it only reports; it does not "fix" the manifest or the file.

Usage:
    python scripts/verify_uef_freeze_manifest.py

Exit code 0 when every file matches; non-zero (the mismatch count) when
one or more files differ from the manifest, or when a listed file is
missing entirely.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs" / "research" / "uef_freeze_manifest.md"

# Matches one manifest table row: | path | stage | date | sha256 |
_ROW_RE = re.compile(
    r"^\|\s*(?P<path>[^|]+?)\s*\|\s*(?P<stage>[^|]+?)\s*\|\s*(?P<date>[^|]+?)\s*\|\s*(?P<sha256>[0-9a-f]{64})\s*\|\s*$",
    re.IGNORECASE,
)


def _parse_manifest(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        match = _ROW_RE.match(line.strip())
        if not match:
            continue
        if match.group("path") == "relative_path":
            continue  # header row
        rows.append(match.groupdict())
    return rows


def _sha256_of(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if not MANIFEST_PATH.is_file():
        print(f"MANIFEST NOT FOUND: {MANIFEST_PATH}")
        return 1

    rows = _parse_manifest(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not rows:
        print(f"MANIFEST EMPTY OR UNPARSEABLE: {MANIFEST_PATH}")
        return 1

    mismatches = 0
    by_stage: dict[str, list[str]] = {}
    for row in rows:
        relative_path = row["path"]
        expected = row["sha256"].lower()
        stage = row["stage"]
        actual_path = REPO_ROOT / relative_path
        actual = _sha256_of(actual_path)
        if actual is None:
            print(f"MISMATCH  [{stage}] {relative_path}  (file not found)")
            mismatches += 1
        elif actual != expected:
            print(f"MISMATCH  [{stage}] {relative_path}")
            print(f"    expected: {expected}")
            print(f"    actual:   {actual}")
            mismatches += 1
        else:
            print(f"MATCH     [{stage}] {relative_path}")
        by_stage.setdefault(stage, []).append(relative_path)

    print()
    for stage, paths in by_stage.items():
        print(f"{stage}: {len(paths)} file(s) tracked")
    print()
    print(f"FILES TRACKED: {len(rows)}")
    print(f"MISMATCH: {mismatches}")
    print("STATUS: PASS" if mismatches == 0 else "STATUS: FAIL")
    return mismatches


if __name__ == "__main__":
    sys.exit(main())
