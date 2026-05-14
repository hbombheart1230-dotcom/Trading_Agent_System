# 2026-05-13 Pending Buy + Human Chart Hard Guard

## 배경

003060 에이프로젠바이오로직스 매수 주문은 브로커가 주문을 접수했지만 `filled_qty=0`, `remaining_qty>0` 상태였습니다. 이 주문은 보유 종목이 아니라 미체결 pending 주문으로 다뤄야 합니다.

같은 케이스에서 모니터 차트 피쳐는 이미 위험을 계산하고 있었습니다.

- 전일 종가 대비 약 +29%권
- `human_reward_room_score=0`
- `late_entry_risk=high`
- `human_chart_entry_score`가 약한 구간

하지만 해당 값이 관측/리포트 성격에 가까워 실제 BUY 차단에는 충분히 쓰이지 않았습니다.

## 패치

- `account_order_is_pending`
  - `remaining_qty>0`이면 `status=COMPLETE` 또는 주문완료 계열 문구가 있어도 pending 주문으로 판정합니다.
  - `remaining_qty`를 `extract_order_status` 표준 출력에 포함했습니다.

- 모니터 신호 엔진
  - `late_entry_risk=high` + reward room 없음 조합을 hard buy guard로 승격했습니다.
  - 전일 대비 +29%권 또는 `human_chart_entry_score<0.50`이면 BUY를 막습니다.
  - 차단 사유는 `human_chart_buy_guard.blocking_features`와 hard filter fail reason에 남습니다.

- 실행 직전 가드
  - 주문 `meta.entry_metrics`에 남은 차트 피쳐를 다시 확인합니다.
  - 모니터를 통과한 주문이라도 `entry_chart_hard_guard_blocked`로 최종 차단할 수 있게 했습니다.

- 상태 업데이트
  - `filled_qty=0`, `remaining_qty>0` 주문은 mock position으로 승격하지 않습니다.
  - `persisted_state.pending_unfilled_orders`에 pending 주문으로 별도 기록합니다.
  - pending 주문은 `last_trade_side`로 기록하지 않습니다.

## 검증

- `venv\Scripts\python.exe -m pytest tests/test_intraday_monitor_signals.py`
- `venv\Scripts\python.exe -m pytest tests/test_execute_from_packet.py tests/test_update_state_after_execution.py`
- `venv\Scripts\python.exe -m pytest tests/test_m22_skill_contracts.py tests/test_m22_skill_native_scanner_monitor.py`

## 남은 장중 확인

- 브로커 order status가 `주문완료 / 체결 0 / 잔량 있음`으로 들어올 때 실제 모니터가 `same_symbol_pending_buy`로 처리하는지 확인합니다.
- `entry_chart_hard_guard_blocked`가 003060 같은 상한가권 추격 후보를 막고, 차순위 cascade가 정상 작동하는지 확인합니다.
- pending 주문이 TTL 이후 중복 매수만 풀리는지, 별도 취소 API까지 필요한지 장중 로그로 판단합니다.
