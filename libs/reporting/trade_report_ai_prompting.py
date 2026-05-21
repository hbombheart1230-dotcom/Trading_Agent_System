from __future__ import annotations

import json
from typing import Any, Callable, Dict, List

from libs.llm.json_response import parse_llm_json_response
from libs.reporting.trade_report_common import (
    compact_scalar_dict,
    listify,
    report_clip,
)


def as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def trade_report_output_template() -> Dict[str, Any]:
    return {
        "executive_summary": {"headline": "", "summary": ""},
        "market_context_at_entry": {"summary": "", "bullets": [""]},
        "strategist_summary": {"summary": "", "bullets": [""]},
        "strategist_refresh_trace": {"summary": "", "bullets": [""], "stages": []},
        "why_this_symbol_was_chosen": {"summary": "", "bullets": [""]},
        "entry_decision": {"summary": "", "bullets": [""]},
        "holding_monitoring_story": {"summary": "", "bullets": [""]},
        "exit_decision": {"summary": "", "bullets": [""]},
        "execution_quality": {"summary": "", "bullets": [""]},
        "scanner_filters": {"summary": "", "bullets": [""]},
        "guard_approval_result": {"summary": "", "bullets": [""]},
        "reporter_evaluation": {"summary": "", "bullets": [""]},
        "errors_weaknesses_improvement_points": {"summary": "", "bullets": [""]},
        "final_operator_conclusion": {"summary": "", "watch_next": [""], "thesis_invalidation": [""]},
    }


def prompt_story_input_for_llm(
    compact_input: Dict[str, Any],
    *,
    compact_section_seed_for_llm: Callable[[Any], Dict[str, Any]],
) -> Dict[str, Any]:
    data = compact_input if isinstance(compact_input, dict) else {}
    market = as_dict(data.get("market_context"))
    commander = as_dict(data.get("commander"))
    scanner = as_dict(data.get("scanner"))
    monitor = as_dict(data.get("monitor"))
    entry_visibility = as_dict(data.get("entry_execution_visibility"))
    seeds = as_dict(data.get("report_section_seeds"))
    return {
        "trade_id": data.get("trade_id"),
        "run_id": data.get("run_id"),
        "symbol": data.get("symbol"),
        "action": data.get("action"),
        "status": data.get("status"),
        "execution_mode_label": data.get("execution_mode_label"),
        "strategist_output": as_dict(data.get("strategist_output")),
        "market_context": {
            "regime": market.get("regime"),
            "market_sentiment": market.get("market_sentiment"),
            "risk_mode": market.get("risk_mode"),
            "selected_playbook": market.get("selected_playbook"),
            "global_sentiment_score": market.get("global_sentiment_score"),
            "vix_level": market.get("vix_level"),
            "preferred_themes": listify(market.get("preferred_themes"), max_items=3, max_len=60),
            "avoid_themes": listify(market.get("avoid_themes"), max_items=3, max_len=60),
            "market_headlines": listify(market.get("market_headlines"), max_items=2, max_len=140),
            "symbol_headlines": listify(market.get("symbol_headlines"), max_items=2, max_len=140),
            "key_events": listify(market.get("key_events"), max_items=2, max_len=140),
        },
        "commander": {
            "command_intent": commander.get("command_intent"),
            "selected_route": commander.get("selected_route"),
            "route_reason_text": commander.get("route_reason_text"),
            "policy_source": commander.get("policy_source"),
            "strategist_cache_used": commander.get("strategist_cache_used"),
            "strategist_called": commander.get("strategist_called"),
            "entry_control": as_dict(commander.get("entry_control")),
        },
        "entry": as_dict(data.get("entry")),
        "scanner": {
            "selected_symbol": scanner.get("selected_symbol"),
            "selected_rank": scanner.get("selected_rank"),
            "universe_size": scanner.get("universe_size"),
            "ranking_basis": scanner.get("ranking_basis"),
            "playbook": scanner.get("playbook"),
            "policy_source": scanner.get("policy_source"),
            "confidence": scanner.get("confidence"),
            "top_reasons": listify(scanner.get("top_reasons"), max_items=3, max_len=120),
            "why_selected": listify(scanner.get("why_selected"), max_items=3, max_len=120),
            "selection_basis": scanner.get("selection_basis"),
            "selection_reason_with_bias": report_clip(scanner.get("selection_reason_with_bias"), max_len=180),
            "runner_ups": listify(scanner.get("runner_ups"), max_items=2, max_len=120),
            "runner_ups_lost": listify(scanner.get("runner_ups_lost"), max_items=2, max_len=160),
            "selection_trace": {
                "ranked_candidates": listify(
                    as_dict(scanner.get("selection_trace")).get("ranked_candidates"),
                    max_items=3,
                    max_len=160,
                ),
                "selected_symbol": as_dict(scanner.get("selection_trace")).get("selected_symbol"),
                "selected_rank": as_dict(scanner.get("selection_trace")).get("selected_rank"),
                "selection_reason": report_clip(as_dict(scanner.get("selection_trace")).get("selection_reason"), max_len=180),
                "selected_symbol_score_drivers": compact_scalar_dict(
                    as_dict(scanner.get("selection_trace")).get("selected_symbol_score_drivers"),
                    max_items=5,
                    max_len=80,
                ),
            },
        },
        "holding": as_dict(data.get("holding")),
        "monitor": {
            "posture": monitor.get("posture"),
            "trigger_type": monitor.get("trigger_type"),
            "summary": report_clip(monitor.get("summary"), max_len=220),
            "entry_check_summary": report_clip(monitor.get("entry_check_summary"), max_len=180),
            "entry_blockers": listify(monitor.get("entry_blockers"), max_items=5, max_len=100),
            "threshold_shortfalls": listify(monitor.get("threshold_shortfalls"), max_items=3, max_len=120),
            "decision_reason_chain": listify(monitor.get("decision_reason_chain"), max_items=5, max_len=80),
            "confirm_required": monitor.get("confirm_required"),
            "confirm_count": monitor.get("confirm_count"),
            "effective_policy_deltas": listify(monitor.get("effective_policy_deltas"), max_items=5, max_len=100),
            "position_age_seconds": monitor.get("position_age_seconds"),
            "effective_stop_loss_pct": monitor.get("effective_stop_loss_pct"),
            "take_profit_pct": monitor.get("take_profit_pct"),
            "trailing_stop_pct": monitor.get("trailing_stop_pct"),
            "current_price": monitor.get("current_price"),
            "average_price": monitor.get("average_price"),
            "peak_price": monitor.get("peak_price"),
            "current_drawdown": monitor.get("current_drawdown"),
            "active_exit_axis": monitor.get("active_exit_axis"),
            "watch_axes": listify(monitor.get("watch_axes"), max_items=4, max_len=80),
            "price_source": monitor.get("price_source"),
            "monitor_stop_policy_trace": compact_scalar_dict(monitor.get("monitor_stop_policy_trace"), max_items=6, max_len=80),
            "entry_candidate_cascade": as_dict(monitor.get("entry_candidate_cascade")),
        },
        "entry_execution_visibility": entry_visibility,
        "exit": as_dict(data.get("exit")),
        "guard": as_dict(data.get("guard")),
        "execution": as_dict(data.get("execution")),
        "reporter": as_dict(data.get("reporter")),
        "operator_conclusion": as_dict(data.get("operator_conclusion")),
        "section_seed_summaries": {
            key: compact_section_seed_for_llm(value)
            for key, value in seeds.items()
            if key
        },
        "timeline": listify(data.get("timeline"), max_items=4, max_len=180),
        "improvement_points": listify(data.get("improvement_points"), max_items=4, max_len=120),
        "ai_report_diagnostics": as_dict(data.get("ai_report_diagnostics")),
    }


