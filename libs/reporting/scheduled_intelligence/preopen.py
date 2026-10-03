from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .artifacts import freshness_seconds, now_iso, read_object, relative_path, write_json, write_text


def materialize_preopen_intelligence(
    *,
    day: str,
    capture_rc: int,
    session_rc: int,
    reports_root: Path = Path("reports"),
) -> dict[str, Any]:
    normalized_day = str(day)[:10]
    root = Path(reports_root)
    strategist_path = _find_preopen_strategist(root, normalized_day)
    strategist = read_object(strategist_path) if strategist_path else {}
    memory = strategist.get("strategy_memory_snapshot") if isinstance(strategist.get("strategy_memory_snapshot"), dict) else {}
    visibility = strategist.get("memory_packet_visibility") if isinstance(strategist.get("memory_packet_visibility"), dict) else {}
    memory_visibility = visibility.get("strategy_memory") if isinstance(visibility.get("strategy_memory"), dict) else {}
    llm = strategist.get("llm_metadata_summary") if isinstance(strategist.get("llm_metadata_summary"), dict) else {}
    thesis = strategist.get("strategy_thesis") if isinstance(strategist.get("strategy_thesis"), dict) else {}
    trace = strategist.get("trace_summary") if isinstance(strategist.get("trace_summary"), dict) else {}
    materialized_at = now_iso()
    execution_completed_at = str(strategist.get("ts") or materialized_at)

    capture_status = "SUCCESS" if int(capture_rc) == 0 else "FAILED"
    strategist_status = "SUCCESS" if int(session_rc) == 0 and strategist else "FAILED" if int(session_rc) else "MISSING_ARTIFACT"
    overall = "SUCCESS" if capture_status == strategist_status == "SUCCESS" else "PARTIAL" if strategist_status == "SUCCESS" else "FAILED"
    packet_receipts = {
        layer: _packet_receipt(visibility, layer)
        for layer in ("daily", "weekly", "monthly")
    }
    memory_present = bool(memory_visibility.get("present"))
    active_layers = [layer for layer, row in packet_receipts.items() if row.get("active")]
    commander_memory = visibility.get("commander_memory_policy") if isinstance(visibility.get("commander_memory_policy"), dict) else {}
    delivery_status = (
        "DELIVERED_ACTIVE" if memory_present and active_layers
        else "DELIVERED_ADVISORY" if memory_present
        else "NOT_CONFIRMED"
    )
    memory_receipt = {
        "schema_version": "memory_delivery_receipt.v1",
        "day": normalized_day,
        "generated_at": materialized_at,
        "delivery_observed_at": execution_completed_at,
        "status": delivery_status,
        "source_day": str(memory_visibility.get("resolved_day") or memory.get("day") or ""),
        "source_artifact": str(memory.get("artifact_path") or ""),
        "strategy_memory_status": str(memory_visibility.get("status") or memory.get("status") or ""),
        "daily_packet": packet_receipts["daily"],
        "weekly_packet": packet_receipts["weekly"],
        "monthly_packet": packet_receipts["monthly"],
        "strategist_input_present": memory_present,
        "application_mode": str(commander_memory.get("application_mode") or ""),
        "active_layers": active_layers,
        "advisory_only": bool(memory.get("advisory_only", True)),
    }
    briefing = {
        "schema_version": "preopen_briefing.v1",
        "day": normalized_day,
        "generated_at": materialized_at,
        "source_as_of": execution_completed_at,
        "status": overall,
        "market_snapshot": {"status": capture_status, "return_code": int(capture_rc)},
        "strategist": {
            "status": strategist_status,
            "return_code": int(session_rc),
            "artifact": relative_path(strategist_path, root.parent) if strategist_path else "",
            "artifact_freshness_seconds": freshness_seconds(strategist.get("ts")),
            "llm_status": str(llm.get("status") or ""),
            "model": str(llm.get("model") or ""),
        },
        "market_frame": {
            "regime": str(strategist.get("market_regime") or ""),
            "sentiment": str(strategist.get("market_sentiment") or ""),
            "playbook": str(strategist.get("final_playbook") or strategist.get("playbook") or ""),
            "tactical_strategy": str(strategist.get("tactical_strategy") or ""),
            "tactical_subtype": str(strategist.get("tactical_subtype") or ""),
            "risk_tone": str(thesis.get("risk_tone") or ""),
            "trade_style": str(thesis.get("trade_style") or ""),
            "one_line": str(thesis.get("one_line") or ""),
        },
        "themes": list(strategist.get("themes") or [])[:8],
        "avoid_themes": list(strategist.get("avoid_themes") or [])[:8],
        "highlights": list(trace.get("highlights") or [])[:8],
        "entry_frame": dict(strategist.get("trade_permission_frame") or {}),
        "memory_delivery": memory_receipt,
        "data_quality_warnings": list((trace.get("missing_flags") or []))[:12],
        "issues": _preopen_issues(capture_status, strategist_status, memory_receipt),
    }
    out_dir = root / "briefings" / normalized_day
    receipt_path = write_json(out_dir / "memory_delivery_receipt.json", memory_receipt)
    json_path = write_json(out_dir / "preopen_briefing.json", briefing)
    md_path = write_text(out_dir / "preopen_briefing.md", _preopen_markdown(briefing))
    manifest = {
        "schema_version": "scheduled_job_manifest.v1",
        "day": normalized_day,
        "job": "preopen",
        "generated_at": execution_completed_at,
        "materialized_at": materialized_at,
        "status": overall,
        "steps": {
            "market_snapshot": briefing["market_snapshot"],
            "strategist": briefing["strategist"],
            "memory_delivery": {"status": memory_receipt["status"], "source_day": memory_receipt["source_day"]},
            "briefing": {"status": "SUCCESS", "json": relative_path(json_path, root.parent), "markdown": relative_path(md_path, root.parent)},
        },
        "issues": briefing["issues"],
    }
    manifest_path = write_json(root / "runtime" / "scheduled_jobs" / normalized_day / "preopen.json", manifest)
    write_json(root / "runtime" / "scheduled_jobs" / "latest_preopen.json", manifest)
    return {
        "status": overall,
        "manifest_path": str(manifest_path),
        "briefing_json_path": str(json_path),
        "briefing_md_path": str(md_path),
        "memory_receipt_path": str(receipt_path),
    }


