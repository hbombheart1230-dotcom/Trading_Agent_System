# 2026-05-07 - Live Open Patch Verification

## Context

장 시작 후 어제 패치가 실제 라이브 런타임에 반영됐는지 확인했다.

확인 대상:

- 전략가 출력 세분화: `tactical_strategy`, `strategy_scores`, `rejected_strategy_reasons`, `candidate_watch_policy`
- Commander 후보 감시 범위 clamp
- Scanner/Monitor 후보 cascade visibility
- 전일 종가/시가 갭 관측 필드
- 비용 인식 익절/보호청산 필드
- KOSPI/KOSDAQ 국내 지수 컨텍스트

## Runtime Evidence

라이브 루프 상태:

- lock owner: PID `9976`
- heartbeat: `2026-05-07T00:56:27+00:00`
- 프로세스 상태: alive

라이브 산출물 확인:

- LLM strategist summary에는 `strategy_detail` 섹션이 생성됨.
- LLM response에는 `tactical_strategy`, `strategy_scores`, `candidate_watch_policy`가 포함됨.
- Commander artifact에는 `candidate_watch_policy_detected=true`, `candidate_watch_policy_applied=true`, `candidate_watch_policy_effect=commander_clamped_execution`가 찍힘.
- open position 상태에서는 Commander가 `max_priority_rank=1`, `max_runner_ups=0`, `reason=open_position_present`로 clamp함.
- Monitor artifact에는 `previous_close`, `open_gap_pct`, `prev_close_distance_pct`가 찍힘.
- Monitor exit watch axes에는 `Cost-aware profit floor`, `Partial take profit`, `Profit ladder`, `Risk/reward take profit`, `VWAP extension take profit`가 포함됨.
- Scanner artifact에는 `market_representative_guard_enabled=true`가 찍힘.
- Strategist artifact에는 KOSPI/KOSDAQ 국내 지수 컨텍스트가 포함됨.

## Gap Found

어제 패치의 실행 경로는 들어갔지만, canonical strategist artifact 최상위에는 전략 세분화 필드가 직접 복사되지 않았다.

영향:

- 매매 판단에는 큰 영향 없음.
- LLM summary와 Commander 실행 경로는 이미 해당 필드를 사용 중.
- 다만 `reports/canonical/.../strategist.json`만 직접 보면 `tactical_strategy`, `strategy_scores`, `candidate_watch_policy`가 누락돼 추적 정합성이 떨어짐.

## Patch Applied

`libs/contracts/agent_outputs.py`의 `build_strategist_output_artifact`에 다음 필드를 top-level 및 `strategy_detail`로 보강했다.

- `pre_llm_playbook`
- `llm_requested_playbook`
- `requested_playbook`
- `requested_playbook_source`
- `final_playbook`
- `tactical_strategy`
- `strategy_scores`
- `rejected_strategy_reasons`
- `candidate_watch_policy`
- `strategy_detail`

테스트 보강:

- `tests/test_phase1_agent_artifact_quality.py`

## Validation

통과:

- `python -m py_compile libs/contracts/agent_outputs.py`
- `pytest tests/test_strategist_frame_llm_integration.py tests/test_strategist_llm_summary.py tests/test_monitor_candidate_cascade.py tests/test_monitor_feedback_adaptive_policy.py tests/test_korea_market_indices_context.py tests/test_kiwoom_market_index_reader.py -q`
  - `53 passed`
- `pytest tests/test_phase1_agent_artifact_quality.py::test_strategist_artifact_contains_phase1_sections tests/test_strategist_llm_summary.py tests/test_trade_report_ai.py::test_ai_trade_report_surfaces_candidate_watch_execution_visibility -q`
  - `6 passed`

## Restart Note

이번 보강은 canonical artifact 출력 보강이다. 현재 실행 중인 live process에는 다음 재시작 후 반영된다.

즉시 매매 판단 로직에는 영향이 없으므로 장중 즉시 재시작은 필수는 아니다.

## Order Path Check

어제 전략 세분화/후보 감시 패치 때문에 주문 경로가 막힌 것은 아니다.

2026-05-07 장초반 canonical executor 기준:

- executor artifact: `19`
- action counts: `BUY 3`, `SELL 1`, `NOOP 15`
- 실제 주문번호 확인: `3`
  - `034020` BUY `10주`, 주문번호 `0061443`
  - `034020` SELL `10주`, 주문번호 `0061748`
  - `088800` BUY `289주`, 주문번호 `0064939`

대부분의 미매매는 `noop_intent_skipped`이며 monitor가 BUY intent를 만들지 않은 정상 대기였다.

주요 no-trade 사유:

- `below_vwap_reclaim_not_ready`
- `pullback_below_vwap_reclaim_not_ready`
- `pullback_not_mature`
- `post_exit_cooldown`

별도 발견 이슈:

- `033790`은 monitor가 BUY intent를 냈지만 supervisor에서 `order_notional_price_missing`으로 막혔다.
- monitor artifact에는 `current_price=16920`이 있었지만, executor notional guard가 monitor 가격을 fallback으로 보지 못했다.

추가 보강:

- `graphs/nodes/execute_from_packet.py`
  - order meta 가격 후보를 notional guard 가격 소스로 추가.
  - `monitor_output`, `monitor`, `monitor_snapshot`, `monitor_state`의 현재가를 notional guard fallback으로 추가.
  - `position_snapshot.current_price`도 fallback으로 추가.
- `tests/test_execute_from_packet.py`
  - monitor 현재가로 notional guard가 가격을 평가하는 회귀 테스트 추가.

검증:

- `python -m py_compile graphs/nodes/execute_from_packet.py tests/test_execute_from_packet.py`
- `pytest tests/test_execute_from_packet.py::test_execute_from_packet_uses_monitor_price_for_notional_guard_when_order_price_missing tests/test_execute_from_packet.py::test_execute_from_packet_blocks_notional_limit_using_selected_price_when_order_price_missing tests/test_execute_from_packet.py::test_execute_from_packet_blocks_buy_when_notional_guard_price_missing -q`
  - `3 passed`

재시작 필요:

- 이 보강은 executor 경로 코드 변경이므로 live process 재시작 후 적용된다.

## Summary Report Noise Policy

요약 리포트는 판단에 필요한 핵심값만 표시한다.

- 후보 감시 요약은 지휘관 적용 범위와 최종 후보만 표시한다.
- 전략가 후보 감시 사유, clamp 사유, 항목 설명은 세부 trade report에서만 확인한다.
- 값이 없는 후보 감시 제안은 `-`로 출력하지 않고 요약에서 생략한다.
- 뉴스 표본이 없을 때 요약에는 `표본 없음`만 표시하고 원문 확인 경로 설명은 넣지 않는다.
- `종목 선정 흐름`에는 내부 정책 문장 대신 `실제 확인: 차순위 미실행 (1순위 034020, 사유: 보유 포지션 존재)`처럼 운영자가 바로 판단할 수 있는 형태만 표시한다.

적용 파일:

- `libs/reporting/trade_report_markdown_clean.py`
- `tests/test_trade_report_ai.py`

## Operator Summary Check

현재 `reports/operator_summary` 집계는 원본 symbol trade history 기준으로 정상 대조됐다.

- 2026-05-07 daily: 거래 `4건`, 완료 `3건`, 회수/partial 실현 청산 `1건`, closed 또는 realized exit `4건`
- 2026-W19 weekly: 거래 `41건`, closed 또는 realized exit `41건`
- 2026-05 monthly: 거래 `41건`, closed 또는 realized exit `41건`
- 2026-05-07 원본 trade directory 4건은 모두 symbol `trade_history.json`에 반영됨.

보강:

- intraday 상태에서 `daily_report.json`/live summary가 없으면 런타임 이벤트와 승인/차단은 `0`으로 단정하지 않고 `미집계`로 표시한다.

적용 파일:

- `libs/reporting/operator_period_summary.py`
- `tests/test_operator_summary_reports.py`

## LLM Strategist Summary Cleanup

`reports/llm/2026-05-07/*/strategist/strategist_summary.md`도 운영 요약 패치 기준에 맞춰 재생성했다.

- 기존 `candidate_watch_policy: rank<= ... runner_ups=... effect=-` 표현 제거.
- 기존 `candidate_watch_reason` 상세 사유 문장 제거.
- 후보 감시는 `후보 감시 제안: 5위까지 / 차순위 4개 / cascade 활성` 형태로 표시.
- 원본 `prompt.json`/`response.json`은 감사 원자료라 수정하지 않음.

적용/검증:

- `libs/reporting/strategist_llm_summary.py`
- `tests/test_strategist_llm_summary.py`
- 2026-05-07 strategist summary 전체 재생성.
- summary markdown 내 구형 후보 감시 문구 `0건`.

## LLM Strategist Strategy Detail Alignment

사용자가 지칭한 패치는 전일 전략가 전략 강화 패치다. 오늘 `reports/llm/2026-05-07`을 해당 패치 기준으로 재점검했다.

확인 결과:

- `strategist_summary.json`에는 전략 강화 필드가 들어와 있다.
  - `tactical_strategy`
  - `strategy_scores`
  - `rejected_strategy_reasons`
  - `candidate_watch_policy`
- 기존 `strategist_summary.md`는 위 필드를 raw JSON 문자열로 보여줘서 운영자가 전술 선택과 탈락 사유를 바로 읽기 어려웠다.

