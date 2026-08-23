from __future__ import annotations

from typing import Any, Mapping

from .loaders import mapping


def _pct(value: Any, *, rate: bool = False) -> str:
    if value is None:
        return "-"
    number = float(value) * 100.0 if rate else float(value)
    return f"{number:+.2f}%" if not rate else f"{number:.1f}%"


def _num(value: Any) -> str:
    return "-" if value is None else f"{float(value):.2f}"


def _metric_cell(candidate: Mapping[str, Any], key: str) -> str:
    metric = mapping(candidate.get(key))
    count = int(metric.get("sample_count") or 0)
    if count <= 0:
        return "-"
    window_count = int(metric.get("window_count") or 0)
    windows = f", windows={window_count}" if window_count > count else ""
    return (
        f"N={count}{windows}, WR {_pct(metric.get('win_rate'), rate=True)}, "
        f"avg {_pct(metric.get('avg_net_return_pct'))}, PF {_num(metric.get('profit_factor'))}"
    )


def render_alpha_research_board(payload: Mapping[str, Any]) -> str:
    candidates = [mapping(row) for row in payload.get("candidates") or []]
    attention = list(payload.get("attention_order") or [])
    by_id = {str(row.get("candidate_id")): row for row in candidates}
    lines = [
        f"# Alpha Research Board - {payload.get('through_day')}",
        "",
        "기존 분석 결과를 한곳에 고정한 read-only 평가표입니다. 이 보고서는 매매 행동을 변경하지 않습니다.",
        "",
        "## 한눈에 보는 결론",
        "",
        "| 우선 | 후보 | 축 | 구분자 | 목표 | 원본 상태 | 보드 판정 | 다음 조치 |",
        "|---:|---|---|---|---|---|---|---|",
    ]
    for index, candidate_id in enumerate(attention, start=1):
        row = by_id[candidate_id]
        lines.append(
            f"| {index} | `{candidate_id}` | `{row.get('track_id')}` | "
            f"{row.get('discriminator')} | `{row.get('target_horizon')}` | "
            f"`{row.get('source_status')}` | `{row.get('board_bucket')}` | "
            f"{row.get('next_action')} |"
        )

    risk_high = by_id.get("R1_SCANNER_RISK_HIGH_30M_V1", {})
    risk_metric = mapping(risk_high.get("prospective"))
    risk_concentration = mapping(risk_high.get("concentration"))
    risk_review = mapping(risk_high.get("sensitivity_review"))
    post_cross = by_id.get("R1_ENTRY_DAILY_MA5_20_EXTENDED_15M_V1", {})
    post_metric = mapping(post_cross.get("prospective"))
    post_concentration = mapping(post_cross.get("concentration"))
    btc = by_id.get("BTC_WOORI_V2_ONLY_LOCAL_CONFIRMATION", {})
    btc_metric = mapping(btc.get("historical"))
    remaining = mapping(payload.get("remaining_candidate_reviews"))
    remaining_by_id = {
        str(row.get("candidate_id")): mapping(row)
        for row in remaining.get("reviews") or []
    }
    immediate_review = remaining_by_id.get("IMMEDIATE_OPENING_PROBE", {})
    btc_review = remaining_by_id.get("BTC_WOORI_V2_ONLY_LOCAL_CONFIRMATION", {})
    runtime_validation = mapping(payload.get("runtime_validation"))
    lines.extend(
        [
            "",
            "## 현재 얻은 힌트",
            "",
            f"- `risk_band=HIGH`: 과거·검증·prospective는 모두 양수였지만 민감도 최종 판정은 "
            f"`{risk_review.get('decision')}`입니다. "
            f"Prospective N={risk_metric.get('sample_count') or 0}, 평균 {_pct(risk_metric.get('avg_net_return_pct'))}지만 "
            f"최대 종목 비중 {_pct(risk_concentration.get('largest_symbol_share'), rate=True)}, "
            f"최대 일자 비중 {_pct(risk_concentration.get('largest_day_share'), rate=True)}입니다. "
            f"{risk_review.get('rationale')}",
            f"- `POST_CROSS_EXTENDED`: prospective 평균 {_pct(post_metric.get('avg_net_return_pct'))}, "
            f"최대 종목 비중 {_pct(post_concentration.get('largest_symbol_share'), rate=True)}로 일반 구분자 근거가 무너졌습니다.",
            f"- `IMMEDIATE_OPENING_PROBE +5m`은 민감도를 통과해 `{immediate_review.get('decision')}`로 남은 유일한 실제 런 검증 후보입니다.",
            "- 반복 Rank +30분은 표본 2건이라 background 계측만 유지하고, 이격 반등 +60분은 종목 기여 의존으로 종료했습니다.",
            f"- BTC-우기투 +30분은 N={btc_metric.get('sample_count') or 0}, 평균 {_pct(btc_metric.get('avg_net_return_pct'))}였지만 "
            f"최종 판정은 `{btc_review.get('decision')}`입니다. 8월 21일을 제외하면 edge가 사라졌습니다.",
            "- 삼성전자·하이닉스는 정합성 수정 이후 독립일이 1일뿐이므로 아직 구분자를 주장할 수 없습니다.",
        ]
    )

    lines.extend(
        [
            "",
            "## 실제 런 검증",
            "",
            f"- 후보: `{runtime_validation.get('candidate_id') or 'IMMEDIATE_OPENING_PROBE'}`",
            f"- 상태: `{runtime_validation.get('decision') or 'COLLECTING'}`",
            f"- 고정 세션: {runtime_validation.get('observed_session_count', 0)} / "
            f"{runtime_validation.get('required_sessions', 5)}",
            f"- 유효 에피소드: "
            f"{mapping(runtime_validation.get('metrics')).get('sample_count', 0)}",
            f"- 남은 세션: {runtime_validation.get('remaining_session_count', 5)}",
            f"- 판정 근거: {runtime_validation.get('rationale') or '-'}",
            "- 이 검증은 관측 전용이며 자동 승격이나 매매 행동 변경을 허용하지 않습니다.",
            "",
            "## 승패 구분자 근거",
            "",
            "| 후보 | 과거 학습 | 시간 분리 검증 | Prospective | 집중도 | 해석 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in candidates:
        concentration = mapping(row.get("concentration"))
        concentration_text = "-"
        if concentration:
            parts = []
            if concentration.get("largest_day_share") is not None:
                parts.append(f"day {_pct(concentration['largest_day_share'], rate=True)}")
            if concentration.get("largest_symbol_share") is not None:
                parts.append(f"symbol {_pct(concentration['largest_symbol_share'], rate=True)}")
            if concentration.get("positive_day_ratio") is not None:
                parts.append(f"positive-day {_pct(concentration['positive_day_ratio'], rate=True)}")
            if concentration.get("largest_day"):
                parts.append(f"max-day {concentration['largest_day']}")
            if concentration.get("largest_symbol"):
                parts.append(f"max-symbol {concentration['largest_symbol']}")
            concentration_text = ", ".join(parts) or "-"
        lines.append(
            f"| `{row.get('candidate_id')}` | {_metric_cell(row, 'historical')} | "
            f"{_metric_cell(row, 'validation')} | {_metric_cell(row, 'prospective')} | "
            f"{concentration_text} | {row.get('evidence_note')} |"
        )

    lines.extend(
        [
            "",
            "## 연구 축",
            "",
            "| 축 | 질문 | 결과가 확정되면 수정할 책임 |",
            "|---|---|---|",
        ]
    )
    for track in payload.get("tracks") or []:
        row = mapping(track)
        lines.append(
            f"| `{row.get('track_id')}` | {row.get('question')} | {row.get('owner_if_proven')} |"
        )

    lines.extend(
        [
            "",
            "## 끝난 결론",
            "",
            "이 항목은 새 이름으로 다시 평가하지 않습니다.",
            "",
            "| 항목 | 상태 | 근거 |",
            "|---|---|---|",
        ]
    )
    for finding in payload.get("settled_findings") or []:
        row = mapping(finding)
        lines.append(
            f"| {row.get('finding')} | `{row.get('status')}` | {row.get('reason')} |"
        )

    integrity = mapping(payload.get("integrity"))
    lines.extend(
        [
            "",
            "## 데이터 신뢰성",
            "",
            f"- 상태: `{integrity.get('status')}`",
            f"- 누락/오류 source: `{', '.join(integrity.get('missing_or_invalid_sources') or []) or 'none'}`",
            "- 실계좌 연구 비용 기준: 왕복 0.28%. Mock broker 비용과 혼합하지 않습니다.",
            "- 반복 분봉 window는 독립 거래 표본으로 해석하지 않습니다.",
            "- `ACTION_REVIEW`도 자동 승격이 아니며 수동 Promotion Review만 허용합니다.",
            "",
            "## 중단 규칙",
            "",
            "- `CLOSED` 후보는 다시 튜닝하거나 다른 이름으로 재개하지 않습니다.",
            "- `OBSERVE_FIXED` 후보는 기존 계약의 종료 조건까지만 수집합니다.",
            "- 행동 패치는 동시에 하나만 검토합니다.",
            "- 새 구분자는 기존 후보가 설명하지 못하는 독립 가설일 때만 추가합니다.",
            "",
        ]
    )
    return "\n".join(lines)
