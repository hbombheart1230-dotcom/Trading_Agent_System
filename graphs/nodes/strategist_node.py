from __future__ import annotations

"""Canonical Strategist node for integrated runtime.

Role boundary:
- owns strategic framing (themes/sectors, sentiment context, candidate hints)
- prepares strategist outputs for scanner/monitor handoff
- does not execute orders
"""

import os
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from libs.data_quality.signal_contract import SIGNAL_STATUS_FALLBACK, make_signal
from libs.llm.llm_router import LLMRouter
from libs.market.global_sentiment import compute_global_sentiment_signal
from libs.news.news_pipeline import collect_news_items, score_news_sentiment_signal
from libs.research.evidence_ledger import (
    record_decision_bridge,
    record_llm_prompt,
    record_llm_response,
    record_raw_input,
)
from libs.runtime.decision_trace import append_decision_trace
from libs.runtime.regime import classify_regime_v2
from libs.strategies.candidates.fallback_pool import resolve_fallback_symbols
from libs.strategies.contracts import StrategistOutput, coerce_strategist_output
from libs.strategies.candidates.market_rank import MarketRankCandidateGenerator
from libs.strategies.candidates.market_rank import TopPicksCandidateGenerator
from libs.strategies.universe_builder import build_candidate_universe


def _is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "1" if default else "0") or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in ("1", "true", "yes", "y", "on")


def _to_int(v: Any, default: int) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _env_int(key: str) -> int | None:
    raw = os.getenv(key)
    if raw in (None, ""):
        return None
    try:
        return int(float(str(raw).strip()))
    except Exception:
        return None


def _resolve_top_n_candidates(policy: Dict[str, Any]) -> int:
    raw = (
        policy.get("candidate_k")
        if policy.get("candidate_k") is not None
        else policy.get("candidate_topk")
    )
    if raw is not None:
        return max(1, _to_int(raw, 10))

    env_topn = _env_int("TOP_N_CANDIDATES")
    if isinstance(env_topn, int) and env_topn > 0:
        return max(1, env_topn)
    # Keep strategist candidate-hint contract stable at Top-5 by default.
    return 5


def _strip_fenced_block(text: str) -> str:
    s = str(text or "").strip()
    if not s.startswith("```"):
        return s
    lines = s.splitlines()
    if not lines:
        return s
    lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_json_object(text: str) -> Dict[str, Any]:
    s = _strip_fenced_block(text)
    if not s:
        return {}
    contract_keys = {
        "market_regime",
        "market_sentiment",
        "key_events",
        "themes",
        "avoid_themes",
        "playbook",
        "scanner_bias",
        "scanner_priority",
        "trade_aggressiveness",
        "risk_tone",
        "monitor_guidance",
        "report_focus",
        "scanner_source_policy",
    }

    def unwrap(obj: Any) -> Dict[str, Any]:
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            obj = obj[0]
        if not isinstance(obj, dict):
            return {}
        if any(k in obj for k in contract_keys):
            return obj
        for key in ("strategist_output", "output", "result", "data"):
            nested = obj.get(key)
            if isinstance(nested, dict) and any(k in nested for k in contract_keys):
                merged = dict(obj)
                merged.pop(key, None)
                merged.update(nested)
                return merged
        return obj
    try:
        obj = json.loads(s)
        unwrapped = unwrap(obj)
        if unwrapped:
            return unwrapped
    except Exception:
        pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(s):
        if ch != "{":
            continue
        try:
            obj, _end = dec.raw_decode(s[i:])
            unwrapped = unwrap(obj)
            if unwrapped:
                return unwrapped
        except Exception:
            continue
    return {}


def _classify_llm_parse_failure(raw: Any) -> str:
    s = _strip_fenced_block(str(raw or "")).strip()
    if not s:
        return "strategist_llm_response_empty"
    if s.startswith("{") or s.startswith("[") or "market_regime" in s or "themes" in s:
        return "strategist_llm_response_truncated_json"
    return "strategist_llm_response_not_json"


def _resolve_strategist_frame_llm_enabled(policy: Dict[str, Any]) -> bool:
    if policy.get("strategist_frame_use_llm") is not None:
        return _is_trueish(policy.get("strategist_frame_use_llm"))

    env_raw = str(os.getenv("STRATEGIST_FRAME_USE_LLM", "") or "").strip()
    if env_raw:
        return _is_trueish(env_raw)

    if os.getenv("PYTEST_CURRENT_TEST"):
        return False

    provider = str(os.getenv("AI_STRATEGIST_PROVIDER", "") or "").strip().lower()
    if provider not in ("openai", "http", "api"):
        return False

    has_key = bool(
        (os.getenv("OPENROUTER_API_KEY", "") or "").strip()
        or (os.getenv("AI_STRATEGIST_API_KEY", "") or "").strip()
    )
    return has_key


