from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


def load_candidate_decision_summary(
    *,
    reports_root: Path,
    day: str,
) -> dict[str, Any]:
    path = (
        Path(reports_root)
        / "operator_summary"
        / "daily"
        / str(day)[:10]
        / "q9_decision_windows.json"
    )
    empty = {
        "available": False,
        "source": str(path),
        "window_count": 0,
        "decision_counts": {},
        "reason_counts": {},
        "candidate_rejected_total": 0,
        "candidate_noop_total": 0,
        "candidate_approved_total": 0,
    }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty

    decision_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    windows = payload.get("windows") if isinstance(payload, Mapping) else []
    for raw in windows or []:
        if not isinstance(raw, Mapping):
            continue
        commander = raw.get("commander_final")
        commander = commander if isinstance(commander, Mapping) else {}
        decision = str(commander.get("decision") or "unknown").strip().lower()
        reason = str(commander.get("reason") or "unspecified").strip()
        decision_counts[decision] += 1
        reason_counts[reason] += 1

    return {
        "available": True,
        "source": str(path),
        "window_count": sum(decision_counts.values()),
        "decision_counts": dict(decision_counts),
        "reason_counts": dict(reason_counts.most_common(10)),
        "candidate_rejected_total": int(decision_counts.get("reject", 0)),
        "candidate_noop_total": int(decision_counts.get("noop", 0)),
        "candidate_approved_total": int(
            decision_counts.get("approve", 0) + decision_counts.get("approved", 0)
        ),
        "semantics": {
            "candidate_rejection": "upstream policy decision before OrderIntent",
            "execution_guard_block": "OrderIntent rejected by execute_from_packet guard",
        },
    }


__all__ = ["load_candidate_decision_summary"]
