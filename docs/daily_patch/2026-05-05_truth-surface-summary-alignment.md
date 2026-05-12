# 클로즈 - 2026-05-05 Truth Surface Summary Alignment

## Closure Status

- status: closed
- closed_at: 2026-05-06
- close_reason: 운영 daily/weekly/monthly/symbol summary와 performance summary가 Truth Surface net 기준을 우선 사용하도록 정렬됐고, 2026-05-04 대표 오매칭 케이스를 재생성해 확인했다.
- evidence:
  - `reports/operator_summary/daily/2026-05-04/daily_summary.json`의 기준은 `truth_surface_net`으로 정렬됐다.
  - `reports/performance/2026-05-04/summary.json`과 `playbook_stats.json`도 Truth Surface 우선 기준으로 재생성됐다.
  - `TRD_20260504_006910_02`는 split row 합산 매칭(`symbol_split_buy_sell_qty_exact`)으로 정정됐다.
  - 관련 회귀 테스트는 `tests/test_operator_summary_reports.py`, `tests/test_kiwoom_day_trade_truth.py`, `tests/test_strategy_performance_feedback.py` 기준 통과했다.
- carry_forward:
  - 일부 한글 markdown 렌더링/문장 품질 정리는 별도 리포트 품질 백로그로 넘긴다.
  - 과거 Truth Surface 자체가 잘못 저장된 산출물은 개별 거래 리포트 재생성으로 처리한다.

## 배경

5월 4일 `ai_trade_summary.md`를 기준으로 보면 순손익은 거의 전패에 가까웠지만,
`operator_summary/daily_summary.json`은 가격 움직임(`result_pct`) 기준으로 5승/10패/3보합처럼 보였다.
운영자가 처음 확인하는 리포트와 집계 리포트의 기준이 달라서 성과 판단이 왜곡됐다.

## 수정

- 운영 daily/weekly/monthly/symbol summary가 `reports/trades/<day>/<trade_id>/reports/ai_trade_summary_input.json`의 Truth Surface 순손익을 우선 사용한다.
- Truth Surface에 `pnl` 금액이 없고 `pnl_pct`만 있는 거래는 승패/평균에서 제외하고 `observed_*` 관측 지표로만 별도 기록한다.
- 가격은 올랐지만 수수료/세금 때문에 순손실인 거래를 `cost_drag_loss_count`로 별도 집계한다.
- 성과 메모리(`reports/performance/<day>/summary.json`, `playbook_stats.json`)도 lifecycle의 오래된 `trade_outcome.return_pct` 대신 Truth Surface 순손익을 우선 사용한다.
- 키움 `ka10077` 당일 실현손익 매칭에서 같은 종목 반복 매매와 분할 체결이 섞일 때, 단순 수량 매칭 전에 매수가/매도가/합산수량이 일치하는 split row를 먼저 합산한다.

## 5월 4일 재집계 결과

- 총 거래: 18
- 순손익 확정 표본: 14
- 확정 승패: 1승 / 13패
- 미확정 관측-only 손실: 4
- 순손익 평균: -0.757%
- 가격 상승 또는 보합인데 비용 때문에 순손실 처리된 거래: 6

## 정정된 대표 케이스

`TRD_20260504_006910_02`

- 기존: 14,735 / 14,790, 실현손익 -1,763, -1.20%, `symbol_qty_exact`
- 수정: 14,780 / 14,790, 실현손익 -1,215, -0.82%, `symbol_split_buy_sell_qty_exact`
- 원인: 같은 종목의 이전 10주 청산 row를 수량만 보고 잘못 붙였다. 실제 해당 거래는 1주 + 9주 split row를 합산해야 했다.

## 재생성

- `reports/trades/2026-05-04/TRD_20260504_006910_02/reports/ai_trade_summary.md`
- `reports/operator_summary/daily/2026-05-04/daily_summary.json`
- `reports/operator_summary/weekly/2026-W19/weekly_summary.json`
- `reports/operator_summary/monthly/2026-05/monthly_summary.json`
- `reports/performance/2026-05-04/summary.json`
- `reports/performance/2026-05-04/playbook_stats.json`

## 검증

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_operator_summary_reports.py tests\test_kiwoom_day_trade_truth.py tests\test_strategy_performance_feedback.py -q
```

Result:

```text
21 passed
```

## 남은 리스크

- `ai_trade_summary.md`의 일부 한글 렌더링은 기존 인코딩/문구 깨짐이 남아 있다. 수치 기준 정합성은 맞췄지만 문장 품질은 별도 정리가 필요하다.
- Truth Surface 자체가 과거 산출물에서 잘못 저장된 경우에는 개별 거래 리포트를 재생성해야 한다. 이번 패치로 미래 생성물은 split-row 매칭을 우선 적용한다.