def _normalize_llm_overrides(raw: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    normalized = coerce_strategist_output(raw)
    allowed = {
        "market_regime",
        "market_sentiment",
        "key_events",
        "themes",
        "avoid_themes",
        "playbook",
        "scanner_bias",
        "scanner_priority",
        "trade_aggressiveness",
        "risk_tone",
        "monitor_guidance",
        "report_focus",
    }
    out: Dict[str, Any] = {}
    for key in allowed:
        if key in raw:
            out[key] = normalized.get(key)
    if isinstance(raw.get("monitor_policy"), dict):
        out["monitor_policy"] = dict(raw.get("monitor_policy") or {})
    return out


def _build_strategist_llm_messages(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    system = (
        "You are the Strategist agent for an automated trading system. "
        "You must output a strategic frame only. "
        "Do not select final stock and do not produce order instructions. "
        "Return strict JSON only."
    )
    contract = {
        "market_regime": "risk_on|neutral|risk_off",
        "market_sentiment": "bullish|neutral|bearish",
        "key_events": ["string"],
        "themes": ["string"],
        "avoid_themes": ["string"],
        "playbook": "breakout|pullback|reversal|defensive",
        "scanner_bias": "large_cap|leader|momentum|value",
        "scanner_priority": ["trading_value", "trend_strength", "volume_surge", "leader_quality"],
        "trade_aggressiveness": "low|medium|high",
        "risk_tone": "conservative|normal|aggressive",
        "monitor_guidance": "hold_through_noise|defensive_exit|quick_take_profit",
        "report_focus": ["theme_accuracy", "exit_quality", "overtrading"],
    }
    user = (
        "Use the provided market context, news/global sentiment, and candidate hints. "
        "Produce a realistic strategic frame for scanner/monitor guidance.\n"
        "JSON contract:\n"
        f"{json.dumps(contract, ensure_ascii=False)}\n\n"
        "Input:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _compact_news_sample_for_llm(sample: Any, *, max_symbols: int = 6, max_titles: int = 2, max_title_len: int = 160) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not isinstance(sample, dict):
        return out
    for symbol, value in list(sample.items())[:max_symbols]:
        if not isinstance(value, dict):
            continue
        rows = value.get("sample") if isinstance(value.get("sample"), list) else []
        titles: List[str] = []
        for row in rows[:max_titles]:
            if isinstance(row, dict):
                title = str(row.get("title") or "").strip()
            else:
                title = str(row or "").strip()
            if not title:
                continue
            if len(title) > max_title_len:
                title = title[: max_title_len - 3] + "..."
            titles.append(title)
        out[str(symbol)] = {
            "count": int(value.get("count") or len(rows)),
            "titles": titles,
        }
    return out


def _build_compact_strategist_llm_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    compact = dict(payload or {})
    compact["market_news_sample"] = _compact_news_sample_for_llm(compact.get("market_news_sample"))
    compact["candidate_news_sample"] = _compact_news_sample_for_llm(compact.get("candidate_news_sample"))
    compact["candidate_symbols_hint"] = list(compact.get("candidate_symbols_hint") or [])[:5]
    compact["key_events_hint"] = [str(x or "") for x in list(compact.get("key_events_hint") or [])[:5]]
    compact["themes_hint"] = [str(x or "") for x in list(compact.get("themes_hint") or [])[:5]]
    return compact


def _build_strategist_llm_repair_messages(payload: Dict[str, Any], raw_response: Any) -> List[Dict[str, str]]:
    compact_payload = _build_compact_strategist_llm_payload(payload)
    system = (
        "You repair strategist outputs for an automated trading system. "
        "Return strict JSON only, matching the required contract exactly. "
        "Do not add commentary, markdown, or explanations."
    )
    contract = {
        "market_regime": "risk_on|neutral|risk_off",
        "market_sentiment": "bullish|neutral|bearish",
        "key_events": ["string"],
        "themes": ["string"],
        "avoid_themes": ["string"],
        "playbook": "breakout|pullback|reversal|defensive",
        "scanner_bias": "large_cap|leader|momentum|value",
        "scanner_priority": ["trading_value", "trend_strength", "volume_surge", "leader_quality"],
        "trade_aggressiveness": "low|medium|high",
        "risk_tone": "conservative|normal|aggressive",
        "monitor_guidance": "hold_through_noise|defensive_exit|quick_take_profit",
        "report_focus": ["theme_accuracy", "exit_quality", "overtrading"],
    }
    raw = str(raw_response or "").strip()
    user = (
        "Fix or regenerate the strategist response as valid JSON.\n"
        "JSON contract:\n"
        f"{json.dumps(contract, ensure_ascii=False)}\n\n"
        "Compact input:\n"
        f"{json.dumps(compact_payload, ensure_ascii=False)}\n\n"
        "Draft response to repair:\n"
        f"{raw}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _messages_to_prompt_text(messages: List[Dict[str, str]]) -> str:
    rows: List[str] = []
    for m in messages:
        role = str(m.get("role") or "").strip().lower() or "unknown"
        content = str(m.get("content") or "")
        rows.append(f"[{role}]\n{content}")
    return "\n\n".join(rows).strip()


def _run_strategist_frame_llm(
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
    payload: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    run_id = str(state.get("run_id") or "").strip() or "strategist-unknown"
    if not _resolve_strategist_frame_llm_enabled(policy):
        return {}, {"enabled": False, "status": "disabled", "reason": "strategist_frame_llm_disabled"}

    if _env_bool("DRY_RUN", False):
        return {}, {"enabled": True, "status": "dry_run", "reason": "dry_run"}

    model = str(
        policy.get("strategist_frame_llm_model")
        or os.getenv("STRATEGIST_FRAME_LLM_MODEL", "")
        or os.getenv("AI_STRATEGIST_MODEL", "")
        or os.getenv("OPENROUTER_DEFAULT_MODEL", "")
        or ""
    ).strip()
    temp_raw = (
        policy.get("strategist_frame_llm_temperature")
        if policy.get("strategist_frame_llm_temperature") is not None
        else os.getenv("STRATEGIST_FRAME_LLM_TEMPERATURE", "0.1")
    )
    max_tokens_raw = (
        policy.get("strategist_frame_llm_max_tokens")
        if policy.get("strategist_frame_llm_max_tokens") is not None
        else os.getenv("STRATEGIST_FRAME_LLM_MAX_TOKENS", "900")
    )
    try:
        temperature = float(temp_raw)
    except Exception:
        temperature = 0.1
    try:
        max_tokens = max(256, int(float(max_tokens_raw)))
    except Exception:
        max_tokens = 900

    router = LLMRouter.from_env()
    if router.client is None:
        return {}, {"enabled": True, "status": "unavailable", "reason": "llm_client_unavailable"}

    route_policy: Dict[str, Any] = {"temperature": float(temperature), "max_tokens": int(max_tokens)}
    if _env_bool("STRATEGIST_FRAME_LLM_JSON_RESPONSE_FORMAT", True):
        route_policy["response_format"] = {"type": "json_object"}
    if model:
        route_policy["model"] = model
    route = router.resolve("strategist", policy=route_policy)
    compact_payload = _build_compact_strategist_llm_payload(payload)
    messages = _build_strategist_llm_messages(compact_payload)
    prompt_text = _messages_to_prompt_text(messages)
    try:
        record_llm_prompt(
            run_id=run_id,
            agent="strategist",
            stage="theme_selection",
            raw_input=dict(compact_payload),
            llm_prompt=prompt_text,
            decision_link={
                "model": str(route.model or ""),
                "provider": "strategist_router",
                "temperature": float(temperature),
                "max_tokens": int(max_tokens),
            },
        )
    except Exception:
        pass

    t0 = time.perf_counter()
    try:
        raw = router.chat("strategist", messages, policy=route_policy)
    except Exception as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        try:
            record_llm_response(
                run_id=run_id,
                agent="strategist",
                stage="theme_selection",
                llm_response=f"ERROR:{type(e).__name__}:{e}",
                parsed_output={},
                decision_link={"status": "error"},
            )
        except Exception:
            pass
        return {}, {
            "enabled": True,
            "status": "error",
            "reason": str(e),
            "error_type": type(e).__name__,
            "latency_ms": latency_ms,
            "model": route.model,
        }
    latency_ms = int((time.perf_counter() - t0) * 1000)

    attempts = 1
    repair_used = False
    obj = _extract_json_object(raw)
    if not isinstance(obj, dict) or not obj:
        reason = _classify_llm_parse_failure(raw)
        retry_raw = ""
        if _env_bool("STRATEGIST_FRAME_LLM_REPAIR_RETRY", True):
            repair_used = True
            repair_messages = _build_strategist_llm_repair_messages(compact_payload, raw)
            repair_prompt_text = _messages_to_prompt_text(repair_messages)
            repair_policy = dict(route_policy)
            repair_policy["temperature"] = 0.0
            repair_policy["max_tokens"] = min(max(384, int(max_tokens)), 768)
            try:
                record_llm_prompt(
                    run_id=run_id,
                    agent="strategist",
                    stage="theme_selection_repair",
                    raw_input={"parse_error_reason": reason, "raw_preview": str(raw or "")[:400]},
                    llm_prompt=repair_prompt_text,
                    decision_link={
                        "model": str(route.model or ""),
                        "provider": "strategist_router",
                        "repair": True,
                    },
                )
            except Exception:
                pass
            try:
                retry_raw = router.chat("strategist", repair_messages, policy=repair_policy)
                attempts += 1
                obj = _extract_json_object(retry_raw)
                if isinstance(obj, dict) and obj:
                    overrides = _normalize_llm_overrides(obj)
                    if overrides:
                        try:
                            record_llm_response(
                                run_id=run_id,
                                agent="strategist",
                                stage="theme_selection_repair",
                                llm_response=str(retry_raw or ""),
                                parsed_output=dict(overrides),
                                decision_link={
                                    "status": "ok",
                                    "repair": True,
                                    "attempts": int(attempts),
                                    "model": str(route.model or ""),
                                },
                            )
                        except Exception:
                            pass
                        return overrides, {
                            "enabled": True,
                            "status": "ok",
                            "latency_ms": latency_ms,
                            "model": route.model,
                            "attempts": int(attempts),
                            "repair_used": True,
                        }
                try:
                    record_llm_response(
                        run_id=run_id,
                        agent="strategist",
                        stage="theme_selection_repair",
                        llm_response=str(retry_raw or ""),
                        parsed_output=dict(obj) if isinstance(obj, dict) else {},
                        decision_link={"status": "parse_error", "repair": True},
                    )
                except Exception:
                    pass
            except Exception as e:
                attempts += 1
                try:
                    record_llm_response(
                        run_id=run_id,
                        agent="strategist",
                        stage="theme_selection_repair",
                        llm_response=f"ERROR:{type(e).__name__}:{e}",
                        parsed_output={},
                        decision_link={"status": "error", "repair": True},
                    )
                except Exception:
                    pass
        try:
            record_llm_response(
                run_id=run_id,
                agent="strategist",
                stage="theme_selection",
                llm_response=str(raw or ""),
                parsed_output={},
                decision_link={"status": "parse_error", "reason": reason, "attempts": int(attempts), "repair_used": bool(repair_used)},
            )
        except Exception:
            pass
        return {}, {
            "enabled": True,
            "status": "parse_error",
            "reason": reason,
            "latency_ms": latency_ms,
            "model": route.model,
            "raw_preview": str(raw or "")[:220],
            "attempts": int(attempts),
            "repair_used": bool(repair_used),
        }

    overrides = _normalize_llm_overrides(obj)
    if not overrides:
        try:
            record_llm_response(
                run_id=run_id,
                agent="strategist",
                stage="theme_selection",
                llm_response=str(raw or ""),
                parsed_output=dict(obj),
                decision_link={"status": "parse_error", "reason": "missing_contract_fields", "attempts": int(attempts)},
            )
        except Exception:
            pass
        return {}, {
            "enabled": True,
            "status": "parse_error",
            "reason": "strategist_llm_response_missing_contract_fields",
            "latency_ms": latency_ms,
            "model": route.model,
            "raw_preview": str(raw or "")[:220],
            "attempts": int(attempts),
            "repair_used": bool(repair_used),
        }

    try:
        record_llm_response(
            run_id=run_id,
            agent="strategist",
            stage="theme_selection",
            llm_response=str(raw or ""),
            parsed_output=dict(overrides),
            decision_link={"status": "ok", "model": str(route.model or ""), "latency_ms": int(latency_ms), "attempts": int(attempts)},
        )
    except Exception:
        pass

    return overrides, {
        "enabled": True,
        "status": "ok",
        "latency_ms": latency_ms,
        "model": route.model,
        "attempts": int(attempts),
        "repair_used": bool(repair_used),
    }


def _extract_themes(state: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    seen = set()

    def add_many(items: Any) -> None:
        if not isinstance(items, list):
            return
        for x in items:
            t = str(x or "").strip()
            if not t or t in seen:
                continue
            seen.add(t)
            out.append(t)

    add_many(state.get("themes"))
    add_many(state.get("top_themes"))
    add_many(state.get("sector_filter"))
    add_many(state.get("theme_filter"))
    add_many(policy.get("themes"))
    add_many(policy.get("top_themes"))
    add_many(policy.get("sector_filter"))
    add_many(policy.get("theme_filter"))

    theme_scores = state.get("theme_scores") if isinstance(state.get("theme_scores"), dict) else {}
    if theme_scores:
        ranked = sorted(
            ((str(k or "").strip(), float(v or 0.0)) for k, v in theme_scores.items()),
            key=lambda kv: kv[1],
            reverse=True,
        )
        for name, _score in ranked:
            if name and name not in seen:
                seen.add(name)
                out.append(name)

    theme_map = policy.get("theme_map") if isinstance(policy.get("theme_map"), dict) else {}
    for k in theme_map.keys():
        name = str(k or "").strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)

    return out[:5]


def _append_unique_text(out: List[str], seen: set[str], raw: Any) -> None:
    s = str(raw or "").strip()
    if not s:
        return
    key = s.lower()
    if key in seen:
        return
    seen.add(key)
    out.append(s)


def _theme_to_news_queries(theme: Any) -> List[str]:
    raw = str(theme or "").strip()
    if not raw:
        return []
    key = raw.lower().replace("-", "_").replace(" ", "_")
    direct_map: Dict[str, List[str]] = {
        "semiconductor": ["반도체", "HBM", "메모리"],
        "semiconductors_hbm": ["반도체", "HBM", "메모리"],
        "ai": ["AI", "인공지능"],
        "battery": ["2차전지", "배터리"],
        "secondary_battery": ["2차전지", "배터리"],
        "defense": ["방산"],
        "energy_security": ["에너지", "국제유가", "천연가스"],
        "renewable_energy": ["재생에너지", "태양광"],
        "bio": ["바이오", "제약"],
        "healthcare": ["헬스케어", "바이오"],
        "finance": ["금융", "은행"],
        "banks": ["금융", "은행"],
        "internet": ["인터넷", "플랫폼"],
        "platform": ["플랫폼", "인터넷"],
        "shipbuilding": ["조선"],
        "autos": ["자동차"],
        "robotics": ["로봇"],
        "broad_market_leaders": ["시가총액 상위", "주도주"],
        "quality_factor": ["실적주", "대형주"],
        "low_volatility": ["방어주", "저변동성"],
    }
    if key in direct_map:
        return list(direct_map[key])
    terms: List[str] = []
    if "semiconductor" in key or "memory" in key:
        terms.extend(["반도체", "HBM"])
    if key == "ai" or "artificial_intelligence" in key:
        terms.extend(["AI", "인공지능"])
    if "energy" in key:
        terms.extend(["에너지", "국제유가"])
    if "defense" in key:
        terms.append("방산")
    if "battery" in key:
        terms.extend(["2차전지", "배터리"])
    if "bank" in key or "finance" in key:
        terms.extend(["금융", "은행"])
    if not terms:
        terms.append(raw)
    return terms


def _build_market_news_query_targets(
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
    global_signal: Dict[str, Any],
    market_context_inputs: Dict[str, float],
    theme_hints: List[str],
) -> List[str]:
    limit = max(
        3,
        _to_int(
            policy.get("strategist_news_query_limit")
            if policy.get("strategist_news_query_limit") is not None
            else os.getenv("STRATEGIST_NEWS_QUERY_LIMIT", "10"),
            10,
        ),
    )
    out: List[str] = []
    seen: set[str] = set()

    explicit_targets: List[Any] = []
    if isinstance(state.get("news_query_targets"), list):
        explicit_targets.extend(list(state.get("news_query_targets") or []))
    if isinstance(policy.get("news_query_targets"), list):
        explicit_targets.extend(list(policy.get("news_query_targets") or []))
    env_targets = str(os.getenv("NEWS_QUERY_TARGETS", "") or "").strip()
    if env_targets:
        explicit_targets.extend([x.strip() for x in env_targets.split(",") if str(x).strip()])
    for raw in explicit_targets:
        _append_unique_text(out, seen, raw)

    global_score = _signal_score(global_signal)
    macro_risk = _to_float(market_context_inputs.get("macro_risk"), 0.0)
    index_trend = _to_float(market_context_inputs.get("index_trend"), 0.0)
    if global_score <= -0.20 or macro_risk >= 0.65:
        base_queries = ["코스피", "미국 증시", "국제유가", "환율", "중동"]
    elif global_score >= 0.20 and index_trend >= -0.05:
        base_queries = ["코스피", "코스닥", "미국 증시", "위험선호", "주도주"]
    else:
        base_queries = ["코스피", "코스닥", "미국 증시", "증시 전망", "거시경제"]
    for raw in base_queries:
        _append_unique_text(out, seen, raw)

    for raw in list(theme_hints or [])[:5]:
        for q in _theme_to_news_queries(raw):
            _append_unique_text(out, seen, q)

    if macro_risk >= 0.65:
        for raw in ("국제유가", "환율", "달러", "중동", "방산", "금"):
            _append_unique_text(out, seen, raw)
    elif global_score <= -0.20:
        for raw in ("환율", "달러", "국채금리", "금", "방어주"):
            _append_unique_text(out, seen, raw)
    elif global_score >= 0.20 and index_trend >= 0.10:
        for raw in ("주도주", "실적주", "수출주"):
            _append_unique_text(out, seen, raw)

    for key in ("macro_events", "global_events", "major_events"):
        values = state.get(key)
        if not isinstance(values, list):
            continue
        for raw in list(values)[:3]:
            _append_unique_text(out, seen, raw)
        if values:
            break

    return out[:limit]


def _build_market_news_query_reasoning(
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
    global_signal: Dict[str, Any],
    market_context_inputs: Dict[str, float],
    theme_hints: List[str],
) -> str:
    explicit_targets: List[str] = []
    if isinstance(state.get("news_query_targets"), list):
        explicit_targets.extend([str(x).strip() for x in list(state.get("news_query_targets") or []) if str(x).strip()])
    if isinstance(policy.get("news_query_targets"), list):
        explicit_targets.extend([str(x).strip() for x in list(policy.get("news_query_targets") or []) if str(x).strip()])
    env_targets = str(os.getenv("NEWS_QUERY_TARGETS", "") or "").strip()
    if env_targets:
        explicit_targets.extend([x.strip() for x in env_targets.split(",") if str(x).strip()])

    global_score = _signal_score(global_signal)
    macro_risk = _to_float(market_context_inputs.get("macro_risk"), 0.0)
    index_trend = _to_float(market_context_inputs.get("index_trend"), 0.0)

    reasons: List[str] = [
        f"global_score={global_score:.2f} macro_risk={macro_risk:.2f} index_trend={index_trend:.2f}"
    ]
    if explicit_targets:
        reasons.append(f"explicit_targets_first={', '.join(explicit_targets[:4])}")

    if global_score <= -0.20 or macro_risk >= 0.65:
        reasons.append("risk-off macro context added oil/fx/geopolitics market queries")
    elif global_score >= 0.20 and index_trend >= -0.05:
        reasons.append("risk-on context added leader/risk-appetite market queries")
    else:
        reasons.append("neutral context kept broad market and macro queries")

    normalized_themes = [str(x).strip() for x in list(theme_hints or []) if str(x).strip()]
    if normalized_themes:
        reasons.append(f"theme hints expanded queries from {', '.join(normalized_themes[:3])}")

    for key in ("macro_events", "global_events", "major_events"):
        values = state.get(key)
        if isinstance(values, list):
            normalized = [str(x).strip() for x in list(values or []) if str(x).strip()]
            if normalized:
                reasons.append(f"macro events appended {', '.join(normalized[:2])}")
                break

    return "; ".join(reasons)


def _default_policy(user_policy: Dict[str, Any] | None) -> Dict[str, Any]:
    p = dict(user_policy or {})
    default_topn = _resolve_top_n_candidates(p)
    pytest_mode = bool(os.getenv("PYTEST_CURRENT_TEST"))
    p.setdefault("use_universe_builder", _is_trueish(os.getenv("USE_UNIVERSE_BUILDER", "true")))
    p.setdefault("universe_require_condition", _is_trueish(os.getenv("UNIVERSE_REQUIRE_CONDITION", "false")))
    # candidate generation
    p.setdefault("candidate_source", "top_picks")  # top_picks | market_rank
    p.setdefault("candidate_k", int(p.get("candidate_topk", default_topn) or default_topn))
    p.setdefault("candidate_rank_mode", "value")
    p.setdefault("candidate_rank_topn", 30)
    # sentiment toggles
    p.setdefault(
        "use_global_sentiment",
        _is_trueish(os.getenv("M10_USE_GLOBAL_SENTIMENT", "false" if pytest_mode else "true")),
    )
    p.setdefault(
        "use_news_analysis",
        _is_trueish(os.getenv("M10_USE_NEWS_SENTIMENT", "false" if pytest_mode else "true")),
    )
    p.setdefault("use_exit_policy", _is_trueish(os.getenv("USE_EXIT_POLICY", "false")))
    # news plugin
    p.setdefault("news_provider", "naver")
    p.setdefault("news_scorer", "simple")
    # rerank weights
    p.setdefault("candidate_news_weight", 0.2)
    p.setdefault("candidate_global_weight", 0.1)
    p.setdefault("candidate_negative_news_threshold", -0.7)
    p.setdefault("candidate_risk_off_threshold", -0.5)
    p.setdefault("candidate_risk_on_threshold", 0.5)
    p.setdefault("candidate_max_count_risk_off", 3)
    return p


def _candidates_from_state(state: Dict[str, Any], k: int) -> List[Dict[str, str]]:
    # Highest priority: explicit candidates provided
    if isinstance(state.get("candidates"), list) and state["candidates"]:
        out = []
        for x in state["candidates"][:k]:
            if isinstance(x, dict) and "symbol" in x:
                out.append({"symbol": str(x["symbol"]), "why": str(x.get("why") or "injected")})
        return out

    # Next: universe list (tests)
    if isinstance(state.get("universe"), list) and state["universe"]:
        syms = [str(s) for s in state["universe"][:k]]
        return [{"symbol": s, "why": "universe"} for s in syms]

    # Next: direct candidate symbols injection
    if isinstance(state.get("candidate_symbols"), list) and state["candidate_symbols"]:
        syms = [str(s) for s in state["candidate_symbols"][:k]]
        return [{"symbol": s, "why": "candidate_symbols"} for s in syms]

    return []


def _signal_score(sig: Any) -> float:
    if not isinstance(sig, dict):
        return 0.0
    try:
        return float(sig.get("score") or 0.0)
    except Exception:
        return 0.0


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _risk_regime_label(score: float) -> str:
    if score >= 0.20:
        return "risk_on"
    if score <= -0.20:
        return "risk_off"
    return "neutral"


def _market_sentiment_label(score: float) -> str:
    if score >= 0.15:
        return "bullish"
    if score <= -0.15:
        return "bearish"
    return "neutral"


def _extract_market_context_inputs(state: Dict[str, Any]) -> Dict[str, float]:
    market_ctx = state.get("market_context") if isinstance(state.get("market_context"), dict) else {}
    macro_ctx = state.get("macro_context") if isinstance(state.get("macro_context"), dict) else {}
    kiwoom_summary = state.get("kiwoom_market_summary") if isinstance(state.get("kiwoom_market_summary"), dict) else {}
    index_trend = _to_float(
        market_ctx.get("index_trend") if market_ctx.get("index_trend") is not None else kiwoom_summary.get("index_trend"),
        0.0,
    )
    realized_vol = _to_float(
        market_ctx.get("realized_volatility")
        if market_ctx.get("realized_volatility") is not None
        else (
            market_ctx.get("realized_vol")
            if market_ctx.get("realized_vol") is not None
            else kiwoom_summary.get("realized_volatility")
        ),
        0.0,
    )
    breadth_raw = market_ctx.get("market_breadth")
    if breadth_raw is None:
        breadth_raw = kiwoom_summary.get("market_breadth")
    market_breadth = _to_float(breadth_raw, 0.0)
    if market_breadth > 1.0:
        market_breadth = _clamp(market_breadth / 100.0, -1.0, 1.0)
    macro_risk = _to_float(
        market_ctx.get("macro_risk")
        if market_ctx.get("macro_risk") is not None
        else (
            macro_ctx.get("macro_risk")
            if macro_ctx.get("macro_risk") is not None
            else kiwoom_summary.get("macro_risk")
        ),
        0.0,
    )
    return {
        "index_trend": float(_clamp(index_trend, -1.0, 1.0)),
        "realized_volatility": float(max(0.0, realized_vol)),
        "market_breadth": float(_clamp(market_breadth, -1.0, 1.0)),
        "macro_risk": float(_clamp(macro_risk, 0.0, 1.0)),
    }


def _market_structure_label(
    *,
    state: Dict[str, Any],
    global_score: float,
    market_context_inputs: Dict[str, float],
) -> Tuple[str, Dict[str, Any]]:
    idx_trend = _to_float(market_context_inputs.get("index_trend"), 0.0)
    realized_vol = _to_float(market_context_inputs.get("realized_volatility"), 0.0)
    breadth = _to_float(market_context_inputs.get("market_breadth"), 0.0)
    breadth_01 = _clamp((breadth + 1.0) / 2.0, 0.0, 1.0)
    regime_obj = classify_regime_v2(
        ma20_gap=idx_trend,
        volatility20=realized_vol,
        index_trend=idx_trend,
        realized_volatility=realized_vol,
        global_sentiment=global_score,
        market_breadth=breadth_01,
    )
    regime = str(regime_obj.get("regime") or "").strip().lower()
    if regime in ("trend", "range", "high_volatility"):
        return regime, dict(regime_obj.get("factors") or {})
    # fallback
    if realized_vol >= 0.040:
        return "high_volatility", {}
    if abs(idx_trend) >= 0.25 and abs(breadth) >= 0.50:
        return "trend", {}
    return "range", {}


def _extract_theme_symbol_index(state: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, set[str]]:
    out: Dict[str, set[str]] = {}

    def add_map(raw: Any) -> None:
        if not isinstance(raw, dict):
            return
        for k, symbols in raw.items():
            name = str(k or "").strip().lower()
            if not name:
                continue
            bucket = out.setdefault(name, set())
            if isinstance(symbols, list):
                for sym in symbols:
                    s = str(sym or "").strip().upper()
                    if s:
                        bucket.add(s)

    add_map(state.get("theme_map"))
    add_map(state.get("sector_map"))
    add_map(policy.get("theme_map"))
    add_map(policy.get("sector_map"))
    return out


def _merge_theme_symbol_map(
    existing: Any,
    *,
    themes: List[str],
    candidate_symbols: List[str],
) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}

    if isinstance(existing, dict):
        for key, symbols in existing.items():
            name = str(key or "").strip().lower()
            if not name:
                continue
            merged: List[str] = []
            seen: set[str] = set()
            if isinstance(symbols, list):
                for sym in symbols:
                    s = str(sym or "").strip().upper()
                    if not s or s in seen:
                        continue
                    seen.add(s)
                    merged.append(s)
            out[name] = merged

    if not candidate_symbols:
        return out

    for theme in themes:
        name = str(theme or "").strip().lower()
        if not name:
            continue
        bucket = list(out.get(name) or [])
        seen = set(bucket)
        for sym in candidate_symbols:
            s = str(sym or "").strip().upper()
            if not s or s in seen:
                continue
            seen.add(s)
            bucket.append(s)
        out[name] = bucket
    return out


def _news_context_summary(
    news_signal_map: Dict[str, Dict[str, Any]],
    news_items_by_symbol: Dict[str, List[Any]],
) -> Dict[str, Any]:
    total = 0
    unavailable = 0
    fallback = 0
    ok = 0
    score_sum = 0.0
    score_cnt = 0
    headline_count = 0

    for symbol, sig in news_signal_map.items():
        _ = symbol
        total += 1
        st = str((sig or {}).get("status") or "").strip().lower()
        if st == "ok":
            ok += 1
        elif st == "fallback":
            fallback += 1
        elif st == "unavailable":
            unavailable += 1
        try:
            score_sum += float((sig or {}).get("score") or 0.0)
            score_cnt += 1
        except Exception:
            pass

    for rows in (news_items_by_symbol or {}).values():
        if isinstance(rows, list):
            headline_count += len(rows)

    avg_score = (score_sum / float(score_cnt)) if score_cnt > 0 else 0.0
    return {
        "signal_total": int(total),
        "ok": int(ok),
        "fallback": int(fallback),
        "unavailable": int(unavailable),
        "avg_score": float(_clamp(avg_score, -1.0, 1.0)),
        "headline_count": int(headline_count),
    }


def _merge_news_contexts(candidate_ctx: Dict[str, Any], market_ctx: Dict[str, Any]) -> Dict[str, Any]:
    cand_total = int(candidate_ctx.get("signal_total") or 0)
    market_total = int(market_ctx.get("signal_total") or 0)
    total = cand_total + market_total
    avg_score = 0.0
    if total > 0:
        avg_score = (
            (_to_float(candidate_ctx.get("avg_score"), 0.0) * float(cand_total))
            + (_to_float(market_ctx.get("avg_score"), 0.0) * float(market_total))
        ) / float(total)
    return {
        "signal_total": int(total),
        "ok": int(candidate_ctx.get("ok") or 0) + int(market_ctx.get("ok") or 0),
        "fallback": int(candidate_ctx.get("fallback") or 0) + int(market_ctx.get("fallback") or 0),
        "unavailable": int(candidate_ctx.get("unavailable") or 0) + int(market_ctx.get("unavailable") or 0),
        "avg_score": float(_clamp(avg_score, -1.0, 1.0)),
        "headline_count": int(candidate_ctx.get("headline_count") or 0) + int(market_ctx.get("headline_count") or 0),
        "candidate_signal_total": int(cand_total),
        "candidate_headline_count": int(candidate_ctx.get("headline_count") or 0),
        "market_signal_total": int(market_total),
        "market_headline_count": int(market_ctx.get("headline_count") or 0),
    }


def _theme_strength_map(
    *,
    themes: List[str],
    candidates: List[Dict[str, Any]],
    theme_scores: Dict[str, Any],
    theme_index: Dict[str, set[str]],
) -> Dict[str, float]:
    out: Dict[str, float] = {}
    candidate_symbols = [str((c or {}).get("symbol") or "").strip().upper() for c in list(candidates or [])]
    candidate_symbols = [s for s in candidate_symbols if s]
    denom = max(1, len(candidate_symbols))

    for raw_theme in list(themes or []):
        t = str(raw_theme or "").strip()
        if not t:
            continue
        key = t.lower()
        score_raw = _to_float(theme_scores.get(t, theme_scores.get(key, 0.0)), 0.0)
        score_norm = _clamp(score_raw / 100.0, -1.0, 1.0) if abs(score_raw) > 1.0 else _clamp(score_raw, -1.0, 1.0)
        mapped = theme_index.get(key, set())
        hits = 0
        if mapped:
            mapped_upper = {str(x).strip().upper() for x in mapped if str(x).strip()}
            hits = len([s for s in candidate_symbols if s in mapped_upper])
        hit_ratio = float(hits) / float(denom)
        out[t] = float(_clamp((0.70 * score_norm) + (0.30 * hit_ratio), -1.0, 1.0))

    return out


def _compose_regime_score(
    *,
    global_score: float,
    news_score: float,
    market_context_inputs: Dict[str, float],
) -> float:
    idx = _to_float(market_context_inputs.get("index_trend"), 0.0)
    breadth = _to_float(market_context_inputs.get("market_breadth"), 0.0)
    macro_risk = _to_float(market_context_inputs.get("macro_risk"), 0.0)
    score = (0.45 * global_score) + (0.20 * news_score) + (0.20 * idx) + (0.15 * breadth) - (0.25 * macro_risk)
    return float(_clamp(score, -1.0, 1.0))


def _pick_playbook(*, market_structure: str, market_regime: str, market_sentiment: str) -> str:
    if str(market_structure).startswith("high_volatility") or market_regime == "risk_off":
        return "defensive"
    if str(market_structure).startswith("trend") and market_regime == "risk_on" and market_sentiment == "bullish":
        return "breakout"
    if str(market_structure).startswith("trend"):
        return "pullback"
    if str(market_structure).startswith("range") and market_regime == "risk_on":
        return "reversal"
    return "defensive"


def _scanner_priority(playbook: str, market_regime: str) -> List[str]:
    if playbook == "breakout":
        return ["momentum", "trend_strength", "volume_surge", "liquidity"]
    if playbook == "pullback":
        return ["trend_strength", "pullback_quality", "relative_strength", "liquidity"]
    if playbook == "reversal":
        return ["oversold_reversal", "volume_confirmation", "risk_reward", "liquidity"]
    # defensive
    base = ["liquidity", "risk_penalty", "low_volatility", "drawdown_control"]
    if market_regime == "risk_off":
        base.insert(0, "capital_preservation")
    return base


def _scanner_bias(*, playbook: str, market_regime: str) -> str:
    if market_regime == "risk_off":
        return "large_cap"
    if playbook == "breakout":
        return "momentum"
    if playbook == "pullback":
        return "leader"
    if playbook == "reversal":
        return "value"
    return "leader"


def _avoid_themes(*, market_sentiment: str, playbook: str) -> List[str]:
    if market_sentiment == "bearish" or playbook == "defensive":
        return ["illiquid_microcap", "headline_only_momentum", "high_gap_speculative"]
    if playbook == "reversal":
        return ["overextended_breakout_without_volume", "late_chasing_moves"]
    if playbook == "pullback":
        return ["counter_trend_low_liquidity"]
    return ["thin_liquidity_names"]


def _trade_aggressiveness(*, market_regime: str, market_structure: str) -> str:
    if market_regime == "risk_off" or str(market_structure).startswith("high_volatility"):
        return "low"
    if market_regime == "risk_on" and str(market_structure).startswith("trend"):
        return "high"
    return "medium"


def _risk_tone(aggressiveness: str) -> str:
    if aggressiveness == "low":
        return "conservative"
    if aggressiveness == "high":
        return "aggressive"
    return "normal"


def _monitor_guidance(*, market_regime: str, playbook: str) -> str:
    if market_regime == "risk_off" or playbook == "defensive":
        return "defensive_exit"
    if playbook == "breakout":
        return "hold_through_noise"
    return "quick_take_profit"


def _condition_search_source_enabled() -> bool:
    return _env_bool("KIWOOM_CANDIDATE_ENABLE_CONDITION_SEARCH", False)


def _monitor_policy(
    *,
    monitor_guidance: str,
    trade_aggressiveness: str,
    risk_tone: str,
) -> Dict[str, Any]:
    min_hold_sec = _to_int(os.getenv("MIN_HOLD_SECONDS", "600"), 600)
    sell_cooldown = _to_int(os.getenv("SELL_COOLDOWN", os.getenv("SELL_COOLDOWN_SEC", "300")), 300)
    confirm_ticks = _to_int(os.getenv("MONITOR_EXIT_CONFIRM_TICKS", "2"), 2)
    adjustments: List[str] = []

    mode = str(monitor_guidance or "").strip().lower()
    if mode == "hold_through_noise":
        min_hold_sec += 300
        confirm_ticks += 1
        sell_cooldown += 60
        adjustments.append("mode:hold_through_noise")
    elif mode == "defensive_exit":
        confirm_ticks = max(1, confirm_ticks - 1)
        min_hold_sec = max(0, min_hold_sec - 120)
        adjustments.append("mode:defensive_exit")
    elif mode == "quick_take_profit":
        confirm_ticks = 1
        min_hold_sec = max(0, min_hold_sec - 300)
        sell_cooldown = max(60, min(sell_cooldown, 180))
        adjustments.append("mode:quick_take_profit")

    tone = str(risk_tone or "").strip().lower()
    if tone == "conservative":
        confirm_ticks += 1
        min_hold_sec += 120
        adjustments.append("risk_tone:conservative")
    elif tone == "aggressive":
        confirm_ticks = max(1, confirm_ticks - 1)
        min_hold_sec = max(0, min_hold_sec - 60)
        adjustments.append("risk_tone:aggressive")

    aggr = str(trade_aggressiveness or "").strip().lower()
    if aggr == "low":
        confirm_ticks = max(confirm_ticks, 3)
        adjustments.append("trade_aggressiveness:low")
    elif aggr == "high":
        confirm_ticks = max(1, confirm_ticks - 1)
        adjustments.append("trade_aggressiveness:high")

    return {
        "min_hold_seconds": max(0, int(min_hold_sec)),
        "sell_cooldown_seconds": max(0, int(sell_cooldown)),
        "exit_confirm_ticks": max(1, min(6, int(confirm_ticks))),
        "adjustments": list(adjustments),
        "note": "monitor_manages_entry_exit_only",
    }


def _exit_policy(
    *,
    playbook: str,
    monitor_guidance: str,
    trade_aggressiveness: str,
    risk_tone: str,
) -> Dict[str, Any]:
    stop_loss_pct = _to_float(os.getenv("EXIT_POLICY_STOP_LOSS_PCT", "0.03"), 0.03)
    take_profit_pct = _to_float(os.getenv("EXIT_POLICY_TAKE_PROFIT_PCT", "0.05"), 0.05)
    trailing_stop_pct = _to_float(os.getenv("EXIT_POLICY_TRAILING_STOP_PCT", "0.0"), 0.0)
    vol_expansion_ratio = _to_float(os.getenv("EXIT_POLICY_VOL_EXPANSION_RATIO", "0.0"), 0.0)
    news_shock_threshold = _to_float(os.getenv("EXIT_POLICY_NEWS_SHOCK_THRESHOLD", "0.0"), 0.0)
    adjustments: List[str] = []

    mode = str(playbook or "").strip().lower()
    guidance = str(monitor_guidance or "").strip().lower()
    tone = str(risk_tone or "").strip().lower()
    aggr = str(trade_aggressiveness or "").strip().lower()

    if mode == "breakout":
        stop_loss_pct *= 0.90
        take_profit_pct *= 1.40
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.90)
        vol_expansion_ratio = max(vol_expansion_ratio, 2.20)
        adjustments.append("playbook:breakout")
    elif mode == "pullback":
        stop_loss_pct *= 1.05
        take_profit_pct *= 1.20
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.75)
        vol_expansion_ratio = max(vol_expansion_ratio, 2.00)
        adjustments.append("playbook:pullback")
    elif mode == "reversal":
        stop_loss_pct *= 0.85
        take_profit_pct *= 1.00
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.70)
        vol_expansion_ratio = max(vol_expansion_ratio, 1.80)
        adjustments.append("playbook:reversal")
    else:
        stop_loss_pct *= 0.80
        take_profit_pct *= 0.90
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.65)
        vol_expansion_ratio = max(vol_expansion_ratio, 1.60)
        adjustments.append("playbook:defensive")

    if guidance == "hold_through_noise":
        stop_loss_pct *= 1.10
        take_profit_pct *= 1.10
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.95)
        adjustments.append("monitor_guidance:hold_through_noise")
    elif guidance == "quick_take_profit":
        stop_loss_pct *= 0.95
        take_profit_pct *= 0.85
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.80)
        adjustments.append("monitor_guidance:quick_take_profit")
    elif guidance == "defensive_exit":
        stop_loss_pct *= 0.92
        take_profit_pct *= 0.92
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.70)
        adjustments.append("monitor_guidance:defensive_exit")

    if tone == "conservative":
        stop_loss_pct *= 0.90
        take_profit_pct *= 0.95
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.75)
        adjustments.append("risk_tone:conservative")
    elif tone == "aggressive":
        stop_loss_pct *= 1.10
        take_profit_pct *= 1.10
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 1.00)
        adjustments.append("risk_tone:aggressive")

    if aggr == "low":
        take_profit_pct *= 0.95
        adjustments.append("trade_aggressiveness:low")
    elif aggr == "high":
        take_profit_pct *= 1.08
        adjustments.append("trade_aggressiveness:high")

    stop_loss_pct = _clamp(stop_loss_pct, 0.003, 0.10)
    take_profit_pct = _clamp(max(take_profit_pct, stop_loss_pct * 1.05), 0.005, 0.25)
    trailing_stop_pct = _clamp(max(trailing_stop_pct, stop_loss_pct * 0.50), 0.0, 0.15)
    vol_expansion_ratio = _clamp(vol_expansion_ratio, 0.0, 5.0)
    news_shock_threshold = _clamp(news_shock_threshold, 0.0, 1.0)

    return {
        "stop_loss_pct": float(stop_loss_pct),
        "take_profit_pct": float(take_profit_pct),
        "trailing_stop_pct": float(trailing_stop_pct),
        "vol_expansion_ratio": float(vol_expansion_ratio),
        "news_shock_threshold": float(news_shock_threshold),
        "adjustments": list(adjustments),
        "note": "strategist_exit_policy_baseline",
    }


