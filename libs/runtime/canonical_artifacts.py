from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from libs.contracts.agent_outputs import (
    build_commander_output_artifact,
    build_commander_shadow_artifact,
    build_executor_output_artifact,
    build_monitor_output_artifact,
    build_scanner_output_artifact,
    build_strategist_output_artifact,
    build_supervisor_output_artifact,
    validate_artifact,
)
from libs.runtime.llm_report_classifier import find_llm_run_dir, organize_llm_run


def _reports_root(state: Dict[str, Any] | None = None) -> Path:
    if isinstance(state, dict):
        raw = str(state.get("reports_root") or "").strip()
        if raw:
            return Path(raw)
    raw_env = str(os.getenv("REPORTS_ROOT", "reports")).strip() or "reports"
    return Path(raw_env)


def _iso_day(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]
    try:
        epoch = int(float(value))
    except Exception:
        epoch = 0
    if epoch > 0:
        return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _resolve_day(state: Dict[str, Any]) -> str:
    for key in ("started_at", "ts", "now_iso", "tick_ts"):
        value = state.get(key)
        if value not in (None, ""):
            return _iso_day(value)
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def canonical_run_artifact_paths(
    run_id: str,
    *,
    day: str,
    reports_root: Path,
) -> Dict[str, Path]:
    base = Path(reports_root) / "canonical" / str(day or "").strip() / str(run_id or "").strip()
    return {
        "base_dir": base,
        "commander": base / "commander.json",
        "commander_shadow": base / "commander_shadow.json",
        "strategist": base / "strategist.json",
        "scanner": base / "scanner.json",
        "monitor": base / "monitor.json",
        "supervisor": base / "supervisor.json",
        "executor": base / "executor.json",
    }


def llm_run_artifact_paths(
    run_id: str,
    *,
    day: str,
    reports_root: Path,
    artifact_name: str,
) -> Dict[str, Path]:
    run_base = find_llm_run_dir(Path(reports_root), str(day or "").strip(), str(run_id or "").strip())
    base = run_base / str(artifact_name or "").strip()
    return {
        "base_dir": base,
        "prompt": base / "prompt.json",
        "response": base / "response.json",
        "meta": base / "meta.json",
    }


_STRATEGIST_STAGE_BY_CALL_KIND: Dict[str, Dict[str, Any]] = {
    "market_strategy_frame": {
        "stage_index": 1,
        "stage_name": "market_strategy_frame",
        "component": "strategist_stage1_market_frame",
    },
    "selected_symbol_tactical_refresh": {
        "stage_index": 2,
        "stage_name": "selected_symbol_tactical_refresh",
        "component": "strategist_stage2_selected_symbol",
    },
    "stale_intraday_hold_review": {
        "stage_index": 3,
        "stage_name": "stale_intraday_hold_review",
        "component": "strategist_stage3_hold_review",
    },
    "end_of_day_carry_review": {
        "stage_index": 4,
        "stage_name": "end_of_day_carry_review",
        "component": "strategist_stage4_carry_review",
    },
}

_STRATEGIST_STAGE_ALIASES: Dict[str, str] = {
    "": "market_strategy_frame",
    "strategic_frame": "market_strategy_frame",
    "theme_selection": "market_strategy_frame",
    "theme_selection_repair": "market_strategy_frame",
    "post_scanner_refresh": "selected_symbol_tactical_refresh",
    "selected_symbol_refresh": "selected_symbol_tactical_refresh",
    "post_scanner_selected_symbol_refresh": "selected_symbol_tactical_refresh",
    "open_position_monitor_refresh": "stale_intraday_hold_review",
    "hold_review": "stale_intraday_hold_review",
    "preopen_open_position_review": "stale_intraday_hold_review",
    "carry_review": "end_of_day_carry_review",
    "overnight_carry_review": "end_of_day_carry_review",
    "closeout_carry_review": "end_of_day_carry_review",
}


def normalize_strategist_llm_call_kind(value: Any) -> str:
    raw = str(value or "").strip().lower()
    normalized = _STRATEGIST_STAGE_ALIASES.get(raw, raw)
    if normalized in _STRATEGIST_STAGE_BY_CALL_KIND:
        return normalized
    return "market_strategy_frame"


def strategist_llm_stage_descriptor(call_kind: Any) -> Dict[str, Any]:
    normalized = normalize_strategist_llm_call_kind(call_kind)
    descriptor = dict(_STRATEGIST_STAGE_BY_CALL_KIND.get(normalized) or {})
    descriptor["call_kind"] = normalized
    return descriptor