보강:

- `strategist_summary.md`의 `Strategy Detail` 섹션을 `전략 디테일`로 재구성.
- `플레이북 흐름`, `LLM 요청 플레이북`, `최종 플레이북`, `선택 전술`, `후보 감시 제안`을 명시.
- `strategy_scores` raw JSON 대신 `전략 점수` 섹션으로 정렬 표시.
- `rejected_strategy_reasons` raw JSON 대신 `탈락 전략 이유` 섹션으로 표시.
- 원본 `prompt.json`/`response.json`은 감사 원자료라 수정하지 않음.

재생성/검증:

- 2026-05-07 strategist summary 전체 재생성.
- 전략 강화 필드 누락 `0건`.
- `strategy_scores:` / `rejected_strategy_reasons:` / `candidate_watch_reason` 구형 문구 `0건`.
- 최종 확인 시 전략가 전술 선택 분포: `leader_vwap_reclaim_pullback 전건`.

리스크:

- 보고서 표현은 개선됐지만, 오늘 LLM 전술 선택이 전부 `leader_vwap_reclaim_pullback`으로 쏠렸다.
- 장중 검증에서는 전략 강화 패치가 정상 적용되는지만 볼 것이 아니라, 시장/테마/가격 입력 변화에 따라 `opening_gap_momentum`, `opening_range_breakout`, `volume_breakout`, `cost_aware_scalp`, `defensive_observe` 등이 실제로 선택 가능한지까지 확인해야 한다.

## LLM Strategy Detail Refresh Timing Fix

추가 확인 중 `reports/llm/.../strategist_summary.md`가 LLM raw response 저장 직후 먼저 생성되고, canonical strategist artifact가 나중에 완성되면서 `pre_llm_playbook`, `llm_requested_playbook`, `requested_playbook`, `requested_playbook_source`가 summary에 비어 남을 수 있는 타이밍 이슈를 확인했다.

원인:

- `write_llm_artifact_bundle()`이 strategist raw response 저장 시 즉시 `strategist_summary`를 생성한다.
- 이 시점에는 canonical strategist artifact가 아직 없을 수 있다.
- 이후 canonical에는 전략 강화 필드가 정상 저장되지만, 기존 summary가 자동 갱신되지 않았다.

보강:

- `write_strategist_artifact()`가 canonical strategist 저장 직후 같은 run의 `reports/llm/.../strategist/response.json`이 있으면 `strategist_summary.md/json`을 다시 생성한다.
- summary renderer는 canonical top-level뿐 아니라 `canonical.strategy_detail`도 source로 사용한다.
- `전략 강화 필드: 적용됨` 판정에 플레이북 흐름 필드도 포함한다. 누락 시 `일부 누락 (...)`으로 표시한다.

재생성/검증:

- 2026-05-07 strategist summary `65개` 재생성.
- 구형 raw JSON 문구 `strategy_scores:` / `rejected_strategy_reasons:` / `candidate_watch_reason` 없음.
- 전략 강화 필드 완전 반영 `51개`.
- 과거 생성분 중 원자료 자체에 플레이북 흐름 필드가 없는 partial `14개`는 `전략 강화 필드: 일부 누락`으로 명시.
- 현재 이후 생성분은 canonical 저장 직후 summary refresh가 실행된다.

적용 파일:

- `libs/runtime/canonical_artifacts.py`
- `libs/reporting/strategist_llm_summary.py`
- `tests/test_canonical_artifact_validation.py`
- `tests/test_strategist_llm_summary.py`

## Executor Notional Guard Canonical Monitor Price Fallback

재시작 후 13:29:52 KST tick에서 모니터가 `000660` BUY intent를 만들었지만 supervisor/executor가 `order_notional_price_missing`으로 차단했다.

확인:

- `reports/canonical/2026-05-07/071e1135fec3490b8f19d1e8fc809087/monitor.json`
  - `symbol=000660`
  - `decision=BUY`
  - `current_price=1,611,000`
- supervisor detail
  - `qty=46`
  - `price=0`
  - `price_evaluable=false`
  - `reason=order_notional_price_missing`

원인:

- monitor canonical artifact에는 가격이 있었지만 executor state의 `monitor_output`/`monitor` 가격 필드에는 전달되지 않았다.
- 기존 fallback은 state 안의 monitor snapshot만 보며, 이미 기록된 canonical monitor artifact를 읽지 않았다.

보강:

- notional guard 가격 후보에 `state.canonical_artifacts.monitor`의 `current_price/price`를 추가.
- source는 `canonical.monitor.current_price`로 기록한다.

검증:

