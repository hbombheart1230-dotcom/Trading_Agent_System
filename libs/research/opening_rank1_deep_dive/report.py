from __future__ import annotations

from typing import Any


def _pct(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):+.3f}%"


def _num(value: Any, digits: int = 3) -> str:
    return "N/A" if value is None else f"{float(value):.{digits}f}"


def _group_table(title: str, groups: dict[str, dict[str, Any]]) -> list[str]:
    lines = [f"## {title}", "", "| 구분 | N | 승률 | 평균 순수익 | PF | 평균 MFE | 평균 MAE |", "|---|---:|---:|---:|---:|---:|---:|"]
    for key, row in groups.items():
        lines.append(
            f"| {key} | {row.get('count')} | {_pct((row.get('win_rate') or 0) * 100)} | "
            f"{_pct(row.get('avg_return_pct'))} | {_num(row.get('profit_factor'))} | "
            f"{_pct(row.get('avg_mfe_pct'))} | {_pct(row.get('avg_mae_pct'))} |"
        )
    lines.append("")
    return lines


def _case_table(title: str, rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        f"## {title}",
        "",
        "| 일자·시간 | 종목 | 테마 | 매수→+30분 가격 | +30 순수익 | MFE / MAE | 전술 | 점수 | VWAP | 거래량배수 | KOSPI/KOSDAQ |",
        "|---|---|---|---:|---:|---:|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        time = str(row.get("decision_time_kst") or "")[5:16].replace("T", " ")
        name = str(row.get("symbol_name") or "이름 미확인")
        symbol = str(row.get("symbol") or "")
        themes = ", ".join(row.get("themes") or []) or "시점 테마명 미보존"
        prices = f"{_num(row.get('virtual_buy_price'), 0)} → {_num(row.get('virtual_sell_price_30m'), 0)}"
        strategy = "/".join(
            str(value)
            for value in (
                row.get("strategist_scenario"),
                row.get("playbook"),
                row.get("tactic_id"),
            )
            if value
        ) or "N/A"
        lines.append(
            f"| {time} | {symbol} {name} | {themes} | {prices} | {_pct(row.get('net_return_30m_pct'))} | "
            f"{_pct(row.get('mfe_30m_pct'))} / {_pct(row.get('mae_30m_pct'))} | {strategy} | "
            f"{_num(row.get('scanner_score'))} | {_pct(row.get('vwap_distance_pct'))} | "
            f"{_num(row.get('volume_ratio'))} | {_pct(row.get('kospi_pct'))}/{_pct(row.get('kosdaq_pct'))} |"
        )
    lines.append("")
    return lines


def _actual_trade_table(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "## 실제 거래 대조",
        "",
        "| 가상 사례 | 실제 Trade ID | 겹침 | 실제 매수 | 실제 매도 | 보유초 | 실현수익률 | 진입/청산 사유 |",
        "|---|---|---|---|---|---:|---:|---|",
    ]
    count = 0
    for row in rows:
        case = f"{row.get('day')} {row.get('symbol')} {row.get('symbol_name') or ''}"
        for trade in row.get("actual_same_day_trades") or []:
            count += 1
            reason = f"{trade.get('entry_reason') or 'N/A'} / {trade.get('exit_reason') or 'N/A'}"
            lines.append(
                f"| {case} | {trade.get('trade_id')} | "
                f"{'opening window' if trade.get('overlaps_opening_window') else 'same day only'} | "
                f"{trade.get('entry_ts') or 'N/A'} @{_num(trade.get('entry_price'), 0)} | "
                f"{trade.get('exit_ts') or 'N/A'} @{_num(trade.get('exit_price'), 0)} | "
                f"{_num(trade.get('holding_seconds'), 0)} | {_pct(trade.get('net_return_pct'))} | {reason} |"
            )
    if not count:
        lines.append("| - | - | - | - | - | - | - | 실제 거래 겹침 없음 |")
    lines.append("")
    return lines


def render_markdown(payload: dict[str, Any]) -> str:
    analysis = payload["analysis"]
    overall = analysis["overall"]
    coverage = payload["coverage"]
    lines = [
        "# OPEN_0_20_RANK1_30M 상세 원인 분석",
        "",
        "## 해석 범위",
        "",
        "* 대상은 2026-06-24~2026-07-30 장초반 20분 내 Scanner Rank-1의 +30분 관측 완료 사례입니다.",
        "* 매수·매도는 실제 주문이 아니라 `결정 이후 첫 1분봉 진입 → 30분 후 가상 청산`입니다.",
        "* 순수익은 왕복 비용 0.28%를 차감했습니다.",
        "* 시장 지표는 각 결정 시각 이전의 가장 가까운 저장 스냅샷입니다.",
        "* 테마는 당시 Q9가 `theme_match/theme_boost`만 보존하고 명칭을 보존하지 않은 경우가 많습니다. 현재 키움 참조 테마는 별도 권위로 표시하며 당시 원인으로 단정하지 않습니다.",
        "* 이 분석은 이미 발견된 cohort의 기술적 설명이며, 인과 증명이나 실전 승격 근거가 아닙니다.",
        "",
        "## 전체 결과",
        "",
        f"* 관측 사례: **{overall['count']}건**",
        f"* 승률: **{_pct((overall.get('win_rate') or 0) * 100)}**",
        f"* 평균 +30분 순수익: **{_pct(overall.get('avg_return_pct'))}**",
        f"* Profit Factor: **{_num(overall.get('profit_factor'))}**",
        f"* 평균 MFE / MAE: **{_pct(overall.get('avg_mfe_pct'))} / {_pct(overall.get('avg_mae_pct'))}**",
        f"* 종목명 확보: **{coverage['name_count']}/{coverage['case_count']}**, 테마 확보: **{coverage['theme_count']}/{coverage['case_count']}**",
        f"* 당시 Q9 상세 결합: **{coverage['q9_count']}/{coverage['case_count']}**, 시점 시장지표 결합: **{coverage['macro_count']}/{coverage['case_count']}**",
        f"* 전략가 시나리오 / tactical ID / 점수 성분 확보: **{coverage['strategist_scenario_count']}/"
        f"{coverage['tactic_id_count']}/{coverage['score_breakdown_count']}건**",
        f"* 같은 날 실제 거래 / 장초반 겹침 사례: **{coverage['actual_trade_case_count']}/"
        f"{coverage['actual_opening_overlap_case_count']}건**",
        "",
        "## 이상치 민감도",
        "",
        "| 조건 | N | 평균 순수익 | 중앙값 | 양수 비율 |",
        "|---|---:|---:|---:|---:|",
    ]
    for key, row in analysis["outlier_sensitivity"].items():
        if key == "contribution":
            continue
        ratio = row.get("positive_ratio")
        lines.append(
            f"| {key} | {row.get('count')} | {_pct(row.get('avg_return_pct'))} | "
            f"{_pct(row.get('median_return_pct'))} | "
            f"{_pct(float(ratio) * 100) if ratio is not None else 'N/A'} |"
        )
    contribution = analysis["outlier_sensitivity"]["contribution"]
    daily = analysis["daily"]
    lines += [
        "",
        f"* 전체 순수익 합: **{_pct(contribution['total_net_return_sum_pct'])}**",
        f"* 상위 1건 / 3건 / 5건 합: **{_pct(contribution['top1_return_pct'])} / "
        f"{_pct(contribution['top3_return_sum_pct'])} / {_pct(contribution['top5_return_sum_pct'])}**",
        f"* 상위 3건의 전체 양수 이익 기여율: **{_pct(contribution['top3_share_of_positive_gains'] * 100)}**",
        f"* {daily['day_count']}일 중 일평균 양수 비율: **{_pct((daily.get('positive_day_ratio') or 0) * 100)}**, "
        f"일별 평균 중앙값: **{_pct(daily.get('median_daily_mean_return_pct'))}**",
        "",
        "이 표는 평균 수익이 몇 개 급등 사례에 의존하는지 확인하는 핵심 검증입니다.",
        "",
        "## 승자와 패자의 차이",
        "",
        "| 성분 | 승자 평균 | 패자 평균 | 차이 | 표준화 차이 | 승자/패자 N |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    features = analysis["winner_loser"]["features"]
    for field, row in sorted(
        features.items(),
        key=lambda item: abs(float(item[1].get("standardized_effect") or 0)),
        reverse=True,
    ):
        lines.append(
            f"| {field} | {_num(row.get('winner_mean'))} | {_num(row.get('loser_mean'))} | "
            f"{_num(row.get('delta'))} | {_num(row.get('standardized_effect'))} | "
            f"{row.get('winner_n')}/{row.get('loser_n')} |"
        )
    lines.extend(["", "차이가 큰 값은 연관성 후보일 뿐입니다. 표본 수와 결측률을 함께 봐야 합니다.", ""])
    lines += _group_table("결정 시각 5분 구간", analysis["by_decision_5m_bucket"])
    lines += _group_table("전술", analysis["by_tactic"])
    lines += _group_table("전략가 시나리오", analysis["by_scenario"])
    lines += _group_table("후보 소스", analysis["by_source_class"])
    lines += _group_table("후보 소스 조합", analysis["by_source_combination"])
    lines += _group_table("시장 상태", analysis["by_market_bucket"])
    lines += _group_table("VWAP 상·하", analysis["by_above_vwap"])
    lines += _group_table("경로 특성", analysis["path_patterns"])
    lines += _case_table("상위 10개 사례", analysis["top_winners"])
    lines += _case_table("하위 10개 사례", analysis["top_losers"])
    lines += _case_table(
        "전체 사례",
        sorted(
            payload.get("cases") or [],
            key=lambda row: (str(row.get("day") or ""), str(row.get("decision_time_kst") or "")),
        ),
    )
    lines += _actual_trade_table(payload.get("cases") or [])
    lines += [
        "## 현재 설명 가능한 결론",
        "",
        *[f"* {item}" for item in payload.get("findings") or []],
        "",
        "## 결론의 한계",
        "",
        "* 65건은 독립 무작위 표본이 아니며 같은 종목과 같은 날이 반복됩니다.",
        "* 테마명은 당시 스냅샷에 완전 보존되지 않아 `theme_match` 효과와 특정 테마 효과를 동일시할 수 없습니다.",
        "* +30분 고정 청산은 연구용 horizon이며 실제 손절·익절 경로가 아닙니다.",
        "* 따라서 원인이 설명되어도 prospective 10일/25건 검증 전에는 행동 정책으로 승격하지 않습니다.",
        "",
    ]
    return "\n".join(lines)