def llm_stage_manifest_path(
    run_id: str,
    *,
    day: str,
    reports_root: Path,
) -> Path:
    run_base = find_llm_run_dir(Path(reports_root), str(day or "").strip(), str(run_id or "").strip())
    return run_base / "llm_stage_manifest.json"


def _read_manifest(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def write_llm_stage_manifest_entry(state: Dict[str, Any], entry: Dict[str, Any]) -> Dict[str, Any]:
    run_id = str(state.get("run_id") or "").strip()
    if not run_id:
        return {}
    day = _resolve_day(state)
    reports_root = _reports_root(state)
    path = llm_stage_manifest_path(run_id, day=day, reports_root=reports_root)
    descriptor = strategist_llm_stage_descriptor(entry.get("call_kind") or entry.get("stage_name"))
    normalized_entry = {
        "stage_index": int(entry.get("stage_index") or descriptor.get("stage_index") or 0),
        "stage_name": str(entry.get("stage_name") or descriptor.get("stage_name") or ""),
        "call_kind": str(descriptor.get("call_kind") or ""),
        "component": str(entry.get("component") or descriptor.get("component") or ""),
        "status": str(entry.get("status") or entry.get("llm_status") or ""),
        "reason": str(entry.get("reason") or ""),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    for key in (
        "prompt_ref",
        "response_ref",
        "meta_ref",
        "legacy_prompt_ref",
        "legacy_response_ref",
        "legacy_meta_ref",
        "strategist_summary_md_ref",
        "strategist_summary_json_ref",
        "skip_reason",
        "model",
    ):
        value = entry.get(key)
        if value not in (None, ""):
            normalized_entry[key] = value

    manifest = _read_manifest(path)
    if not manifest:
        manifest = {
            "schema_version": "llm_stage_manifest.v1",
            "run_id": run_id,
            "day": day,
            "stages": [],
        }
    stages: List[Dict[str, Any]] = [
        dict(row)
        for row in list(manifest.get("stages") or [])
        if isinstance(row, dict)
    ]
    stage_index = int(normalized_entry.get("stage_index") or 0)
    component = str(normalized_entry.get("component") or "")
    replaced = False
    for idx, row in enumerate(stages):
        if int(row.get("stage_index") or 0) == stage_index and str(row.get("component") or "") == component:
            stages[idx] = normalized_entry
            replaced = True
            break
    if not replaced:
        stages.append(normalized_entry)
    stages = sorted(stages, key=lambda row: (int(row.get("stage_index") or 0), str(row.get("component") or "")))
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    manifest["stages"] = stages
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    llm_map = state.get("llm_artifacts") if isinstance(state.get("llm_artifacts"), dict) else {}
    llm_map = dict(llm_map)
    llm_map["llm_stage_manifest"] = str(path)
    state["llm_artifacts"] = llm_map
    return {"llm_stage_manifest_ref": str(path), "stage_entry": normalized_entry}


def write_llm_stage_skip_entry(state: Dict[str, Any], *, call_kind: Any, reason: str) -> Dict[str, Any]:
    run_id = str(state.get("run_id") or "").strip()
    if not run_id:
        return {}
    day = _resolve_day(state)
    reports_root = _reports_root(state)
    descriptor = strategist_llm_stage_descriptor(call_kind)
    path = llm_stage_manifest_path(run_id, day=day, reports_root=reports_root)
    manifest = _read_manifest(path)
    stage_index = int(descriptor.get("stage_index") or 0)
    component = str(descriptor.get("component") or "")
    for row in list(manifest.get("stages") or []):
        if not isinstance(row, dict):
            continue
        if int(row.get("stage_index") or 0) == stage_index and str(row.get("component") or "") == component:
            return {"llm_stage_manifest_ref": str(path), "stage_entry": dict(row), "already_present": True}
    return write_llm_stage_manifest_entry(
        state,
        {
            **dict(descriptor),
            "status": "skipped",
            "reason": str(reason or ""),
            "skip_reason": str(reason or ""),
        },
    )


def _with_validation(payload: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(payload or {}) if isinstance(payload, dict) else {}
    if not isinstance(out.get("validation"), dict):
        out["validation"] = validate_artifact(out)
    return out


def _write_artifact(path: Path, payload: Dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_with_validation(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _record_path(state: Dict[str, Any], agent: str, path: str) -> None:
    if not path:
        return
    current = state.get("canonical_artifacts") if isinstance(state.get("canonical_artifacts"), dict) else {}
    current = dict(current)
    current[str(agent or "").strip()] = str(path)
    state["canonical_artifacts"] = current


def _write_artifact_once(
    state: Dict[str, Any],
    *,
    agent: str,
    path: Path,
    payload: Dict[str, Any],
    overwrite: bool = False,
) -> str:
    cache = state.get("_canonical_written_paths") if isinstance(state.get("_canonical_written_paths"), dict) else {}
    cache = dict(cache)
    existing = str(cache.get(str(agent or "").strip()) or "").strip()
    if not overwrite and existing and existing == str(path) and path.exists():
        _record_path(state, agent, str(path))
        state["_canonical_written_paths"] = cache
        return str(path)
    out = _write_artifact(path, payload)
    cache[str(agent or "").strip()] = str(path)
    state["_canonical_written_paths"] = cache
    _record_path(state, agent, out)
    return out


def _stable_json_text(payload: Any) -> str:
    try:
        if isinstance(payload, (dict, list)):
            return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        pass
    return str(payload or "")


def _sha256_text(text: Any) -> str:
    value = str(text or "")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_llm_artifact_bundle(
    state: Dict[str, Any],
    *,
    artifact_name: str,
    prompt_payload: Dict[str, Any] | None,
    response_payload: Dict[str, Any] | None,
    meta_payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    run_id = str(state.get("run_id") or "").strip()
    if not run_id:
        return {}
    day = _resolve_day(state)
    paths = llm_run_artifact_paths(
        run_id,
        day=day,
        reports_root=_reports_root(state),
        artifact_name=str(artifact_name or "").strip(),
    )
    prompt_obj = dict(prompt_payload or {})
    response_obj = dict(response_payload or {})
    meta_obj = dict(meta_payload or {})

    prompt_obj.setdefault("schema_version", "llm_prompt_raw.v1")
    prompt_obj.setdefault("run_id", run_id)
    prompt_obj.setdefault("day", day)
    prompt_obj.setdefault("artifact_name", str(artifact_name or "").strip())
    prompt_obj.setdefault("saved_at", datetime.now(timezone.utc).isoformat())

    response_obj.setdefault("schema_version", "llm_response_raw.v1")
    response_obj.setdefault("run_id", run_id)
    response_obj.setdefault("day", day)
    response_obj.setdefault("artifact_name", str(artifact_name or "").strip())
    response_obj.setdefault("saved_at", datetime.now(timezone.utc).isoformat())

    prompt_text = _stable_json_text(prompt_obj)
    response_text = _stable_json_text(response_obj)
    prompt_hash = _sha256_text(prompt_text)
    response_hash = _sha256_text(response_text)

    meta_obj = dict(meta_obj)
    meta_obj.setdefault("schema_version", "llm_artifact_meta.v1")
    meta_obj.setdefault("run_id", run_id)
    meta_obj.setdefault("day", day)
    meta_obj.setdefault("artifact_name", str(artifact_name or "").strip())
    meta_obj["prompt_ref"] = str(paths["prompt"])
    meta_obj["response_ref"] = str(paths["response"])
    meta_obj["prompt_hash"] = prompt_hash
    meta_obj["response_hash"] = response_hash
    meta_obj.setdefault("saved_at", datetime.now(timezone.utc).isoformat())

    for key, payload in (("prompt", prompt_obj), ("response", response_obj), ("meta", meta_obj)):
        path = paths[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_refs: Dict[str, str] = {}
    summary_error = ""
    artifact_key = str(artifact_name or "").strip()
    component_key = str(meta_obj.get("component") or "").strip()
    if (
        artifact_key == "strategist"
        or artifact_key.startswith("strategist_stage")
        or component_key == "strategist"
        or component_key.startswith("strategist_stage")
    ):
        try:
            from libs.reporting.strategist_llm_summary import generate_strategist_llm_summary

            summary_md, summary_json, _summary_payload = generate_strategist_llm_summary(paths["response"])
            summary_refs = {
                "strategist_summary_md_ref": str(summary_md),
                "strategist_summary_json_ref": str(summary_json),
            }
            meta_obj.update(summary_refs)
        except Exception as exc:
            summary_error = f"{type(exc).__name__}: {exc}"[:500]
            meta_obj["strategist_summary_error"] = summary_error
        if summary_refs or summary_error:
            paths["meta"].write_text(json.dumps(meta_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    llm_map = state.get("llm_artifacts") if isinstance(state.get("llm_artifacts"), dict) else {}
    llm_map = dict(llm_map)
    llm_map[str(artifact_name or "").strip()] = str(paths["meta"])
    state["llm_artifacts"] = llm_map

    refs = {
        "base_dir": str(paths["base_dir"]),
        "prompt_ref": str(paths["prompt"]),
        "response_ref": str(paths["response"]),
        "meta_ref": str(paths["meta"]),
        "prompt_hash": prompt_hash,
        "response_hash": response_hash,
        "llm_status": str(meta_obj.get("llm_status") or meta_obj.get("status") or "").strip(),
    }
    refs.update(summary_refs)
    if summary_error:
        refs["strategist_summary_error"] = summary_error
    return refs


def write_strategist_artifact(state: Dict[str, Any]) -> str:
    run_id = str(state.get("run_id") or "").strip()
    if not run_id:
        return ""
    day = _resolve_day(state)
    reports_root = _reports_root(state)
    paths = canonical_run_artifact_paths(run_id, day=day, reports_root=reports_root)
    path = _write_artifact_once(state, agent="strategist", path=paths["strategist"], payload=build_strategist_output_artifact(state))
    _refresh_strategist_llm_summary_after_canonical(run_id=run_id, day=day, reports_root=reports_root)
    return path


def _refresh_strategist_llm_summary_after_canonical(*, run_id: str, day: str, reports_root: Path) -> None:
    paths = llm_run_artifact_paths(run_id, day=day, reports_root=reports_root, artifact_name="strategist")
    response_path = paths["response"]
    if not response_path.exists():
        return
    try:
        from libs.reporting.strategist_llm_summary import generate_strategist_llm_summary

        generate_strategist_llm_summary(response_path)
    except Exception:
        return


def write_scanner_artifact(state: Dict[str, Any]) -> str:
    run_id = str(state.get("run_id") or "").strip()
    if not run_id:
        return ""
    paths = canonical_run_artifact_paths(run_id, day=_resolve_day(state), reports_root=_reports_root(state))
    # Scanner can run twice in one integrated cycle when commander refreshes the
    # strategist frame after the first scanner selection. The canonical scanner
    # artifact must reflect the scanner output actually handed to monitor.
    path = _write_artifact_once(
        state,
        agent="scanner",
        path=paths["scanner"],
        payload=build_scanner_output_artifact(state),
        overwrite=True,
    )
    return path


def write_monitor_artifact(state: Dict[str, Any]) -> str:
    run_id = str(state.get("run_id") or "").strip()
    if not run_id:
        return ""
    paths = canonical_run_artifact_paths(run_id, day=_resolve_day(state), reports_root=_reports_root(state))
    path = _write_artifact_once(state, agent="monitor", path=paths["monitor"], payload=build_monitor_output_artifact(state))
    return path


def write_supervisor_artifact(
    state: Dict[str, Any],
    *,
    order: Dict[str, Any],
    allowed: bool,
    reason: str,
    details: Dict[str, Any] | None = None,
    strategy_policy_summary: Dict[str, Any] | None = None,
) -> str:
    run_id = str(state.get("run_id") or "").strip()
    if not run_id:
        return ""
    paths = canonical_run_artifact_paths(run_id, day=_resolve_day(state), reports_root=_reports_root(state))
    payload = build_supervisor_output_artifact(
        state,
        order=order,
        allowed=bool(allowed),
        reason=str(reason or ""),
        details=dict(details or {}),
        strategy_policy_summary=dict(strategy_policy_summary or {}),
    )
    path = _write_artifact_once(state, agent="supervisor", path=paths["supervisor"], payload=payload)
    return path


def _rewrite_state_llm_artifact_refs(state: Dict[str, Any], *, day: str, run_id: str, category: str) -> None:
    if not category:
        return
    old_backslash = f"reports\\llm\\{day}\\{run_id}\\"
    new_backslash = f"reports\\llm\\{day}\\{category}\\{run_id}\\"
    old_slash = f"reports/llm/{day}/{run_id}/"
    new_slash = f"reports/llm/{day}/{category}/{run_id}/"
    old_abs_backslash = f"\\llm\\{day}\\{run_id}\\"
    new_abs_backslash = f"\\llm\\{day}\\{category}\\{run_id}\\"
    old_abs_slash = f"/llm/{day}/{run_id}/"
    new_abs_slash = f"/llm/{day}/{category}/{run_id}/"
    llm_map = state.get("llm_artifacts") if isinstance(state.get("llm_artifacts"), dict) else {}
    if not llm_map:
        return
    updated: Dict[str, Any] = {}
    for key, value in dict(llm_map).items():
        text = str(value)
        text = text.replace(old_backslash, new_backslash).replace(old_slash, new_slash)
        text = text.replace(old_abs_backslash, new_abs_backslash).replace(old_abs_slash, new_abs_slash)
        updated[key] = text
    state["llm_artifacts"] = updated


def write_executor_artifact(state: Dict[str, Any], *, execution: Dict[str, Any], order: Dict[str, Any] | None = None) -> str:
    run_id = str(state.get("run_id") or "").strip()
    if not run_id:
        return ""
    day = _resolve_day(state)
    reports_root = _reports_root(state)
    paths = canonical_run_artifact_paths(run_id, day=day, reports_root=reports_root)
    payload = build_executor_output_artifact(state, execution=dict(execution or {}), order=dict(order or {}))
    path = _write_artifact_once(state, agent="executor", path=paths["executor"], payload=payload)
    try:
        classification = organize_llm_run(reports_root, day=day, run_id=run_id, dry_run=False, update_day_index=True)
        state["llm_report_classification"] = dict(classification)
        _rewrite_state_llm_artifact_refs(
            state,
            day=day,
            run_id=run_id,
            category=str(classification.get("category") or ""),
        )
    except Exception as exc:
        state["llm_report_classification_error"] = f"{type(exc).__name__}: {exc}"[:300]
    return path


def write_commander_artifact(
    state: Dict[str, Any],
    *,
    mode: str,
    phase: str,
    path: str,
    status: str,
    reason: str = "",
) -> str:
    run_id = str(state.get("run_id") or "").strip()
    if not run_id:
        return ""
    paths = canonical_run_artifact_paths(run_id, day=_resolve_day(state), reports_root=_reports_root(state))
    payload = build_commander_output_artifact(
        state,
        mode=str(mode or ""),
        phase=str(phase or ""),
        path=str(path or ""),
        status=str(status or "ok"),
        reason=str(reason or ""),
    )
    path_text = _write_artifact_once(state, agent="commander", path=paths["commander"], payload=payload)
    return path_text


def write_commander_shadow_artifact(
    state: Dict[str, Any],
    *,
    mode: str,
    phase: str,
    path: str,
    status: str,
    reason: str = "",
) -> str:
    run_id = str(state.get("run_id") or "").strip()
    if not run_id:
        return ""
    paths = canonical_run_artifact_paths(run_id, day=_resolve_day(state), reports_root=_reports_root(state))
    payload = build_commander_shadow_artifact(
        state,
        mode=str(mode or ""),
        phase=str(phase or ""),
        path=str(path or ""),
        status=str(status or "ok"),
        reason=str(reason or ""),
    )
    path_text = _write_artifact_once(state, agent="commander_shadow", path=paths["commander_shadow"], payload=payload)
    return path_text


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def find_run_artifact_dir(reports_root: Path, run_id: str, *, day_hint: str = "") -> Path | None:
    reports_root = Path(reports_root)
    if day_hint:
        candidate = reports_root / "canonical" / day_hint / run_id
        if candidate.exists():
            return candidate
    candidates = sorted((reports_root / "canonical").glob(f"*/{run_id}"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return candidates[0] if candidates else None


def load_run_canonical_artifacts(
    *,
    reports_root: Path,
    run_id: str,
    day_hint: str = "",
) -> Dict[str, Any]:
    run_id = str(run_id or "").strip()
    if not run_id:
        return {}
    base = find_run_artifact_dir(Path(reports_root), run_id, day_hint=str(day_hint or "").strip())
    if base is None:
        return {}
    out = {
        "base_dir": str(base),
        "paths": {},
        "artifacts": {},
    }
    for agent in ("commander", "strategist", "scanner", "monitor", "supervisor", "executor"):
        path = base / f"{agent}.json"
        out["paths"][agent] = str(path) if path.exists() else ""
        out["artifacts"][agent] = _read_json(path) if path.exists() else {}
    return out
