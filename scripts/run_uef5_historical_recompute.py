"""UEF-5.2: run the canonical historical recompute over admissible evidence.

Canonical recompute only -- no legacy comparison, no parity claim (UEF-5.3).
Writes ONLY under --out-root (default: reports/evaluation/uef5/historical_recompute
in the repo, a NEW namespace); never touches legacy artifacts.

  python scripts/run_uef5_historical_recompute.py [--repo-root DIR] [--out-root DIR] [--no-write]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.uef5.historical_recompute import OUTPUT_NAMESPACE, run_historical_recompute  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=str(ROOT))
    ap.add_argument("--out-root", default="")
    ap.add_argument("--no-write", action="store_true", help="classify and recompute in memory only")
    ap.add_argument("--raw-archive-root", default="", help="MarketDataReceipt raw archive root (default: none -> no receipt can resolve)")
    ap.add_argument("--receipt-root", default="", help="MarketDataReceipt store root (default: none -> no receipt can resolve)")
    ap.add_argument("--normalized-root", default="", help="attested normalized-artifact root (default: none -> no receipt can resolve)")
    args = ap.parse_args()

    repo_root = Path(args.repo_root)
    out_root = None if args.no_write else Path(args.out_root or (repo_root / OUTPUT_NAMESPACE))
    raw_archive_root = Path(args.raw_archive_root) if args.raw_archive_root else None
    receipt_root = Path(args.receipt_root) if args.receipt_root else None
    normalized_root = Path(args.normalized_root) if args.normalized_root else None
    run = run_historical_recompute(repo_root, out_root, raw_archive_root=raw_archive_root,
                                   receipt_root=receipt_root, normalized_root=normalized_root)
    print(json.dumps(run.summary, sort_keys=True, indent=2, ensure_ascii=True))
    if run.output_dir is not None:
        print(f"outputs: {run.output_dir}", file=sys.stderr)
    return 0 if run.status.value in ("COMPLETE", "PARTIAL", "BLOCKED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
