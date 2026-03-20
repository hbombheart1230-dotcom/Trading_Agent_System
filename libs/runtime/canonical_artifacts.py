from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from libs.contracts.agent_outputs import (
    build_commander_output_artifact,
    build_executor_output_artifact,
    build_monitor_output_artifact,
    build_scanner_output_artifact,
    build_strategist_output_artifact,
    build_supervisor_output_artifact,
    validate_artifact,
)


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
    base = (
        Path(reports_root)
        / "llm"
        / str(day or "").strip()
        / str(run_id or "").strip()
        / str(artifact_name or "").strip()
    )
    return {
        "base_dir": base,
        "prompt": base / "prompt.json",
        "response": base / "response.json",
        "meta": base / "meta.json",
    }


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


def _write_artifact_once(state: Dict[str, Any], *, agent: str, path: Path, payload: Dict[str, Any]) -> str:
    cache = state.get("_canonical_written_paths") if isinstance(state.get("_canonical_written_paths"), dict) else {}
    cache = dict(cache)
    existing = str(cache.get(str(agent or "").strip()) or "").strip()
    if existing and existing == str(path) and path.exists():
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

    llm_map = state.get("llm_artifacts") if isinstance(state.get("llm_artifacts"), dict) else {}
    llm_map = dict(llm_map)
    llm_map[str(artifact_name or "").strip()] = str(paths["meta"])
    state["llm_artifacts"] = llm_map

    return {
        "base_dir": str(paths["base_dir"]),
        "prompt_ref": str(paths["prompt"]),
        "response_ref": str(paths["response"]),
        "meta_ref": str(paths["meta"]),
        "prompt_hash": prompt_hash,
        "response_hash": response_hash,
        "llm_status": str(meta_obj.get("llm_status") or meta_obj.get("status") or "").strip(),
    }


def write_strategist_artifact(state: Dict[str, Any]) -> str:
    run_id = str(state.get("run_id") or "").strip()
    if not run_id:
        return ""
    paths = canonical_run_artifact_paths(run_id, day=_resolve_day(state), reports_root=_reports_root(state))
    path = _write_artifact_once(state, agent="strategist", path=paths["strategist"], payload=build_strategist_output_artifact(state))
    return path


def write_scanner_artifact(state: Dict[str, Any]) -> str:
    run_id = str(state.get("run_id") or "").strip()
    if not run_id:
        return ""
    paths = canonical_run_artifact_paths(run_id, day=_resolve_day(state), reports_root=_reports_root(state))
    path = _write_artifact_once(state, agent="scanner", path=paths["scanner"], payload=build_scanner_output_artifact(state))
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


def write_executor_artifact(state: Dict[str, Any], *, execution: Dict[str, Any], order: Dict[str, Any] | None = None) -> str:
    run_id = str(state.get("run_id") or "").strip()
    if not run_id:
        return ""
    paths = canonical_run_artifact_paths(run_id, day=_resolve_day(state), reports_root=_reports_root(state))
    payload = build_executor_output_artifact(state, execution=dict(execution or {}), order=dict(order or {}))
    path = _write_artifact_once(state, agent="executor", path=paths["executor"], payload=payload)
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
