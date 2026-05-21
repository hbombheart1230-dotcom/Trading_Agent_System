from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set, Tuple

from libs.core.symbols import normalize_symbol
from libs.reporting.live_execution_open_monitor import safe_float
from libs.reporting.live_execution_report_context import to_epoch
from libs.reporting.trade_story_pipeline import safe_int


def row_event_name(row: Dict[str, Any]) -> str:
    text = str(row.get("event_name") or "").strip()
    if text:
        return text
    stage = str(row.get("stage") or "").strip()
    event = str(row.get("event") or "").strip()
    return ".".join(part for part in (stage, event) if part)


def event_row_symbol(row: Dict[str, Any]) -> str:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    return normalize_symbol(
        row.get("symbol")
        or payload.get("symbol")
        or payload.get("selected_symbol")
        or payload.get("position_symbol")
        or "",
        allow_test_symbols=True,
    )


def event_row_name(row: Dict[str, Any]) -> str:
    return str(row.get("event_name") or row.get("name") or row.get("event") or "").strip()


def merge_rows_by_identity(*collections: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for rows in collections:
        for row in list(rows or []):
            if not isinstance(row, dict):
                continue
            key = (
                str(row.get("ts") or row.get("timestamp") or ""),
                str(row.get("run_id") or ""),
                event_row_name(row),
                event_row_symbol(row),
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
    return out


def filter_canonical_events(
    rows: List[Dict[str, Any]],
    *,
    run_ids: List[str],
    agent: str,
    event_names: List[str],
) -> List[Dict[str, Any]]:
    run_set = {str(item or "").strip() for item in list(run_ids or []) if str(item or "").strip()}
    names = {str(item or "").strip() for item in list(event_names or []) if str(item or "").strip()}
    out: List[Dict[str, Any]] = []
    for row in rows:
        if run_set and str(row.get("run_id") or "").strip() not in run_set:
            continue
        row_agent = str(row.get("agent") or row.get("stage") or "").strip().lower()
        if row_agent != str(agent or "").strip().lower():
            continue
        if names and row_event_name(row) not in names:
            continue
        out.append(
            {
                "ts": str(row.get("ts") or ""),
                "event_name": row_event_name(row),
                "level": str(row.get("level") or "info"),
                "run_id": str(row.get("run_id") or ""),
                "trade_id": str(row.get("trade_id") or ""),
                "session_id": str(row.get("session_id") or ""),
                "cycle_id": str(row.get("cycle_id") or ""),
                "agent": str(row.get("agent") or row.get("stage") or ""),
                "phase": str(row.get("phase") or ""),
                "symbol": str(row.get("symbol") or ""),
                "payload": dict(row.get("payload") or {}) if isinstance(row.get("payload"), dict) else {},
            }
        )
    out.sort(key=lambda item: to_epoch(item.get("ts")) or 0)
    return out


def resolve_strategist_source_run_ids(
    *,
    event_rows: List[Dict[str, Any]],
    lifecycle: Dict[str, Any],
) -> Tuple[List[str], Dict[str, str]]:
    lifecycle_run_ids = [str(x or "").strip() for x in list(lifecycle.get("run_ids_all") or []) if str(x or "").strip()]
    if not lifecycle_run_ids:
        return [], {}

    strategist_event_names = {
        "strategist.market_context_snapshot",
        "strategist.global_sentiment_breakdown",
        "strategist.news_evidence_ranked",
        "strategist.decision_frame",
        "strategist.llm_response_saved",
    }
    strategist_run_ids = {
        str(row.get("run_id") or "").strip()
        for row in event_rows
        if str(row.get("run_id") or "").strip() in set(lifecycle_run_ids)
        and str(row.get("agent") or row.get("stage") or "").strip().lower() == "strategist"
        and row_event_name(row) in strategist_event_names
    }

    strategist_frame_rows = [
        row
        for row in event_rows
        if str(row.get("agent") or row.get("stage") or "").strip().lower() == "strategist"
        and row_event_name(row) == "strategist.decision_frame"
    ]
    strategist_frame_rows.sort(key=lambda row: to_epoch(row.get("ts")) or 0)

    linked_cached_frames: Dict[str, str] = {}
    for run_id in lifecycle_run_ids:
        if run_id in strategist_run_ids:
            continue
        fast_path_rows = [
            row
            for row in event_rows
            if str(row.get("run_id") or "").strip() == run_id
            and row_event_name(row) == "commander_router.fast_path"
        ]
        if not fast_path_rows:
            continue
        fast_path = fast_path_rows[-1]
        payload = fast_path.get("payload") if isinstance(fast_path.get("payload"), dict) else {}
        if str(payload.get("path") or "").strip() != "integrated_chain_cached_frame":
            continue
        target_ts = to_epoch(fast_path.get("ts")) or 0
        reuse_sec = max(30, safe_int(payload.get("reuse_sec"), 180))
        candidate_rows = [
            row
            for row in strategist_frame_rows
            if str(row.get("run_id") or "").strip() != run_id
            and (to_epoch(row.get("ts")) or 0) <= target_ts
            and target_ts - (to_epoch(row.get("ts")) or 0) <= reuse_sec + 30
        ]
        if not candidate_rows:
            continue
        source_run_id = str(candidate_rows[-1].get("run_id") or "").strip()
        if not source_run_id:
            continue
        strategist_run_ids.add(source_run_id)
        linked_cached_frames[run_id] = source_run_id

    return sorted(strategist_run_ids), linked_cached_frames


def expand_targeted_run_ids_with_cached_strategist_sources(
    *,
    event_rows: List[Dict[str, Any]],
    targeted_run_ids: Iterable[str],
) -> Set[str]:
    out: Set[str] = {
        str(run_id or "").strip()
        for run_id in list(targeted_run_ids or [])
        if str(run_id or "").strip()
    }
    if not out:
        return out

    strategist_frame_rows = [
        row
        for row in list(event_rows or [])
        if str(row.get("agent") or row.get("stage") or "").strip().lower() == "strategist"
        and row_event_name(row) == "strategist.decision_frame"
    ]
    strategist_frame_rows.sort(key=lambda row: to_epoch(row.get("ts")) or 0)
    if not strategist_frame_rows:
        return out

    fast_path_rows = [
        row
        for row in list(event_rows or [])
        if str(row.get("run_id") or "").strip() in out
        and row_event_name(row) == "commander_router.fast_path"
    ]
    for fast_path in fast_path_rows:
        payload = fast_path.get("payload") if isinstance(fast_path.get("payload"), dict) else {}
        if str(payload.get("path") or "").strip() != "integrated_chain_cached_frame":
            continue
        target_run_id = str(fast_path.get("run_id") or "").strip()
        target_ts = to_epoch(fast_path.get("ts")) or 0
        reuse_sec = max(30, safe_int(payload.get("reuse_sec"), 180))
        candidate_rows = [
            row
            for row in strategist_frame_rows
            if str(row.get("run_id") or "").strip() != target_run_id
            and (to_epoch(row.get("ts")) or 0) <= target_ts
            and target_ts - (to_epoch(row.get("ts")) or 0) <= reuse_sec + 30
        ]
        if not candidate_rows:
            continue
        source_run_id = str(candidate_rows[-1].get("run_id") or "").strip()
        if source_run_id:
            out.add(source_run_id)
    return out


def latest_event_payload(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {}
    payload = rows[-1].get("payload") if isinstance(rows[-1], dict) else {}
    return dict(payload or {}) if isinstance(payload, dict) else {}


def headline_count(news_rows: List[Dict[str, Any]]) -> int:
    total = 0
    for row in list(news_rows or []):
        if not isinstance(row, dict):
            continue
        total += safe_int(row.get("headline_count"), 0)
    return total


def hydrate_strategist_payload_from_evidence(
    strategist_payload: Dict[str, Any],
    strategist_evidence: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(strategist_payload or {})
    snapshot = latest_event_payload(list(strategist_evidence.get("market_context_snapshots") or []))
    decision_frame = latest_event_payload(list(strategist_evidence.get("decision_frames") or []))
    news_ranked = latest_event_payload(list(strategist_evidence.get("news_evidence_ranked") or []))
    llm_saved = latest_event_payload(list(strategist_evidence.get("llm_response_saved") or []))

    global_signal = snapshot.get("global_signal") if isinstance(snapshot.get("global_signal"), dict) else {}
    if not isinstance(out.get("llm_parsed_output"), dict) or not out.get("llm_parsed_output"):
        out["llm_parsed_output"] = dict(decision_frame or {})
    if not str(out.get("market_regime") or "").strip():
        out["market_regime"] = str(decision_frame.get("market_regime") or "")
    if not str(out.get("market_sentiment") or "").strip():
        out["market_sentiment"] = str(decision_frame.get("market_sentiment") or "")
    if not str(out.get("playbook") or "").strip():
        out["playbook"] = str(decision_frame.get("playbook") or "")
    if not list(out.get("themes") or []):
        out["themes"] = [str(x or "") for x in list(decision_frame.get("themes") or []) if str(x or "").strip()]
    existing_global_score = out.get("global_sentiment_score")
    existing_global_status = str(out.get("global_sentiment_status") or "").strip()
    if existing_global_score in (None, "") or (
        safe_float(existing_global_score, None) == 0.0
        and not existing_global_status
        and isinstance(global_signal, dict)
        and global_signal.get("score") not in (None, "")
    ):
        out["global_sentiment_score"] = global_signal.get("score")
    if not str(out.get("global_sentiment_status") or "").strip():
        out["global_sentiment_status"] = str(global_signal.get("status") or "")
    if not str(out.get("global_sentiment_source") or "").strip():
        out["global_sentiment_source"] = str(global_signal.get("source") or "")
    if not isinstance(out.get("fear_index"), dict) or not out.get("fear_index"):
        out["fear_index"] = dict(global_signal.get("fear_index") or {})
    if not isinstance(out.get("global_macro_moves"), dict) or not out.get("global_macro_moves"):
        out["global_macro_moves"] = dict(global_signal.get("macro_moves") or {})
    if not isinstance(out.get("macro_stress_overlay"), dict) or not out.get("macro_stress_overlay"):
        out["macro_stress_overlay"] = dict(snapshot.get("macro_stress_overlay") or {})
    if not str(out.get("news_query_reasoning") or "").strip():
        reasons = list(decision_frame.get("reason_chain") or [])
        out["news_query_reasoning"] = str(reasons[-1] or "") if reasons else ""
    if not list(out.get("news_query_targets") or []):
        out["news_query_targets"] = [str(x or "") for x in list(news_ranked.get("news_query_targets") or []) if str(x or "").strip()]
    if safe_int(out.get("market_news_query_count"), 0) <= 0:
        out["market_news_query_count"] = len(list(news_ranked.get("news_query_targets") or []))
    if safe_int(out.get("market_news_total_headlines"), 0) <= 0:
        ranked_rows = list(news_ranked.get("market_news_ranked") or []) + list(news_ranked.get("candidate_news_ranked") or [])
        out["market_news_total_headlines"] = headline_count(ranked_rows)
    if not str(out.get("llm_provider") or "").strip():
        out["llm_provider"] = str(llm_saved.get("provider") or "OpenRouter")
    if not str(out.get("llm_model") or "").strip():
        out["llm_model"] = str(llm_saved.get("model") or "")
    return out
