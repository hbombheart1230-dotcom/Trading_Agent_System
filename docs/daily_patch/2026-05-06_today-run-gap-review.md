# 2026-05-06 - 오늘 런 부족분 점검과 즉시 패치 후보

## Summary

오늘 기준으로 이전 daily patch의 남은 항목을 다시 보지 않아도 되게, 2026-05-06 런 산출물 기준의 현재 상태와 남은 패치 후보를 이 문서에 합쳤다.

결론:

- 런타임 자체는 정상 동작 중이다.
- 오늘 리포트/집계 정합성에는 즉시 손볼 만한 항목이 있다.
- 진입을 더 완화하거나 bounded probe lane을 먼저 켜는 것보다, 오늘은 report aggregation과 operator-facing 문구 정합성을 먼저 고치는 쪽이 맞다.

## Runtime Check

기준 시각:

- watch 갱신: 2026-05-06 11:55:07 KST
- loop PID: `4888`
- loop alive: `true`
- event lag: `0s`
- health: `GREEN`

최근 10분 live watch:

- window events: `325`
- strategist LLM: `3 ok / 0 error`
- execution verdict: `4`
- allowed / blocked: `1 / 3`
- executed: `1`
- broker fail: `0`
- executed action: `SELL 1`

운영 해석:

- 프로세스 정지나 broker 실패로 인한 공백은 아니다.
- watch snapshot은 09:13 이후 한동안 갱신되지 않았지만, 수동 `watch --once` 갱신 시 GREEN으로 확인됐다.
- runtime은 계속 canonical 산출물을 만들고 있었으므로, watch 자동 갱신/표시 계층이 운영 가시성 리스크다.

## Today Summary Snapshot

`reports/operator_summary/daily/2026-05-06/daily_summary.json` 기준:

- 총 거래: `9`
- 완료 거래: `8`
- return sample: `7`
- unavailable return: `1`
- Truth Surface count: `8`
- return basis: `truth_surface_net`
- 승패: `0승 / 7패`
- 평균 순손익률: `-0.83%`
- 가격 상승 또는 보합인데 비용 때문에 순손실: `4건`
- 관측-only 손실: `1건`

중요한 caveat:

- `036540_01`은 Truth Surface상 `8,620 -> 8,970`, 실현손익 `+2,711`, `+3.15%`가 있다.
- 하지만 lifecycle status가 `partial`이라 daily summary의 완료/승률/평균에는 들어가지 않았다.
- 이 거래를 "오늘 신규 진입 성과"가 아니라 "당일 실현된 carry/recovered partial 청산"으로 별도 집계하면, 확정 표본은 `1승 / 7패`, 평균은 약 `-0.34%`로 바뀐다.
- 따라서 현재 daily summary의 `0승 / 평균 -0.83%`는 intraday completed-only 관점으로는 맞지만, operator가 보는 "오늘 실현손익" 관점에서는 불완전하다.

## Immediate Patch Candidates

### P0 - recovered partial SELL 집계 분리

문제:

- `TRD_20260506_036540_01`은 entry evidence가 부족해 `partial`로 남았다.
- 동시에 exit evidence는 충분하다.
  - action: `SELL`
  - filled qty: `10`
  - filled price: `8,970`
  - broker day match: `symbol_qty_price_exact`
  - Truth Surface: `+3.15%`
- daily summary는 status가 `closed`가 아니므로 이 실현 이익을 승패/평균에서 제외했다.

패치 방향:

- `partial`을 무조건 closed로 바꾸면 안 된다. 진입 근거가 없는 거래와 당일 신규 진입 거래가 섞인다.
- 대신 operator summary에 별도 bucket을 추가한다.
  - `realized_exit_count`
  - `recovered_partial_exit_count`
  - `carryover_exit_count`
  - `realized_exit_return_sample_count`
  - `realized_exit_avg_return_pct`
- `status=partial`이어도 `last_action=SELL`, exit filled qty 존재, Truth Surface net return 존재하면 "당일 실현 청산"으로 집계한다.
- main intraday win/loss와 realized/carryover win/loss를 분리해서 보여준다.

우선순위:

- 당장 패치 필요.
- 운영자가 `ai trade report summary.md`와 daily summary를 같이 볼 때 가장 크게 오해할 수 있는 부분이다.

### P0 - recovered partial 리포트 문구 정리

