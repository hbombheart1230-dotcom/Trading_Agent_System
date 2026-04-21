# Kiwoom Truth

이 폴더는 Kiwoom API를 런타임 truth source로 올리는 작업만 다룬다.

범위:
- 계좌 잔고/보유 truth
- 주문가능금액 truth
- 주문/체결 truth
- 당일 매매/실현손익 truth
- 수수료/세금 truth
- trade report 가격/손익 정렬

이 폴더는 아래 문서와 분리한다.
- `docs/runtime_memory`: strategist memory packet
- `docs/trade_report_plan`: report LLM / report canonicalization
- `docs/commander_control`: carry / session posture / commander doctrine

핵심 원칙:
1. Kiwoom API 값이 1순위 truth다.
2. Kiwoom 호출 실패 시에만 last-known broker snapshot을 쓴다.
3. 그것도 없을 때만 로컬 계산값이나 monitor 관측값을 쓴다.
4. fallback으로 쓴 값은 항상 source를 남긴다.

현재 확인된 hot path truth source:
- `kt00018`
  - 사용 위치:
    - `libs/kiwoom/kiwoom_account_client.py`
    - `libs/read/kiwoom_portfolio_reader.py`
    - `graphs/nodes/build_portfolio_snapshot.py`
    - `graphs/nodes/monitor_node.py`
    - `libs/runtime/exit_policy.py`

현재 확인된 non-hot-path broker source:
- `kt00007`
- `kt00009`
  - 사용 위치:
    - `scripts/demo_m14_order_status.py`
    - `scripts/run_broker_trade_reconciliation.py`
    - `config/skills/order.status.yaml`
    - `config/skills/account.orders.yaml`

즉 현재 구조는 부분적으로만 Kiwoom-first다.
- open position cross-check: 일부 Kiwoom-first
- trade report 청산 체결가/실현손익: 아직 monitor/local fallback 비중이 큼
- 당일 손익률: 현재 risk proxy와 broker truth가 섞여 있음

이번 축의 우선순위:
1. SELL 체결 truth 정렬
2. 수수료/세금 truth 정렬
3. 당일 실현손익/수익률 truth 정렬
4. 주문가능금액 truth 정렬
5. report JSON/MD field 분리 및 source 표기

검증 surface:
- broker/account truth:
  - `graphs/nodes/build_portfolio_snapshot.py`
  - `libs/read/kiwoom_portfolio_reader.py`
- 체결 truth:
  - `scripts/run_broker_trade_reconciliation.py`
  - `scripts/demo_m14_order_status.py`
  - 추후 hot path broker fill snapshot
- report truth:
  - `reports/trades/<day>/<trade_id>/ai_trade_report_input.json`
  - `reports/trades/<day>/<trade_id>/reports/ai_trade_report.json`
  - `reports/trades/<day>/<trade_id>/reports/ai_trade_report.md`

현재 이 폴더의 문서:
- `docs/kiwoom_truth/kiwoom_truth_current_state_2026-04-20.md`
- `docs/kiwoom_truth/kiwoom_truth_alignment_plan_2026-04-20.md`
- `docs/kiwoom_truth/kiwoom_scanner_strategist_inventory_2026-04-20.md`
- `docs/kiwoom_truth/kiwoom_role_inventory_2026-04-20.md`
