# 2026-05-12 Trade Summary Entry/Exit Numeric Context

## 변경

- `ai_trade_summary.md` 진입 판단에 모니터 진입 수치를 노출한다.
  - 현재가
  - VWAP
  - VWAP 대비 이격
  - 거래량 비율과 기준값
  - 최근 고점/돌파 기준
- `VWAP 이탈` 청산 트리거에 실제 이탈폭을 같이 노출한다.
  - 예: `트리거: VWAP 이탈 (VWAP 대비 -0.62%)`
  - 모니터 관측값에는 현재가, 계산 VWAP, 이탈폭, 이탈 기준을 같이 표시한다.
- 리포트 생성 단계에서 BUY 당시 `entry_metrics`를 `monitor_snapshot`으로 보존하도록 보강했다.

## 검증

- `tests/test_trade_report_ai.py::test_trade_summary_surfaces_entry_vwap_volume_and_vwap_exit_distance`
- `tests/test_trade_report_ai.py::test_entry_monitor_reason_preserves_entry_metrics_from_decision_detail`
- `tests/test_trade_report_ai.py` 전체 통과

## 주의

- 과거에 이미 생성된 일부 리포트는 BUY 당시 `entry_metrics`가 요약 입력에 없으면 VWAP/거래량 대신 현재가만 표시될 수 있다.
- 신규 생성 리포트는 monitor entry decision detail에서 수치를 보존해 요약에 반영한다.
