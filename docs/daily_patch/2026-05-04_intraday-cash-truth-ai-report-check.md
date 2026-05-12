# 2026-05-04 - 장중 현금 truth와 AI 리포트 점검

## Summary

2026-05-04 장중 점검의 핵심은 모의투자 재시작 이후 Kiwoom 인증, portfolio cash truth, live loop 상태, 그리고 `ai_trade_summary.md`의 운영 판단 문구가 실제 artifact와 일치하는지 확인한 것이다.

## Runtime Status

- 모의투자 만료 후 새 키로 교체했고, Kiwoom mock 인증은 정상 통과했다.
- 기존 오류였던 `[8001: App Key와 Secret Key 검증에 실패했습니다]`는 더 이상 재현되지 않았다.
- 토큰 캐시는 새 토큰으로 갱신됐다.
- live intraday loop는 패치 반영 후 재시작했다.
  - lock owner PID: `19248`
  - watch status: `GREEN`
  - event lag: `0s` 확인
- 최신 commander는 `portfolio_preflight.blocked=false`로 진입 전 계좌조회 차단 상태가 아니다.

## Cash Truth Fix

문제:

- 계좌에는 100,000,000원이 들어 있었지만 runtime snapshot은 cash를 2,000,000원 fallback으로 보고 있었다.
- Kiwoom `kt00018` 응답에는 `prsm_dpst_aset_amt=100000000`이 들어왔지만, parser가 앞의 `tot_evlt_amt=0`을 먼저 현금 후보로 잡았다.
- 결과적으로 계좌조회는 성공했는데도 cash가 0으로 해석되어 fallback cash가 적용됐다.

수정:

- `libs/read/kiwoom_portfolio_reader.py`
  - `_extract_cash()`에서 `prsm_dpst_aset_amt`, `day_stk_asst`, `dbst_bal`을 `tot_evlu_amt`, `tot_evlt_amt`보다 먼저 보도록 우선순위를 변경했다.
- `tests/test_m9_snapshots.py`
  - `prsm_dpst_aset_amt=100000000`, `tot_evlt_amt=0` 응답을 cash `100000000.0`으로 읽는 회귀 테스트를 추가했다.

