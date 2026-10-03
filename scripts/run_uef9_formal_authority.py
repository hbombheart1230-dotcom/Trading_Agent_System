"""Verify two frozen UEF authority JSON documents and write a UEF-9 manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.uef9.authority import verify_formal_evaluation_authority  # noqa: E402
from libs.reporting.evaluation.uef9.reporter import write_formal_evaluation_authority  # noqa: E402
from libs.reporting.evaluation.uef9.run_identity import uef9_implementation_digest  # noqa: E402


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uef7-json", required=True, type=Path)
    parser.add_argument("--uef8-json", required=True, type=Path)
    parser.add_argument("--repo-root", default=ROOT, type=Path)
    args = parser.parse_args()
    authority = verify_formal_evaluation_authority(
        _load_json(args.uef7_json),
        uef8=_load_json(args.uef8_json),
        uef9_implementation_digest_value=uef9_implementation_digest(),
    )
    out_dir = write_formal_evaluation_authority(authority, repo_root=args.repo_root)
    print(json.dumps({"uef9_run_id": authority.uef9_run_id, "authority_status": authority.authority_status, "output_dir": str(out_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
