# 클로즈 - 2026-04-30 - 진입 게이트 리포트 분리와 메모리 기본값 정리

## Closure Status

- status: closed
- closed_at: 2026-05-06
- close_reason: 후속 패치와 2026-05-06 런타임 산출물에서 주요 후속 항목이 모두 확인됐다.
- evidence:
  - position sizing은 `position_sizing_enabled`, `position_sizing_qty`, `position_sizing_reason` 형태로 commander/monitor 산출물에 노출된다.
  - trade report는 실제 진입 시점, 사후 모니터 재평가, 청산 직전 상태를 분리해서 표시한다.
  - 메모리 정책은 관측 전용/판단 개입 금지 기본값으로 고정됐다.
  - 장 초반 갭 필드(`previous_close`, `open_gap_pct`, `prev_close_distance_pct`)는 visibility/설명용으로 들어가며 하드 게이트로 쓰지 않는다.
  - order notional guard hydration과 test/live parity guard 검증까지 포함해 4/30 follow-up은 별도 오픈 항목 없이 닫는다.

## Summary

2026-04-30 작업의 핵심은 메모리 영향도를 관측 전용으로 낮추고, 장 초반 갭 관련 관측 필드를 추가하며, trade report가 실제 BUY 시점 게이트와 사후 모니터 게이트를 섞어 쓰지 않도록 고친 것이다.

## Main Updates

- `.env`에 늘어난 임시 정책 플래그를 줄이고 지휘관 런타임 코드의 얇은 기본값으로 이동했다.
- 전략가/지휘관의 메모리 활용은 당분간 비활성 또는 관측 전용으로 정리했다.
- scanner 후보 검토 범위를 top10으로 넓혀 상위 후보만 모니터가 확인하도록 운영 기준을 맞췄다.
- 장 초반 판단 설명을 위해 다음 필드를 관측/설명용으로 추가했다.
  - `previous_close`
  - `open_gap_pct`
  - `prev_close_distance_pct`
- 보유 중 종목 refresh 전략이 반복 실행되는 것으로 기대한 운영 관점에 맞춰 post-scanner refresh 흐름을 점검하고 개선했다.
- `050890_01` 리포트에서 실제 진입 시점 게이트와 사후 모니터 재평가 게이트가 섞여 보이는 문제를 수정했다.
- `199820_02` 리포트에서 브로커 당일 손익/체결가가 늦게 복구된 뒤에도 기존 요약이 누락값과 보합 판정을 유지하던 문제를 수정했다.

## Entry Gate Report Fix

문제:

- `TRD_20260430_050890_01` 리포트가 진입 설명에 `VWAP 재회복 미통과`, `신뢰도 게이트 미통과`, `0.5488 / 0.5500`을 표시했다.
- 실제 BUY 이벤트는 `reclaim_gate_ok=true`, `extension_ok=true`, `confidence_gate_ok=true`, `confidence_score=0.5500`이었다.
- 따라서 리포트가 사후 모니터 재평가 값을 진입 시점 값처럼 보여 준 것이 문제였다.

수정:

- `libs/reporting/trade_report_ai.py`에서 진입 설명용 게이트를 실제 `BUY` 또는 `entry_triggered=true`인 `entry_decision_detail`에서 가져오도록 변경했다.
- `monitor_timeline`이 비어 있으면 `artifacts.monitor_evidence_json`의 `monitor_evidence.json`을 보조로 읽는다.
- 사후 모니터 값은 별도 문장으로 분리했다.

현재 표시:

```text
진입 게이트 상태는 VWAP 재회복 통과, 과확장 점검 통과, 신뢰도 게이트 통과였습니다.
진입 게이트 점수는 0.5500이며 기준 0.5500과 동일했습니다.
사후 모니터 재평가 게이트는 VWAP 재회복 미통과, 과확장 점검 통과, 신뢰도 게이트 미통과였습니다. 점수는 0.5488 / 기준 0.5500였습니다.
```

## Runtime Defaults

지휘관 코드 안의 임시 기본값으로 정리한 정책:

- `COMMANDER_POST_SCANNER_REFRESH_ENABLED=true`
- `MEMORY_BIAS_OBSERVATION_ONLY=true`
- `USE_STRATEGY_MEMORY_FEEDBACK=false`
- `USE_STRATEGY_PERFORMANCE_MEMORY=false`
- `COMMANDER_MEMORY_USAGE_DISABLED=true`
- `STRATEGIST_MEMORY_USAGE_DISABLED=true`
- `STRATEGY_MEMORY_PERSIST_ENABLED=false`

운영 의미:

