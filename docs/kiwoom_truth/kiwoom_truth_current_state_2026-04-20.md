# Kiwoom Truth Current State

## 문제 정의

사용자 앱에서 보이는 청산가/손익률과 `trade_report`에 적힌 값이 어긋난다.

현재 구조는 아래 세 값을 혼용한다.
1. broker/account 값
2. monitor 관측값
3. 로컬 계산 fallback 값

이 구조 때문에 report에 적힌 청산 가격이나 손익률이 실제 Kiwoom 체결 truth와 다를 수 있다.

## 현재 붙어 있는 Kiwoom truth

### 1. 계좌 잔고 / 보유 종목

사용 API:
- `kt00018`

확인된 코드:
- `libs/kiwoom/kiwoom_account_client.py`
- `libs/read/kiwoom_portfolio_reader.py`
- `graphs/nodes/build_portfolio_snapshot.py`

현재 읽는 값:
- 보유 수량
- 평균 단가
- 현재가
- 미실현손익
- `account_pnl_ratio`

현재 역할:
- open position 상태 파악
- monitor/exit 판단 cross-check

### 2. 주문/체결 truth

사용 가능한 API:
- `kt00007`
- `kt00009`

확인된 코드:
- `scripts/demo_m14_order_status.py`
- `scripts/run_broker_trade_reconciliation.py`
- `config/skills/order.status.yaml`
- `config/skills/account.orders.yaml`

현재 역할:
- 수동 조회
- reconciliation

핫패스 상태:
- live runtime hot path에는 아직 직접 안 붙어 있음

## 현재 truth gap

### A. `daily_pnl_ratio`는 broker 당일 손익률이 아님

코드:
- `graphs/nodes/build_risk_context.py`

현재 계산:
- `unrealized_sum / cash`

즉 현재 `daily_pnl_ratio`는 계좌 앱의 당일 매매 손익률이 아니라 risk proxy다.

### B. trade report는 실제 fill price 없이도 청산가처럼 보이는 값을 만들 수 있음

코드:
- `libs/reporting/trade_execution_snapshot.py`
- `libs/reporting/trade_story_pipeline.py`
- `libs/reporting/trade_report_ai.py`

현재 동작:
- `filled_price`가 없으면
  - context price
  - `monitor_context.average_price`
  - `monitor_context.current_price`
  같은 fallback을 사용한다.

즉 실제 Kiwoom 체결가가 비어 있으면 monitor 값이 report에 청산 proxy처럼 올라갈 수 있다.

### C. 수수료/세금은 아직 hot path truth가 아님

현재 report/exit/pnl 계산은 확정 fee/tax truth source 기준이 아니다.

즉 gross/net 분리가 아직 불완전하다.

## 확인된 실제 예시

대상 trade:
- `reports/trades/2026-04-20/TRD_20260420_209640_01`

확인된 상태:
- `exit_execution_details.filled_price = null`
- `exit_execution_details.avg_price = 6290.0`
- `monitor_reason_human.current_price = 6220.0`
- report `shared_facts.pnl_pct = -0.012698...`

해석:
- 실제 broker fill price가 아니라 monitor 관측값이 exit proxy로 쓰였다.
- 앱과 report 손익률이 어긋날 수 있는 구조다.

## 현재 truth hierarchy 평가

지금 구조:
1. 일부 account truth
2. local/monitor fallback
3. reconciliation script 별도

필요한 구조:
1. Kiwoom broker/account/fill truth
2. last-known broker snapshot
3. local/monitor fallback

즉 현재는 truth-first 계층이 아직 뒤집혀 있다.

## 2026-04-20 Hot Path Update

- `libs/read/kiwoom_order_fill_reader.py`
  - `kt00007` / `kt00009` module owner added
- `libs/read/kiwoom_day_pnl_reader.py`
  - `ka10074` / `ka10077` / `ka10085` module owner added
- `libs/read/kiwoom_orderable_cash_reader.py`
  - `kt00001` / `kt00010` module owner added

### Live/report hot path now connected

- `libs/reporting/trade_bundle_assembly.py`
  - injects broker order-status truth
  - injects broker day-pnl truth for SELL-side execution context
- `libs/reporting/trade_execution_snapshot.py`
  - prefers broker fill truth for `filled_price`, `filled_qty`, `fill_status`
  - surfaces additive fields:
    - `broker_realized_pnl`
    - `broker_realized_pnl_pct`
    - `broker_fee`
    - `broker_tax`
    - `pnl_truth_source`
- `libs/reporting/trade_report_ai.py`
  - `shared_facts` now prefers broker realized pnl/pnl_pct when day-trade truth is authoritative
  - `shared_facts` now surfaces `broker_fee`, `broker_tax`, `pnl_truth_source`

### Current caution

- `ka10077` day-trade truth is treated as authoritative only when the match is unambiguous.
- Matching rule:
  - exact `symbol + filled_qty + filled_price`
  - else exact `symbol + filled_qty`
  - else exact `symbol + filled_price`
  - else only if there is exactly one symbol row
- ambiguous symbol-day aggregates are not promoted to report truth.


## 2026-04-20 Update: Orderable Cash Truth in Risk/Sizing
- Added `graphs/nodes/risk_cash_truth.py` as the thin cash-truth resolver for runtime risk.
- `build_risk_context` now carries:
  - `broker_deposit`
  - `broker_withdrawable_cash`
  - `broker_orderable_amount`
  - `capital_available_for_sizing`
  - `cash_truth_source`
  - `cash_truth_available`
