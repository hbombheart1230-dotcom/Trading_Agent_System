from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contracts import END, START, TOP_K


KST = timezone(timedelta(hours=9))


def days(start: str = START, end: str = END) -> Iterable[str]:
    current = date.fromisoformat(start[:10])
    last = date.fromisoformat(end[:10])
    while current <= last:
        yield current.isoformat()
        current += timedelta(days=1)


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def valid_decision_epoch(epoch: int, day: str) -> bool:
    if epoch <= 0:
        return False
    try:
        value = datetime.fromtimestamp(epoch, tz=KST)
    except Exception:
        return False
    minute = value.hour * 60 + value.minute
    return value.date().isoformat() == day and 9 * 60 <= minute <= 15 * 60 + 20


def load_q9_candidate_windows(
    *,
    reports_root: Path,
    start: str = START,
    end: str = END,
    top_k: int = TOP_K,
) -> dict[str, Any]:
    canonical: dict[tuple[str, int], dict[str, Any]] = {}
    raw_window_count = 0
    invalid_epoch_count = 0
    missing_universe_count = 0
    source_paths: list[str] = []
    for day in days(start, end):
        path = reports_root / "operator_summary" / "daily" / day / "q9_decision_windows.json"
        payload = read_json(path)
        if not payload:
            continue
        source_paths.append(str(path))
        for raw in payload.get("windows") or []:
            if not isinstance(raw, Mapping) or raw.get("window_type") != "scanner_selection":
                continue
            raw_window_count += 1
            epoch = int(raw.get("decision_epoch") or 0)
            if not valid_decision_epoch(epoch, day):
                invalid_epoch_count += 1
                continue
            universe = raw.get("scanner_pre_strategist_universe")
            universe = universe if isinstance(universe, Mapping) else {}
            candidates = [
                dict(row)
                for row in universe.get("intrinsic_ranked_top20") or []
                if isinstance(row, Mapping) and str(row.get("symbol") or "").strip()
            ]
            candidates.sort(key=lambda row: (int(row.get("rank") or 999), str(row.get("symbol") or "")))
            candidates = candidates[: max(1, int(top_k))]
            if not candidates:
                missing_universe_count += 1
                continue
            row = {
                "decision_id": str(raw.get("decision_id") or ""),
                "day": day,
                "decision_epoch": epoch,
                "candidates": candidates,
                "scanner_control": dict(raw.get("scanner_control") or {}),
                "strategist_selection": dict(raw.get("strategist_selection") or {}),
                "commander_final": dict(raw.get("commander_final") or {}),
                "source_path": str(path),
            }
            key = (day, epoch)
            prior = canonical.get(key)
            if prior is None or len(candidates) > len(prior["candidates"]):
                canonical[key] = row
    windows = [canonical[key] for key in sorted(canonical)]
    return {
        "raw_window_count": raw_window_count,
        "canonical_window_count": len(windows),
        "invalid_epoch_count": invalid_epoch_count,
        "missing_universe_count": missing_universe_count,
        "day_count": len({row["day"] for row in windows}),
        "symbol_count": len(
            {
                str(candidate.get("symbol") or "")
                for window in windows
                for candidate in window["candidates"]
            }
        ),
        "source_paths": source_paths,
        "windows": windows,
    }


def load_latest_q16_samples(
    *,
    reports_root: Path,
    start: str = START,
    end: str = END,
) -> dict[str, Any]:
    candidates: list[tuple[int, str, Path, dict[str, Any]]] = []
    for day in days(start, end):
        path = reports_root / "evaluation" / "daily" / day / "q16_proxy_rejection_review.json"
        payload = read_json(path)
        rows = payload.get("samples") if isinstance(payload.get("samples"), list) else []
        if rows:
            candidates.append((len(rows), str(payload.get("end_day") or day), path, payload))
    if not candidates:
        return {"sample_count": 0, "samples": [], "source_path": ""}
    _, _, path, payload = max(candidates, key=lambda row: (row[0], row[1]))
    deduped: dict[tuple[str, int], dict[str, Any]] = {}
    for raw in payload.get("samples") or []:
        if not isinstance(raw, Mapping):
            continue
        outcome = raw.get("shadow_forward_outcome")
        if not isinstance(outcome, Mapping) or not outcome.get("available"):
            continue
        key = (
            str(raw.get("symbol") or ""),
            int(outcome.get("baseline_epoch") or 0),
        )
        prior = deduped.get(key)
        if prior is None or int(outcome.get("observed_checkpoint_count") or 0) > int(
            (prior.get("shadow_forward_outcome") or {}).get("observed_checkpoint_count") or 0
        ):
            deduped[key] = dict(raw)
    rows = [deduped[key] for key in sorted(deduped)]
    return {
        "sample_count": len(rows),
        "raw_sample_count": len(payload.get("samples") or []),
        "start_day": str(payload.get("start_day") or ""),
        "end_day": str(payload.get("end_day") or ""),
        "source_path": str(path),
        "samples": rows,
    }