- 메모리는 저장/판단에 직접 개입하지 않고 관측 중심으로 남긴다.
- 전략가와 지휘관은 과거 데이터 품질 문제로 진입을 과도하게 보수화하지 않도록 막는다.
- post-scanner refresh는 유지해서 보유 중 종목의 재평가 누락을 줄인다.

## Validation

리포트 게이트 분리 검증:

```powershell
.\venv\Scripts\python.exe -m pytest -q tests/test_trade_report_ai.py
```

Result:

```text
108 passed
```

리포트 read model 기본값 영향 검증:

```powershell
.\venv\Scripts\python.exe -m pytest -q tests/test_trade_read_model.py
```

Result:

```text
4 passed
```

## Trade Report Truth Surface Fix

대상:

- `reports/trades/2026-04-30/TRD_20260430_199820_02`

문제:

- 최초 리포트는 브로커 당일 손익 매칭이 `ambiguous_symbol_rows`였고, 매도가/수수료/세금/실현손익 금액이 비어 있었다.
- 이후 재생성 가능한 근거에서는 `symbol_buy_sell_qty_exact`로 매칭이 개선됐지만, 기존 보고서는 누락값과 `보합` 판정을 계속 보여 줬다.
- read model의 기본 `pnl=0.0`이 확정 손익처럼 승격될 수 있어, 음수 관측 수익률이 `보합`으로 표시될 위험이 있었다.
- 요약 원인 해석이 청산 직전 모니터가 함께 감시한 `목표 수익 실현 기준` 문구를 실제 청산 원인으로 오인했다.

수정:

- `report_truth_surface`가 확정 손익값 또는 권위 있는 브로커 매칭 없이 `pnl_truth_source`만 있다고 해서 브로커 손익 확보로 표시하지 않도록 변경했다.
- 요약 입력/마크다운은 손익 금액이 없더라도 음수 관측 수익률이면 `손실 관측`으로 표시한다.
- read model의 provenance가 `default`인 `pnl=0.0`은 shared fact로 승격하지 않는다.
- 요약 원인 해석은 모니터 감시축 문구가 아니라 정규화된 실제 exit reason을 기준으로 `고정 손절`, `목표 수익`, `peak_drawdown`을 구분한다.
- `entry.json`/`exit.json` 루트 요약 필드에도 `execution_details`의 체결 요약을 백필해 폴더 직접 확인 시 누락처럼 보이지 않게 했다.
- 모니터 `Current drawdown`을 요약에서 `신호 기준 손익`으로 표시하던 문구를 `고점 대비 하락폭`으로 변경했다.
- `199820_02`는 LLM 모드로 재생성해 실제 리포트 파일을 업데이트했다.

업데이트 후 주요 값:

```text
매수가 / 매도가: 17,800 / 17,400
실현 손익: -554 (-3.11%)
수수료 / 세금: 120 / 34
브로커 당일 손익 매칭 방식: symbol_buy_sell_qty_exact
진입 게이트: VWAP 재회복 통과, 과확장 점검 통과, 신뢰도 게이트 통과
실제 청산 트리거: 고정 손절 기준
```

추가 검증:

```powershell
.\venv\Scripts\python.exe -m pytest -q tests/test_trade_bundle_state.py
```

Result:

```text
6 passed
```

관련 이전 검증:

```text
tests/test_commander_env_migration_phase1.py tests/test_m21_commander_runtime_entry.py
73 passed

tests/test_strategist_frame_llm_integration.py tests/test_commander_memory_policy.py tests/test_strategy_performance_feedback.py
47 passed
```

## Post-Exit Shadow Watchlist

문제:

- `TRD_20260430_001440_07`의 매도 후 가격 추적은 `no_rows_after_exit`로 남았다.
- `data/state.json`의 `001440` 분봉 최신 시각은 `2026-04-30T06:15:00+00:00`였고, 실제 매도 체결 시각은 `2026-04-30T06:17:52+00:00`였다.
- 즉 분봉 저장 자체는 있었지만, 매도 후 해당 종목을 계속 관측 대상으로 남기는 경로가 없어 `post_exit_shadow` checkpoint가 채워질 수 없었다.

수정:

- SELL 성공 시 `persisted_state.post_exit_shadow_watchlist`에 종목, 매도 시각, 매도 기준가, 만료 시각을 관측-only로 기록한다.
- 모니터 틱마다 active watchlist 종목 최대 3개를 의사결정과 분리해 분봉 갱신한다.
- BUY가 다시 발생하면 같은 종목의 post-exit watch를 정리한다.
- 라이브 리포트 생성기는 top-level state뿐 아니라 `persisted_state`, `skill_results`, `skill_results_history`의 분봉 후보까지 확인하고 가장 최신 row source를 사용한다.