def _scanner_source_policy(
    *,
    playbook: str,
    risk_tone: str,
    trade_aggressiveness: str,
    market_regime: str,
    themes: List[str],
) -> Dict[str, Any]:
    normalized_playbook = str(playbook or "").strip().lower()
    normalized_tone = str(risk_tone or "").strip().lower()
    normalized_aggr = str(trade_aggressiveness or "").strip().lower()
    normalized_regime = str(market_regime or "").strip().lower()
    has_themes = bool(list(themes or []))
    allow_condition_search = _condition_search_source_enabled()

    policy: Dict[str, Any] = {
        "preferred_sources": ["top_value", "top_volume", "sector_theme", "operator_watchlist"],
        "include_top_value": True,
        "include_top_volume": True,
        "include_change_rate": True,
        "include_condition_search": False,
        "include_sector_candidates": has_themes,
        "include_watchlist": True,
        "top_candidate_pool": 30,
        "condition_limit": 0,
        "source_weights": {
            "top_value": 2.0,
            "top_volume": 1.7,
            "condition_search": 0.0,
            "sector_theme": 1.6,
            "operator_watchlist": 0.8,
            "top_change_rate": 1.3,
        },
        "reason": "balanced baseline prefers liquidity and theme/watchlist sources; condition search is opt-in only",
    }

    if normalized_playbook == "defensive" or normalized_tone == "conservative" or normalized_regime == "risk_off":
        policy.update(
            {
                "preferred_sources": ["top_value", "top_volume", "sector_theme", "operator_watchlist"],
                "include_change_rate": False,
                "include_condition_search": False,
                "include_sector_candidates": has_themes,
                "include_watchlist": True,
                "top_candidate_pool": 18,
                "condition_limit": 0,
                "source_weights": {
                    "top_value": 2.2,
                    "top_volume": 1.9,
                    "condition_search": 0.0,
                    "sector_theme": 1.8 if has_themes else 0.0,
                    "operator_watchlist": 1.1,
                    "top_change_rate": 0.0,
                },
                "reason": "defensive frame prioritizes liquid leaders and suppresses fast-mover sources",
            }
        )
    elif normalized_playbook == "breakout":
        policy.update(
            {
                "preferred_sources": ["top_change_rate", "top_volume", "sector_theme", "operator_watchlist"],
                "include_change_rate": True,
                "include_condition_search": False,
                "include_sector_candidates": has_themes,
                "include_watchlist": normalized_aggr != "high",
                "top_candidate_pool": 32,
                "condition_limit": 0,
                "source_weights": {
                    "top_value": 1.4,
                    "top_volume": 1.9,
                    "condition_search": 0.0,
                    "sector_theme": 1.7 if has_themes else 0.0,
                    "operator_watchlist": 0.5 if normalized_aggr == "high" else 0.8,
                    "top_change_rate": 2.2,
                },
                "reason": "breakout baseline prioritizes fast movers and volume expansion; condition search remains optional",
            }
        )
    elif normalized_playbook == "pullback":
        policy.update(
            {
                "preferred_sources": ["top_value", "sector_theme", "top_volume", "operator_watchlist"],
                "include_change_rate": False,
                "include_condition_search": False,
                "include_sector_candidates": has_themes,
                "include_watchlist": True,
                "top_candidate_pool": 24,
                "condition_limit": 0,
                "source_weights": {
                    "top_value": 2.1,
                    "top_volume": 1.5,
                    "condition_search": 0.0,
                    "sector_theme": 1.9 if has_themes else 0.0,
                    "operator_watchlist": 0.9,
                    "top_change_rate": 0.0,
                },
                "reason": "pullback baseline prioritizes liquid leaders and theme/watchlist support; condition search remains optional",
            }
        )
    elif normalized_playbook == "reversal":
        policy.update(
            {
                "preferred_sources": ["top_change_rate", "operator_watchlist", "top_volume", "sector_theme"],
                "include_change_rate": True,
                "include_condition_search": False,
                "include_sector_candidates": has_themes,
                "include_watchlist": True,
                "top_candidate_pool": 22,
                "condition_limit": 0,
                "source_weights": {
                    "top_value": 1.3,
                    "top_volume": 1.5,
                    "condition_search": 0.0,
                    "sector_theme": 1.3 if has_themes else 0.0,
                    "operator_watchlist": 1.0,
                    "top_change_rate": 1.9,
                },
                "reason": "reversal baseline leans on sharp movers and watchlist context; condition search remains optional",
            }
        )

    if allow_condition_search:
        if normalized_playbook == "breakout":
            policy["preferred_sources"] = ["top_change_rate", "condition_search", "top_volume", "sector_theme"]
            policy["condition_limit"] = 240
            cond_weight = 2.4
        elif normalized_playbook == "pullback":
            policy["preferred_sources"] = ["top_value", "condition_search", "sector_theme", "top_volume"]
            policy["condition_limit"] = 180
            cond_weight = 2.0
        elif normalized_playbook == "reversal":
            policy["preferred_sources"] = ["condition_search", "top_change_rate", "operator_watchlist", "top_volume"]
            policy["condition_limit"] = 220
            cond_weight = 2.2
        else:
            policy["preferred_sources"] = ["top_value", "top_volume", "condition_search", "sector_theme"]
            policy["condition_limit"] = 160
            cond_weight = 2.0
        policy["include_condition_search"] = True
        source_weights = dict(policy.get("source_weights") or {})
        source_weights["condition_search"] = cond_weight
        policy["source_weights"] = source_weights
        policy["reason"] = str(policy.get("reason") or "") + "; condition search explicitly enabled"

    return policy