검증:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_m9_snapshots.py
```

Result:

```text
19 passed
```

직접 snapshot 확인:

```text
reader_ok=true
source=reader
cash=100000000.0
cash_source=reader_cash_authoritative
positions_source=reader_positions_authoritative_empty
```

주의:

- `kt00001` 주문가능금액 truth는 현재 `broker_deposit=0`, `broker_orderable_amount=0`, `cash_truth_available=false`로 들어온다.
- 현재 sizing은 `portfolio.cash=100000000` fallback을 통해 `capital_available_for_sizing=100000000`을 사용한다.
- 장중 주문 거절이 발생하면 `kt00001` deposit/orderable parser 또는 body/header 요구사항을 별도 점검해야 한다.

## AI Trade Summary Files Reviewed

대상:

- `reports/trades/2026-05-04/TRD_20260504_018880_01/reports/ai_trade_summary.md`
- `reports/trades/2026-05-04/TRD_20260504_010170_01/reports/ai_trade_summary.md`
- `reports/trades/2026-05-04/TRD_20260504_006340_01/reports/ai_trade_summary.md`
- `reports/operator_summary/daily/2026-05-04/daily_summary.md`

확인된 거래 요약:

| Trade | Truth 기준 | 선정/진입 | 청산 | 리포트 주의점 |
| --- | --- | --- | --- | --- |
| `018880_01` | 4,810 -> 4,870 / +173 / +0.36% / fee 330 / tax 97 | scanner 1위 | `peak_drawdown` | entry gate가 `0.5474 < 0.55` 미통과로 표시되는데 실제 BUY가 실행됨 |
| `010170_01` | 17,340 -> 17,490 / -59 / -0.03% / fee 1,210 / tax 349 | 018880 보류 후 5위 재평가 | `trailing_stop` | 가격은 +0.87%지만 모의투자 비용 드래그 0.90% 때문에 net 손실 |
| `006340_01` | 17,420 -> 17,419 / broker PnL unavailable / fallback pct -0.90% | 018880 보류 후 4위 재평가 | `stop_loss` | `ka10077`가 `ambiguous_symbol_rows`라 확정 실현손익으로 읽으면 안 됨 |

## AI Report Quality Findings

1. `same_day_context.summary`가 리포트 생성 시점 기준이다.
   - `010170_01`은 자기 거래가 손실인데 `당일 성과: 1건 중 1승 / 0패 / 평균 0.36%`로 표시된다.
   - 이는 앞선 `018880_01`만 집계된 시점 값으로 보이며, 문구를 `리포트 생성 시점 이전 당일 집계`처럼 바꾸는 것이 안전하다.

2. `reports/operator_summary/daily/2026-05-04/daily_summary.md`의 평균 0.70%는 net realized PnL 기준이 아니다.
   - 018880 +0.36%, 010170 -0.03%, 006340 fallback -0.90%와 맞지 않는다.
   - 현재 표시는 가격 변동률 또는 gross 쪽에 가까워 보인다.
   - daily summary에는 `평균 손익률 기준: gross price move / broker realized / fallback observed`를 명시해야 한다.

3. `018880_01`은 진입 게이트 설명과 실제 BUY가 충돌한다.
   - report: `신뢰도 게이트 미통과`, `0.5474 / 0.5500`
   - artifact: 실제 BUY 체결 존재
   - 원인 후보: entry artifact에는 실제 entry gate detail이 충분히 없고, report가 exit 시점 monitor 재평가 값을 entry 판단처럼 사용했을 가능성이 있다.
   - 이 케이스는 2026-04-30에 고친 "실제 BUY 시점 게이트와 사후 모니터 게이트 분리"가 아직 모든 경로에 적용되지 않았는지 확인해야 한다.

4. `final_operator_summary`가 SELL 종결 거래에서도 `현재 판단은 진입 유지`라고 나온다.
   - 대상: `018880_01`, `006340_01`
   - closed SELL 거래에서는 `청산 완료` 또는 `포지션 종료`로 나와야 한다.

5. LLM 문장에 혼합 언어/비정상 토큰이 섞인다.
   - 예: `중립 inúmer`, `により`, `阈值`, `미달성况`
   - operator-facing markdown에는 post-sanitize가 필요하다.

6. 선택 사유 번역이 일부 덜 적용된다.
   - 예: `turnover and volume`
   - 표시 문구는 `회전율/거래량`으로 통일하는 것이 좋다.

7. `Route mix is led by monitor_only 0/105` 문구는 운영자가 오해하기 쉽다.
   - `led by`라고 쓰지만 count가 0이라 의미가 맞지 않는다.
   - route mix 집계 source와 numerator/denominator 의미를 다시 확인해야 한다.

## Patch Applied

수정:

- `libs/reporting/trade_report_ai.py`
  - 실제 BUY 시점 `entry_decision_detail`이 없고, 현재 모니터 스냅샷이 closed/SELL/보유·청산 축이면 entry gate로 쓰지 않는다.
  - 해당 값은 `post_entry_gate_observation`으로 분리해 "사후 모니터 재평가"로만 표시한다.
- `libs/reporting/trade_report_markdown_clean.py`
  - `당일 성과` 라벨을 `당일 성과(리포트 생성 시점 기준)`으로 변경했다.
  - `turnover and volume` 등 selection basis를 요약 입력/markdown 모두에서 한국어로 정규화했다.
  - `broker_day_authoritative=false` 또는 fallback mark-only 손익률은 `실현 손익`으로 표시하지 않고 `실현 손익: 확인 불가`, `관측 손익률`로 분리했다.
  - closed SELL인데 기존 report seed가 `현재 판단은 진입 유지`를 들고 있으면 요약 표시 단계에서 `현재 판단은 청산 완료`로 보정한다.
  - 기존/stale report에 이미 들어간 `진입 게이트 상태 ... 미통과`도 실제 BUY 체결 이후 사후 모니터 재평가와 혼재 가능성이 있으면 확정 진입 게이트로 표시하지 않는다.
  - LLM summary의 혼합 언어 토큰(`により`, `阈值`, `inúmer`, `况`)을 operator-facing markdown에서 정리한다.
- `libs/reporting/reporter_feedback.py`
  - route mix 리더 문구는 실제 count가 가장 큰 route를 기준으로 쓰고, 0-count route를 `led by`로 표시하지 않는다.
- `libs/reporting/trade_story_pipeline.py`, `libs/reporting/live_execution_bundle_runner.py`
  - closed lifecycle에서 entry 실행 객체가 anchor로 남아 있어도 exit outcome/action이 SELL이면 최종 운영 판단을 `청산 완료`로 만든다.

오늘 리포트 재렌더:

- `reports/trades/2026-05-04/*/reports/ai_trade_summary_input.json`
- `reports/trades/2026-05-04/*/reports/ai_trade_summary.md`

재렌더 후 확인:

- `TRD_20260504_018880_01`의 진입 판단은 `신뢰도 게이트 미통과`를 확정 진입 게이트처럼 표시하지 않고, 사후 모니터 재평가 혼재 가능성으로 표시한다.
- `TRD_20260504_006340_01`의 Truth Surface는 `실현 손익: 확인 불가`, `관측 손익률: -0.90%`, `가격 변동률: -0.01%`로 분리된다.
- `ai_trade_summary.md`와 `ai_trade_summary_input.json`에서는 `현재 판단은 진입 유지`, `turnover and volume`, `により`, `阈值`, `inúmer`, `Route mix is led by monitor_only 0` 잔여 문구가 검출되지 않았다.

검증:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_trade_report_ai.py
.\venv\Scripts\python.exe -m pytest tests\test_reporter_feedback.py tests\test_trade_story_pipeline_enrichment.py tests\test_live_execution_bundle_report.py -k "closed or final_operator_conclusion or lifecycle or route_summary_names_actual_leader or operator_conclusion_treats_sell"
```