def load_quant_shadow_samples(
    *,
    logs_root: Path,
    start: str = START,
    end: str = END,
    gap_sec: int = 15 * 60,
) -> dict[str, Any]:
    by_minute: dict[tuple[str, int], dict[str, Any]] = {}
    raw_candidate_count = 0
    source_file_count = 0
    sampled_source_file_count = 0
    for day in days(start, end):
        day_dir = logs_root / day
        if not day_dir.exists():
            continue
        all_paths = sorted(day_dir.glob("*.json"))
        source_file_count += len(all_paths)
        snapshot_paths: dict[str, Path] = {}
        for path in all_paths:
            match = re.match(r"^(\d{8})_(\d{2})(\d{2})(\d{2})Z_", path.name)
            if match:
                bucket = f"{match.group(1)}:{match.group(2)}:{int(match.group(3)) // 15}"
            else:
                bucket = f"fallback:{path.name}"
            snapshot_paths.setdefault(bucket, path)
        sampled_source_file_count += len(snapshot_paths)
        for path in snapshot_paths.values():
            payload = read_json(path)
            if not payload:
                continue
            for candidate in payload.get("candidates") or []:
                if not isinstance(candidate, Mapping):
                    continue
                raw_candidate_count += 1
                base = candidate.get("shadow_forward_base")
                base = base if isinstance(base, Mapping) else {}
                symbol = str(candidate.get("symbol") or "")
                baseline_epoch = int(base.get("baseline_epoch") or 0)
                baseline_price = float(base.get("baseline_price") or 0.0)
                if not symbol or baseline_epoch <= 0 or baseline_price <= 0.0:
                    continue
                row = dict(candidate)
                row.update(
                    {
                        "day": day,
                        "q16_day": day,
                        "baseline_epoch": baseline_epoch,
                        "baseline_price": baseline_price,
                        "decision_epoch": baseline_epoch,
                        "source_path": str(path),
                        "evidence_class": "RECONSTRUCTED_QUANT_SHADOW",
                        "opportunity_disposition": (
                            "intent_submitted"
                            if bool(candidate.get("intent_submitted"))
                            else "guard_blocked"
                            if bool(candidate.get("guard_blocked"))
                            else "would_enter_shadow"
                            if bool(candidate.get("would_enter"))
                            else "observed_not_entered"
                        ),
                    }
                )
                key = (symbol, baseline_epoch)
                prior = by_minute.get(key)
                richness = len(row) + len(dict(row.get("quant_factor_snapshot") or {}))
                prior_richness = (
                    len(prior) + len(dict(prior.get("quant_factor_snapshot") or {}))
                    if prior
                    else -1
                )
                if prior is None or richness > prior_richness:
                    by_minute[key] = row

    spaced: list[dict[str, Any]] = []
    last_epoch: dict[tuple[str, str], int] = {}
    for (_, _), row in sorted(
        by_minute.items(),
        key=lambda item: (str(item[1].get("day") or ""), int(item[1].get("baseline_epoch") or 0), item[0][0]),
    ):
        key = (str(row.get("day") or ""), str(row.get("symbol") or ""))
        epoch = int(row.get("baseline_epoch") or 0)
        if epoch - int(last_epoch.get(key) or 0) < max(0, int(gap_sec)):
            continue
        spaced.append(row)
        last_epoch[key] = epoch
    return {
        "source_file_count": source_file_count,
        "sampled_source_file_count": sampled_source_file_count,
        "raw_candidate_count": raw_candidate_count,
        "minute_deduped_count": len(by_minute),
        "spaced_sample_count": len(spaced),
        "day_count": len({str(row.get("day") or "") for row in spaced}),
        "symbol_count": len({str(row.get("symbol") or "") for row in spaced}),
        "samples": spaced,
    }


def load_trade_evaluations(
    *,
    reports_root: Path,
    start: str = START,
    end: str = END,
) -> dict[str, Any]:
    rows: dict[str, dict[str, Any]] = {}
    root = reports_root / "evaluation" / "trades"
    for path in sorted(root.glob("*/*/trade_evaluation.json")):
        day = path.parents[1].name
        if not (start <= day <= end):
            continue
        payload = read_json(path)
        trade_id = str(payload.get("trade_id") or path.parent.name)
        if trade_id:
            rows[trade_id] = payload
    values = [rows[key] for key in sorted(rows)]
    return {
        "trade_count": len(values),
        "day_count": len({str(row.get("day") or "") for row in values}),
        "rows": values,
    }
