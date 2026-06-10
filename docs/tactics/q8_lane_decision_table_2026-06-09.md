# Q8 Lane Decision Table - 2026-06-09

## Summary

- payloads: 354
- candidates: 1172
- evaluated: 1164
- forward observed: 1097 (93.6%)
- would-enter: 16
- top reasons: volume_insufficient 332, below_vwap_reclaim_not_ready 226, breakout_not_ready 206, too_extended_from_vwap 188, quant_entry_block:cost_edge_fail 74, human_chart_sanity_guard_blocked 53

## Lane Verdicts

| Lane | Verdict | Decision | n | obs | +5m | +15m | +30m | MFE5 | MAE5 | Rationale |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| opening_momentum | MISSED_OPPORTUNITY | 완화 후보 | 74 | 72 | 0.6848% | 0.6752% | 1.1030% | 2.5045% | -2.0399% | 차단 후보의 forward 상승 여지가 관측됨. 단, MAE가 커서 소액 probe 또는 기준 재검토만 허용. |
| cost_edge | GOOD_BLOCK | 차단 유지 | 277 | 269 | -0.0912% | -0.2253% | -0.2229% | 0.6981% | -0.8368% | 차단 후 forward 수익률이 부진 |
| vwap_reclaim | GOOD_BLOCK | 차단 유지 | 229 | 213 | -0.0401% | -0.5685% | -1.0218% | 1.1909% | -1.1705% | VWAP 미회복 차단 후 단기/중기 수익률이 음수 |
| pullback_quality | GOOD_BLOCK | 차단 유지 | 17 | 16 | -0.8240% | -0.9913% | -3.5128% | 1.0864% | -2.4789% | 차단 후 forward 수익률이 부진 |
| volume_confirmation | DATA_INCOMPLETE | 혼합 관찰 | 209 | 192 | 0.1607% | 0.3817% | -0.0715% | 0.9935% | -1.0234% | 방향성은 있으나 즉시 정책화할 정도로 선명하지 않음 |
| breakout_readiness | DATA_INCOMPLETE | 혼합 관찰 | 159 | 154 | 0.0103% | 0.2254% | 0.3746% | 0.5937% | -0.7478% | 방향성은 있으나 즉시 정책화할 정도로 선명하지 않음 |
| runner_up_selection | DATA_INCOMPLETE | 혼합 관찰 | 172 | 150 | -0.1465% | 0.0336% | 0.4118% | 0.7774% | -1.0157% | 방향성은 있으나 즉시 정책화할 정도로 선명하지 않음 |
| human_chart_sanity | DATA_INCOMPLETE | 혼합 관찰 | 24 | 20 | -0.2994% | 0.1225% | 0.8570% | 0.7507% | -1.5534% | 방향성은 있으나 즉시 정책화할 정도로 선명하지 않음 |
| confirmed_or_other | DATA_INCOMPLETE | 혼합 관찰 | 10 | 10 | 0.0304% | 0.2191% | 0.2660% | 0.6030% | -1.0234% | 방향성은 있으나 즉시 정책화할 정도로 선명하지 않음 |
| opening_largecap_surge | DATA_INCOMPLETE | 관찰 유지 | 1 | 1 | -0.3236% | -0.8091% | -1.4563% | 0.0000% | -0.8091% | 표본 또는 forward coverage 부족 |

## Operating Interpretation

- `MISSED_OPPORTUNITY`: 차단 후보가 이후 의미 있게 상승했습니다. 즉시 무조건 진입이 아니라 완화 후보입니다.
- `GOOD_BLOCK`: 차단 후 forward 성과가 부진했습니다. 해당 gate는 유지합니다.
- `DATA_INCOMPLETE`: 표본 또는 coverage가 부족하거나 변동성이 커서 정책 변경 대상이 아닙니다.

## Current Action

오늘 장중에는 이 표를 기준으로 추가 행동 패치를 하지 않습니다. 장후 같은 표를 재생성해서 판정이 유지되는지 확인합니다.
