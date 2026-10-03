"""CLI entrypoint for the UEF-5.3 historical dual run.

Reads a FROZEN UEF-5.2 ``historical_recompute`` run plus the legacy
per-day evaluation artifacts it was compared against, classifies every
comparison unit, and writes
``reports/evaluation/uef5_dual_run/<dual_run_id>/``.

This script never modifies UEF-1..UEF-5.2 output. It is read-only against
the UEF-5.2 run directory and the legacy report tree.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from libs.reporting.evaluation.uef5_3.dual_run import run_dual_run, write_dual_run_outputs  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="repository root (default: current directory)")
    parser.add_argument(
        "--uef52-run-id",
        default=None,
        help="UEF-5.2 historical_recompute run_id to compare against (default: latest under reports/evaluation/uef5/historical_recompute/)",
    )
    parser.add_argument(
        "--families",
        default=None,
        help="comma-separated family keys to compare numerically (default: q10_semiconductor,q12_calc1)",
    )
    parser.add_argument("--no-write", action="store_true", help="run the comparison but do not write output artifacts")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    family_keys = args.families.split(",") if args.families else None

    result = run_dual_run(repo_root, uef52_run_id=args.uef52_run_id, family_keys=family_keys)
    counts = result.counts()

    print(f"dual_run_id: {result.dual_run_id}")
    print(f"uef52_run_id: {result.uef52_run_id}")
    print(f"families_compared: {result.families_compared}")
    print(f"families_non_comparable: {result.families_non_comparable}")
    print(f"parse_errors: {len(result.parse_errors)}")
    for k, v in counts.items():
        print(f"{k}: {v}")
    print(f"unexplained_divergences: {counts['unexplained_divergence']}")

    if not args.no_write:
        out_dir = write_dual_run_outputs(repo_root, result)
        print(f"wrote: {out_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