def _report_focus(*, playbook: str, themes: List[str]) -> List[str]:
    if playbook == "defensive":
        return ["theme_accuracy", "exit_quality", "overtrading", "guard_blocks"]
    if playbook == "breakout":
        return ["theme_accuracy", "scanner_fit", "exit_quality", "overtrading"]
    return ["theme_accuracy", "scanner_fit", "exit_quality", "overtrading"]


def _augment_strategy_fields(
    *,
    themes: List[str],
    avoid_themes: List[str],
    scanner_priority: List[str],
    report_focus: List[str],
    market_context_inputs: Dict[str, float],
    news_ctx: Dict[str, Any],
) -> Tuple[List[str], List[str], List[str], List[str]]:
    out_themes = list(themes or [])
    out_avoid = list(avoid_themes or [])
    out_priority = list(scanner_priority or [])
    out_focus = list(report_focus or [])

    macro_risk = _to_float(market_context_inputs.get("macro_risk"), 0.0)
    realized_vol = _to_float(market_context_inputs.get("realized_volatility"), 0.0)
    fallback_n = int(news_ctx.get("fallback") or 0)
    unavailable_n = int(news_ctx.get("unavailable") or 0)

    if macro_risk >= 0.65 or realized_vol >= 0.045:
        for x in ("liquidity", "risk_penalty", "drawdown_control"):
            if x not in out_priority:
                out_priority.append(x)
        for x in ("high_gap_speculative", "illiquid_microcap"):
            if x not in out_avoid:
                out_avoid.append(x)
        if "guard_blocks" not in out_focus:
            out_focus.append("guard_blocks")

    if (fallback_n + unavailable_n) > 0:
        if "data_quality" not in out_focus:
            out_focus.append("data_quality")
        if "headline_only_momentum" not in out_avoid:
            out_avoid.append("headline_only_momentum")

    if not out_themes:
        out_themes = ["broad_market_leaders"]

    return out_themes[:5], out_avoid[:6], out_priority[:6], out_focus[:6]