- `tests/test_execute_from_packet.py::test_execute_from_packet_uses_canonical_monitor_price_for_notional_guard_when_state_price_missing`
- `tests/test_execute_from_packet.py::test_execute_from_packet_uses_monitor_price_for_notional_guard_when_order_price_missing`
- `tests/test_execute_from_packet.py::test_execute_from_packet_blocks_buy_when_notional_guard_price_missing`
- 결과: `3 passed`

적용 파일:

- `graphs/nodes/execute_from_packet.py`
- `tests/test_execute_from_packet.py`

## Scanner Live Symbol Guard

13:37 KST tick 확인 중 scanner가 `SK`를 1위 후보로 선택하는 문제를 확인했다.

현상:

- `reports/canonical/2026-05-07/1ef1ca4df0f54152aaa1e41cee25f1e3/scanner.json`
  - `selected_symbol=SK`
  - ranking table 1위 `SK`, 2위 `000660`
- `SK`는 6자리 KRX 종목코드가 아니라 이름/문자 토큰이다.
- monitor는 해당 값을 종목코드로 처리하려다 `minute_candle_missing` NOOP로 끝났다.

보강:

- live 기본 동작에서 scanner candidate는 6자리 KRX 종목코드만 통과시킨다.
- 테스트 환경에서는 기존 `AAA` 같은 fixture symbol을 유지하되, `policy.enforce_live_equity_symbols=true`면 테스트에서도 필터를 강제할 수 있다.
- 제외 내역은 `scanner_candidate_pool.live_equity_symbol_excluded_symbols`에 기록한다.

검증:

- `tests/test_scanner_live_symbol_filter.py`
- 결과: `7 passed` 검증 세트에 포함.

적용 파일:

- `graphs/nodes/scanner_node.py`
- `tests/test_scanner_live_symbol_filter.py`

## Trade Report Hour Bucket Layout

Request:

- Reorganize this week's `reports/trades/<day>/TRD_*` folders under hourly buckets such as `0900`, `1000`, `1200`.
- Ensure `TRD_20260507_010170_01` is under `reports/trades/2026-05-07/1200/`.

Changes:

- Added shared trade-directory discovery that supports both legacy flat layout and new `reports/trades/<day>/<HH00>/TRD_*` layout.
- Updated report health, AI trade report batch, operator brief batch, reporter feedback, lifecycle reuse, symbol report, performance aggregation, and operator UI indexing to scan bucketed trade folders.
- Live execution bundle writer now writes new runtime trade reports into a KST hourly bucket outside pytest.
- Moved 45 this-week trade folders:
  - 2026-05-04: 18 folders
  - 2026-05-06: 20 folders
  - 2026-05-07: 7 folders
- Rewrote embedded old report paths inside moved JSON/MD/TXT artifacts.

Verification:

- `reports/trades/2026-05-07/1200/TRD_20260507_010170_01` exists.
- Direct `TRD_*` folders left under 2026-05-04, 2026-05-06, 2026-05-07: 0.
- `scripts/check_reports_trades_health.py --day 2026-05-07 --json`: ok, 7 trade dirs, no issues.
- `tests/test_phase3_lifecycle_bundle.py tests/test_check_reports_trades_health.py tests/test_trade_lifecycle_builder.py tests/test_symbol_trade_report.py tests/test_symbol_read_model.py tests/test_run_ai_trade_report_batch.py -q`: 45 passed.

Applied files:

- `libs/reporting/llm_artifacts.py`
- `libs/reporting/live_execution_bundle_runner.py`
- `libs/reporting/trade_lifecycle_builder.py`
- `libs/reporting/single_trade_report.py`
- `libs/reporting/reporter_feedback.py`
- `libs/reporting/profitability_recovery_day1.py`
- `libs/performance/performance_aggregator.py`
- `libs/reporting/symbol_trade_report.py`
- `apps/operator_ui/data_access_core.py`
- `scripts/check_reports_trades_health.py`
- `scripts/run_ai_trade_report_batch.py`
- `scripts/run_operator_brief_batch.py`
- `scripts/sync_legacy_brief_llm.py`
- `tests/test_phase3_lifecycle_bundle.py`
- `tests/test_check_reports_trades_health.py`

## Entry Net Edge Filter Tightening

Context:

- Today's cost-aware entry filter was present, but several live trade artifacts showed `estimated_gross_edge_source` coming only from ATR/volatility proxy fields such as `features.atr14_ratio` or `features.volatility20`.
- That meant the monitor was treating "this can move a lot" as "this has enough expected upside after fees/tax", which is not a valid net-edge check.

Changes:

- Monitor entry cost filter now separates directional edge evidence from proxy volatility evidence.
- Directional evidence includes explicit `expected_gross_edge_pct`, `expected_move_pct`, `target_move_pct`, `target_profit_pct`, `take_profit_pct`, and explicit target/resistance prices.
- ATR, volatility, recent realized move, and intraday range are now proxy evidence only.
- Default live behavior requires directional edge evidence and does not allow volatility/quality proxy evidence to pass the entry cost filter by itself.
- Filter output now records `directional_edge_required`, `directional_edge_available`, `proxy_edge_available`, `edge_evidence_type`, `directional_edge_candidates`, and `proxy_edge_candidates`.
- If a BUY signal has only ATR/volatility proxy edge, the monitor blocks it with `cost_adjusted_edge_not_ready`; the detailed fail reasons include `directional_edge_evidence_missing` and `estimated_gross_edge_missing`.

Operational note:

- This can reduce trade count until strategist/scanner/commander outputs consistently provide explicit expected move or target/resistance fields.
- That trade-off is intentional for this patch because today's losses showed that volatility-only edge was letting weak net-expectancy entries through.

Verification:

- `venv\Scripts\python.exe -m py_compile graphs\nodes\monitor_node.py tests\test_monitor_exit_guard.py`
- `venv\Scripts\python.exe -m pytest -q tests\test_monitor_exit_guard.py`
- Result: `94 passed`.

Applied files:

- `graphs/nodes/monitor_node.py`
- `tests/test_monitor_exit_guard.py`

## Trade Report Strategy Detail Consistency

Context:

- Some regenerated trade reports had `entry_execution_visibility` with strategist candidate-watch details, but no top-level `strategist_output`.
- In that case the detailed report could show monitor scope while omitting the separate `전략가 출력 근거` section, making it hard to compare:
  - strategist proposal
  - Commander final clamp
  - Monitor cascade result

Changes:

- `entry_execution_visibility.strategy_candidate_watch_proposal` now backfills missing proposal rank fields from Commander `proposed_max_priority_rank` and `proposed_max_runner_ups`.
- Detailed trade reports now reconstruct a minimal `전략가 출력 근거` surface from `entry_execution_visibility` when `strategist_output` is missing.
- Full reports show:
  - `전략 디테일`: selected tactical strategy and strategist proposal scope
  - `후보 감시 실행`: Commander final scope, strategist proposal scope, and Monitor cascade result
- Summary reports still keep the shorter operator-facing candidate-watch text and do not include raw clamp reasons.
- Candidate-watch display filters non-6-digit runner-up symbols so stale artifacts such as `SK` or `DB` do not reappear as executable Korean equity codes in the report text.

Regeneration:

- Rebuilt 2026-05-07 trade reports with deterministic/no-LLM mode:
  - `venv\Scripts\python.exe scripts\run_ai_trade_report_batch.py --day 2026-05-07 --no-llm --json`
  - processed `8` trades.

Verification:

- `venv\Scripts\python.exe -m py_compile libs\reporting\trade_report_ai.py libs\reporting\trade_report_markdown_clean.py tests\test_trade_report_ai.py`
- Targeted strategy/candidate-watch report tests: `9 passed`
- `venv\Scripts\python.exe scripts\check_reports_trades_health.py --day 2026-05-07 --json`: `ok`, `8` trade dirs, no issues.
- Search check found no old summary/detail strings:
  - `전략가 후보 감시 제안은 -`
  - `candidate_watch_reason`
  - `지휘관 최종 적용 범위`
  - `모니터 차순위 확인은 실행되지 않았습니다`
  - `차순위 ... SK/DB`

Applied files:

- `libs/reporting/trade_report_ai.py`
- `libs/reporting/trade_report_markdown_clean.py`
- `tests/test_trade_report_ai.py`

## Trade Report Reconciliation Cleanup

Context:

- End-of-day review found that the trade report structure was valid, but several operator-facing values were still misleading.
- Main gaps:
  - `post_exit_shadow` existed in lifecycle/input artifacts but disappeared after deterministic `ai_trade_report` regeneration.
  - closed SELL reports could keep `shared_facts.exit_reason=no_position` from canonical monitor entry-state artifacts.
  - bucketed trade folders were not always resolved when operator daily summary enriched rows from `ai_trade_summary_input.json`.
  - broker day truth rows all looked equally non-authoritative in the rendered truth surface.
  - same-price round trips with missing quantity lost `price_move_pct=0.0`, so cost-only losses were undercounted.

Changes:

- Preserved `post_exit_shadow` through deterministic and status-matrix report generation.
- Skipped `no_position`/`no position` as a closed-trade exit reason and preferred monitor exit trigger fields such as `stop_loss`, `intraday_low_break`, `peak_drawdown`, and `vwap_breakdown`.
- Added broker day match status/confidence fields:
  - `exact/high`
  - `estimated/medium`
  - `ambiguous/low`
