# 2026-05-12 live monitor crash hotfix

## 배경

- 장 시작 후 live loop가 09:00 직후 종료됨.
- watch 상태는 `RED`였고, 사유는 `loop_not_alive`, `event_lag_exceeded`, `window_empty`.
- 원인은 `graphs/nodes/monitor_node.py`의 strategy horizon translation 패치 중 `_extract_monitor_strategy_frame()`에서 존재하지 않는 `frame` 변수를 참조한 `NameError`.

## 수정

- `_extract_monitor_strategy_frame()`의 중복 horizon policy 추출 블록 제거.
- `_apply_exit_policy_strategy_frame()`에 `commander_horizon_policy`와 `behavior_translation` 추출을 명시 추가.
- 기존 적용부의 `frame` 참조는 실제 적용 frame을 받는 정상 경로라 유지.

## 검증

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py`: 통과.
- `venv\Scripts\python.exe -m pytest tests\test_strategy_horizon_feedback.py tests\test_intraday_monitor_signals.py tests\test_scanner_monitor_compatibility.py -q`: 81 passed.
- `venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py -q`: 99 passed.
- live one-shot 실행 정상 종료.
- live watch 09:33 KST 기준 `GREEN`, `loop_alive=true`, `event_lag_sec=0`.

## 런타임 확인

- `reports/canonical/2026-05-12/51b4563329d24a49ae1bd921a58d56cf` 기준:
  - commander/strategist/monitor에 `strategy_horizon=scalp`, `allow_behavior_translation=true`, `behavior_translation` 반영 확인.
  - scanner에 `scanner_chart_fit_score`, `scanner_chart_fit_authority=soft_rank_bias_only` 반영 확인.
  - monitor에 `human_chart_context` 반영 확인.

## 남은 관찰점

- scanner의 `scanner_chart_fit_components`가 일부 후보에서 `{}`로 비어 있음. minute feature가 부족한 후보의 정상 fallback인지, 계산 누락인지 장중 artifact를 더 쌓아서 확인 필요.
- live loop는 parent/child 두 Python 프로세스로 보이며 lock PID는 child가 보유함. 중복 주문 프로세스가 아니라 wrapper/child 구조로 관찰되지만, 이후 watch에서 PID/heartbeat를 계속 확인한다.