def _key_events(
    *,
    state: Dict[str, Any],
    global_signal: Dict[str, Any],
    news_signal_map: Dict[str, Dict[str, Any]],
    market_regime: str,
    playbook: str,
    market_context_inputs: Dict[str, float],
    news_ctx: Dict[str, Any],
    theme_strength: Dict[str, float],
) -> List[str]:
    out: List[str] = []

    def add(x: Any) -> None:
        s = str(x or "").strip()
        if s and s not in out:
            out.append(s)

    # highest priority: explicit externally-provided macro/event list
    for key in ("macro_events", "global_events", "major_events"):
        vals = state.get(key)
        if isinstance(vals, list):
            for row in vals:
                add(row)
            break

    add(
        "global_sentiment "
        f"score={_signal_score(global_signal):.3f} "
        f"status={str(global_signal.get('status') or '')} "
        f"source={str(global_signal.get('source') or '')}"
    )
    components = global_signal.get("components") if isinstance(global_signal.get("components"), dict) else {}
    if components:
        add(
            "us_indices "
            f"sp500={_to_float(components.get('sp500_ret'), 0.0) * 100.0:.2f}% "
            f"nasdaq={_to_float(components.get('nasdaq_ret'), 0.0) * 100.0:.2f}% "
            f"dow={_to_float(components.get('dow_ret'), 0.0) * 100.0:.2f}%"
        )
    add(
        "market_context "
        f"index_trend={_to_float(market_context_inputs.get('index_trend'), 0.0):.3f} "
        f"breadth={_to_float(market_context_inputs.get('market_breadth'), 0.0):.3f} "
        f"realized_vol={_to_float(market_context_inputs.get('realized_volatility'), 0.0):.3f} "
        f"macro_risk={_to_float(market_context_inputs.get('macro_risk'), 0.0):.3f}"
    )
    add(
        "news_signal_health "
        f"ok={int(news_ctx.get('ok') or 0)} "
        f"unavailable={int(news_ctx.get('unavailable') or 0)} "
        f"fallback={int(news_ctx.get('fallback') or 0)} "
        f"avg_score={_to_float(news_ctx.get('avg_score'), 0.0):.3f}"
    )
    if theme_strength:
        top_theme = sorted(theme_strength.items(), key=lambda kv: kv[1], reverse=True)[0]
        add(f"theme_strength top={top_theme[0]} score={float(top_theme[1]):.3f}")
    add(f"market_regime={market_regime}")
    add(f"playbook={playbook}")

    return out[:5]


