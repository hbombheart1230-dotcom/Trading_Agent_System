from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from libs.reporting.quant_shadow_candidate_evaluation import (
    _augment_missing_q9_commander_candidate,
    shadow_candidate_root_for_reports,
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _normalized_generated_at(value: Any) -> tuple[str, int | None]:
    text = str(value or "").strip()
    try:
        dt = datetime.fromtimestamp(float(text), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text, None
    return dt.isoformat(timespec="seconds"), int(dt.timestamp())


def _compact_candidate(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "symbol": str(row.get("symbol") or ""),
        "rank": row.get("rank"),
        "score_total": row.get("score_total"),
        "q9_selected": bool(row.get("q9_selected")),
        "sources": list(row.get("q9_candidate_sources") or []),
        "source_scores": dict(row.get("q9_candidate_source_scores") or {}),
    }


def _ranked_role_rows(payload: Mapping[str, Any], role: str, *, limit: int) -> list[dict[str, Any]]:
    rows = [
        _compact_candidate(row)
        for row in payload.get("q9_decision_candidates") or []
        if isinstance(row, Mapping) and str(row.get("q9_decision_role") or "") == role
    ]
    rows.sort(
        key=lambda row: (
            int(row.get("rank")) if str(row.get("rank") or "").isdigit() else 10_000,
            str(row.get("symbol") or ""),
        )
    )
    return rows[:limit]


def _window_from_shadow(payload: Mapping[str, Any]) -> dict[str, Any]:
    decision_id = str(payload.get("q9_decision_id") or "").strip()
    if not decision_id:
        return {}
    generated_at, epoch = _normalized_generated_at(payload.get("generated_at"))
    pre = _ranked_role_rows(payload, "P_SCANNER_PRE_STRATEGIST_UNIVERSE", limit=20)
    scanner = _ranked_role_rows(payload, "A_SCANNER_CONTROL", limit=20)
    strategist = _ranked_role_rows(payload, "B_STRATEGIST_RANKED", limit=10)
    commander_rows = [
        row
        for row in payload.get("q9_decision_candidates") or []
        if isinstance(row, Mapping)
        and str(row.get("q9_decision_role") or "") == "C_COMMANDER_FINAL"
    ]
    commander = commander_rows[0] if commander_rows else {}
    decision = str(commander.get("q9_commander_decision") or "noop").lower()
    candidate_symbol = str(commander.get("symbol") or "")
    window: dict[str, Any] = {
        "schema_version": "q9_decision_window.v1",
        "behavior_effect": "observation_only",
        "decision_id": decision_id,
        "decision_epoch": epoch,
        "generated_at": generated_at,
        "run_id": str(payload.get("run_id") or ""),
        "window_type": "scanner_selection" if scanner else "commander_monitor_only",
        "recovery": {
            "source": "quant_shadow_candidates",
            "evidence_reconstruction": True,
        },
    }
    if scanner:
        window["scanner_control"] = {
            "scope": "same_candidate_universe_ranking_only",
            "source": "recovered_q9_shadow_role",
            "evidence_class": "TRUSTED_SHADOW",
            "top10": scanner[:10],
            "top20": scanner,
            "top1_symbol": str(scanner[0].get("symbol") or ""),
        }
    if pre:
        window["scanner_pre_strategist_universe"] = {
            "schema_version": "q9_scanner_pre_strategist_universe.v1",
            "behavior_effect": "evaluation_only",
            "intrinsic_ranked_top20": pre,
            "source": "recovered_q9_shadow_role",
        }
    if strategist:
        selected = next((row for row in strategist if row.get("q9_selected")), strategist[0])
        window["strategist_selection"] = {
            "post_strategist_top10": strategist,
            "selected_symbol": str(selected.get("symbol") or ""),
            "evidence_class": "TRUSTED_SHADOW",
            "source": "recovered_q9_shadow_role",
        }
    if commander:
        window["commander_final"] = {
            "decision_id": decision_id,
            "decision": decision,
            "selected_symbol": candidate_symbol if decision == "approve" else "",
            "candidate_symbol": candidate_symbol,
            "veto": decision == "reject",
            "no_trade": bool(commander.get("q9_commander_no_trade")) or decision != "approve",
            "reason": str(commander.get("reason") or ""),
            "authority_scope": "final_approval_or_veto",
            "evidence_class": "TRUSTED_SHADOW",
            "source": "recovered_q9_shadow_role",
        }
    return window


def _merge_shadow_windows(
    *,
    reports_root: Path,
    day: str,
    windows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, int]:
    shadow_root = shadow_candidate_root_for_reports(Path(reports_root)) / day
    by_id = {
        str(row.get("decision_id") or ""): row
        for row in windows
        if str(row.get("decision_id") or "")
    }
    added = 0
    enriched = 0
    for path in sorted(shadow_root.glob("*.json")) if shadow_root.exists() else []:
        if path.name == "latest.json":
            continue
        recovered = _window_from_shadow(_read_json(path))
        decision_id = str(recovered.get("decision_id") or "")
        if not decision_id:
            continue
        existing = by_id.get(decision_id)
        if existing is None:
            windows.append(recovered)
            by_id[decision_id] = recovered
            added += 1
            continue
        changed = False
        for key in (
            "scanner_control",
            "scanner_pre_strategist_universe",
            "strategist_selection",
            "commander_final",
        ):
            if key not in existing and key in recovered:
                existing[key] = recovered[key]
                changed = True
        if changed:
            existing.setdefault("recovery", recovered.get("recovery"))
            existing["window_type"] = (
                "scanner_selection"
                if isinstance(existing.get("scanner_control"), Mapping)
                else "commander_monitor_only"
            )
            enriched += 1
    windows.sort(
        key=lambda row: (
            int(row.get("decision_epoch") or 0),
            str(row.get("decision_id") or ""),
        )
    )
    return windows, added, enriched


def repair_q9_day_artifacts(*, reports_root: Path, day: str) -> dict[str, Any]:
    normalized_day = str(day or "")[:10]
    decision_path = (
        Path(reports_root)
        / "operator_summary"
        / "daily"
        / normalized_day
        / "q9_decision_windows.json"
    )
    decision_payload = _read_json(decision_path)
    windows = [
        dict(row)
        for row in decision_payload.get("windows") or []
        if isinstance(row, Mapping)
    ]
    windows, recovered_windows, enriched_windows = _merge_shadow_windows(
        reports_root=Path(reports_root),
        day=normalized_day,
        windows=windows,
    )
    normalized_windows = 0
    windows_by_id: dict[str, dict[str, Any]] = {}
    for row in windows:
        before = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        row["window_type"] = (
            "scanner_selection"
            if isinstance(row.get("scanner_control"), Mapping)
            else "commander_monitor_only"
        )
        generated_at, epoch = _normalized_generated_at(row.get("generated_at"))
        if generated_at:
            row["generated_at"] = generated_at
        if row.get("decision_epoch") is None and epoch is not None:
            row["decision_epoch"] = epoch
        if json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) != before:
            normalized_windows += 1
        decision_id = str(row.get("decision_id") or "")
        if decision_id:
            windows_by_id[decision_id] = row
    if windows:
        decision_payload.setdefault("schema_version", "q9_decision_windows.v1")
        decision_payload.setdefault("behavior_effect", "observation_only")
        decision_payload.setdefault("day", normalized_day)
        decision_payload["windows"] = windows
        decision_payload["window_count"] = len(windows)
        decision_payload["recovery"] = {
            "source": "quant_shadow_candidates",
            "recovered_window_count": recovered_windows,
            "enriched_window_count": enriched_windows,
            "repaired_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        _write_json_atomic(decision_path, decision_payload)

    shadow_root = shadow_candidate_root_for_reports(Path(reports_root)) / normalized_day
    repaired_payloads = 0
    complete_payloads = 0
    for path in sorted(shadow_root.glob("*.json")) if shadow_root.exists() else []:
        if path.name == "latest.json":
            continue
        payload = _read_json(path)
        if not payload:
            continue
        before = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        payload = _augment_missing_q9_commander_candidate(
            payload,
            windows_by_id=windows_by_id,
        )
        roles = {
            str(row.get("q9_decision_role") or "")
            for row in payload.get("q9_decision_candidates") or []
            if isinstance(row, Mapping)
        }
        if "C_COMMANDER_FINAL" in roles:
            complete_payloads += 1
            payload["q9_sync_status"] = {
                "status": "complete",
                "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "role_count": len(roles),
                "source": "q9_artifact_repair",
            }
        after = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        if after != before:
            _write_json_atomic(path, payload)
            repaired_payloads += 1
    return {
        "ok": True,
        "day": normalized_day,
        "decision_path": str(decision_path),
        "window_count": len(windows),
        "recovered_window_count": recovered_windows,
        "enriched_window_count": enriched_windows,
        "normalized_window_count": normalized_windows,
        "shadow_payload_repaired_count": repaired_payloads,
        "shadow_payload_complete_count": complete_payloads,
    }


__all__ = ["repair_q9_day_artifacts"]
