from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contracts import EPISODE_GAP_SEC
from .hypotheses import matched_hypotheses


def _days(start: str, end: str) -> Iterable[str]:
    current = date.fromisoformat(start[:10])
    last = date.fromisoformat(end[:10])
    while current <= last:
        yield current.isoformat()
        current += timedelta(days=1)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _factors(row: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = row.get("quant_factor_snapshot")
    snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    factors = snapshot.get("factors")
    return dict(factors) if isinstance(factors, Mapping) else {}


def _richness(row: Mapping[str, Any]) -> tuple[int, int, int]:
    factors = _factors(row)
    populated = sum(value not in (None, "") for value in factors.values())
    base = row.get("shadow_forward_base")
    base = base if isinstance(base, Mapping) else {}
    return (
        populated,
        int(_number(base.get("baseline_price")) is not None),
        int(bool(row.get("entry_lane_observation"))),
    )


def load_candidate_snapshots(
    *,
    root: Path,
    start: str,
    end: str,
) -> dict[str, Any]:
    canonical: dict[tuple[str, str, int], dict[str, Any]] = {}
    raw_count = 0
    for day in _days(start, end):
        day_root = root / day
        if not day_root.exists():
            continue
        for path in sorted(day_root.glob("*.json")):
            if path.name == "latest.json":
                continue
            payload = _read_json(path)
            generated_at = str(payload.get("generated_at") or "")
            for raw in payload.get("candidates") or []:
                if not isinstance(raw, Mapping):
                    continue
                raw_count += 1
                base = raw.get("shadow_forward_base")
                base = base if isinstance(base, Mapping) else {}
                epoch = int(_number(base.get("baseline_epoch")) or 0)
                symbol = str(raw.get("symbol") or "").strip()
                price = _number(base.get("baseline_price"))
                if not symbol or epoch <= 0 or price is None or price <= 0:
                    continue
                row = dict(raw)
                row["_payload_day"] = day
                row["_payload_generated_at"] = generated_at
                row["_source_path"] = str(path)
                key = (day, symbol, epoch)
                prior = canonical.get(key)
                if prior is None or _richness(row) > _richness(prior):
                    canonical[key] = row
    return {
        "raw_candidate_count": raw_count,
        "canonical_candidate_count": len(canonical),
        "rows": [
            canonical[key]
            for key in sorted(canonical, key=lambda item: (item[0], item[2], item[1]))
        ],
    }


def build_hypothesis_episodes(
    rows: list[Mapping[str, Any]],
    *,
    gap_sec: int = EPISODE_GAP_SEC,
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw in rows:
        row = dict(raw)
        day = str(row.get("_payload_day") or "")
        symbol = str(row.get("symbol") or "")
        base = row.get("shadow_forward_base")
        base = base if isinstance(base, Mapping) else {}
        epoch = int(_number(base.get("baseline_epoch")) or 0)
        for hypothesis_id in matched_hypotheses(row):
            grouped[(hypothesis_id, day, symbol)].append(row)

    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (hypothesis_id, day, symbol), candidates in sorted(grouped.items()):
        previous_epoch = 0
        episode_index = 0
        for row in sorted(
            candidates,
            key=lambda item: int(
                _number((item.get("shadow_forward_base") or {}).get("baseline_epoch"))
                or 0
            ),
        ):
            base = row.get("shadow_forward_base") or {}
            epoch = int(_number(base.get("baseline_epoch")) or 0)
            if previous_epoch == 0 or epoch - previous_epoch >= int(gap_sec):
                episode_index += 1
                output[hypothesis_id].append(
                    {
                        "episode_id": (
                            f"{hypothesis_id}:{day.replace('-', '')}:{symbol}:"
                            f"{episode_index}"
                        ),
                        "hypothesis_id": hypothesis_id,
                        "day": day,
                        "symbol": symbol,
                        "baseline_epoch": epoch,
                        "baseline_price": _number(base.get("baseline_price")),
                        "baseline_raw_ts": str(base.get("baseline_raw_ts") or ""),
                        "source_path": str(row.get("_source_path") or ""),
                        "factors": _factors(row),
                    }
                )
            previous_epoch = epoch
    return dict(output)
