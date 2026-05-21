from __future__ import annotations

import json
from typing import Any, Callable, Dict, List


AI_TRADE_SUMMARY_EVALUATION_KEYS = (
    "conclusion",
    "root_cause",
    "priority_actions",
    "risk_notes",
    "validation_questions",
)


def trade_summary_evaluation_template() -> Dict[str, Any]:
    return {
        "conclusion": "",
        "root_cause": "",
        "priority_actions": [],
        "risk_notes": [],
        "validation_questions": [],
    }


def normalize_trade_summary_evaluation(
    value: Any,
    *,
    clip: Callable[..., str],
    listify: Callable[..., List[Any]],
) -> Dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    if isinstance(payload.get("llm_evaluation"), dict):
        payload = dict(payload.get("llm_evaluation") or {})
    out = trade_summary_evaluation_template()
    out["conclusion"] = clip(payload.get("conclusion"), max_len=420)
    out["root_cause"] = clip(payload.get("root_cause"), max_len=520)
    out["priority_actions"] = listify(payload.get("priority_actions"), max_items=5, max_len=180)
    out["risk_notes"] = listify(payload.get("risk_notes"), max_items=5, max_len=180)
    out["validation_questions"] = listify(payload.get("validation_questions"), max_items=5, max_len=180)
    return out


def trade_summary_parse_meta(raw_response: Any, candidate: Dict[str, Any]) -> Dict[str, Any]:
    evaluation = candidate.get("llm_evaluation") if isinstance(candidate.get("llm_evaluation"), dict) else candidate
    evaluation = evaluation if isinstance(evaluation, dict) else {}
    present = [key for key in AI_TRADE_SUMMARY_EVALUATION_KEYS if key in evaluation]
    missing = [key for key in AI_TRADE_SUMMARY_EVALUATION_KEYS if key not in evaluation]
    return {
        "parse_mode": "json",
        "required_keys_expected": list(AI_TRADE_SUMMARY_EVALUATION_KEYS),
        "required_keys_present": present,
        "required_keys_missing": missing,
        "completeness_score": float(len(present)) / float(len(AI_TRADE_SUMMARY_EVALUATION_KEYS)),
        "raw_char_count": len(str(raw_response or "")),
    }


def build_trade_summary_evaluation_messages(
    summary_input: Dict[str, Any],
    *,
    korean_rules: str,
    previous_response_text: str = "",
    repair: bool = False,
) -> List[Dict[str, str]]:
    mode_label = "복구 모드" if repair else "작성 모드"
    previous_note = f"\n이전 응답:\n{previous_response_text}\n" if repair else ""
    return [
        {
            "role": "system",
            "content": (
                "당신은 트레이딩 시스템의 운영 요약 평가자입니다. "
                "반드시 JSON 객체 하나만 반환하십시오. markdown, code fence, 설명문, 사고 과정은 금지합니다. "
                "가격, 손익, 수수료, 세금, 체결 사실, 순위, 점수는 절대 만들거나 수정하지 마십시오. "
                "모든 판단은 제공된 ai_trade_summary_input 안의 사실로만 제한하십시오. "
                "체결가, 매수가, 매도가, 실현손익, 수수료, 세금은 truth_surface만 정답으로 사용하십시오. "
                "decision_flow.exit_observation은 모니터 신호 판단용 스냅샷일 뿐이며 체결가나 실현손익으로 해석하지 마십시오. "
                "post_exit_shadow는 매도 후 가격 관측-only 근거이며 보유 연장 규칙이 이미 바뀐 것으로 해석하지 마십시오. "
                "deterministic_findings는 확정 원인이 아니라 검증 후보로 다루십시오. "
                "root_cause_candidates, deterministic_findings, decision_flow 같은 내부 키 이름을 출력문에 그대로 쓰지 마십시오. "
                "종목명은 trade.symbol을 그대로 사용하고 00번.symbol 같은 placeholder를 만들지 마십시오. "
                "한국어만 사용하고 일본어/중국어 조각이나 번역되지 않은 문장을 남기지 마십시오. "
                f"{korean_rules} "
                "근거가 약하면 단정하지 말고 검증 필요라고 쓰십시오."
            ),
        },
        {
            "role": "user",
            "content": (
                f"{mode_label}: 아래 ai_trade_summary_input만 사용해서 llm_evaluation JSON을 작성하십시오.\n"
                "출력 필드는 conclusion, root_cause, priority_actions, risk_notes, validation_questions 다섯 개뿐입니다.\n"
                "conclusion은 운영자가 바로 볼 수 있게 종목, 결과, 핵심 운영 판단을 한두 문장으로 요약하십시오.\n"
                "root_cause는 확정 사실과 검증 후보를 구분하고, 입력에 있는 정책/선정/청산 근거로만 제한하십시오.\n"
                "priority_actions는 다음 검증 또는 패치 우선순위이며 실행 가능한 문장으로 쓰십시오.\n"
                "risk_notes는 이 거래를 해석할 때 조심해야 할 점이며 과잉 일반화를 막는 문장으로 쓰십시오.\n"
                "validation_questions는 다음 라이브 검증에서 확인할 질문이며 물음표로 끝내십시오.\n"
                "청산 관련 가격을 언급할 때는 Truth Surface 기준과 모니터 관측값 기준을 반드시 구분하십시오.\n"
                "post_exit_shadow를 언급할 때는 관측-only, 표본 부족, 행동 변경 금지를 함께 전제하십시오.\n"
                "출력 템플릿:\n"
                f"{json.dumps(trade_summary_evaluation_template(), ensure_ascii=False)}\n"
                "입력:\n"
                f"{json.dumps(summary_input, ensure_ascii=False)}"
                f"{previous_note}"
            ),
        },
    ]


def deterministic_trade_summary_report(
    summary_input: Dict[str, Any],
    *,
    status: str,
    mode: str,
    model: str,
    reason: str,
    evaluation: Dict[str, Any] | None = None,
    llm_response_artifact: Dict[str, Any] | None = None,
    as_dict: Callable[[Any], Dict[str, Any]],
    normalize_evaluation: Callable[[Any], Dict[str, Any]],
) -> Dict[str, Any]:
    trade = as_dict(summary_input.get("trade"))
    out = {
        "schema_version": "ai_trade_summary.v1",
        "artifact_type": "ai_trade_summary",
        "source_artifact": "ai_trade_summary_input.json",
        "trade": trade,
        "truth_surface": as_dict(summary_input.get("truth_surface")),
        "same_day_context": as_dict(summary_input.get("same_day_context")),
        "market_and_strategy": as_dict(summary_input.get("market_and_strategy")),
        "decision_flow": as_dict(summary_input.get("decision_flow")),
        "memory_and_policy": as_dict(summary_input.get("memory_and_policy")),
        "deterministic_findings": as_dict(summary_input.get("deterministic_findings")),
        "llm_evaluation": normalize_evaluation(evaluation or {}),
        "generation": {
            "status": str(status or ""),
            "mode": str(mode or ""),
            "model": str(model or ""),
            "reason": str(reason or ""),
        },
        "summary_status": str(status or ""),
    }
    if llm_response_artifact:
        out["llm_response_artifact"] = dict(llm_response_artifact)
    return out