검증:

```powershell
.\venv\Scripts\python.exe -m pytest -q tests\test_monitor_exit_guard.py
.\venv\Scripts\python.exe -m pytest -q tests\test_live_execution_bundle_report.py
.\venv\Scripts\python.exe -m pytest -q tests\test_update_state_after_execution.py
```

Result:

```text
92 passed
65 passed
21 passed
```

## Runtime Restart

패치 반영 후 live intraday 세션을 재시작했다.

- 이전 프로세스: `9952`, `5364`
- 새 parent PID: `17208`
- 새 child PID: `18416`
- command: `scripts\run_session.py --mode live --phase intraday --session-hard-gate`
- log prefix: `reports/runtime/run_session_live_intraday_report_gate_patch_20260430_105219`
- 새 canonical run 확인: `ca33b4de7f124c3ab698b15c73cedb33`

## Profit-Taking Exit Axes

문제:

- 기존 청산 정책은 `take_profit_pct` 고정 목표 외에는 수익권에서 능동적으로 줄이는 옵션이 부족했다.
- `peak_drawdown`, `trailing_stop`, `vwap_breakdown`은 실제로 수익 보전에도 쓰일 수 있지만 리포트/운영 관점에서는 손절성 트리거처럼 보였다.

수정:

- `exit_policy`에 다음 익절형 청산 축 8개를 추가하고 기본 활성화했다.
  - `partial_take_profit`: 1차 목표 수익 도달 시 일부 매도
  - `profit_ladder`: +0.5%, +1.0%, +1.5% 구간별 분할 익절
  - `vwap_extension_take_profit`: VWAP 과확장 상태에서 최소 수익을 확보했을 때 수익 실현
  - `resistance_take_profit`: 직전 고점/당일 고점/저항권 근접 시 수익 실현
  - `volume_exhaustion_take_profit`: 수익권에서 거래량/체결 강도 둔화 시 수익 실현
  - `opening_gap_profit_take`: 장초반 갭 상승 후 추격 매수 상태에서 빠른 수익 실현
  - `time_decay_profit_exit`: 일정 시간 경과 후 수익권이지만 고점 대비 되돌림이 나온 경우 수익 보전
  - `risk_reward_take_profit`: 유효 손절폭 대비 1R, 1.5R, 2R 목표 도달 시 수익 실현
- 새 설정은 `.env`를 늘리지 않고 모니터의 얇은 기본 정책으로만 넣었다.
- 각 축은 자기 설정값으로 독립 동작한다. 끄려면 해당 축의 threshold/fraction/levels를 명시적으로 `0` 또는 `[]`로 둔다.
- 방어 청산 우선순위는 유지했다. `stop_loss`, `peak_drawdown`, `vwap_breakdown`, `intraday_low_break`, `trend_breakdown`이 새 익절 축보다 먼저 평가된다.
- 장마감 오버나잇 판단에서는 부분익절/래더/R익절 같은 soft profit 신호를 매도 강제 blocker로 쓰지 않고 참고 positive signal로 기록한다.
- 모니터 `watch_axes`, `active_exit_axis`, report label, artifact 필드에 새 트리거를 반영했다.

운영 기본값:

```text
risk_reward_take_profit_rungs=[1.0, 1.5, 2.0]
risk_reward_take_profit_fraction=0.34
risk_reward_take_profit_r=1.0
risk_reward_take_profit_min_pct=0.006
partial_take_profit_pct=0.005
partial_take_profit_fraction=0.50
profit_ladder_levels_pct=[0.005, 0.010, 0.015]
profit_ladder_fraction=0.34
vwap_extension_take_profit_pct=0.030
vwap_extension_take_profit_min_pct=0.006
resistance_take_profit_near_pct=0.003
resistance_take_profit_min_pct=0.004
volume_exhaustion_take_profit_min_pct=0.006
volume_exhaustion_volume_ratio_max=0.80
volume_exhaustion_strength_max=0.75
opening_gap_profit_take_min_pct=0.004
opening_gap_profit_take_window_sec=1200
opening_gap_profit_take_fraction=1.0
profit_time_stop_sec=900
profit_time_stop_min_pct=0.006
profit_time_stop_peak_giveback_pct=0.003
```

## Follow-Up

