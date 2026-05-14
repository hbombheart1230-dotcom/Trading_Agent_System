# 2026-05-12 same-day summary PnL unknown fix

## 배경

- `ai_trade_summary.md` 운영 요약에서 실제 개별 거래 결과는 손실인데 `당일 성과`가 `3건 중 0승 / 0패 / 평균 0.00%`로 표시되는 문제가 확인됐다.
- 원인은 닫힌 거래 리포트 중 실현손익 값이 아직 비어 있는 거래를 `0.00% 보합`처럼 집계하거나, 기존 리포터 문장을 요약 렌더러가 그대로 축약한 경로였다.

## 패치

- `libs/reporting/reporter_feedback.py`
  - 손익 값이 없는 닫힌 거래를 `flat_count`가 아니라 `unknown_pnl_count`로 분리한다.
  - 평균 손익률은 실제 `pnl_pct` 표본이 있는 거래만 사용하고 `pnl_pct_sample_count`를 함께 기록한다.
- `libs/reporting/trade_report_ai.py`
  - 리포터 피드백 요약에 `손익 미확정 N건`과 `확인분 평균 손익률`을 명시한다.
- `libs/reporting/trade_report_markdown_clean.py`
  - 운영 요약의 `당일 성과` 렌더링에서 `0승/0패/평균 0.00%` 모순 문장은 `손익 미확정`으로 표시한다.
  - 현재 거래의 Truth Surface 손익이 확정되어 있으면, 같은-day 리포터 문장이 오래되어도 최소 1건의 승/패를 현재 거래 기준으로 보정한다.
  - 기존 정상 문장 예: `9건 중 2승 / 6패 / 평균 -0.40%`는 유지한다.

## 검증

- `venv\Scripts\python.exe -m py_compile libs\reporting\reporter_feedback.py libs\reporting\trade_report_ai.py libs\reporting\trade_report_markdown_clean.py`
- `venv\Scripts\python.exe -m pytest -q tests\test_reporter_feedback.py tests\test_trade_report_ai.py`
- 결과: `141 passed`
