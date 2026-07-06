from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.runtime.q9_decision_snapshots import _compact_candidates, _compact_mapping


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _compact_window(window: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(window)
    scanner = _as_dict(out.get("scanner_control"))
    if scanner:
        scanner = _compact_mapping(scanner, list_limit=20)
        if isinstance(scanner.get("top10"), list):
            scanner["top10"] = _compact_candidates(scanner["top10"], limit=10)
        if isinstance(scanner.get("top20"), list):
            scanner["top20"] = _compact_candidates(scanner["top20"], limit=20)
        out["scanner_control"] = scanner

    pre = _as_dict(out.get("scanner_pre_strategist_universe"))
    if pre:
        compact_pre = _compact_mapping(pre, list_limit=20)
        if isinstance(compact_pre.get("intrinsic_ranked_top20"), list):
            compact_pre["intrinsic_ranked_top20"] = _compact_candidates(
                compact_pre["intrinsic_ranked_top20"],
                limit=20,
            )
        out["scanner_pre_strategist_universe"] = compact_pre

    strategist = _as_dict(out.get("strategist_selection"))
    if strategist:
        compact_strategist = _compact_mapping(strategist, list_limit=10)
        if isinstance(compact_strategist.get("post_strategist_top10"), list):
            compact_strategist["post_strategist_top10"] = _compact_candidates(
                compact_strategist["post_strategist_top10"],
                limit=10,
            )
        out["strategist_selection"] = compact_strategist

    return out


def compact_file(path: Path, *, backup: bool = True) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("q9 decision payload must be a JSON object")
    before = path.stat().st_size
    windows = [
        _compact_window(row)
        for row in payload.get("windows") or []
        if isinstance(row, Mapping)
    ]
    payload["windows"] = windows
    payload["window_count"] = len(windows)
    backup_path = path.with_suffix(path.suffix + ".precompact.bak")
    if backup and not backup_path.exists():
        shutil.copy2(path, backup_path)
    temp = path.with_suffix(path.suffix + ".compact.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)
    after = path.stat().st_size
    return {
        "path": str(path),
        "backup_path": str(backup_path) if backup else "",
        "before_bytes": before,
        "after_bytes": after,
        "reduced_bytes": before - after,
        "reduced_pct": round((before - after) / before, 4) if before else 0.0,
        "window_count": len(windows),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compact an existing Q9 decision window artifact.")
    parser.add_argument("--path", required=True)
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args(argv)
    result = compact_file(Path(args.path), backup=not args.no_backup)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
