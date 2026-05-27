# 2026-05-24 Broker Alignment at Report Generation

## 목적

리포트 저장 누락이나 주문/체결 누락이 생겼을 때 장중에 바로 보이도록, 리포트 생성 시점마다 Kiwoom 주문/체결 기준과 로컬 이벤트/리포트 기준을 대조한다.

## 변경

- 공용 모듈 추가: `libs/reporting/broker_alignment.py`
  - `KiwoomOrderFillReader`로 당일 broker/local execution reconciliation 생성.
  - 결과를 `reports/reconciliation/broker_trade_reconciliation_YYYY-MM-DD.json/md`에 저장.
  - Kiwoom 조회 실패 시 리포트 생성을 막지 않고 `status=unavailable`로 표면화.
- Daily report:
  - `Broker Alignment` 섹션에 local/broker 주문 수, ord_no 매칭 수, 누락 수를 표시.
- Trade report summary:
  - `ai_trade_summary_input.json`에 `broker_alignment` 스냅샷 포함.
  - `ai_trade_summary.md` 확정 진단에 `브로커 주문 정합성` 줄 표시.

## 운영 기준

- `status=ok`: local/broker 누락이 모두 0.
- `status=mismatch`: Kiwoom과 로컬 이벤트 기준 주문/체결 건수가 어긋남.
- `status=unavailable`: Kiwoom 조회 또는 reconciliation 생성 실패. 이 경우 리포트는 생성하되 정합성 확인은 별도 점검 대상.

## 검증

- `venv\Scripts\python.exe -m pytest tests/test_trade_summary_symbol_metadata.py::test_trade_summary_input_and_diagnostics_surface_broker_alignment tests/test_daily_report.py::test_generate_daily_report_surfaces_broker_alignment tests/test_live_execution_bundle_report.py -q`
- `python -m py_compile libs/reporting/broker_alignment.py libs/reporting/daily_report_generator.py libs/reporting/live_execution_bundle_runner.py libs/reporting/trade_report_markdown_clean.py`