- position sizing 활성화 후 다음 실거래 리포트에서 `position_sizing_enabled`, `position_sizing_qty`, `position_sizing_reason`, 실제 주문 수량을 함께 확인한다.
- daily patch 작성은 작업이 끝난 직후 이 폴더에 추가한다.
- trade report에는 계속 `실제 진입 시점`, `사후 모니터 재평가`, `청산 직전 상태`를 분리해서 표시한다.
- 메모리 정책은 관측 결과가 안정될 때까지 판단 개입을 금지한다.
- 장 초반 갭 필드는 우선 설명/가시성용으로 보고, 충분한 표본 전에는 하드 게이트로 쓰지 않는다.

## Entry Position Sizing

문제:

- `MAX_ORDER_QTY=10`, `MAX_ORDER_NOTIONAL=1000000`은 실행 직전의 하드 상한으로는 정상 동작했다.
- 하지만 모니터 진입 수량 계산이 꺼져 있으면 기본 매수 수량이 `1`주로 남는다.
- 1주 포지션에서는 `partial_take_profit`, `profit_ladder` 같은 분할 익절 축이 실질적으로 작동하기 어렵다.
- 수량 계산의 손절폭이 기본 `3%`에 머물면, 실제 진입 근거가 깨지는 가격과 sizing risk가 어긋날 수 있다.

수정:

- 지휘관 적용 정책에 얇은 기본 position sizing을 추가했다. `.env` 키를 새로 늘리지 않고 기존 주문 한도 값을 그대로 참조한다.
- 기본값은 `enabled=true`, `risk_per_trade_ratio=0.01`, `position_notional_ratio=0.50`, `min_position_qty=1`, `lot_size=1`이다.
- `max_position_qty`는 `MAX_ORDER_QTY`를, `max_position_notional`은 `MAX_ORDER_NOTIONAL`을 상한으로 사용한다.
- 모니터는 `applied_policy.monitor.entry.position_sizing`을 읽어 진입 수량을 산정한다.
- sizing 계산기는 `max_order_qty`, `max_order_notional` 별칭도 받아서 주문 한도와 sizing 상한이 어긋나지 않게 했다.
- sizing 실행 시점을 entry signal 평가 뒤로 옮겨, 실제 entry metrics의 `vwap`, `breakout_level`, `recent_high`, `prior_bar_low`, `current_low`를 볼 수 있게 했다.
- 구조적 무효화 가격이 있으면 `stop_loss_pct`를 고정 3% 대신 `(진입가 - 무효화가) / 진입가`로 계산한다.
- 너무 가까운 구조선 때문에 과대 sizing되지 않도록 기본 최소 구조 손절폭은 `0.8%`로 둔다.
- sizing 결과에는 `stop_loss_source`, `invalidation_price`, `raw_structure_stop_loss_pct`를 남긴다.
- BUY 체결 후에는 진입 수량 산정에 사용한 `stop_loss_pct`를 `position_entry_risk_by_symbol`에 저장한다.
- 보유 중 모니터 청산 정책이 이 값보다 느슨한 손절폭을 쓰려 하면, 진입 sizing 손절폭으로 `stop_loss_pct`를 조인다.

운영 의미:

- 실행 가드는 여전히 최종 방어선이다. 주문 수량/금액이 한도를 넘으면 실행 직전에 막힌다.
- sizing은 그보다 앞단에서 “몇 주를 살지”를 정한다.
- `hard_stop`은 장애/급락 대비 최종 방어선이고, 실제 일반 손절 기준은 진입 때 계산한 구조적 무효화 손절폭보다 넓어지지 않는다.
- 예를 들어 현금 200만원, 가격 56,500원, 손절폭 3%, `MAX_ORDER_QTY=10`, `MAX_ORDER_NOTIONAL=1000000`이면 위험 예산과 금액 예산을 계산한 뒤 최종 수량은 10주 상한에 맞춰진다.
- 현금, 가격, 손절폭, 리스크 배수에 따라 10주보다 작아질 수는 있다.
- 이제 장 초반 VWAP 재회복/돌파 진입은 가능한 경우 VWAP floor, 돌파선, 직전 저점 같은 구조선을 sizing stop으로 사용한다.
- 명시적인 `invalidation_price`, `stop_price`, `structural_stop_price`가 들어오면 그 값을 우선한다.

## Test/Live Parity Guard

문제:

- pytest 중 일부 리포트 번들 경로가 기본 `data/logs/events.jsonl`로 이벤트를 써서, 운영 로그에 `.pytest-work` 경로가 섞일 수 있었다.
- 지휘관의 `position_sizing.max_position_notional`은 라이브 `.env`가 로드되면 `MAX_ORDER_NOTIONAL=1000000`을 보지만, 테스트처럼 env가 비어 있으면 코드 기본값이 `0.0`으로 떨어질 수 있었다.
- `applied_policy`에는 position sizing 기본값이 들어가도 `commander_applied_policy_summary` 상위에는 해당 값이 없어, 운영자가 라이브 요약만 보면 테스트 기대와 다르게 보일 수 있었다.