- Updated operator daily summary truth-surface enrichment to find `reports/trades/<day>/<HH00>/TRD_*/reports/ai_trade_summary_input.json`.
- Refreshed operator daily summary automatically at the end of canonical `run_ai_trade_report_batch.py` regeneration.
- Normalized operator daily top exit reasons from raw strings like `SELL was triggered because stop_loss.` to Korean labels.
- When news samples are empty, summary markdown now points to the exact source fields:
  - `ai_trade_report_input.json` / `market_context_at_entry.market_news_titles`
  - `ai_trade_report_input.json` / `market_context_at_entry.candidate_news_titles`
- Cost analysis now records `price_move_pct=0.0` even when quantity is unavailable, and derives cost drag from broker PnL% when possible.

Regeneration:

- Rebuilt 2026-05-07 trade reports with deterministic/no-LLM mode.
- Refreshed `reports/operator_summary/daily/2026-05-07/daily_summary.{json,md}`.

Post-regeneration checks:

- `scripts/check_reports_trades_health.py --day 2026-05-07 --json`: `ok`, `8` trade dirs, no issues.
- `post_exit_shadow` appears in 7/8 reports. The remaining report is a recovered/partial sell without post-exit shadow source data.
- `shared_facts.exit_reason` no longer contains `no_position`.
- Broker day match confidence:
  - all current 2026-05-07 reports with truth rows show `match_status=exact`, `match_confidence=high`.
- Operator daily summary now reports:
  - total trades `8`
  - closed trades `7`
  - return samples `7`
  - wins/losses `0/7`
  - average return `-1.1883%`
  - cost-drag losses `2`
  - realized partial/carryover exit `1`, average `-0.9473%`
- Top exit reasons are now Korean labels:
  - `고정 손절 기준` 5
  - `장중 저점 이탈 기준` 1
  - `고점 대비 하락폭 기준` 1
  - `VWAP 이탈` 1

Verification:

- `venv\Scripts\python.exe -m pytest tests/test_trade_report_ai.py -q --basetemp .pytest-work-trade-report3`
  - `123 passed`
- `venv\Scripts\python.exe -m pytest tests/test_operator_summary_reports.py tests/test_run_ai_trade_report_batch.py -q --basetemp .pytest-work-operator-report2`
  - `27 passed`

Applied files:

- `libs/reporting/trade_report_ai.py`
- `libs/reporting/trade_report_markdown_clean.py`
- `libs/reporting/report_truth_surface.py`
- `libs/reporting/operator_period_summary.py`
- `scripts/run_ai_trade_report_batch.py`
- `tests/test_trade_report_ai.py`
- `tests/test_operator_summary_reports.py`
- `tests/test_run_ai_trade_report_batch.py`

## Weekly Monthly Pattern Summary Cleanup

Context:

- The same raw-pattern issue existed in weekly/monthly summaries.
- Affected generated artifacts included:
  - `reports/operator_summary/weekly/2026-W17`
  - `reports/operator_summary/weekly/2026-W18`
  - `reports/operator_summary/weekly/2026-W19`
  - `reports/operator_summary/monthly/2026-04`
  - `reports/operator_summary/monthly/2026-05`
- Raw terms found before the patch:
  - `Scanner selected ...`
  - `SELL was triggered because ...`
  - `unknown`
  - `pullback_rebound_above...`
  - `trailing_stop`
  - open/partial non-exit notes counted as exit patterns

Changes:

- Extended operator pattern normalization for weekly/monthly summaries.
- Weekly/monthly rows now also attempt to enrich entry/exit reasons from each trade dir's `reports/ai_trade_summary_input.json`, so older symbol-history rows can be corrected when the canonical trade report has a better actual entry trigger.
- Normalized additional codes:
  - `pullback_rebound_above_vwap_with_volume_confirmation` -> `눌림목 반등 + VWAP + 거래량 확인`
  - `trailing_stop` -> `추적 손절 기준`
  - `eod_flat` -> `장마감 정리 기준`
- Excluded non-exit noise from exit reason/pattern aggregation:
  - open-position monitoring notes
  - partial lifecycle rows without confirmed exit reason
  - recovered context placeholder notes
- Rebuilt all existing weekly/monthly operator summary artifacts listed above.

Post-regeneration check:

- `rg "Scanner selected|SELL was triggered|unknown|pullback_rebound|trailing_stop|Entry context was recovered|청산 근거가 누락|아직 열려" reports/operator_summary/weekly reports/operator_summary/monthly`
  - no matches

Verification:

- `venv\Scripts\python.exe -m pytest tests/test_operator_summary_reports.py tests/test_symbol_trade_report.py tests/test_run_ai_trade_report_batch.py -q --basetemp .pytest-work-period-summary-final`
  - `39 passed`