def build_concise_trade_report_messages(
    compact_input: Dict[str, Any],
    contract: Dict[str, Any],
    *,
    korean_rules: str,
    compact_section_seed_for_llm: Callable[[Any], Dict[str, Any]],
    partial_note: str = "",
    previous_response_text: str = "",
    repair: bool = False,
    enforce_korean: bool = False,
) -> List[Dict[str, str]]:
    prompt_input = prompt_story_input_for_llm(
        compact_input,
        compact_section_seed_for_llm=compact_section_seed_for_llm,
    )
    mode_label = "복구 모드" if repair else "작성 모드"
    korean_note = ""
    if enforce_korean:
        korean_note = "\n최종 JSON을 반환하기 전에 남아 있는 영어 설명 문장을 모두 한국어로 번역하십시오."
    previous_note = ""
    if repair:
        previous_note = f"\n이전 응답:\n{previous_response_text}\n"
    return [
        {
            "role": "system",
            "content": (
                "당신은 트레이딩 시스템의 사후 거래 리포트 narrative editor입니다. "
                "반드시 JSON 객체 하나만 반환하십시오. 설명문, 사고 과정, markdown, code fence, 계획 문장은 절대 쓰지 마십시오. "
                "trade lifecycle retrospective만 작성하고, 숫자, 이벤트, 이유, evidence를 지어내지 마십시오. "
                f"{korean_rules} "
                "값을 모르면 빈 문자열, 빈 리스트, null을 사용하십시오."
            ),
        },
        {
            "role": "user",
            "content": (
                f"{mode_label}: 아래 compact input과 출력 템플릿만 사용해 ai_trade_report narrative JSON을 작성하십시오.\n"
                "파이프라인 순서는 strategist -> scanner -> monitor -> supervisor -> executor -> reporter입니다.\n"
                "답해야 할 질문은 왜 진입했는가, 왜 보유했는가, 왜 청산했는가, 실행은 어땠는가, 다음에는 무엇을 개선할 것인가입니다.\n"
                "LLM은 전체 리포트/타임라인/메타데이터를 재생성하지 않습니다. 템플릿에 있는 narrative section만 채우십시오.\n"
                "영어 source 문장을 그대로 복사하지 마십시오. 사람이 읽는 문장은 한국어로 번역하십시오.\n"
                "selection_basis, runner_ups_lost, decision_reason_chain, monitor thresholds가 있으면 해당 섹션에 직접 반영하십시오.\n"
                "strategist_output이 있으면 strategy_thesis, strategy_refresh_trace, memory_usage_trace, news_usage_trace, scanner_handoff, monitor_handoff를 직접 사용하십시오.\n"
                "The strategist is not the final symbol selector; scanner/why_this_symbol_was_chosen owns selection_trace/rank/score.\n"
                "memory_usage_trace와 news_usage_trace는 메모리/뉴스 사용 설명의 기준입니다. 새 근거를 만들지 마십시오.\n"
                "strategy_refresh_trace가 있으면 1차 전략 프레임, 2차 후보 확정 후 refresh, 최종 적용 결과를 한 문단으로 합치지 말고 분리하십시오.\n"
                f"{partial_note}{korean_note}{previous_note}\n"
                "출력 템플릿:\n"
                f"{json.dumps(contract, ensure_ascii=False)}\n"
                "입력:\n"
                f"{json.dumps(prompt_input, ensure_ascii=False)}"
            ),
        },
    ]