수정:

- pytest 중 명시 env 없이 canonical 운영 로그 경로를 쓰려는 `EventLogger`는 `data/logs/dev/testing/pytest_events.jsonl`로 자동 우회한다.
- 지휘관 코드 기본 `max_position_notional`을 `1,000,000`으로 맞췄다.
- `commander_applied_policy_summary` 상위에도 `position_sizing_enabled`, risk/notional ratio, max qty/notional을 노출한다.

검증:

```powershell
.\venv\Scripts\pytest.exe -q tests\test_event_logger.py tests\test_commander_env_migration_phase1.py tests\test_m29_4_monitor_position_sizing.py tests\test_m29_3_monitor_exit_policy.py tests\test_update_state_after_execution.py tests\test_live_execution_bundle_report.py::test_live_execution_bundle_report_skips_when_background_job_is_already_running
```

Result:

```text
52 passed
data/logs/events.jsonl delta=0
```

운영 메모:

- 기존 `data/logs/events.jsonl`에는 과거 pytest 오염 이벤트가 남아 있다. 이번 패치는 추가 오염 방지이며, 과거 로그 정리는 별도 승인 후 날짜/패턴 기준으로 해야 한다.

## Order Notional Guard Hydration

문제:

- 2026-04-29 `000660` 거래는 1주 매수였지만 체결 단가가 각각 `1,299,000`, `1,301,000`이라 `MAX_ORDER_NOTIONAL=1,000,000`을 초과했다.
- 당시 산출물에는 position sizing이 비활성 상태였고, 주문 intent의 가격이 비어 있는 시장가 경로에서 주문 직전 금액 계산이 평가되지 않을 수 있었다.
- 결과적으로 "1주" 수량 제한은 통과했지만, `qty * price` 금액 제한이 가격 부재 때문에 최종 방어선으로 동작하지 못했다.

수정:

- `execute_from_packet` 주문 금액 가드가 `order.price`가 비어 있으면 `selected`, `scanner_selected_snapshot`, `market.quote`, `market_snapshot`에서 평가 가격을 보강한다.
- `MAX_ORDER_NOTIONAL`이 설정된 BUY에서 평가 가격을 끝내 찾지 못하면 `order_notional_price_missing`으로 실행을 차단한다.
- degrade mode 금액 가드도 동일하게 관측 가격을 보강하고, BUY 가격 미확인 시 `degrade_missing_price_for_notional_guard`로 차단한다.
- `Supervisor`의 strategy position sizing 정책에도 `max_position_notional` 검사를 추가해, 실행 직전 가드와 전략 정책 가드가 같은 방향으로 동작하게 했다.
- legacy `ExecutorAgent` 직접 실행 경로도 `MAX_ORDER_NOTIONAL`이 켜진 BUY에서 가격이 없으면 실행하지 않는다.

검증:

```powershell
.\venv\Scripts\pytest.exe -q tests\test_execute_from_packet.py tests\test_supervisor.py tests\test_m15_smoke.py tests\test_m16_approval_api.py tests\test_m23_5_safe_degrade_execution_policy.py tests\test_m29_4_monitor_position_sizing.py tests\test_strategy_sizing_exit_upgrade.py
```

Result:

```text
73 passed
```

추가 회귀 검증:

```powershell
.\venv\Scripts\pytest.exe -q tests\test_commander_env_migration_phase1.py tests\test_commander_env_migration_phase2.py tests\test_m21_commander_runtime_entry.py tests\test_event_logger.py tests\test_live_execution_bundle_report.py::test_live_execution_bundle_report_skips_when_background_job_is_already_running tests\test_m29_4_monitor_position_sizing.py tests\test_strategy_sizing_exit_upgrade.py tests\test_m29_3_monitor_exit_policy.py tests\test_update_state_after_execution.py tests\test_execute_from_packet.py tests\test_supervisor.py tests\test_monitor_exit_guard.py tests\test_m15_smoke.py tests\test_m16_approval_api.py tests\test_m23_5_safe_degrade_execution_policy.py
```

Result:

```text
285 passed
```

운영 메모:

- 내일 장중에는 고가 종목 BUY가 나올 경우 `execution.order_limit_guard.price_source`, `order_notional`, `max_notional`, `reason`을 먼저 확인한다.
- 정상 기대값은 100만원 초과 고가 1주 BUY가 `order_notional_limit_exceeded` 또는 가격 미확인 시 `order_notional_price_missing`으로 막히는 것이다.
