# 2026-05-13 Exit Trigger / Execution Status Separation

## 배경

- 일부 청산 리포트에서 `청산 트리거`가 실제 모니터 신호가 아니라 `SELL 실행 및 잔여수량 0 확인으로 전량 청산됐습니다`로 표시됐다.
- 이 문구는 체결/잔여수량 정합성 확인 결과이지, VWAP 이탈/고점 대비 하락/추세 훼손 같은 청산 판단 트리거가 아니다.

## 변경

- `live_execution_bundle_runner`
  - 전량 SELL 확인 문구를 `exit_reason`에 넣지 않도록 분리했다.
  - 모니터 청산 트리거가 없거나 `hold` placeholder만 있으면 `exit_reason=exit_trigger_not_captured`로 기록한다.
  - 체결 완료 상태는 `exit_execution_status=sell_execution_full_close_confirmed` 및 `exit_execution_status_human`으로 별도 기록한다.

- `trade_report_ai` / `trade_report_markdown_clean`
  - 과거 아티팩트에 남아 있는 `SELL 실행 및 잔여수량...`, `sell_execution_confirmed`, `full_sell_quantity_reconciled`를 청산 트리거로 표시하지 않는다.
  - 요약 리포트에서는 `트리거: 모니터 청산 트리거 미확인`으로 표시하고, 체결 확인은 `체결 상태` 줄로 분리한다.
  - 마지막 모니터 관측값은 `청산 트리거 아님`으로 라벨링한다.

- `operator_period_summary` / `symbol_trade_report`
  - 일간/주간/종목 요약 집계에서 전량 SELL 확인 문구가 주요 청산 사유나 청산 패턴으로 집계되지 않게 정규화했다.

## 재생성

- `reports/operator_summary/daily/2026-05-13`
- `reports/operator_summary/weekly/2026-W20`
- `reports/operator_summary/symbols/034730`
- `reports/operator_summary/symbols/064240`

## 검증

- `.\venv\Scripts\python.exe -m pytest tests/test_trade_report_ai.py tests/test_operator_summary_reports.py tests/test_symbol_trade_report.py -q`
  - 결과: `165 passed`

## 운영 메모

- 라이브 세션을 재시작해 새 리포트 로직을 로드했다.
- 현재 새 로그:
  - `reports/runtime/run_session_live_intraday_exit_trigger_fix_20260513_131351.out.log`
  - `reports/runtime/run_session_live_intraday_exit_trigger_fix_20260513_131351.err.log`