- `venv\Scripts\python.exe -m pytest tests/test_operator_summary_reports.py tests/test_symbol_trade_report.py tests/test_run_ai_trade_report_batch.py -q --basetemp .pytest-work-period-summary-final2`
  - `39 passed`

## Symbol Report Pattern Cleanup

Context:

- The same raw/internal wording also remained under `reports/operator_summary/symbols`.
- Affected surfaces included:
  - `trade_history.json`
  - `symbol_trade_report.{json,md}`
  - `symbol_memory.json`
  - `symbol_summary.{json,md}`
  - `latest_snapshot.json`
- Raw terms found before cleanup:
  - `Scanner selected ...`
  - `SELL was triggered because ...`
  - `unknown`
  - `pullback_rebound...`
  - `trailing_stop`
  - recovered/open/partial placeholder text

Changes:

- Symbol report generation now normalizes operator-facing entry/exit reasons and pattern fields.
- Symbol `trade_history.json` now stores cleaned operator labels for:
  - `entry_reason`
  - `exit_reason`
  - `entry_pattern_type`
  - `exit_pattern_type`
  - `lifecycle_summary`
  - report/brief summary fields that previously leaked raw trigger strings
- Symbol memory now uses cleaned pattern labels and `execution_risk_level=not_available` instead of `unknown`.
- Existing 107 symbol artifact directories were normalized in place using the same rules.

Post-cleanup check:

- `rg "Scanner selected|SELL was triggered|unknown|pullback_rebound|trailing_stop|Entry context was recovered|청산 근거가 누락|아직 열려" reports/operator_summary/symbols`
  - no matches

Verification:

- `venv\Scripts\python.exe -m pytest tests/test_symbol_trade_report.py tests/test_operator_summary_reports.py tests/test_run_ai_trade_report_batch.py -q --basetemp .pytest-work-symbol-summary-final2`
  - `39 passed`

## Operator Daily Pattern Summary Cleanup

Context:

- `reports/operator_summary/daily/2026-05-07/daily_summary.md` still exposed raw internal strings in `## 핵심 패턴`.
- Examples:
  - `Scanner selected ...`
  - `SELL was triggered because ...`
  - `unknown`
- Some rows also mixed scanner top-pick selection with actual monitor fallback entries, so the summary could describe a different top-ranked symbol than the executed trade.

Changes:

- Daily summary now prefers same-day `daily_report.trade_index` plus each trade dir's latest `ai_trade_summary_input.json` for daily rows.
- For monitor fallback/cascade entries, the summary uses the actual fallback trigger or actual entry path instead of the scanner top-pick sentence.
- Raw scanner sentences are only a last resort and are normalized if they must appear.
- Exit reasons are normalized before aggregation:
  - `SELL was triggered because stop_loss.` -> `고정 손절 기준`
  - `intraday_low_break` -> `장중 저점 이탈 기준`
  - `peak_drawdown` -> `고점 대비 하락폭 기준`
- `unknown` entry/exit pattern labels no longer dominate summaries; exit patterns are derived from exit reason when the pattern field is missing.
- `run_ai_trade_report_batch.py` now refreshes symbol reports before daily summary refresh when possible, while daily summary no longer depends on stale symbol history for same-day rows.

Current 2026-05-07 `핵심 패턴`:

- 주요 진입 사유: `직전 고점 돌파 + VWAP 유지 + 거래량 확인 (2)`, `눌림목 + 거래량 경로 (1)`, `VWAP 위 눌림목 + 거래량 확인 (1)`
- 주요 청산 사유: `고정 손절 기준 (5)`, `장중 저점 이탈 기준 (1)`, `고점 대비 하락폭 기준 (1)`
- 진입 패턴: `돌파 (4)`, `눌림목 (3)`
- 청산 패턴: `손절 (5)`, `장중 저점 이탈 (1)`, `고점 대비 하락폭 (1)`

Verification:

- `venv\Scripts\python.exe -m pytest tests/test_operator_summary_reports.py tests/test_symbol_trade_report.py -q --basetemp .pytest-work-summary-clean7`
  - `20 passed`
- `venv\Scripts\python.exe -m pytest tests/test_run_ai_trade_report_batch.py -q --basetemp .pytest-work-run-ai-summary-clean2`
  - `18 passed`

Applied files:

- `libs/reporting/operator_period_summary.py`
- `libs/reporting/symbol_trade_report.py`
- `scripts/run_ai_trade_report_batch.py`
- `tests/test_operator_summary_reports.py`
- `tests/test_symbol_trade_report.py`
- `tests/test_run_ai_trade_report_batch.py`

