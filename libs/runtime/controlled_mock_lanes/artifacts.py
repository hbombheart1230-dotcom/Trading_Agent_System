from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def q12_hypothesis_path(reports_root: Path, day: str) -> Path:
    return (
        reports_root
        / "evaluation"
        / "baseline_btc_woori_tech"
        / day
        / "q12_btc_woori_hypothesis_validation.json"
    )


def q10_artifact_paths(reports_root: Path, day: str) -> dict[str, Path]:
    root = (
        reports_root
        / "evaluation"
        / "baseline_samsung_hynix"
        / day
        / "q10_forward_validation"
    )
    return {
        "preopen": root / "q10_preopen_signal_snapshot.json",
        "reactions": root / "q10_actual_market_reactions.json",
        "expected_actual": root / "q10_expected_vs_actual.json",
    }


__all__ = ["q10_artifact_paths", "q12_hypothesis_path", "read_json"]