문제:

- `036540_01` 리포트에 아래처럼 operator-facing 문구가 섞였다.
  - `상태: partial`
  - `진입 사유는 Entry evidence was 기록되지 않음 for this day...`
  - `스캐너 순위: 0위`
  - `청산 트리거: Stop Loss`
  - Truth Surface는 `+3.15%` 이익
- 실제 의미는 "당일 진입 근거가 부족한 회수/recovered 포지션 청산"에 가깝다.

패치 방향:

- recovered partial이면 진입 판단 섹션을 다음처럼 바꾼다.
  - `당일 진입 증거가 부족해 신규 진입 판단은 평가하지 않습니다. 이 리포트는 보유/회수 포지션의 당일 청산 결과를 중심으로 봅니다.`
- scanner rank `0위`는 숨기거나 `기록 없음`으로 표시한다.
- `Stop Loss`가 실제 순이익 청산과 충돌해 보이면, 청산 트리거 문구에 "모니터 신호명"과 "Truth Surface 실현손익"을 분리한다.

우선순위:

- 당장 패치 필요.
- 거래 판단 자체보다 리포트 해석 오류를 줄이는 패치다.

### P1 - daily summary runtime activity 보강

문제:

- daily summary markdown은 `런타임 이벤트: 0건`, 승인/차단 `0 / 0`으로 표시한다.
- 같은 시각 live watch는 최근 10분 기준 이벤트 `325`, 실행 `SELL 1`, broker fail `0`을 확인했다.
- `reports/operator_summary/daily/2026-05-06/daily_report.json`이 없어서 runtime activity가 0으로 fallback 된 상태다.

패치 방향:

- daily summary 생성 시 `daily_report.json`이 없으면 같은 날짜의 `reports/live_summary` 최신 JSON 또는 `data/logs/events.jsonl` 집계를 fallback으로 사용한다.
- operator summary에는 `runtime_activity_source`를 표시한다.

우선순위:

- 오늘 중 패치 후보.
- 매매 판단에는 직접 영향이 없지만, 운영자가 런이 멈췄다고 오해할 수 있다.

### P1 - post-exit shadow refresh 확인

현재 상태:

- 최근 `018880_04`의 post-exit shadow는 `pending`, reason `no_rows_after_exit`다.
- exit 이후 minute row가 아직 리포트 생성 시점에 없어서 +5m/+15m checkpoint가 비어 있다.

패치 방향:

- runtime이 다음 minute 데이터를 받은 뒤 기존 trade report의 post-exit shadow를 자동 갱신하는지 확인한다.
- 자동 갱신이 없으면 별도 refresh job 또는 report regeneration hook이 필요하다.

우선순위:

- 오늘 장 마감 전 확인.
- 즉시 매매 로직 패치보다는 관측 데이터 채움 패치다.

### P2 - bounded probe lane

현재 상태:

- 오늘은 매매가 안 나오는 문제가 아니라, 매매는 발생했고 손익/청산/리포트 정합성이 더 큰 이슈다.
- strict lane 중심 운영은 유지 중이다.

판단:

- 당장 켜지 않는다.
- report aggregation과 exit behavior를 먼저 정리한 뒤, 반복적으로 "좋은 후보가 조건 1개 차이로 누락"되는 표본이 충분할 때 다시 본다.

### P2 - watchdog 자동 복구

현재 상태:

- lock owner와 canonical run은 살아 있다.
- watch snapshot은 자동 갱신이 끊겼다가 수동 갱신으로 GREEN 확인됐다.

판단:

- 런타임 자동복구보다 watch/visibility 갱신 문제가 먼저다.
- missing lock owner 또는 canonical gap 자동 재시작은 계속 백로그로 둔다.

## Cost Drag Read

오늘 현재까지 비용 드래그 패턴:

- daily summary 기준 cost-drag loss: `4건`
- 가격 상승/보합인데 순손실인 대표 케이스:
  - `047040_01`: 가격 +0.15%, 비용 드래그 약 0.90%, 순손실 -0.74%
  - `038880_01`: 가격 +0.10%, 비용 드래그 약 0.79%, 순손실 -0.70%
  - `018880_04`: 가격 +0.56%, 비용 드래그 약 0.88%, 순손실 -0.31%
  - `001510_01`: 가격 0.00%, 비용 드래그 약 0.87%, 순손실 -0.87%