Result:

```text
111 passed
12 passed / 91 deselected
```

## Cost-Aware Exit Patch

문제:

- 오늘 체결 중 일부는 매수가보다 매도가가 높았지만, 왕복 수수료/거래세 때문에 최종 수익률이 음수였다.
- 확인된 사례 기준 비용 드래그는 대략 0.89~0.90%였고, `000660_01`처럼 가격 움직임이 +0.07% 수준이면 실제로는 비용을 넘지 못한다.
- 기존 익절 트리거는 `+0.5%`, `+0.6%`, `+0.8%` 같은 작은 수익권에서도 청산 신호를 낼 수 있어, 1주 소액 거래에서는 “올라서 팔았는데 순손실”이 반복될 수 있었다.

수정:

- `libs/runtime/exit_policy.py`
  - `cost_aware_profit_floor_enabled`를 추가했다.
  - 기본 왕복 비용 바닥선은 `round_trip_cost_floor_pct=0.009`, 최소 순수익 버퍼는 `min_net_profit_buffer_pct=0.003`으로 잡아 총 `cost_aware_profit_floor_pct=0.012`를 적용한다.
  - 이익성 청산은 현재 손익률이 비용 인식 바닥선 아래면 `cost_aware_profit_floor_not_met`로 보류한다.
  - 손절, 하드스탑, 구조 붕괴 계열 리스크 청산은 비용 바닥선 때문에 막지 않는다.
  - `peak_drawdown`은 기본 분할익절보다 우선하게 유지했다. 이미 충분히 오른 뒤 고점 대비 급락한 상황은 수익 보호 청산으로 처리해야 하기 때문이다.
- `graphs/nodes/monitor_node.py`
  - monitor exit 기본값에 비용 인식 수익 바닥선을 반영했다.
  - 기본 분할익절/ladder/저항/VWAP 과확장/시간감쇠 익절 최소 기준을 `1.2%` 이상으로 올렸다.
  - monitor output, `monitor_exit`, threshold snapshot, reasoning trace에 비용 바닥선 적용 여부와 미달 gap을 남기도록 했다.
- `libs/reporting/trade_story_pipeline.py`
  - 리포트의 monitor stop policy trace에 `Cost-aware profit floor`를 표시하도록 했다.

운영 의미:

- 이제 `+0.5~0.9%` 수준의 작은 수익권은 기본적으로 바로 팔지 않고 관측/보유한다.
- `+1.2%` 이상이거나 명시적으로 더 높은 익절 조건을 넘을 때 이익성 청산이 가능하다.
- 손실 확대 방지용 stop loss, hard stop, vwap breakdown, intraday low break, trend breakdown은 그대로 작동한다.
- 이 패치는 수익을 보장하는 장치가 아니라, 비용을 넘지 못하는 “작은 gross 익절”을 줄이는 장치다.

