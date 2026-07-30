from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contracts import EPISODE_GAP_SEC, TARGET_SUBTYPE


def _day_range(start: str, end: str) -> Iterable[str]:
    current = date.fromisoformat(start[:10])
    last = date.fromisoformat(end[:10])
    while current <= last:
        yield current.isoformat()
        current += timedelta(days=1)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _target_subtype(row: Mapping[str, Any]) -> str:
    observation = row.get("below_vwap_reclaim_observation")
    observation = observation if isinstance(observation, Mapping) else {}
    lane = row.get("entry_lane_observation")
    lane = lane if isinstance(lane, Mapping) else {}
    return str(
        observation.get("subtype_v2")
        or lane.get("subtype_v2")
        or ""
    ).strip()


def load_target_candidate_rows(
    *,
    root: Path,
    start: str,
    end: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for day in _day_range(start, end):
        day_root = root / day
        if not day_root.exists():
            continue
        for path in sorted(day_root.glob("*.json")):
            if path.name == "latest.json":
                continue
            payload = _read_json(path)
            generated_at = str(payload.get("generated_at") or "")
            for raw in payload.get("candidates") or []:
                if not isinstance(raw, Mapping) or _target_subtype(raw) != TARGET_SUBTYPE:
                    continue
                row = dict(raw)
                row["_payload_day"] = day
                row["_payload_generated_at"] = generated_at
                row["_source_path"] = str(path)
                rows.append(row)
    return rows


def build_independent_episodes(
    rows: list[Mapping[str, Any]],
    *,
    episode_gap_sec: int = EPISODE_GAP_SEC,
) -> dict[str, Any]:
    canonical: dict[tuple[str, str, int, str], dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        base = row.get("shadow_forward_base")
        base = base if isinstance(base, Mapping) else {}
        epoch = int(_number(base.get("baseline_epoch")) or 0)
        day = str(row.get("_payload_day") or "")
        symbol = str(row.get("symbol") or "").strip()
        if not day or not symbol or epoch <= 0:
            continue
        key = (day, symbol, epoch, TARGET_SUBTYPE)
        canonical.setdefault(key, row)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for (day, symbol, _epoch, _subtype), row in canonical.items():
        grouped[(day, symbol)].append(row)

    episodes: list[dict[str, Any]] = []
    for (day, symbol), candidates in sorted(grouped.items()):
        previous_epoch = 0
        episode_index = 0
        for row in sorted(
            candidates,
            key=lambda item: int(
                _number(
                    (
                        item.get("shadow_forward_base")
                        if isinstance(item.get("shadow_forward_base"), Mapping)
                        else {}
                    ).get("baseline_epoch")
                )
                or 0
            ),
        ):
            base = row.get("shadow_forward_base")
            base = base if isinstance(base, Mapping) else {}
            epoch = int(_number(base.get("baseline_epoch")) or 0)
            if previous_epoch == 0 or epoch - previous_epoch >= int(episode_gap_sec):
                episode_index += 1
                factors = row.get("quant_factor_snapshot")
                factors = factors if isinstance(factors, Mapping) else {}
                factor_values = factors.get("factors")
                factor_values = factor_values if isinstance(factor_values, Mapping) else {}
                episodes.append(
                    {
                        "episode_id": (
                            f"{day.replace('-', '')}:{symbol}:"
                            f"{TARGET_SUBTYPE}:{episode_index}"
                        ),
                        "day": day,
                        "symbol": symbol,
                        "baseline_epoch": epoch,
                        "baseline_price": _number(base.get("baseline_price")),
                        "baseline_raw_ts": str(base.get("baseline_raw_ts") or ""),
                        "source_path": str(row.get("_source_path") or ""),
                        "shadow_role": str(row.get("shadow_role") or ""),
                        "reason": str(row.get("reason") or ""),
                        "market_regime_rail": str(
                            (
                                row.get("entry_lane_observation")
                                if isinstance(row.get("entry_lane_observation"), Mapping)
                                else {}
                            ).get("market_regime_rail")
                            or ""
                        ),
                        "factors": dict(factor_values),
                    }
                )
            previous_epoch = epoch

    return {
        "raw_candidate_count": len(rows),
        "canonical_candidate_count": len(canonical),
        "episode_count": len(episodes),
        "episode_day_count": len({row["day"] for row in episodes}),
        "episode_symbol_count": len({row["symbol"] for row in episodes}),
        "episodes": episodes,
    }
