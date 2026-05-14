# 2026-05-12 Overnight Decision Report Clarity

## 목적

- 장마감 잔여 보유 종목이 있을 때 실제 오버나이트 판단이 수행됐는지, 아니면 판단 기록이 누락됐는지 daily report에서 즉시 구분되도록 정리.
- 오래된 closeout 메타가 당일 오버나이트 승인/정리 근거처럼 보이지 않도록 기록시각과 당일 근거 여부를 함께 표시.

## 변경

- `libs/reporting/operator_period_summary.py`
  - 잔여 보유 종목 payload에 `overnight_decision_status`, `overnight_decision_label` 추가.
  - 15:20 이전 마지막 모니터 이후 재점검이 없으면 `오버나이트 판단: 미수행(15:20 이후 재점검 없음)`으로 렌더링.
  - closeout 상태에 `applied_at_kst`, `stale_for_day`, `report_note` 추가.
- `scripts/generate_daily_report.py`
  - daily report의 잔여 보유 종목 렌더링도 동일한 문구 정책으로 정렬.

## 2026-05-12 확인

- 064240은 `overnight_decision_by_symbol`에 저장된 결정이 없었음.
- 마지막 064240 모니터는 2026-05-12 15:08:19 KST의 `HOLD(hold)`.
- 15:20 이후 런은 있었지만 064240 대상 EOD/오버나이트 판단이 아니라 `portfolio_preflight_guard` 반복이었음.
- 따라서 리포트 표기는 오버나이트 승인/보류가 아니라 `미수행(15:20 이후 재점검 없음)`이 맞음.

## 검증

- `venv\Scripts\python.exe -m pytest -q tests/test_operator_summary_reports.py tests/test_daily_report.py`
  - 25 passed
- `reports/operator_summary/daily/2026-05-12/daily_summary.md` 재생성 완료.
- `reports/operator_summary/daily/2026-05-12/daily_report.md` 재생성 완료.
