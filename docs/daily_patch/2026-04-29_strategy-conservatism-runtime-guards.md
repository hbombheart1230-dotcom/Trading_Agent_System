# 2026-04-29 - 전략 보수성 진단과 런타임 안전장치

## Summary

2026-04-29 작업의 핵심은 "매매가 안 나오는 이유"를 전략/모니터/런타임으로 분리해서 확인하고, 중복 매수와 장마감 근접 판단 오류를 막는 안전장치를 문서화한 것이다.

## Main Updates

- 장전 `mock_live` 기준 preflight와 live intraday 실행 상태를 확인했다.
- 주간 매매 집계를 기준으로 전략가가 거의 항상 `defensive` 프레임을 내고 있음을 확인했다.
- `12:20` 이후 무매매 구간을 두 구간으로 분리했다.
  - `12:20-12:53`: 모니터가 후보를 계속 보되 VWAP 재회복, 돌파, 과확장, cooldown 등으로 NOOP 처리한 구간
  - `12:53-13:36`: 런타임 프로세스가 사라져 canonical run이 멈춘 구간
- 2026-04-28 late-session 중복 BUY 재발 방지를 위해 최근 BUY guard와 장마감 clock 재계산 규칙을 정리했다.
- `reports/milestones`는 운영 산출물 위치 정책에 맞춰 `reports/dev` 아래로 이동하는 방향으로 정리했다.

## Findings

- 모니터가 임의로 전부 막는 문제가 아니라, 전략가/지휘관 프레임 자체가 과도하게 보수적인 쪽으로 집중돼 있었다.
- `defensive`, `leader` bias, `require_vwap_reclaim=true`, `require_rebound=true`가 동시에 걸리면서 후보군이 넓어도 실제 BUY 통과 후보가 매우 적어졌다.
- 비용 드래그가 큰 고가 1주 종목은 차트상 본전처럼 보여도 수수료/세금 기준으로는 손실이 누적될 수 있었다.
- 무매매 원인은 반드시 `정상 거절`, `후보 미성숙`, `런타임 정지`로 분리해서 봐야 한다.

## Documents Updated

- `docs/runtime_entrypoint/preopen_readiness_2026-04-29.md`
- `docs/runtime_entrypoint/strategy_conservatism_review_2026-04-29.md`
- `docs/commander_control/duplicate_buy_and_closeout_guard_2026-04-29.md`

## Validation

Documented validation included:

```powershell
.\venv\Scripts\python.exe -m pytest .\tests\test_m28_1_runtime_profile_scaffold.py .\tests\test_m28_4_startup_preflight_check.py .\tests\test_strategist_llm_summary.py .\tests\test_strategist_explanation_contract.py .\tests\test_m31_17_theme_candidate_flow_upgrade.py .\tests\test_scanner_fallback_policy.py::test_commander_injects_scanner_policy_defaults_into_applied_policy -q
```

Result recorded in the 2026-04-29 readiness note:

```text
25 passed
```

Duplicate BUY / closeout guard validation was documented against:

- `tests/test_execute_from_packet.py::test_execute_from_packet_blocks_recent_same_symbol_buy_before_position_reflects`
- `tests/test_m21_commander_runtime_entry.py::test_m21_ensure_market_context_clock_fields_overrides_stale_minutes_to_close_from_tick_ts`
- `tests/test_monitor_exit_guard.py::test_monitor_overrides_stale_minutes_to_close_before_entry_closeout_guard`

## Follow-Up

- Add a cost-aware entry filter before loosening exits.
- Split strict entry lane and bounded probe lane.
- Add watchdog recovery for missing lock owner or canonical run gaps.
- Keep weekly profitability coverage warnings explicit when PnL truth is incomplete.

## Closure Review - 2026-05-06

- status: open
- closed_items:
  - cost-aware entry/exit cost visibility는 `entry_cost_filter`와 `cost_aware_profit_floor` 계열 산출물로 확인된다.
  - PnL truth 불완전성은 2026-05-05 Truth Surface summary alignment에서 `truth_surface_net`, `truth_surface_observation_only`, `cost_drag_loss_count`로 분리됐다.
- remaining_open_items:
  - bounded probe lane은 아직 운영 코드에서 독립 lane으로 닫히지 않았다. 현재는 strict lane 중심이다.
  - missing lock owner 또는 canonical run gap에 대한 watch 진단은 있으나, 자동 복구 watchdog 정책은 별도 구현이 남아 있다.
- decision: 위 2개 항목이 운영 코드/테스트/런타임 산출물로 확인되기 전까지 이 노트는 클로즈하지 않는다.
