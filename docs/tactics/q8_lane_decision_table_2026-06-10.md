# Q8 Lane Decision Table - 2026-06-10

## Summary

- payloads: 26
- candidates: 42
- evaluated: 42
- forward observed: 27 (64.3%)
- would-enter: 0
- top reasons: volume_confirmation_missing 24, pullback_below_vwap_reclaim_not_ready 7, volume_insufficient 3, pullback_not_mature 3, minute_candle_missing 2, below_vwap_reclaim_not_ready 2

## Lane Verdicts

| Lane | Verdict | Decision | n | obs | +5m | +15m | +30m | MFE5 | MAE5 | Rationale |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| opening_momentum | MISSED_OPPORTUNITY | 완화 후보 | 32 | 25 | 1.1382% | 3.6951% | - | 1.5298% | -0.8847% | 차단 후보의 forward 상승 여지가 관측됨. |
| vwap_reclaim | DATA_INCOMPLETE | 관찰 유지 | 9 | 2 | -1.0703% | - | - | 0.7357% | -4.1454% | 표본 또는 forward coverage 부족 |

## Operating Interpretation

- `MISSED_OPPORTUNITY`: 차단 후보가 이후 의미 있게 상승했습니다. 즉시 무조건 진입이 아니라 완화 후보입니다.
- `GOOD_BLOCK`: 차단 후 forward 성과가 부진했습니다. 해당 gate는 유지합니다.
- `DATA_INCOMPLETE`: 표본 또는 coverage가 부족하거나 변동성이 커서 정책 변경 대상이 아닙니다.

## Current Action

오늘 장중에는 이 표를 기준으로 추가 행동 패치를 하지 않습니다. 장후 같은 표를 재생성해서 판정이 유지되는지 확인합니다.
