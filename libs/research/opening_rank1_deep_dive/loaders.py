from __future__ import annotations

import json
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def load_opening_episodes(evidence_path: Path) -> list[dict[str, Any]]:
    payload = load_json(evidence_path)
    return [
        row
        for row in list(payload.get("episodes") or [])
        if isinstance(row, dict)
        and row.get("time_bucket") == "open_0_20m"
        and int(row.get("rank") or 0) == 1
        and (row.get("checkpoints") or {}).get("+30m", {}).get("status") == "observed"
    ]


def load_q9_windows(
    reports_root: Path,
    episodes: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    wanted: dict[str, set[str]] = {}
    for row in episodes:
        wanted.setdefault(str(row.get("day") or ""), set()).add(str(row.get("decision_id") or ""))
    found: dict[str, dict[str, Any]] = {}
    for day, decision_ids in wanted.items():
        payload = load_json(reports_root / "operator_summary" / "daily" / day / "q9_decision_windows.json")
        for window in list(payload.get("windows") or []):
            if not isinstance(window, dict):
                continue
            decision_id = str(window.get("decision_id") or "")
            if decision_id in decision_ids:
                found[decision_id] = window
    return found


def load_all_q9_windows(
    reports_root: Path,
    days: set[str],
) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for day in sorted(days):
        payload = load_json(reports_root / "operator_summary" / "daily" / day / "q9_decision_windows.json")
        for window in list(payload.get("windows") or []):
            if not isinstance(window, dict):
                continue
            decision_id = str(window.get("decision_id") or "")
            if decision_id:
                found[decision_id] = window
    return found


def _snapshot_epoch(path: Path, payload: dict[str, Any]) -> int:
    raw = str(payload.get("generated_at") or "")
    if raw:
        try:
            return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
        except ValueError:
            pass
    stamp = path.name.split("_", 1)[0]
    try:
        local = datetime.strptime(path.parent.name + stamp, "%Y-%m-%d%H%M%S").replace(tzinfo=KST)
        return int(local.timestamp())
    except ValueError:
        return 0


def load_point_in_time_macro(
    logs_root: Path,
    episodes: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    by_day: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for day in sorted({str(row.get("day") or "") for row in episodes}):
        rows: list[tuple[int, dict[str, Any]]] = []
        for path in sorted((logs_root / day).glob("*_macro_indicators.json")):
            payload = load_json(path)
            epoch = _snapshot_epoch(path, payload)
            if epoch > 0:
                rows.append((epoch, payload))
        by_day[day] = rows

    result: dict[str, dict[str, Any]] = {}
    for episode in episodes:
        rows = by_day.get(str(episode.get("day") or "")) or []
        epochs = [row[0] for row in rows]
        index = bisect_right(epochs, int(episode.get("decision_epoch") or 0)) - 1
        if index >= 0:
            result[str(episode.get("episode_id") or "")] = rows[index][1]
    return result


def load_symbol_metadata(path: Path) -> dict[str, dict[str, Any]]:
    payload = load_json(path)
    rows = payload.get("symbols") if isinstance(payload.get("symbols"), dict) else {}
    return {str(key): dict(value) for key, value in rows.items() if isinstance(value, dict)}


def load_actual_trades(reports_root: Path, days: set[str]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    result: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for day in sorted(days):
        for path in (reports_root / "trades" / day).glob("*/*/lifecycle_bundle.json"):
            payload = load_json(path)
            symbol = str(payload.get("symbol") or "")
            entry = payload.get("entry") if isinstance(payload.get("entry"), dict) else {}
            exit_row = payload.get("exit") if isinstance(payload.get("exit"), dict) else {}
            outcome = payload.get("trade_outcome") if isinstance(payload.get("trade_outcome"), dict) else {}
            raw_return = outcome.get("pnl_pct") or outcome.get("net_return_pct") or (
                payload.get("shared_facts") or {}
            ).get("pnl_pct")
            try:
                normalized_return = float(raw_return) * 100.0 if raw_return not in (None, "") else None
            except (TypeError, ValueError):
                normalized_return = None
            result.setdefault((day, symbol), []).append(
                {
                    "trade_id": str(payload.get("trade_id") or path.parent.name),
                    "entry_ts": entry.get("ts"),
                    "entry_price": entry.get("avg_price") or entry.get("filled_price") or entry.get("price"),
                    "exit_ts": exit_row.get("ts") or exit_row.get("timestamp"),
                    "exit_price": exit_row.get("avg_price") or exit_row.get("filled_price") or exit_row.get("price"),
                    "holding_seconds": payload.get("hold_duration_sec"),
                    "net_return_pct": normalized_return,
                    "entry_reason": entry.get("reason_human"),
                    "exit_reason": exit_row.get("reason_human"),
                }
            )
    return result


def epoch_to_kst(epoch: Any) -> str:
    try:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc).astimezone(KST).isoformat()
    except (TypeError, ValueError, OSError):
        return ""
