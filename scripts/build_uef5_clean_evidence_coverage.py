"""UEF-5.1: print the deterministic FILE-LEVEL ARTIFACT COVERAGE manifest.

This is NOT complete historical clean-evidence coverage (see the manifest's
`record_level_not_scanned`). Read-only. Writes nothing unless --out is given (never under reports/ or
data/ by default). Computes no performance metric.

  python scripts/build_uef5_clean_evidence_coverage.py [--repo-root DIR] [--out FILE] [--pretty]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.uef5.clean_evidence_coverage import (  # noqa: E402
    build_coverage_manifest,
    build_repo_registry,
    coverage_manifest_json,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=str(ROOT))
    ap.add_argument("--out", default="")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    repo_root = Path(args.repo_root)
    registry, day_validity = build_repo_registry(repo_root)
    manifest = build_coverage_manifest(repo_root, registry, day_validity=day_validity)
    text = (
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=True)
        if args.pretty
        else coverage_manifest_json(manifest)
    )
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
