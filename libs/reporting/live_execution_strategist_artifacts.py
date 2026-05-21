from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from libs.reporting.llm_artifacts import build_compact_input_artifact, split_prompt_text
from libs.reporting.live_execution_report_artifacts import read_json_if_exists
from libs.reporting.trade_story_pipeline import safe_int, utc_now_iso


def _safe_float(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except Exception:
        return default


def _to_epoch(ts: Any) -> Optional[int]:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return int(ts)
    raw = str(ts).strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except Exception:
        pass
    stamped = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        dt = datetime.fromisoformat(stamped)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def latest_strategist_evidence_ledger_row(
    evidence_rows: List[Dict[str, Any]],
    strategist_run_ids: List[str],
) -> Dict[str, Any]:
    run_set = {str(item or "").strip() for item in list(strategist_run_ids or []) if str(item or "").strip()}
    candidates: List[Dict[str, Any]] = []
    for row in list(evidence_rows or []):
        if run_set and str(row.get("run_id") or "").strip() not in run_set:
            continue
        if str(row.get("agent") or "").strip().lower() != "strategist":
            continue
        if str(row.get("stage") or "").strip() not in {"theme_selection", "theme_selection_repair"}:
            continue
        if not any(
            (
                bool(str(row.get("llm_prompt") or "").strip()),
                bool(str(row.get("llm_response") or "").strip()),
                isinstance(row.get("parsed_output"), dict) and bool(row.get("parsed_output")),
            )
        ):
            continue
        candidates.append(row)
    if not candidates:
        return {}
    candidates.sort(key=lambda item: _to_epoch(item.get("timestamp") or item.get("ts")) or 0)
    return dict(candidates[-1])


def latest_strategist_input_collection_row(
    evidence_rows: List[Dict[str, Any]],
    strategist_run_ids: List[str],
) -> Dict[str, Any]:
    run_set = {str(item or "").strip() for item in list(strategist_run_ids or []) if str(item or "").strip()}
    candidates: List[Dict[str, Any]] = []
    for row in list(evidence_rows or []):
        if run_set and str(row.get("run_id") or "").strip() not in run_set:
            continue
        if str(row.get("agent") or "").strip().lower() != "strategist":
            continue
        raw_input = row.get("raw_input")
        if not isinstance(raw_input, dict) or not raw_input:
            continue
        if str(row.get("stage") or "").strip() != "theme_selection":
            continue
        decision_link = row.get("decision_link") if isinstance(row.get("decision_link"), dict) else {}
        if str(decision_link.get("stage") or "").strip() != "strategist_input_collection" and "llm_payload" not in raw_input:
            continue
        candidates.append(row)
    if not candidates:
        return {}
    candidates.sort(key=lambda item: _to_epoch(item.get("timestamp") or item.get("ts")) or 0)
    return dict(candidates[-1])


def latest_strategist_prompt_input_row(
    evidence_rows: List[Dict[str, Any]],
    strategist_run_ids: List[str],
) -> Dict[str, Any]:
    run_set = {str(item or "").strip() for item in list(strategist_run_ids or []) if str(item or "").strip()}
    candidates: List[Dict[str, Any]] = []
    for row in list(evidence_rows or []):
        if run_set and str(row.get("run_id") or "").strip() not in run_set:
            continue
        if str(row.get("agent") or "").strip().lower() != "strategist":
            continue
        if str(row.get("stage") or "").strip() != "theme_selection":
            continue
        if not isinstance(row.get("raw_input"), dict) or not dict(row.get("raw_input") or {}):
            continue
        if not str(row.get("llm_prompt") or "").strip():
            continue
        candidates.append(row)
    if not candidates:
        return {}
    candidates.sort(key=lambda item: _to_epoch(item.get("timestamp") or item.get("ts")) or 0)
    return dict(candidates[-1])


def flatten_news_titles(sample: Any, *, max_groups: int = 10, max_titles_per_group: int = 2) -> List[str]:
    out: List[str] = []
    if not isinstance(sample, dict):
        return out

    def _extract_title(row: Any) -> str:
        if isinstance(row, dict):
            return html.unescape(str(row.get("title") or "").strip())
        text = str(row or "").strip()
        if not text:
            return ""
        for pattern in (r"title='([^']+)'", r'title="([^"]+)"'):
            match = re.search(pattern, text)
            if match:
                return html.unescape(str(match.group(1) or "").strip())
        return html.unescape(text[:160])

    for symbol, rows in list(sample.items())[:max_groups]:
        items = rows
        if isinstance(rows, dict):
            items = rows.get("sample")
        if not isinstance(items, list):
            continue
        for row in items[:max_titles_per_group]:
            title = _extract_title(row)
            if not title:
                continue
            out.append(f"{symbol}: {title}")
    return out


def build_strategist_input_summary(
    source_input: Dict[str, Any],
    compact_input: Dict[str, Any],
) -> Dict[str, Any]:
    src = source_input if isinstance(source_input, dict) else {}
    compact = compact_input if isinstance(compact_input, dict) else {}
    global_signal = src.get("global_sentiment_signal") if isinstance(src.get("global_sentiment_signal"), dict) else {}
    if not global_signal and isinstance(compact.get("global_sentiment_signal"), dict):
        global_signal = dict(compact.get("global_sentiment_signal") or {})
    news_ctx = src.get("news_context") if isinstance(src.get("news_context"), dict) else {}
    if not news_ctx and isinstance(compact.get("news_context"), dict):
        news_ctx = dict(compact.get("news_context") or {})
    macro_moves = global_signal.get("macro_moves") if isinstance(global_signal.get("macro_moves"), dict) else {}
    fear_index = global_signal.get("fear_index") if isinstance(global_signal.get("fear_index"), dict) else {}
    korea_indices = global_signal.get("korea_indices") if isinstance(global_signal.get("korea_indices"), dict) else {}
    macro_stress = src.get("macro_stress_overlay_hint") if isinstance(src.get("macro_stress_overlay_hint"), dict) else {}
    if not macro_stress and isinstance(compact.get("macro_stress_overlay_hint"), dict):
        macro_stress = dict(compact.get("macro_stress_overlay_hint") or {})
    market_news_sample = src.get("market_news_sample") if isinstance(src.get("market_news_sample"), dict) else {}
    candidate_news_sample = src.get("candidate_news_sample") if isinstance(src.get("candidate_news_sample"), dict) else {}
    if not market_news_sample and isinstance(compact.get("market_news_sample"), dict):
        market_news_sample = dict(compact.get("market_news_sample") or {})
    if not candidate_news_sample and isinstance(compact.get("candidate_news_sample"), dict):
        candidate_news_sample = dict(compact.get("candidate_news_sample") or {})
    market_regime_hint = str(src.get("market_regime_hint") or compact.get("market_regime_hint") or "").strip()
    market_sentiment_hint = str(src.get("market_sentiment_hint") or compact.get("market_sentiment_hint") or "").strip()
    playbook_hint = str(src.get("playbook_hint") or compact.get("playbook_hint") or "").strip()
    return {
        "market_regime_hint": market_regime_hint,
        "market_sentiment_hint": market_sentiment_hint,
        "playbook_hint": playbook_hint,
        "global_sentiment_score": _safe_float(global_signal.get("score"), None),
        "vix_level": _safe_float(fear_index.get("level"), _safe_float(macro_moves.get("vix_level"), None)),
        "vix_change_pct": _safe_float(fear_index.get("change_pct"), _safe_float(macro_moves.get("vix_pct"), None)),
        "vix_level_pressure": _safe_float(fear_index.get("level_pressure"), _safe_float(macro_moves.get("vix_level_pressure"), None)),
        "korea_indices": dict(korea_indices or {}),
        "headline_count": safe_int(news_ctx.get("headline_count"), 0),
        "candidate_signal_total": safe_int(news_ctx.get("candidate_signal_total"), 0),
        "market_signal_total": safe_int(news_ctx.get("market_signal_total"), 0),
        "news_query_targets": [str(x or "") for x in list(src.get("news_query_targets") or compact.get("news_query_targets") or []) if str(x or "").strip()][:8],
        "candidate_symbols_hint": [str(x or "") for x in list(src.get("candidate_symbols_hint") or compact.get("candidate_symbols_hint") or []) if str(x or "").strip()][:6],
        "themes_hint": [str(x or "") for x in list(src.get("themes_hint") or compact.get("themes_hint") or []) if str(x or "").strip()][:6],
        "key_events_hint": [str(x or "") for x in list(src.get("key_events_hint") or compact.get("key_events_hint") or []) if str(x or "").strip()][:6],
        "macro_stress_active": bool(macro_stress.get("active")),
        "macro_stress_flags": [str(x or "") for x in list(macro_stress.get("stress_flags") or []) if str(x or "").strip()][:6],
        "market_news_titles": flatten_news_titles(market_news_sample),
        "candidate_news_titles": flatten_news_titles(candidate_news_sample),
    }


def enrich_strategist_from_input_summary(
    strategist_payload: Dict[str, Any],
    strategist_input_artifact: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(strategist_payload or {})
    summary = strategist_input_artifact.get("summary") if isinstance(strategist_input_artifact.get("summary"), dict) else {}
    if not summary:
        return out
    out["input_summary"] = dict(summary)
    if not str(out.get("market_regime") or "").strip():
        out["market_regime"] = str(summary.get("market_regime_hint") or "").strip()
    if not str(out.get("market_sentiment") or "").strip():
        out["market_sentiment"] = str(summary.get("market_sentiment_hint") or "").strip()
    if not str(out.get("playbook") or "").strip():
        out["playbook"] = str(summary.get("playbook_hint") or "").strip()
    if not list(out.get("themes") or []):
        out["themes"] = [
            str(x or "")
            for x in list(summary.get("themes_hint") or [])
            if str(x or "").strip()
        ]
    if out.get("global_sentiment_score") in (None, ""):
        out["global_sentiment_score"] = summary.get("global_sentiment_score")

    fear_index = out.get("fear_index") if isinstance(out.get("fear_index"), dict) else {}
    if not fear_index and summary.get("vix_level") not in (None, ""):
        fear_index = {
            "level": summary.get("vix_level"),
            "change_pct": summary.get("vix_change_pct"),
            "level_pressure": summary.get("vix_level_pressure"),
        }
    out["fear_index"] = dict(fear_index or {})
    if not isinstance(out.get("korea_indices"), dict) or not out.get("korea_indices"):
        if isinstance(summary.get("korea_indices"), dict):
            out["korea_indices"] = dict(summary.get("korea_indices") or {})

    macro_moves = out.get("global_macro_moves") if isinstance(out.get("global_macro_moves"), dict) else {}
    if summary.get("vix_level") not in (None, "") and macro_moves.get("vix_level") in (None, ""):
        macro_moves["vix_level"] = summary.get("vix_level")
    if summary.get("vix_change_pct") not in (None, "") and macro_moves.get("vix_pct") in (None, ""):
        macro_moves["vix_pct"] = summary.get("vix_change_pct")
    if summary.get("vix_level_pressure") not in (None, "") and macro_moves.get("vix_level_pressure") in (None, ""):
        macro_moves["vix_level_pressure"] = summary.get("vix_level_pressure")
    out["global_macro_moves"] = dict(macro_moves or {})

    news_context = out.get("news_context") if isinstance(out.get("news_context"), dict) else {}
    if summary.get("headline_count") not in (None, "") and news_context.get("headline_count") in (None, ""):
        news_context["headline_count"] = summary.get("headline_count")
    if summary.get("candidate_signal_total") not in (None, "") and news_context.get("candidate_signal_total") in (None, ""):
        news_context["candidate_signal_total"] = summary.get("candidate_signal_total")
    if summary.get("market_signal_total") not in (None, "") and news_context.get("market_signal_total") in (None, ""):
        news_context["market_signal_total"] = summary.get("market_signal_total")
    out["news_context"] = dict(news_context or {})

    if safe_int(out.get("market_news_total_headlines"), 0) <= 0:
        out["market_news_total_headlines"] = safe_int(summary.get("headline_count"), 0)
    if safe_int(out.get("market_news_query_count"), 0) <= 0:
        out["market_news_query_count"] = len(list(summary.get("news_query_targets") or []))
    if not list(out.get("news_query_targets") or []):
        out["news_query_targets"] = [str(x or "") for x in list(summary.get("news_query_targets") or []) if str(x or "").strip()]
    return out


def build_strategist_input_artifacts(
    bundle_out: Dict[str, Any],
    *,
    day: str,
    trade_id: str,
    reports_root: Path | None = None,
    strategist_evidence: Dict[str, Any] | None = None,
    evidence_rows: List[Dict[str, Any]] | None = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    strategist = bundle_out.get("strategist") if isinstance(bundle_out.get("strategist"), dict) else {}
    strategist_evidence = strategist_evidence if isinstance(strategist_evidence, dict) else {}
    strategist_run_ids = list(strategist_evidence.get("run_ids") or [])
    input_row = latest_strategist_input_collection_row(list(evidence_rows or []), strategist_run_ids)
    prompt_row = latest_strategist_prompt_input_row(list(evidence_rows or []), strategist_run_ids)

    source_input: Dict[str, Any] = {}
    raw_input = input_row.get("raw_input") if isinstance(input_row.get("raw_input"), dict) else {}
    if isinstance(raw_input.get("llm_payload"), dict) and dict(raw_input.get("llm_payload") or {}):
        source_input = dict(raw_input.get("llm_payload") or {})
    elif raw_input:
        source_input = dict(raw_input)

    compact_input = prompt_row.get("raw_input") if isinstance(prompt_row.get("raw_input"), dict) else {}
    if not compact_input and isinstance(strategist.get("llm_payload"), dict):
        compact_input = dict(strategist.get("llm_payload") or {})
    if not source_input and isinstance(strategist.get("llm_payload"), dict):
        source_input = dict(strategist.get("llm_payload") or {})
    if not source_input and compact_input:
        source_input = dict(compact_input)

    prompt_text = str(prompt_row.get("llm_prompt") or "")
    system_prompt, user_prompt = split_prompt_text(prompt_text)
    source_run_id = str(
        prompt_row.get("run_id")
        or input_row.get("run_id")
        or (strategist_run_ids[0] if strategist_run_ids else "")
        or bundle_out.get("run_id")
        or ""
    ).strip()

    source_stage = str(prompt_row.get("stage") or input_row.get("stage") or "").strip()
    if not source_input and not compact_input and reports_root is not None and source_run_id:
        prompt_artifact = read_json_if_exists(
            Path(reports_root) / "llm" / str(day or "") / str(source_run_id) / "strategist" / "prompt.json"
        )
        prompt_payload = {}
        if isinstance(prompt_artifact, dict):
            prompt_payload = (
                prompt_artifact.get("payload")
                if isinstance(prompt_artifact.get("payload"), dict)
                else prompt_artifact.get("user_payload")
                if isinstance(prompt_artifact.get("user_payload"), dict)
                else {}
            )
            if prompt_payload:
                source_input = dict(prompt_payload)
                compact_input = dict(prompt_payload)
                source_stage = str(prompt_artifact.get("stage") or source_stage or "").strip()
    reconstructed = bool(source_input or compact_input or system_prompt or user_prompt)
    input_artifact = {
        "schema_version": "strategist_input_artifact.v1",
        "component": "strategist",
        "role": "strategist",
        "run_id": str(bundle_out.get("run_id") or ""),
        "trade_id": str(trade_id or ""),
        "story_id": str(trade_id or ""),
        "day": str(day or ""),
        "saved_at": utc_now_iso(),
        "status": "ok" if bool(source_input or compact_input) else "placeholder",
        "summary": build_strategist_input_summary(source_input, compact_input),
        "source_input": source_input if isinstance(source_input, dict) else {},
        "meta": {
            "source_run_id": source_run_id,
            "source_stage": source_stage,
            "reconstructed_from_evidence_ledger": reconstructed,
            "system_prompt_available": bool(system_prompt),
            "user_prompt_available": bool(user_prompt),
        },
    }
    if system_prompt:
        input_artifact["system_prompt"] = system_prompt
    if user_prompt:
        input_artifact["user_prompt"] = user_prompt

    compact_artifact = build_compact_input_artifact(
        component="strategist",
        run_id=str(bundle_out.get("run_id") or ""),
        trade_id=trade_id,
        story_id=trade_id,
        day=day,
        source_artifact_path="",
        source_input=source_input if isinstance(source_input, dict) else {},
        compact_input=compact_input if isinstance(compact_input, dict) else {},
    )
    compact_artifact["meta"] = {
        "source_run_id": source_run_id,
        "source_stage": source_stage,
        "reconstructed_from_evidence_ledger": reconstructed,
    }
    return input_artifact, compact_artifact