## Cost Drag Stop Basis Separation

Context:

- Today showed same-price or small price-move exits where broker/account PnL was already about `-0.88%~-0.90%`.
- Existing cost patches worked for profit-taking floors and entry cost checks, but `stop_loss` still used the conservative account/net PnL basis.
- With `stop_loss_pct=0.80%`, broker cost drag alone could make a flat trade look like a stop-loss breach.

Changes:

- Exit policy now separates:
  - `gross_pnl_ratio` / `technical_pnl_ratio`: raw market price basis for stop/structure checks.
  - `pnl_ratio` / `effective_pnl_ratio`: conservative account/net basis for reporting and net PnL visibility.
  - `stop_pnl_ratio`: normal `stop_loss` trigger basis.
  - `hard_stop_pnl_ratio`: hard stop trigger basis, still using the conservative account/net basis.
- Normal `stop_loss` no longer triggers solely because account/net PnL is worse from cost drag when raw/technical price has not crossed the stop.
- Such cases are recorded as:
  - `cost_drag_pressure=true`
  - `stop_loss_cost_drag_blocked=true`
  - `hold_block_reason=stop_loss_cost_drag_only`
- `vwap_breakdown`/`intraday_low_break` cost-floor guard now detects gross-positive but net-negative cases using gross PnL, so cost-loss exits below the floor are blocked unless hard invalidation is present.
- Monitor evidence, monitor output, order metadata, and canonical monitor artifact now carry the new stop/cost-drag fields.

Risk:

- This can hold a position that previously would have been sold by account/net PnL alone.
- `hard_stop` remains immediate, so true fail-safe loss control is still active.
- Tomorrow's live check should verify that flat or slightly positive price moves no longer become `stop_loss` purely from fees/tax, while actual price-based stop breaches still sell.

Verification:

- `venv\Scripts\python.exe -m pytest tests/test_strategy_sizing_exit_upgrade.py -q`
  - `28 passed`
- `venv\Scripts\python.exe -m pytest tests/test_monitor_exit_guard.py -q`
  - `94 passed`
- `venv\Scripts\python.exe -m pytest tests/test_phase1_agent_artifact_quality.py -q`
  - `22 passed`
- `venv\Scripts\python.exe -m pytest tests/test_m21_commander_runtime_entry.py -q`
  - `71 passed`

Applied files:

- `libs/runtime/exit_policy.py`
- `graphs/nodes/monitor_node.py`
- `libs/contracts/agent_outputs.py`
- `tests/test_strategy_sizing_exit_upgrade.py`
- `tests/test_monitor_exit_guard.py`

## Trade Report Stop/Cost Basis Visibility

Context:

- The stop basis separation patch changed the runtime decision surface, but the operator-facing trade summary also needs to show why a trade was or was not stopped.
- Without this, the daily/trade report can still look like "fees caused another stop" even when the monitor correctly blocked a cost-only stop.

Changes:

- `ai_trade_summary.md` now enriches the exit observation from `monitor_snapshot` when execution detail does not already carry the new fields.
- The summary can now display:
  - price/gross PnL basis
  - account/cost-reflected PnL basis
  - normal stop-loss trigger basis
  - hard-stop trigger basis
  - cost-drag pressure
  - cost-only stop-loss block reason
- This keeps the short summary readable while making the key cost-vs-price distinction visible at the point the operator checks first.

Risk:

- Existing generated reports will not change until regenerated.
- If an old trade directory lacks `monitor_snapshot`, the report falls back to the previous available exit observation fields.

Verification:

- `venv\Scripts\python.exe -m pytest tests/test_trade_report_ai.py -q`
  - `123 passed`
- `venv\Scripts\python.exe -m pytest tests/test_run_ai_trade_report_batch.py tests/test_phase1_agent_artifact_quality.py -q`
  - `40 passed`
- `venv\Scripts\python.exe -m py_compile libs\runtime\exit_policy.py graphs\nodes\monitor_node.py libs\contracts\agent_outputs.py libs\reporting\trade_report_markdown_clean.py`
  - passed

Applied files:

- `libs/reporting/trade_report_markdown_clean.py`
- `tests/test_trade_report_ai.py`

Runtime restart:

- Started live intraday loop through the official entrypoint:
  - `venv\Scripts\python.exe scripts\run_session.py --mode live --phase intraday --tick-pipeline integrated_chain --sleep-sec 30 --session-hard-gate --allow-offhours`
- Lock owner after restart:
  - `data/state/m13_live_loop.lock` -> `pid=13548`
- Watch check:
  - loop is alive
  - health is `RED` because the check ran at `2026-05-07T23:43:46+09:00`, outside market hours, with no recent event window
  - this is an off-hours/event-lag status, not a startup failure