def _find_preopen_strategist(reports_root: Path, day: str) -> Path | None:
    target = date.fromisoformat(day)
    candidates = []
    for offset in (0, -1):
        path = reports_root / "canonical" / (target + timedelta(days=offset)).isoformat() / "run-session-live-preopen" / "strategist.json"
        if path.is_file():
            candidates.append(path)
    same_day = [path for path in candidates if str(read_object(path).get("day") or "")[:10] == day]
    pool = same_day or candidates
    return max(pool, key=lambda path: path.stat().st_mtime) if pool else None


def _packet_receipt(visibility: dict[str, Any], layer: str) -> dict[str, Any]:
    packets = visibility.get("memory_packets") if isinstance(visibility.get("memory_packets"), dict) else {}
    row = packets.get(layer) if isinstance(packets.get(layer), dict) else {}
    return {"status": str(row.get("status") or ""), "active": bool(row.get("active")), "resolved_day": str(row.get("resolved_day") or "")}


def _preopen_issues(capture_status: str, strategist_status: str, receipt: dict[str, Any]) -> list[str]:
    issues = []
    if capture_status != "SUCCESS": issues.append("PREOPEN_MARKET_SNAPSHOT_FAILED")
    if strategist_status != "SUCCESS": issues.append("PREOPEN_STRATEGIST_ARTIFACT_UNAVAILABLE")
    if receipt.get("status") == "NOT_CONFIRMED": issues.append("STRATEGY_MEMORY_DELIVERY_NOT_CONFIRMED")
    return issues


def _preopen_markdown(payload: dict[str, Any]) -> str:
    frame = payload["market_frame"]
    memory = payload["memory_delivery"]
    lines = [
        f"# 장전 시장 브리핑 - {payload['day']}", "",
        f"- 상태: **{payload['status']}**",
        f"- 시장: `{frame['regime']}` / 심리 `{frame['sentiment']}` / 위험 `{frame['risk_tone']}`",
        f"- 전략: `{frame['playbook']}` / `{frame['tactical_strategy']}` / `{frame['tactical_subtype']}`",
        f"- 요약: {frame['one_line'] or '-'}", "",
        "## 테마", "",
        f"- 선호: {', '.join(payload['themes']) or '-'}",
        f"- 회피: {', '.join(payload['avoid_themes']) or '-'}", "",
        "## 메모리 전달", "",
        f"- 상태: `{memory['status']}`",
        f"- 원본 거래일: `{memory['source_day'] or '-'}`",
        f"- 전략가 입력 포함: `{memory['strategist_input_present']}`", "",
        f"- 적용 모드: `{memory['application_mode'] or '-'}` / 활성 레이어: `{', '.join(memory['active_layers']) or 'none'}`", "",
        "## 근거", "",
    ]
    lines.extend(f"- {row}" for row in payload["highlights"])
    if payload["issues"]:
        lines += ["", "## 점검 필요", ""] + [f"- `{row}`" for row in payload["issues"]]
    if payload["data_quality_warnings"]:
        lines += ["", "## 데이터 품질 경고", ""] + [f"- `{row}`" for row in payload["data_quality_warnings"]]
    return "\n".join(lines)