def build_repair_messages(
    story_input: Dict[str, Any],
    raw_response: Any,
    *,
    sparse_story_input_for_llm: Callable[[Dict[str, Any]], Dict[str, Any]],
    compact_section_seed_for_llm: Callable[[Any], Dict[str, Any]],
    korean_rules: str,
    sparse: bool = False,
    enforce_korean: bool = False,
) -> List[Dict[str, str]]:
    compact_input = sparse_story_input_for_llm(story_input)
    contract = trade_report_output_template()
    previous_response = str(raw_response or "").strip()
    previous_parse = parse_llm_json_response(previous_response)
    previous_response_text = "[previous response was non-JSON reasoning or invalid text; ignore it]"
    if bool(previous_parse.get("is_full")):
        previous_response_text = previous_response[:1800]
    elif bool(previous_parse.get("is_partial")) and isinstance(previous_parse.get("partial_object"), dict):
        previous_response_text = json.dumps(previous_parse.get("partial_object") or {}, ensure_ascii=False)[:1800]
    partial_note = ""
    if str(story_input.get("status") or "").strip().lower() == "partial":
        partial_note = (
            "\n이 lifecycle은 partial 상태입니다. 일부 entry 또는 holding 근거가 비어 있습니다. "
            "확인되지 않은 진입 근거는 만들어 쓰지 말고, 저장되지 않았다고 명확히 적으십시오."
        )
    shape_note = ""
    if sparse:
        shape_note = "\n마지막 복구 시도입니다. 각 summary는 2문장 이하, bullets는 1~3개만 작성하십시오."
    return build_concise_trade_report_messages(
        compact_input,
        contract,
        korean_rules=korean_rules,
        compact_section_seed_for_llm=compact_section_seed_for_llm,
        partial_note=f"{partial_note}{shape_note}",
        previous_response_text=previous_response_text,
        repair=True,
        enforce_korean=enforce_korean,
    )


def build_messages(
    story_input: Dict[str, Any],
    *,
    sparse_story_input_for_llm: Callable[[Dict[str, Any]], Dict[str, Any]],
    compact_section_seed_for_llm: Callable[[Any], Dict[str, Any]],
    korean_rules: str,
) -> List[Dict[str, str]]:
    compact_input = sparse_story_input_for_llm(story_input)
    contract = trade_report_output_template()
    partial_note = ""
    if str(story_input.get("status") or "").strip().lower() == "partial":
        partial_note = "\n이 lifecycle은 partial 상태입니다. 확인되지 않은 진입/보유 근거를 새로 만들지 마십시오."
    return build_concise_trade_report_messages(
        compact_input,
        contract,
        korean_rules=korean_rules,
        compact_section_seed_for_llm=compact_section_seed_for_llm,
        partial_note=partial_note,
    )