def _extract_ai_overrides(state: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    # External LLM strategists can inject this shape without breaking node contract.
    for key in ("ai_strategist_output", "strategist_ai_output", "strategic_brief"):
        raw = state.get(key)
        if isinstance(raw, dict):
            return dict(raw)
    raw_policy = policy.get("strategist_ai_output") if isinstance(policy.get("strategist_ai_output"), dict) else {}
    return dict(raw_policy)


def _merge_override_text_list(base: List[str], override_values: Any, *, limit: int = 8) -> List[str]:
    if not isinstance(override_values, list):
        return list(base)[:limit]
    merged: List[str] = []
    seen = set()
    for row in list(override_values) + list(base):
        s = str(row or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        merged.append(s)
        if len(merged) >= limit:
            break
    return merged


def _build_strategic_answers(
    *,
    market_regime: str,
    market_sentiment: str,
    key_events: List[str],
    themes: List[str],
    avoid_themes: List[str],
    playbook: str,
    scanner_bias: str,
    scanner_priority: List[str],
    trade_aggressiveness: str,
    risk_tone: str,
    monitor_guidance: str,
    report_focus: List[str],
) -> Dict[str, Any]:
    return {
        "q1_market_mode": market_regime,
        "q2_global_macro_events": list(key_events),
        "q3_leading_themes": list(themes),
        "q4_theme_strength_check": "use_scanner_score_breakdown_and_theme_boost",
        "q5_preferred_playbook": playbook,
        "q6_scanner_priority_stocks": list(scanner_priority),
        "q7_avoid_conditions": list(avoid_themes),
        "q8_trade_aggressiveness": trade_aggressiveness,
        "q9_risk_tone": risk_tone,
        "q10_scanner_ranking_priority": list(scanner_priority),
        "q11_monitor_exit_guidance": monitor_guidance,
        "q12_reporter_focus": list(report_focus),
        "scanner_bias": scanner_bias,
    }


def _make_event_logger(state: Dict[str, Any]) -> Any:
    injected = state.get("event_logger")
    if injected is not None and hasattr(injected, "log"):
        return injected
    from libs.core.event_logger import EventLogger, resolve_event_log_path

    return EventLogger(log_path=resolve_event_log_path())


def _log_strategist_summary(state: Dict[str, Any], payload: Dict[str, Any]) -> None:
    try:
        logger = _make_event_logger(state)
        run_id = str(state.get("run_id") or "strategist-node")
        logger.log(run_id=run_id, stage="strategist", event="summary", payload=dict(payload))
    except Exception:
        return


def _log_strategist_llm_result(state: Dict[str, Any], payload: Dict[str, Any]) -> None:
    try:
        logger = _make_event_logger(state)
        run_id = str(state.get("run_id") or "strategist-node")
        logger.log(run_id=run_id, stage="strategist_llm", event="result", payload=dict(payload))
    except Exception:
        return


def _sample_news_for_evidence(
    news_items_by_symbol: Dict[str, List[Any]],
    *,
    max_symbols: int = 8,
    max_items_per_symbol: int = 3,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for symbol, rows in list(news_items_by_symbol.items())[:max_symbols]:
        sample: List[Any] = []
        if isinstance(rows, list):
            for item in rows[:max_items_per_symbol]:
                if isinstance(item, dict):
                    sample.append(
                        {
                            "title": str(item.get("title") or ""),
                            "source": str(item.get("source") or ""),
                            "published_at": str(item.get("published_at") or ""),
                        }
                    )
                else:
                    sample.append(str(item))
        out[str(symbol)] = {"count": len(rows) if isinstance(rows, list) else 0, "sample": sample}
    return out


def _merge_news_samples(*samples: Dict[str, Any], limit: int = 12) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        for key, value in sample.items():
            if len(out) >= limit:
                return out
            norm_key = str(key or "").strip()
            if not norm_key or norm_key in out:
                continue
            out[norm_key] = value
    return out


def strategist_node(state: Dict[str, Any]) -> Dict[str, Any]:
    policy = _default_policy(state.get("policy"))
    k = _resolve_top_n_candidates(policy)
    policy["candidate_k"] = int(k)

    # 1) candidates (injected or generated)
    candidates = _candidates_from_state(state, k)
    universe_candidates: List[Dict[str, Any]] = []

    if not candidates:
        if bool(policy.get("use_universe_builder", True)):
            universe_candidates = build_candidate_universe(state=state, policy=policy, topk=k)
            if universe_candidates:
                candidates = [
                    {
                        "symbol": str(r.get("symbol") or ""),
                        "why": str(r.get("why") or "universe_builder"),
                        "sources": list(r.get("sources") or []),
                        "universe_score": float(r.get("score") or 0.0),
                        "source_scores": dict(r.get("source_scores") or {}),
                        "source_count": int(r.get("source_count") or len(list(r.get("sources") or []))),
                    }
                    for r in universe_candidates
                    if str(r.get("symbol") or "").strip()
                ]

    if not candidates:
        source = str(policy.get("candidate_source") or "top_picks")
        if source == "market_rank":
            gen = MarketRankCandidateGenerator()
            # tolerate signature differences
            try:
                symbols = gen.generate(state=state, policy=policy, k=k)
            except TypeError:
                try:
                    symbols = gen.generate(state=state, k=k)
                except TypeError:
                    symbols = gen.generate(state=state)
            candidates = [{"symbol": str(s), "why": "market_rank"} for s in symbols[:k]]
        else:
            # top_picks (M18-2): generator signature is generate(state)
            gen = TopPicksCandidateGenerator(
                rank_mode=str(policy.get("candidate_rank_mode") or "value"),
                rank_topn=int(policy.get("candidate_rank_topn") or 30),
                topk=int(policy.get("candidate_topk") or k),
            )
            symbols = gen.generate(state=state)
            candidates = [{"symbol": str(s), "why": "top_picks"} for s in symbols[:k]]

    # Absolute fallback:
    # - source is configurable (`fallback_candidate_symbols`, `FALLBACK_CANDIDATE_SYMBOLS`)
    # - static default remains as last-resort compatibility path
    if not candidates:
        fallback, fallback_source = resolve_fallback_symbols(state=state, policy=policy, limit=k)
        fallback_why = "fallback_static" if fallback_source == "static_default" else "fallback_configured"
        candidates = [{"symbol": s, "why": fallback_why, "fallback_source": fallback_source} for s in fallback]
        state["strategist_fallback_source"] = fallback_source

    state["universe_candidates"] = universe_candidates
    symbols = [c["symbol"] for c in candidates]

    # 2) Global sentiment (score + data-quality signal)
    now = int(time.time())
    global_enabled = bool(policy.get("use_global_sentiment", True)) or state.get("mock_global_sentiment") is not None
    if global_enabled:
        try:
            global_signal = dict(compute_global_sentiment_signal(state=state, policy=policy))
        except Exception:
            global_signal = make_signal(
                score=0.0,
                status=SIGNAL_STATUS_FALLBACK,
                source="strategist_node",
                reason="global_sentiment_exception",
                ts=now,
            )
    else:
        global_signal = make_signal(
            score=0.0,
            status=SIGNAL_STATUS_FALLBACK,
            source="global_policy",
            reason="global_sentiment_disabled",
            ts=now,
        )
    gs = _signal_score(global_signal)
    policy["global_sentiment"] = float(gs)
    # Keep canonical state-level score and signal shape for downstream nodes.
    state["global_sentiment"] = {"score": float(gs)}
    state["global_sentiment_signal"] = dict(global_signal)
    market_context_inputs = _extract_market_context_inputs(state)
    theme_hints = _extract_themes(state, policy)
    news_query_targets = _build_market_news_query_targets(
        state=state,
        policy=policy,
        global_signal=global_signal,
        market_context_inputs=market_context_inputs,
        theme_hints=theme_hints,
    )
    news_query_reasoning = _build_market_news_query_reasoning(
        state=state,
        policy=policy,
        global_signal=global_signal,
        market_context_inputs=market_context_inputs,
        theme_hints=theme_hints,
    )
    state["news_query_targets"] = list(news_query_targets)
    state["news_query_reasoning"] = news_query_reasoning

    # policy adjustment based on global sentiment
    # - risk-off: max_risk decreases, min_confidence increases
    # - risk-on : max_risk increases, min_confidence decreases
    base_max_risk = float(policy.get("max_risk", 0.7))
    base_min_conf = float(policy.get("min_confidence", 0.6))
    off_th = float(policy.get("candidate_risk_off_threshold", -0.5))
    on_th = float(policy.get("candidate_risk_on_threshold", 0.5))

    if gs <= off_th:
        policy["max_risk"] = max(0.05, base_max_risk - 0.1)
        policy["min_confidence"] = min(0.99, base_min_conf + 0.1)
    elif gs >= on_th:
        policy["max_risk"] = min(1.0, base_max_risk + 0.1)
        policy["min_confidence"] = max(0.01, base_min_conf - 0.1)
    else:
        policy["max_risk"] = base_max_risk
        policy["min_confidence"] = base_min_conf

    # 3) News analysis (score + data-quality signal)
    news_items_by_symbol = {s: [] for s in symbols}
    news_signal_map: Dict[str, Dict[str, Any]] = {}
    market_news_items_by_target = {q: [] for q in news_query_targets}
    market_news_signal_map: Dict[str, Dict[str, Any]] = {}

    if bool(policy.get("use_news_analysis", False)) or state.get("mock_news_sentiment") is not None:
        # mock_news_sentiment path is handled inside score_news_sentiment_signal.
        if bool(policy.get("use_news_analysis", False)) or state.get("mock_news_items") is not None:
            if symbols:
                news_items_by_symbol = collect_news_items(symbols, state=state, policy=policy)
            if news_query_targets:
                market_news_items_by_target = collect_news_items(news_query_targets, state=state, policy=policy)
        try:
            if symbols:
                news_signal_map = score_news_sentiment_signal(
                    news_items_by_symbol,
                    state=state,
                    policy=policy,
                    symbols=symbols,
                )
            else:
                news_signal_map = {}
            if news_query_targets:
                market_news_signal_map = score_news_sentiment_signal(
                    market_news_items_by_target,
                    state=state,
                    policy=policy,
                    symbols=news_query_targets,
                )
            else:
                market_news_signal_map = {}
        except Exception:
            news_signal_map = {
                s: make_signal(
                    score=0.0,
                    status=SIGNAL_STATUS_FALLBACK,
                    source="strategist_node",
                    reason="news_sentiment_exception",
                    ts=now,
                )
                for s in symbols
            }
            market_news_signal_map = {
                q: make_signal(
                    score=0.0,
                    status=SIGNAL_STATUS_FALLBACK,
                    source="strategist_node",
                    reason="market_news_sentiment_exception",
                    ts=now,
                )
                for q in news_query_targets
            }
    else:
        news_signal_map = {
            s: make_signal(
                score=0.0,
                status=SIGNAL_STATUS_FALLBACK,
                source="news_policy",
                reason="news_analysis_disabled",
                ts=now,
                )
                for s in symbols
        }
        market_news_signal_map = {
            q: make_signal(
                score=0.0,
                status=SIGNAL_STATUS_FALLBACK,
                source="news_policy",
                reason="news_analysis_disabled",
                ts=now,
            )
            for q in news_query_targets
        }

    news_sent = {s: _signal_score(news_signal_map.get(s)) for s in symbols}
    candidate_news_ctx = _news_context_summary(news_signal_map, news_items_by_symbol)
    market_news_ctx = _news_context_summary(market_news_signal_map, market_news_items_by_target)
    news_ctx = _merge_news_contexts(candidate_news_ctx, market_news_ctx)
    news_avg_score = _to_float(news_ctx.get("avg_score"), 0.0)

    state["policy"] = policy
    state["candidates"] = candidates
    # store per-symbol news items (dict)
    state["news_items"] = news_items_by_symbol
    state["news_sentiment"] = news_sent
    state["news_sentiment_signal"] = news_signal_map
    state["candidate_news_items"] = dict(news_items_by_symbol)
    state["candidate_news_context"] = dict(candidate_news_ctx)
    state["market_news_items"] = dict(market_news_items_by_target)
    state["market_news_sentiment"] = {q: _signal_score(market_news_signal_map.get(q)) for q in news_query_targets}
    state["market_news_sentiment_signal"] = dict(market_news_signal_map)
    state["market_news_context"] = dict(market_news_ctx)

    # 4) Candidate rerank (M18-5): apply weights and negative-news filter, then risk-off count reduction
    w_news = float(policy.get("candidate_news_weight", 0.2))
    w_g = float(policy.get("candidate_global_weight", 0.1))
    neg_th = float(policy.get("candidate_negative_news_threshold", -0.7))

    # assign candidate_score
    scored = []
    candidate_meta = {str(c.get("symbol")): dict(c) for c in candidates if isinstance(c, dict)}
    for idx, c in enumerate(candidates):
        s = c["symbol"]
        rank_bias = (len(candidates) - idx) / max(len(candidates), 1) * 0.01  # small deterministic tie-break
        cs = rank_bias + (w_news * news_sent.get(s, 0.0)) + (w_g * gs)
        scored.append((s, cs, news_sent.get(s, 0.0), c.get("why") or ""))

    # filter overly negative news, but don't drop below 3 items if possible
    filtered = [t for t in scored if t[2] >= neg_th]
    if len(filtered) >= 3:
        scored = filtered

    scored.sort(key=lambda x: x[1], reverse=True)
    candidates = []
    for (s, cs, _ns, why) in scored:
        base = dict(candidate_meta.get(s) or {})
        base["symbol"] = s
        base["why"] = why
        base["rank_score"] = float(cs)
        candidates.append(base)

    # risk-off reduces count
    if gs <= float(policy.get("candidate_risk_off_threshold", -0.5)):
        max_cnt = int(policy.get("candidate_max_count_risk_off", 3))
        candidates = candidates[: max(1, max_cnt)]
    else:
        candidates = candidates[:k]

    state["candidates"] = candidates
    themes = list(theme_hints)
    pre_ai_overrides = _extract_ai_overrides(state, policy)
    themes = _merge_override_text_list(themes, pre_ai_overrides.get("themes"), limit=5)
    candidate_symbols = [str(c.get("symbol") or "") for c in candidates if str(c.get("symbol") or "").strip()]
    theme_index = _extract_theme_symbol_index(state, policy)
    theme_scores = state.get("theme_scores") if isinstance(state.get("theme_scores"), dict) else {}
    theme_strength = _theme_strength_map(
        themes=list(themes),
        candidates=list(candidates),
        theme_scores=theme_scores,
        theme_index=theme_index,
    )
    if theme_strength:
        ranked_theme_names = [k for k, _v in sorted(theme_strength.items(), key=lambda kv: kv[1], reverse=True)]
        themes = _merge_override_text_list(ranked_theme_names, themes, limit=5)

    state["themes"] = themes
    state["candidate_symbols"] = list(candidate_symbols)
    state["theme_map"] = _merge_theme_symbol_map(
        state.get("theme_map"),
        themes=list(themes),
        candidate_symbols=list(candidate_symbols),
    )
    state["sector_map"] = _merge_theme_symbol_map(
        state.get("sector_map"),
        themes=list(themes),
        candidate_symbols=list(candidate_symbols),
    )

    regime_score = _compose_regime_score(
        global_score=gs,
        news_score=news_avg_score,
        market_context_inputs=market_context_inputs,
    )
    sentiment_score = float(
        _clamp(
            (0.60 * gs)
            + (0.30 * _to_float(news_ctx.get("avg_score"), 0.0))
            + (0.10 * _to_float(market_context_inputs.get("index_trend"), 0.0)),
            -1.0,
            1.0,
        )
    )
    market_regime = _risk_regime_label(regime_score)
    market_sentiment = _market_sentiment_label(sentiment_score)
    market_structure, regime_factors = _market_structure_label(
        state=state,
        global_score=gs,
        market_context_inputs=market_context_inputs,
    )
    playbook = _pick_playbook(
        market_structure=market_structure,
        market_regime=market_regime,
        market_sentiment=market_sentiment,
    )
    scanner_priority = _scanner_priority(playbook, market_regime)
    scanner_bias = _scanner_bias(playbook=playbook, market_regime=market_regime)
    avoid_themes = _avoid_themes(market_sentiment=market_sentiment, playbook=playbook)
    trade_aggressiveness = _trade_aggressiveness(market_regime=market_regime, market_structure=market_structure)
    risk_tone = _risk_tone(trade_aggressiveness)
    monitor_guidance = _monitor_guidance(market_regime=market_regime, playbook=playbook)
    monitor_policy = _monitor_policy(
        monitor_guidance=monitor_guidance,
        trade_aggressiveness=trade_aggressiveness,
        risk_tone=risk_tone,
    )
    exit_policy = _exit_policy(
        playbook=playbook,
        monitor_guidance=monitor_guidance,
        trade_aggressiveness=trade_aggressiveness,
        risk_tone=risk_tone,
    )
    report_focus = _report_focus(playbook=playbook, themes=themes)
    themes, avoid_themes, scanner_priority, report_focus = _augment_strategy_fields(
        themes=themes,
        avoid_themes=avoid_themes,
        scanner_priority=scanner_priority,
        report_focus=report_focus,
        market_context_inputs=market_context_inputs,
        news_ctx=news_ctx,
    )
    key_events = _key_events(
        state=state,
        global_signal=global_signal,
        news_signal_map=news_signal_map,
        market_regime=market_regime,
        playbook=playbook,
        market_context_inputs=market_context_inputs,
        news_ctx=news_ctx,
        theme_strength=theme_strength,
    )

    llm_payload = {
        "global_sentiment_signal": dict(global_signal),
        "news_context": dict(news_ctx),
        "market_context_inputs": dict(market_context_inputs),
        "market_regime_hint": market_regime,
        "market_sentiment_hint": market_sentiment,
        "market_structure_hint": market_structure,
        "playbook_hint": playbook,
        "theme_strength": dict(theme_strength),
        "themes_hint": list(themes),
        "news_query_targets": list(news_query_targets),
        "market_news_sample": _sample_news_for_evidence(
            market_news_items_by_target,
            max_symbols=6,
            max_items_per_symbol=2,
        ),
        "candidate_news_sample": _sample_news_for_evidence(
            news_items_by_symbol,
            max_symbols=6,
            max_items_per_symbol=2,
        ),
        "candidate_symbols_hint": list(candidate_symbols)[:10],
        "key_events_hint": list(key_events),
    }
    candidate_news_sample = _sample_news_for_evidence(news_items_by_symbol)
    market_news_sample = _sample_news_for_evidence(market_news_items_by_target)
    try:
        record_raw_input(
            run_id=str(state.get("run_id") or "strategist-unknown"),
            agent="strategist",
            stage="theme_selection",
            raw_input={
                "collected_news": _merge_news_samples(market_news_sample, candidate_news_sample),
                "collected_market_news": market_news_sample,
                "collected_candidate_news": candidate_news_sample,
                "news_query_targets": list(news_query_targets),
                "global_sentiment_inputs": dict(global_signal),
                "macro_indicators": dict(market_context_inputs),
                "market_summary": {
                    "market_regime_hint": market_regime,
                    "market_sentiment_hint": market_sentiment,
                    "market_structure_hint": market_structure,
                    "news_query_targets": list(news_query_targets),
                    "news_query_reasoning": news_query_reasoning,
                    "candidate_symbols_hint": list(candidate_symbols)[:10],
                },
                "llm_payload": dict(llm_payload),
            },
            decision_link={"stage": "strategist_input_collection"},
        )
    except Exception:
        pass
    llm_overrides, llm_meta = _run_strategist_frame_llm(state=state, policy=policy, payload=llm_payload)
    manual_overrides = _extract_ai_overrides(state, policy)
    ai_overrides = {**dict(llm_overrides or {}), **dict(manual_overrides or {})}

    if _resolve_strategist_frame_llm_enabled(policy):
        llm_payload_log: Dict[str, Any] = {
            "provider": "openrouter",
            "model": str(llm_meta.get("model") or ""),
            "ok": str(llm_meta.get("status") or "") == "ok",
            "status": str(llm_meta.get("status") or ""),
            "latency_ms": int(llm_meta.get("latency_ms") or 0),
            "attempts": int(llm_meta.get("attempts") or 1),
            "repair_used": bool(llm_meta.get("repair_used")),
            "prompt_version": str(os.getenv("STRATEGIST_FRAME_LLM_PROMPT_VERSION", "m31-strategic-frame-v1") or "m31-strategic-frame-v1"),
            "schema_version": "strategist_output.v1",
            "themes": list((llm_overrides or {}).get("themes") or [])[:5],
            "avoid_themes": list((llm_overrides or {}).get("avoid_themes") or [])[:5],
            "playbook": str((llm_overrides or {}).get("playbook") or ""),
            "scanner_bias": str((llm_overrides or {}).get("scanner_bias") or ""),
            "risk_tone": str((llm_overrides or {}).get("risk_tone") or ""),
            "monitor_guidance": str((llm_overrides or {}).get("monitor_guidance") or ""),
            "candidate_hint_count": len(list(candidate_symbols)),
        }
        if llm_meta.get("reason"):
            llm_payload_log["error"] = str(llm_meta.get("reason"))
        if llm_meta.get("error_type"):
            llm_payload_log["error_type"] = str(llm_meta.get("error_type"))
        _log_strategist_llm_result(state, llm_payload_log)

    # Optional AI overrides are additive and bounded to keep deterministic fallback.
    market_regime = str(ai_overrides.get("market_regime") or market_regime).strip() or market_regime
    market_sentiment = str(ai_overrides.get("market_sentiment") or market_sentiment).strip() or market_sentiment
    playbook = str(ai_overrides.get("playbook") or playbook).strip() or playbook
    trade_aggressiveness = str(ai_overrides.get("trade_aggressiveness") or trade_aggressiveness).strip() or trade_aggressiveness
    risk_tone = str(ai_overrides.get("risk_tone") or risk_tone).strip() or risk_tone
    if isinstance(ai_overrides.get("themes"), list) and list(ai_overrides.get("themes") or []):
        themes = _merge_override_text_list([], ai_overrides.get("themes"), limit=5)
    else:
        themes = _merge_override_text_list(themes, ai_overrides.get("themes"), limit=5)
    key_events = _merge_override_text_list(key_events, ai_overrides.get("key_events"), limit=5)
    avoid_themes = _merge_override_text_list(avoid_themes, ai_overrides.get("avoid_themes"), limit=6)
    scanner_priority = _merge_override_text_list(scanner_priority, ai_overrides.get("scanner_priority"), limit=6)
    report_focus = _merge_override_text_list(report_focus, ai_overrides.get("report_focus"), limit=6)
    scanner_bias = str(ai_overrides.get("scanner_bias") or scanner_bias).strip().lower() or scanner_bias
    monitor_guidance = str(ai_overrides.get("monitor_guidance") or monitor_guidance).strip().lower() or monitor_guidance
    monitor_policy_override = ai_overrides.get("monitor_policy")
    if isinstance(monitor_policy_override, dict):
        monitor_policy = {**monitor_policy, **dict(monitor_policy_override)}
    else:
        monitor_policy = _monitor_policy(
            monitor_guidance=monitor_guidance,
            trade_aggressiveness=trade_aggressiveness,
            risk_tone=risk_tone,
        )
    exit_policy_override = ai_overrides.get("exit_policy")
    if isinstance(exit_policy_override, dict):
        exit_policy = {**exit_policy, **dict(exit_policy_override)}
    else:
        exit_policy = _exit_policy(
            playbook=playbook,
            monitor_guidance=monitor_guidance,
            trade_aggressiveness=trade_aggressiveness,
            risk_tone=risk_tone,
        )
    scanner_source_policy = _scanner_source_policy(
        playbook=playbook,
        risk_tone=risk_tone,
        trade_aggressiveness=trade_aggressiveness,
        market_regime=market_regime,
        themes=list(themes),
    )

    if isinstance(ai_overrides.get("themes"), list) and list(ai_overrides.get("themes") or []):
        # Keep runtime theme/sector maps aligned with the final strategist frame
        # only when AI/manual overrides actually replace themes. Unconditionally
        # syncing broad fallback themes makes scanner sector-theme sourcing too
        # aggressive in deterministic baseline paths.
        state["theme_map"] = _merge_theme_symbol_map(
            state.get("theme_map"),
            themes=list(themes),
            candidate_symbols=list(state.get("candidate_symbols") or []),
        )
        state["sector_map"] = _merge_theme_symbol_map(
            state.get("sector_map"),
            themes=list(themes),
            candidate_symbols=list(state.get("candidate_symbols") or []),
        )

    strategic_answers = _build_strategic_answers(
        market_regime=market_regime,
        market_sentiment=market_sentiment,
        key_events=key_events,
        themes=themes,
        avoid_themes=avoid_themes,
        playbook=playbook,
        scanner_bias=scanner_bias,
        scanner_priority=scanner_priority,
        trade_aggressiveness=trade_aggressiveness,
        risk_tone=risk_tone,
        monitor_guidance=monitor_guidance,
        report_focus=report_focus,
    )

    state["market_regime"] = market_regime
    state["market_sentiment"] = market_sentiment
    state["market_structure"] = market_structure
    state["market_context_inputs"] = dict(market_context_inputs)
    state["regime_factors"] = dict(regime_factors)
    state["theme_strength"] = dict(theme_strength)
    state["key_events"] = list(key_events)
    state["avoid_themes"] = list(avoid_themes)
    state["playbook"] = playbook
    state["scanner_bias"] = scanner_bias
    state["scanner_priority"] = list(scanner_priority)
    state["trade_aggressiveness"] = trade_aggressiveness
    state["risk_tone"] = risk_tone
    state["monitor_guidance"] = monitor_guidance
    state["monitor_policy"] = dict(monitor_policy)
    state["strategist_exit_policy"] = dict(exit_policy)
    state["report_focus"] = list(report_focus)
    state["scanner_guidance"] = {
        "themes": list(themes),
        "avoid_themes": list(avoid_themes),
        "playbook": playbook,
        "scanner_bias": scanner_bias,
        "scanner_priority": list(scanner_priority),
        "scanner_source_policy": dict(scanner_source_policy),
        "trade_aggressiveness": trade_aggressiveness,
        "risk_tone": risk_tone,
    }
    strategist_output = StrategistOutput(
        market_regime=market_regime,
        market_sentiment=market_sentiment,
        key_events=list(key_events),
        themes=list(themes),
        avoid_themes=list(avoid_themes),
        playbook=playbook,
        scanner_bias=scanner_bias if scanner_bias in ("large_cap", "leader", "momentum", "value") else "leader",
        scanner_priority=list(scanner_priority),
        scanner_source_policy=dict(scanner_source_policy),
        trade_aggressiveness=trade_aggressiveness,
        risk_tone=risk_tone if risk_tone in ("conservative", "normal", "aggressive") else "normal",
        monitor_guidance=(
            monitor_guidance
            if monitor_guidance in ("hold_through_noise", "defensive_exit", "quick_take_profit")
            else "defensive_exit"
        ),
        report_focus=list(report_focus),
        candidates=list(state["candidate_symbols"]),
        candidate_count=len(list(state["candidate_symbols"])),
        candidate_hints=list(state["candidate_symbols"]),
        strategic_answers=dict(strategic_answers),
        source="strategist_node",
    ).to_dict()
    strategist_output["monitor_policy"] = dict(monitor_policy)
    strategist_output["exit_policy"] = dict(exit_policy)
    strategist_output["market_structure"] = market_structure
    strategist_output["regime_score"] = float(regime_score)
    strategist_output["sentiment_score"] = float(sentiment_score)
    strategist_output["news_context"] = dict(news_ctx)
    strategist_output["candidate_news_context"] = dict(candidate_news_ctx)
    strategist_output["market_news_context"] = dict(market_news_ctx)
    strategist_output["news_query_targets"] = list(news_query_targets)
    strategist_output["news_query_reasoning"] = news_query_reasoning
    strategist_output["market_context_inputs"] = dict(market_context_inputs)
    strategist_output["theme_strength"] = dict(theme_strength)
    strategist_output["playbook"] = playbook
    strategist_output["llm_frame_status"] = str(llm_meta.get("status") or "disabled")
    strategist_output["llm_frame_applied"] = bool(llm_overrides)
    strategist_output["llm_frame_model"] = str(llm_meta.get("model") or "")
    strategist_output["runtime_theme_map_keys"] = sorted(list((state.get("theme_map") or {}).keys()))
    strategist_output["runtime_sector_map_keys"] = sorted(list((state.get("sector_map") or {}).keys()))
    state["strategist_output"] = strategist_output
    state["strategist_llm"] = {
        "status": str(llm_meta.get("status") or "disabled"),
        "model": str(llm_meta.get("model") or ""),
        "applied": bool(llm_overrides),
        "latency_ms": int(llm_meta.get("latency_ms") or 0),
        "attempts": int(llm_meta.get("attempts") or 1),
        "repair_used": bool(llm_meta.get("repair_used")),
        "reason": str(llm_meta.get("reason") or ""),
        "error": str(llm_meta.get("reason") or ""),
    }
    _log_strategist_summary(
        state,
        {
            "market_regime": market_regime,
            "market_sentiment": market_sentiment,
            "themes": list(themes),
            "avoid_themes": list(avoid_themes),
            "playbook": playbook,
            "scanner_bias": scanner_bias,
            "scanner_priority": list(scanner_priority),
            "scanner_source_policy": dict(scanner_source_policy),
            "trade_aggressiveness": trade_aggressiveness,
            "risk_tone": risk_tone,
            "monitor_guidance": monitor_guidance,
            "candidate_count": len(list(state["candidate_symbols"])),
            "regime_score": float(regime_score),
            "sentiment_score": float(sentiment_score),
            "report_focus": list(report_focus)[:3],
            "news_query_targets": list(news_query_targets)[:6],
            "news_query_reasoning": news_query_reasoning,
            "llm_frame_status": str(llm_meta.get("status") or "disabled"),
            "llm_frame_applied": bool(llm_overrides),
            "llm_frame_model": str(llm_meta.get("model") or ""),
        },
    )
    append_decision_trace(
        state,
        agent="strategist",
        event="strategic_frame",
        payload={
            "market_regime": market_regime,
            "market_sentiment": market_sentiment,
            "themes": list(themes)[:5],
            "avoid_themes": list(avoid_themes)[:5],
            "playbook": playbook,
            "scanner_bias": scanner_bias,
            "scanner_priority": list(scanner_priority)[:5],
            "scanner_source_policy": dict(scanner_source_policy),
            "trade_aggressiveness": trade_aggressiveness,
            "risk_tone": risk_tone,
            "monitor_guidance": monitor_guidance,
            "report_focus": list(report_focus)[:5],
            "news_query_targets": list(news_query_targets)[:6],
            "news_query_reasoning": news_query_reasoning,
            "regime_score": float(regime_score),
            "sentiment_score": float(sentiment_score),
            "key_events": list(key_events)[:3],
            "llm_frame_status": str(llm_meta.get("status") or "disabled"),
            "llm_frame_applied": bool(llm_overrides),
            "llm_frame_model": str(llm_meta.get("model") or ""),
        },
    )
    try:
        record_decision_bridge(
            run_id=str(state.get("run_id") or "strategist-unknown"),
            agent="strategist",
            stage="decision_bridge",
            parsed_output={
                "market_regime": market_regime,
                "market_sentiment": market_sentiment,
                "themes": list(themes),
                "avoid_themes": list(avoid_themes),
                "playbook": playbook,
                "scanner_bias": scanner_bias,
                "scanner_priority": list(scanner_priority),
                "scanner_source_policy": dict(scanner_source_policy),
                "trade_aggressiveness": trade_aggressiveness,
                "risk_tone": risk_tone,
                "monitor_guidance": monitor_guidance,
                "report_focus": list(report_focus),
                "news_query_targets": list(news_query_targets),
                "news_query_reasoning": news_query_reasoning,
                "candidate_symbols": list(state.get("candidate_symbols") or []),
            },
            decision_link={
                "decision_chain": {
                    "theme": (list(themes)[0] if list(themes) else ""),
                    "candidate_symbols": list(state.get("candidate_symbols") or []),
                }
            },
        )
    except Exception:
        pass
    return state
