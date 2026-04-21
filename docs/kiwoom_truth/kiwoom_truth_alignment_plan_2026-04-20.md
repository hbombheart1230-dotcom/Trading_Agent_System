# Kiwoom Truth Alignment Plan

## 목표

Kiwoom API를 runtime/report truth의 1순위 source로 올린다.

우선순위:
1. 실제 청산 체결가
2. 실제 실현손익
3. 수수료/세금
4. 주문가능금액
5. 당일 손익률 현황

이 순서를 지킨다.
이유:
- app과 report의 가장 큰 충돌은 청산 체결가/손익률이다.
- 주문가능금액과 당일 손익률도 중요하지만, exit truth보다 뒤다.

## 원칙

### Truth hierarchy
1. Kiwoom API response
2. last-known broker snapshot
3. local computed fallback

### Field rule
- truth 값과 fallback 값을 섞어서 하나의 필드처럼 보이게 두지 않는다.
- source를 분리한다.

예:
- `broker_fill_price`
- `account_mark_price`
- `monitor_mark_price`
- `pnl_truth_source`

## 단계별 계획

### Phase 0. Source inventory 고정

먼저 실제 쓸 Kiwoom source를 문서와 코드에서 고정한다.

현재 확인 완료:
- `kt00018`: hot path 사용 중
- `kt00007`: 수동/skill/reconciliation
- `kt00009`: 수동/skill/reconciliation

아직 필요한 것:
- 주문가능금액 truth endpoint
- 당일 실현손익/수익률 truth endpoint
- fee/tax truth source

주의:
- endpoint id는 catalog/코드에서 확인되기 전까지 가정으로 박지 않는다.

### Phase 1. SELL 체결 truth hot path 연결

가장 먼저 할 일이다.

목표:
- SELL 이후 `ord_no` 기준으로 broker fill을 조회해서
- `exit_execution_details.filled_price`를 비우지 않게 만든다.

후보 연결 지점:
- `libs/reporting/trade_execution_snapshot.py`
- `libs/reporting/live_execution_bundle_runner.py`
- `graphs/nodes/monitor_node.py`

필수 저장값:
- `ord_no`
- `filled_qty`
- `filled_price`
- `fill_status`
- `broker_fill_ts`
- `truth_source = broker_fill`

현재 가장 중요한 결함:
- `filled_price`가 비면 monitor 값이 청산 proxy로 올라간다.

### Phase 2. Fee / tax / net pnl truth 연결

SELL 체결 truth 다음 우선순위다.

목표:
- gross pnl과 net pnl을 분리
- fee/tax를 broker truth로 저장

필수 필드:
- `broker_fee`
- `broker_tax`
- `broker_realized_pnl_gross`
- `broker_realized_pnl_net`

주의:
- fee/tax source가 API 직접 제공인지, order/fill row derivation인지 먼저 확인해야 한다.

### Phase 3. Report field 분리

trade report에 아래를 분리해서 남긴다.

필수 필드:
- `broker_fill_price`
- `broker_realized_pnl`
- `broker_realized_pnl_pct`
- `broker_fee`
- `broker_tax`
- `account_mark_price`
- `monitor_mark_price`
- `price_truth_source`
- `pnl_truth_source`

이 단계 전까지는 markdown/JSON에 청산가처럼 보이는 monitor proxy를 단일 진실처럼 보여주면 안 된다.

### Phase 4. 당일 손익률 truth 정렬

현재:
- `daily_pnl_ratio`는 risk proxy

분리 목표:
- `risk_daily_pnl_ratio`
- `broker_day_realized_pnl_ratio`

즉 전략/risk용 proxy와 계좌 앱 truth를 같은 이름으로 쓰지 않게 만든다.

### Phase 5. 주문가능금액 truth 연결

목표:
- sizing/risk/supervision이 실제 주문가능금액을 볼 수 있게 한다.

현재는 보유/미실현 쪽이 먼저고, 주문가능금액 truth는 별도 정렬이 필요하다.

## 구현 우선순위

### 1순위
- SELL 체결 truth
- report price/pnl source 분리

### 2순위
- fee/tax
- net pnl truth

### 3순위
- 당일 손익률 truth
- 주문가능금액 truth

## 검증 기준

### SELL truth 검증
- 앱 체결가 == `exit_execution_details.broker_fill_price`
- 앱 체결수량 == `filled_qty`
- report `pnl_truth_source == broker_fill`

### fallback 검증
- Kiwoom 조회 실패 시에만 fallback 사용
- fallback이면 JSON/MD에 source가 남아야 함

예:
- `price_truth_source = account_mark_fallback`
- `pnl_truth_source = monitor_proxy`

### regression 검증
- 기존 open-position exit 판단이 깨지지 않아야 함
- `kt00018` 기반 account cross-check는 유지

## 지금 하지 말아야 할 것

1. monitor current price를 실제 청산가처럼 계속 쓰는 것
2. fee/tax 없는 gross pnl을 확정 손익처럼 쓰는 것
3. `daily_pnl_ratio`를 계좌 앱 당일 손익률처럼 해석하는 것
4. endpoint truth가 확인되지 않은 필드를 임의 이름으로 먼저 고정하는 것

## 현재 라운드의 출력물

이 문서는 우선순위만 고정한다.
다음 구현 라운드는 아래 순서로 간다.

1. source inventory 확인
2. SELL fill truth patch
3. fee/tax patch
4. report field/source split patch

## Phase Status Update: 2026-04-20

### Completed in this round

1. `kt00007` / `kt00009` module owner extraction
2. broker fill truth injection into report hot path
3. `ka10077` day-trade realized pnl / fee / tax injection into `execution_details`
4. `shared_facts` broker truth preference for pnl/pnl_pct when the match is authoritative

### Next priority

1. fee/tax/day pnl values in markdown and operator-facing report surfaces
2. explicit `broker_fill_price` / `account_mark_price` / `monitor_mark_price` separation
3. orderable-cash truth integration into sizing/risk
4. broader day-pnl truth validation against live Kiwoom fills


## Completed Slice: Orderable Cash Truth -> Risk/Sizing
- Implemented thin resolver: `graphs/nodes/risk_cash_truth.py`
- Connected broker cash truth to:
  - `graphs/nodes/build_risk_context.py`
  - `graphs/nodes/decide_trade.py`
  - `graphs/nodes/monitor_node.py`
- This is additive only. It does not remove `portfolio.cash`; it gives runtime sizing a higher-priority broker truth source.

## Next Kiwoom Truth Priority
1. Live verification that `risk_context.capital_available_for_sizing` is reflected in fresh artifacts.
2. Surface `cash_truth_source` more explicitly in operator/report observability where useful.
3. Keep fee/tax/day-PnL truth broker-first and verify app/report alignment on the next real SELL artifacts.


## Completed Slice: Cash Truth Artifact Surface
- Added cash-truth observability to `libs/contracts/agent_outputs.py`.
- Canonical `commander.json` can now be used to verify whether sizing/risk consumed broker cash truth or raw portfolio cash.
- After-hours note: live intraday loop may not stay up after market close, so builder-level verification is acceptable for this slice.


## Completed Slice: AI Trade Report Execution Truth Surface
- Added `libs/reporting/execution_truth_surface.py` as a thin owner for broker execution truth display lines.
- Added top-level `truth_surface` in `ai_trade_report.json` as the compact operator-facing truth block derived from `shared_facts`.
- Connected it to:
  - `_build_execution_quality_section(...)`
  - `render_trade_report_markdown(...)`
- Result: execution section now states broker fill/pnl/fee/tax and truth-source lines directly instead of hiding them under monitor snapshot only.
