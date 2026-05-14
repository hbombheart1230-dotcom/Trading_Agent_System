# 2026-05-12 Cost Floor and Truth Surface Hotfix

## 배경

- `003060` 거래에서 매수가 2,949원, 모니터 매도 기준 2,970원으로 가격은 약 +0.71%였지만, 세금/수수료를 고려하면 비용 하한인 약 +1.2%에 못 미치는 구간에서 빠른 청산이 발생했다.
- 해당 리포트의 Truth Surface는 `ka10077` 매칭이 `ambiguous_symbol_rows`였는데도 `손익 기준: 키움 당일 실현손익 기준(ka10077)`처럼 확정값으로 오해될 수 있게 표시됐다.

## 원인

- 비용 하한 필드는 적용되어 있었지만, VWAP/장중 저점 이탈이 `*_deep` metric hard invalidation으로 판정되면 비용 하한을 우회할 수 있었다.
- `003060` 산출물에는 `vwap_distance=-43.8%`처럼 비정상적으로 큰 VWAP 이탈값이 들어와 하드 이탈로 처리될 수 있었다.
- 브로커 당일 손익 매칭이 authoritative가 아닌 경우에도 리포트 요약의 손익 기준 문구가 확정/미확정을 구분하지 않았다.

## 변경 사항

- `libs/runtime/exit_policy.py`
  - 비용 하한 미달의 양수 수익 구간에서는 `vwap_breakdown_deep`, `intraday_low_break_deep` 같은 metric-only hard invalidation만으로 비용 하한을 우회하지 못하게 했다.
  - 명시적 `hard_invalidation_confirmed` 또는 reason별 hard flag는 기존처럼 비용 하한을 우회할 수 있다.
  - 차단 사유로 `protective_exit_hard_invalidation_suppressed_by_cost_floor`와 suppression reason을 남긴다.
- `libs/reporting/trade_report_markdown_clean.py`
  - `ka10077`이 authoritative가 아니면 손익 기준을 `미확정`으로 표시한다.
  - fallback/monitor 기반 수익률은 `관측 손익률(비용 미반영)`으로 표시한다.

## 검증

```text
venv\Scripts\python.exe -m pytest tests\test_strategy_sizing_exit_upgrade.py tests\test_trade_report_ai.py::test_truth_surface_treats_ambiguous_broker_day_pct_as_observation_only tests\test_trade_report_ai.py::test_trade_summary_labels_observed_negative_pct_as_loss_not_breakeven tests\test_monitor_exit_guard.py::test_monitor_vwap_breakdown_exit_prefers_fresh_minute_vwap_over_stale_feature -q
```

결과:

```text
34 passed
```

## 운영 확인 포인트

- 다음 런에서 +0.5~+1.0% 수준의 작은 양수 구간에서 VWAP 이탈만으로 즉시 전량 청산되는지 확인한다.
- 실제 stop loss/hard stop 손실 방어는 비용 하한 때문에 막히면 안 된다.
- `ka10077` 매칭이 ambiguous일 때 요약 리포트가 `미확정`과 `관측 손익률(비용 미반영)`으로 표시되는지 확인한다.

