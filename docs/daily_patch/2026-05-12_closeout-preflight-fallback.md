# 2026-05-12 Closeout Preflight Fallback

## 배경

- 064240 잔여 보유 원인 점검 결과, 15:20 이후 오버나이트 판단을 한 것이 아니라 `portfolio_snapshot_reader_error`로 지휘관 preflight가 반복 차단됐다.
- 당시 상태는 계좌 reader 포지션 0건, 내부 persisted 포지션 1건이라 mismatch가 있었고, 기존 로직은 안전하게 전체 실행을 중단했다.
- 문제는 장마감 청산 구간에서도 같은 차단이 적용되어 Stage4/모니터/EOD 판단 자체가 실행되지 않았다는 점이다.

## 변경

- `graphs/commander_runtime.py`
  - `COMMANDER_CLOSEOUT_PREFLIGHT_FALLBACK_ENABLED=true` 기본값으로 closeout 전용 fallback 추가.
  - session 중 closeout window가 활성이고 내부 persisted 포지션이 남아 있으면, `portfolio_snapshot_reader_error` 또는 unresolved mismatch가 있어도 신규 매수는 계속 막고 closeout fast path는 진행한다.
  - fallback 진행 시 `portfolio_preflight.blocked=false`, `degraded=true`, `closeout_fallback.reason=session_closeout_preflight_fallback`으로 기록한다.
  - closeout path에서는 기존처럼 Stage4 carry review, 모니터 청산 판단, decision, executor 흐름을 탄다.

## 의도

- 계좌 reader 실패를 무시하고 신규 진입하는 것이 아니다.
- 장마감 보유 포지션이 내부 상태에 명확히 남아 있을 때만, 청산/오버나이트 판단 경로가 preflight에서 끊기지 않게 한다.
- 실제 SELL 주문은 broker가 최종 거부할 수 있으므로, 계좌 truth 불확실성을 완전히 제거하는 패치는 아니다. 다만 오늘처럼 아무 판단도 남기지 못하고 잔여 보유가 되는 문제를 막는다.

## 검증

- `venv\Scripts\python.exe -m pytest -q tests/test_m21_commander_runtime_entry.py`
  - 81 passed
- `venv\Scripts\python.exe -m pytest -q tests/test_execute_from_packet.py -k "portfolio_snapshot or closeout"`
  - 3 passed, 32 deselected