판단:

- cost-aware filter/floor 자체는 런타임 산출물에 보인다.
- 다만 protective exit 계열(`stop_loss`, `vwap_breakdown`, `peak_drawdown`, `intraday_low_break`)은 net breakeven 전에도 나갈 수 있다.
- 이건 무조건 오류라고 보기 어렵지만, operator report에는 "가격은 올랐지만 비용 때문에 손실"과 "방어 청산이라 비용 floor를 무시한 것인지"를 분리해서 보여야 한다.

추가 패치 후보:

- daily summary에 `gross_positive_net_loss_count`와 `protective_exit_below_breakeven_count`를 분리한다.
- exit trigger별로 cost drag loss를 집계한다.

## Today's Decision

오늘 당장 필요한 패치:

1. recovered partial SELL을 daily summary에서 별도 실현 청산 bucket으로 집계한다.
2. recovered partial 리포트의 진입/스캐너/청산 문구를 operator-facing으로 정리한다.
3. daily summary runtime activity가 0으로 보이는 fallback을 고친다.

오늘 당장 하지 않을 패치:

1. bounded probe lane 활성화
2. 진입 threshold 완화
3. memory feedback 재활성화

이유:

- 오늘 문제의 핵심은 "매매가 없다"가 아니라 "매매 결과를 어떻게 정확히 해석하고 집계하느냐"다.
- 집계/문구를 먼저 고치지 않으면, 실제로는 +3.15% 실현 청산이 있는 날도 `0승 / 평균 -0.83%`처럼 읽혀 잘못된 전략 변경으로 이어질 수 있다.

## Patch Applied

적용 시각:

- 2026-05-06 장중

적용 내용:

1. `partial` 회수 매도 별도 집계 추가
   - 기존 `closed_trade_count`, `win_count`, `avg_return_pct`는 완료 거래 기준으로 유지했다.
   - 완료 외 실현 청산은 별도 bucket으로 노출한다.
   - 추가 필드: `realized_exit_count`, `recovered_partial_exit_count`, `carryover_exit_count`, `realized_exit_return_sample_count`, `realized_exit_win_count`, `realized_exit_loss_count`, `realized_exit_avg_return_pct`.

2. recovered partial 리포트 문구 정리
   - `TRD_20260506_036540_01`은 신규 진입 평가가 아니라 보유/회수 포지션의 당일 청산 결과로 표시한다.
   - 스캐너 순위 `0위`는 `기록 없음`으로 바꿨다.
   - 진입 판단 섹션은 "당일 진입 증거 부족, 신규 진입 평가는 제외"로 명시했다.
   - `Stop Loss` 신호명과 Truth Surface 실현 이익을 분리해 표시한다.

3. daily summary runtime fallback 추가
   - `daily_report.json`이 없으면 같은 날짜의 최신 `reports/live_summary/live_summary_*.json`을 fallback으로 읽는다.
   - runtime source를 `live_summary_fallback`으로 표시한다.

재생성 결과:

- `reports/trades/2026-05-06/TRD_20260506_036540_01/reports/ai_trade_summary.md`
- `reports/trades/2026-05-06/TRD_20260506_036540_01/reports/ai_trade_summary_input.json`
- `reports/operator_summary/daily/2026-05-06/daily_summary.md`
- `reports/operator_summary/daily/2026-05-06/daily_summary.json`

현재 daily summary 기준:

- 총 거래: `11`
- 완료 거래: `10`
- 완료 거래 성과: `0승 / 9패`, 평균 `-0.78%`
- 완료 외 실현 청산: `1건`, `1승 / 0패`, 평균 `+3.15%`
- runtime fallback: `live_summary_fallback`
- 최근 10분 runtime event: `325`
- 승인/차단: `1 / 3`

검증:

- `python -m py_compile libs/reporting/operator_period_summary.py libs/reporting/trade_report_markdown_clean.py`
- `pytest tests/test_operator_summary_reports.py tests/test_trade_report_ai.py::test_trade_summary_marks_recovered_partial_sell_as_exit_only -q`
- `pytest tests/test_trade_report_ai.py -q`
- `pytest tests/test_daily_report.py tests/test_operator_summary_refresh.py -q`

## Restart Note

재시작:

- 기존 live loop PID `7428` / lock owner `4888` 정리.
- stale `data/state/m13_live_loop.lock` 제거.
- live intraday loop 재시작.
- 새 parent PID: `23280`
- 새 lock owner PID: `19392`
- 실행 옵션: `--mode live --phase intraday --tick-pipeline integrated_chain --sleep-sec 30 --session-hard-gate --allow-offhours`

재시작 후 watch:

- 기준 시각: 2026-05-06 12:27:02 KST
- health: `GREEN`
- event lag: `0s`
- 최근 10분 events: `294`
- strategist LLM: `3 ok / 0 error`
- execution verdict: `5`
- allowed / blocked: `4 / 1`
- executed: `4`
- broker fail: `0`
- action counts: `BUY 2 / SELL 2`

부가 조치:

- 재시작 직후 `TRD_20260506_018880_05` 리포트 번들이 heartbeat 없이 멈춘 상태라 live loop는 유지하고 번들 PID `5024` / `18452`만 종료했다.
- stale `reports/runtime/intraday_trade_report_bundle.lock` 제거.
- 후속 watch 기준 live loop는 계속 `GREEN`이며 report bundle lock은 비어 있다.

## Quantity Cap Adjustment

적용 내용:

- `MAX_ORDER_QTY=10`을 `MAX_ORDER_QTY=100`으로 변경했다.
- 지휘관/모니터 position sizing의 `max_position_qty`는 이 값을 상한으로 사용한다.
- `MAX_ORDER_NOTIONAL=1500000`은 유지했다.

운영 해석:

- 저가 종목은 이제 수량 상한 때문에 10주에 막히지 않는다.
- 고가 종목은 여전히 금액 상한 `150만원` 안에서 수량이 계산된다.
- 예: 5,500원 종목은 100주까지 가능하지만, 56,000원 종목은 100주가 아니라 금액 상한 기준 약 26주 전후가 상한이다.

재시작 필요:

- live runtime은 시작 시점의 `.env`를 읽으므로, 변경 반영을 위해 live loop를 재시작한다.

재시작/확인:

- 기존 live loop PID `21124` / lock owner `25832` 정리 후 재시작.
- 새 parent PID: `21124`
- 새 lock owner PID: `25832`
- 2026-05-06 12:31:07 KST watch 기준 health `GREEN`, event lag `10s`, broker fail `0`.
- 2026-05-06 12:30:57 KST 이후 commander policy summary에서 `position_sizing_max_position_qty=100` 확인.

검증:

- `.env` 로딩 확인: `MAX_ORDER_QTY=100`, `MAX_ORDER_NOTIONAL=1500000`.
- 수량 가드 관련 테스트 통과:
  - `test_execute_from_packet_blocks_qty_limit_with_max_qty_alias`
  - `test_execute_from_packet_allows_sell_even_when_qty_exceeds_limit`
  - `tests/test_commander_env_migration_phase1.py`
- 참고: `tests/test_execute_from_packet.py tests/test_commander_env_migration_phase1.py` 전체 묶음은 33개 중 1개 실패했다. 실패 항목은 `252670`의 mock-broker restricted block 기대값보다 common-stock universe block이 먼저 걸리는 기존 우선순위 이슈로, 이번 수량 상한 변경과 직접 관련은 없다.

추가 조정:

- `MAX_ORDER_QTY=100`에서도 저가주가 계속 수량 상한에 걸려 `MAX_ORDER_QTY=1000`으로 확대했다.
- `MAX_ORDER_NOTIONAL=1500000`은 유지한다.
- 따라서 1,500원대 저가주는 1000주까지 가능하지만, 5,500원대 종목은 약 272주, 56,000원대 종목은 약 26주처럼 금액 상한이 계속 최종 cap 역할을 한다.
- `.env` 로딩 확인: `MAX_ORDER_QTY=1000`, `MAX_ORDER_NOTIONAL=1500000`.
- 기존 live loop PID `21124` / lock owner `25832` 정리 후 재시작했다.
- 새 parent PID: `10384`
- 새 lock owner PID: `6136`
- 2026-05-06 12:45:58 KST policy summary에서 `position_sizing_max_position_qty=1000` 반영 확인.
- watch 기준 broker fail은 `0`이다. health는 `YELLOW`였는데 사유는 최근 verdict가 전부 `noop_intent_skipped`로 차단되어 `blocked_rate_high`가 뜬 것이다.
