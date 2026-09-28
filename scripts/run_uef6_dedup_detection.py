"""CLI entrypoint for UEF-6A Population Dedup Detection.

Reads a FROZEN UEF-5.2 ``historical_recompute`` run's ``episodes.jsonl``
(read-only), classifies population overlap/duplication using the frozen
UEF-1 identity model, and writes
``reports/evaluation/uef6_dedup/<UEF6A_RUN_ID>/``.

Never modifies UEF-1..UEF-5.3. Never regenerates or modifies the UEF-5.2
run it reads.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from libs.reporting.evaluation.uef6.reporter import write_dedup_report_outputs  # noqa: E402
from libs.reporting.evaluation.uef6.run_uef6a import run_uef6a_dedup_detection  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="repository root (default: current directory)")
    parser.add_argument("--uef52-run-id", required=True, help="UEF-5.2 historical_recompute run_id to analyze")
    parser.add_argument("--no-write", action="store_true", help="run the analysis but do not write output artifacts")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    result = run_uef6a_dedup_detection(repo_root, args.uef52_run_id)
    report = result.report

    print(f"uef6a_run_id: {result.uef6a_run_id}")
    print(f"source_uef52_run_id: {result.source_uef52_run_id}")
    print(f"raw_episodes_content_sha256: {result.raw_episodes_content_sha256}")
    print(f"population_semantic_digest: {result.population_semantic_digest}")
    print(f"detector_implementation_digest: {result.detector_implementation_digest}")
    for key, value in report.summary_dict().items():
        print(f"{key}: {value}")

    if not args.no_write:
        out_dir = write_dedup_report_outputs(repo_root, result.uef6a_run_id, report, result.input_manifest())
        print(f"wrote: {out_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