검증:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_strategy_sizing_exit_upgrade.py tests\test_m29_3_monitor_exit_policy.py tests\test_monitor_exit_guard.py
.\venv\Scripts\python.exe -m pytest tests\test_trade_story_pipeline_enrichment.py tests\test_trade_report_ai.py
```

Result:

```text
130 passed
142 passed
```

## Intraday Checklist

장중에는 아래 순서로 본다.

1. Runtime health
   - `scripts/run_session.py --mode live --phase watch --once --json`
   - watch `GREEN`, `event_lag_sec`, loop PID, lock heartbeat 확인

2. Portfolio preflight
   - 최신 `reports/canonical/<day>/<run_id>/commander.json`
   - `portfolio_preflight.blocked=false`
   - `portfolio_state_summary.cash=100000000`
   - `observations.capital_available_for_sizing=100000000`

3. Cash truth
   - `kt00018` cash parser가 `prsm_dpst_aset_amt`를 우선하는지 확인
   - `kt00001` orderable amount가 계속 0이면 주문 거절 여부와 함께 별도 점검

4. Order guard
   - `MAX_ORDER_NOTIONAL=1500000` 기준 고가 1주 허용 여부 확인
   - BUY 발생 시 `execution.order_limit_guard.price_source`, `order_notional`, `max_notional`, `reason` 확인

5. AI trade summary
   - `truth_surface.pnl_truth_source`
   - `broker_day_authoritative`
   - `broker_day_match_mode`
   - `pnl_pct_display_role`
   - entry gate가 실제 BUY 시점인지 exit 재평가 시점인지 확인
   - final operator summary가 BUY/SELL/closed 상태와 맞는지 확인

6. Strategy behavior
   - 1순위 보류 후 4위/5위 차순위 진입의 기대값을 따로 집계
   - `peak_drawdown`, `trailing_stop`, `stop_loss`가 3분 내 청산을 과도하게 만드는지 확인
   - 모의투자 비용 드래그가 1주/소액 거래에서 성과를 왜곡하는지 별도 표시

## Late-Session BUY Guard

15:21 `036540` BUY는 의도된 오버나이트가 아니라 마감 전 신규매수 차단 경계가 부족했던 케이스로 분류했다.

원인:

- 모니터는 `minutes_to_close=10.4667`, `eod_flat_cutoff_min=10` 상태를 마감 차단 구간 밖으로 판단했다.
- 주문은 15:21에 접수됐지만 실제 체결은 15:30:29에 완료되어, 마감 closeout 경로가 포지션 보유를 보지 못했다.
- 미체결 BUY 주문을 closeout 경로에서 먼저 취소하는 보호 로직이 없었다.

수정:

- 신규 BUY 차단 전용 `monitor.entry.buy_closeout_cutoff_min`을 추가하고 기본값을 15분으로 둔다.
- EOD 강제 청산 컷오프(`monitor.exit.eod_flat.cutoff_min`)는 기존 10분 의미를 유지한다.
- Commander session closeout fast-path는 BUY 전용 15분 버퍼부터 활성화된다.
- Monitor는 `buy_closeout_cutoff_min`, `buy_blocked_closeout_window`를 artifact에 명시한다.
- Executor도 BUY 직전 동일 가드를 한 번 더 적용해 stale monitor output으로 들어온 주문을 차단한다.
- Closeout fast-path 진입 시 계좌 주문 내 미체결 BUY가 있으면 monitor/strategy를 돌리기 전에 `kt10003` CANCEL intent를 먼저 실행한다.

검증:

```powershell
.\venv\Scripts\python.exe -m pytest tests\test_monitor_exit_guard.py tests\test_m21_commander_runtime_entry.py tests\test_execute_from_packet.py
```

Result:

```text
191 passed
```

운영 확인 포인트:

- 마감 15분 이내 신규 BUY는 `buy_blocked_closeout_window`로 막혀야 한다.
- `runtime_fast_path.payload.cutoff_min`은 EOD 청산 기준 10분, `buy_cutoff_min`은 신규매수 차단 기준 15분으로 분리되어야 한다.
- 마감 구간에 미체결 매수 주문이 남아 있으면 `commander_pending_buy_cancel.detected=true`와 `decision_reason=session_closeout_pending_buy_cancel`가 남아야 한다.

## Follow-Up

- daily summary 평균 손익률에 truth basis를 붙인다.
- `reports/operator_summary/daily/2026-05-04/daily_summary.md`의 평균 0.70%가 gross/price-move/net realized 중 어느 기준인지 명시한다.
- 신규 리포트 생성 시 `entry_decision_detail` 누락률을 별도 metric으로 집계한다.

## Closure Review - 2026-05-06

- status: partially_closed
- closed_items:
  - cash truth 파싱은 `prsm_dpst_aset_amt` 우선순위 수정과 회귀 테스트로 닫았다.
  - SELL 종결 거래의 `현재 판단은 진입 유지` 오표시는 report markdown 보정과 재렌더로 닫았다.
  - 비용 드래그로 가격 상승 거래가 순손실이 되는 문제는 cost-aware exit patch와 2026-05-05 Truth Surface summary alignment로 닫았다.
  - 마감 15분 이내 신규 BUY 차단과 pending BUY cancel fast-path는 late-session BUY guard로 닫았다.
  - daily summary의 truth basis는 `truth_surface_net` / 관측-only 기준으로 분리됐다.
- remaining_open_items:
  - `entry_decision_detail` 누락률은 아직 신규 리포트 생성 지표로 별도 집계되지 않는다.
  - 일부 markdown 문장 품질/한글 렌더링 정리는 별도 리포트 품질 백로그로 남긴다.
- decision: 핵심 거래/현금/손익 정합성은 닫혔지만, 누락률 metric과 문장 품질 항목이 남아 있어 제목에는 아직 `클로즈`를 붙이지 않는다.
