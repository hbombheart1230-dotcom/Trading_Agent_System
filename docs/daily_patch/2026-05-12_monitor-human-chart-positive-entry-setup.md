# 2026-05-12 Monitor Human Chart Positive Entry Setup

## 배경

기존 모니터의 사람형 차트 판단은 약한 자리 차단 쪽에 가까웠다.
`human_chart_buy_guard`는 VWAP 붕괴, 고점 실패, 높은 청산 위험을 막지만, 차트상 좋은 진입 자리 자체를 적극적으로 식별해 WAIT을 BUY로 올리는 역할은 약했다.

## 변경

- `human_chart_entry_setup.v1` 추가
  - `entry_chart_score`, `exit_risk_score`, VWAP 재회복 지속성, 거래량 확장, 고저점 구조를 함께 평가한다.
  - A급 setup일 때만 WAIT을 BUY로 승격한다.
  - 승격 라벨은 `breakout_retest_hold`, `higher_low_vwap_reclaim`, `vwap_support_reclaim`, `clean_vwap_continuation` 중 하나로 기록한다.

- 기존 게이트 우회 방지
  - 신뢰도 미통과, 과확장, 강한 VWAP 붕괴, 스윙 저점 이탈, 높은 청산 위험은 승격하지 않는다.
  - 거래량 미확인으로 막힌 케이스는 승격하지 않는다.
  - 정책 필수 실패는 기본적으로 막되, `reclaim_gate_ok`가 아주 근접한 A급 차트일 때만 제한적으로 허용한다.

- 관측/리포트 필드
  - `human_chart_entry_setup`
  - `human_chart_setup_quality`
  - `human_chart_setup_label`
  - `human_chart_setup_score`
  - `human_chart_entry_setup_applied`

## 검증

- `tests/test_intraday_monitor_signals.py`: 통과
- `tests/test_m21_commander_runtime_entry.py`, `tests/test_scanner_monitor_compatibility.py`: 통과
- `tests/test_trade_report_ai.py -k "trade_summary or horizon"`: 통과
- `py_compile libs/runtime/intraday_monitor_signals.py`: 통과

## 런 검증 포인트

- `human_chart_entry_setup_applied=true`가 생긴 경우 실제 체결 후 비용 포함 손익이 개선되는지 확인한다.
- A급 setup 승격이 너무 잦으면 `min_a_setup_score` 또는 `max_exit_risk_score`를 더 보수적으로 조정한다.
- 승격된 매매의 차트 사유가 리포트에 충분히 보이는지 다음 장중 리포트에서 확인한다.