- `daily_pnl_ratio` now prefers `broker_deposit` as denominator when broker cash truth is available.
- `decide_trade` now prefers `risk_context.capital_available_for_sizing` over raw `portfolio.cash`.
- `monitor_node` sizing cash resolution now prefers `risk_context.capital_available_for_sizing` over raw portfolio snapshot cash.
- Fallback order remains explicit:
  1. injected broker cash snapshot
  2. live `kt00001` deposit snapshot
  3. `portfolio.cash`


## 2026-04-20 Update: Cash Truth Observability
- `commander.json.observations` now surfaces broker cash truth fields:
  - `capital_available_for_sizing`
  - `cash_truth_source`
  - `cash_truth_available`
  - `broker_orderable_amount`
  - `broker_withdrawable_cash`
  - `broker_deposit`
- This closes the observability gap between `risk_context` and canonical commander artifacts.


## 2026-04-20 Update: Execution Truth Surface in AI Trade Report
- `ai_trade_report.json` / markdown execution section now surfaces broker execution truth more directly.
- Added execution truth bullets for:
  - broker fill price
  - broker realized pnl / pnl%
  - broker fee / tax
  - broker fill truth source
  - broker pnl truth source
- This reduces the previous ambiguity where broker truth was visible only through shared facts or monitor snapshot text.


## 2026-04-20 Update: Top-Level Truth Surface in AI Trade Report
- `ai_trade_report.json` now includes top-level `truth_surface`.
- `truth_surface` is a compact operator-facing view derived from `shared_facts`, not a second truth calculator.
- It groups:
  - `status`
  - `price`
  - `pnl`
  - `availability`
- This makes broker/account/monitor truth easier to read without traversing the full `shared_facts` block.

## 2026-04-20 Post-Market Artifact Validation

- Existing `reports/trades/2026-04-20/*/reports/ai_trade_report.json` artifacts were backfilled so `truth_surface` is now physically present in stored files.
- Current stored-day result for the four 2026-04-20 trades:
  - `price_truth_source = monitor_mark`
  - `pnl_truth_source = unavailable`
- Interpretation:
  - truth-surface visibility is now fixed at the artifact level
  - today’s saved report inputs still did not contain authoritative broker realized-pnl rows
  - next validation target is a day where Kiwoom fill/day-pnl truth is available end-to-end in stored trade report artifacts

## 2026-04-21 Validation Update

- `2026-04-21` stored trade reports now show broker truth end-to-end for executed trades when Kiwoom rows are available.
- Verified examples:
  - `reports/trades/2026-04-21/TRD_20260421_005380_01/reports/ai_trade_report.json`
  - `reports/trades/2026-04-21/TRD_20260421_000660_01/reports/ai_trade_report.json`
- Current stored truth surface now includes:
  - `price.broker_buy_price`
  - `price.broker_fill_price`
  - `pnl.value`
  - `pnl.pct`
  - `pnl.broker_fee`
  - `pnl.broker_tax`
  - `pnl.broker_day_truth_source`
  - `pnl.broker_day_match_mode`
  - `availability.broker_buy_present`
  - `availability.broker_pnl_present`

### Entry-side execution truth

- Entry-side `order_id` / `filled_price` is now preserved into:
  - `lifecycle_bundle.json`
  - `ai_trade_report_input.json`
- This closes the previous gap where sell-side broker truth could be rehydrated, but buy-side price had to depend on `ka10077.buy_price` or reverse estimation.

### Remaining runtime check

- Historical/regenerated reports now validate correctly.
- The remaining operational check is the next live trade:
  - confirm first-write `ai_trade_report_input.json` already contains entry-side broker truth
  - confirm no regeneration is required for `broker_buy_price` / `broker_fill_price` / broker pnl truth to appear

## 2026-04-21 Development Start: Ambiguous Day-PnL Tie-Breaker

- Added a conservative repeated-symbol tie-breaker for `ka10077` matching.
- New rule:
  - if exact `symbol + filled_qty + filled_price` still leaves multiple rows
  - and entry-side broker fill is unavailable
  - runtime may use monitor/account snapshot implied buy basis as a tie-breaker
  - only when the nearest row is clearly unique
- New match mode:
  - `symbol_qty_price_estimated_buy_anchor`
- This is still deterministic and conservative.
- It does not promote ambiguous rows unless the estimated buy anchor is materially better than the next candidate.

## 2026-04-21 Post-Close Result

- `2026-04-21` regenerated stored reports now show:
  - `12/12` trades with `price_truth_source = broker_fill`
  - `12/12` trades with `broker_day_authoritative = true`
  - `12/12` trades with `availability.broker_buy_present = true`
- Added a second repeated-symbol tie-breaker for cases where:
  - entry-side broker buy fill is missing
  - exact sell-side row candidates remain multiple
  - exit monitor still preserves the live position basis via `average_price` / `avg_price`
- New match mode:
  - `symbol_qty_price_monitor_buy_anchor`
- Confirmed recovery example:
  - `reports/trades/2026-04-21/TRD_20260421_005930_01/reports/ai_trade_report.json`
  - resolved from `ambiguous_symbol_rows` to authoritative using exit monitor `average_price = 217750`
