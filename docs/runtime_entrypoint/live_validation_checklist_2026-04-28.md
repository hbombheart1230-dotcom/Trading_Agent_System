# Live Validation Checklist 2026-04-28

## Preopen Status

- 기준 시각: 2026-04-28 08:53 KST
- 실행 명령: `venv\Scripts\python.exe scripts\run_session.py --mode live --phase intraday --tick-pipeline integrated_chain --sleep-sec 30 --allow-offhours`
- 환경 확인: `KIWOOM_MODE=mock`, `EXECUTION_MODE=real`
- 런타임 상태: `data/state/m13_live_loop.lock` heartbeat 갱신 확인
- preopen 확인: 08:56 KST `run-session-live-preopen` 경로에서 strategist LLM 1회 성공
- watch 확인: 08:57 KST 최근 10분 이벤트 13건, strategist LLM 1회 성공, health `GREEN`
- 장 시작 확인: 09:01 KST 최근 10분 이벤트 45건, health `GREEN`, event lag 11초
- 첫 장중 artifact: `reports/canonical/2026-04-28/087bce61a42e4d4a90923233278a7069/`
- 첫 장중 상태: `monitor_only`, 005930 보유 4주, 평균가 224500, 신규 매수는 open position 때문에 차단
- 주의: preopen artifact는 KST 거래일이 2026-04-28이어도 UTC 날짜 기준 `reports/canonical/2026-04-27/run-session-live-preopen`에 기록됐다. 장중 trade/report 경로와 날짜 기준이 갈리는지 확인한다.

## 1. Runtime Entrypoint

검증 대상:

- `docs/runtime_entrypoint`
- `scripts/run_session.py`
- `scripts/run_m13_live_loop.py`
- `data/state/m13_live_loop.lock`
- `reports/live_watch/live_watch_2026-04-28.jsonl`

체크리스트:

- [ ] `run_session.py --mode live --phase intraday` 프로세스가 1개 루프 lock owner를 가진다.
- [ ] lock heartbeat가 60초 이내로 갱신된다.
- [ ] 장 시작 후 1~2분 안에 `events.jsonl` 신규 이벤트가 기록된다.
- [ ] `reports/canonical/2026-04-28/<run_id>/` 하위에 commander/scanner/monitor artifact가 생성된다.
- [ ] watch health가 `RED(window_empty)`에서 `GREEN` 또는 원인 있는 `YELLOW`로 전환된다.

장 시작 직후 명령:

```powershell
venv\Scripts\python.exe scripts\run_session.py --mode live --phase watch --once --json --event-log-path data\logs\events.jsonl --summary-report-dir reports\live_summary --watch-report-dir reports\live_watch --lock-path data\state\m13_live_loop.lock --lookback-min 10 --sleep-sec 30
```

## 2. Commander Control

검증 대상:

- `docs/commander_control`
- `reports/canonical/2026-04-28/<run_id>/commander.json`
- `reports/canonical/2026-04-28/<run_id>/commander_shadow.json`

체크리스트:

- [ ] `commander_entry_control.mode`가 시장 상태에 맞게 `expand_when_market_ok` 또는 보수 모드로 정리된다.
- [ ] `max_priority_rank`와 `max_runner_ups`가 top5 확장 이후 의도대로 기록된다.
- [ ] repeated blocker가 있으면 `dominant_blocker`, `failure_streak`, `near_ready_flag`가 남는다.
- [ ] 지휘관이 시장이 괜찮은데 매매가 계속 안 되는 상황을 `candidate pool/dynamic entry band`로 통솔한다.
- [ ] 시장이 나쁘면 거래 감소가 의도된 보수 판단으로 기록된다.

## 3. Strategist Output

검증 대상:

- `docs/strategist_output`
- `reports/canonical/2026-04-28/<run_id>/strategist.json`
- `reports/llm/2026-04-28/<run_id>/strategist/prompt.json`

체크리스트:

- [ ] `strategy_thesis`에 playbook, risk tone, market view가 구조화되어 있다.
- [ ] `memory_usage_trace`가 active layers, priority, layer decisions를 설명한다.
- [ ] `news_usage_trace`가 시장 뉴스와 후보 뉴스가 어떻게 쓰였는지 명시한다.
- [ ] `scanner_handoff`와 `monitor_handoff`가 따로 존재한다.
- [ ] 전략가는 최종 종목 선정자가 아니라는 boundary가 출력 또는 리포트에 유지된다.
- [ ] 전략가 LLM 호출이 장중 끊기지 않고 fresh/cached 경로가 commander artifact에 남는다.

## 4. Runtime Memory

검증 대상:

- `docs/runtime_memory`
- strategist prompt memory packet
- `memory_surface`
- `memory_application_surface`

체크리스트:

- [ ] 전략가 프롬프트에 들어간 메모리와 사후 복원 메모리가 리포트에서 분리된다.
- [ ] daily/weekly/monthly/symbol layer의 active/not_used 사유가 표시된다.
- [ ] scanner memory bias captured/enabled/applied가 기록된다.
- [ ] monitor memory bias entry/hold/exit delta가 기록된다.
- [ ] 메모리가 비활성인 경우 `레이어 비활성`, `거래 수 부족`, `bias_disabled` 등 이유가 남는다.

## 5. Strategy Horizon Feedback

검증 대상:

- `docs/strategy_horizon_feedback`
- monitor artifact `exit_vs_strategy_intent`
- commander horizon policy

체크리스트:

- [ ] `horizon_owner=commander`가 유지된다.
- [ ] `observability_only=true`, `allow_behavior_change=false`, `do_not_force_hold=true`가 live 검증 모드에서 유지된다.
- [ ] 실제 보유 시간과 expected hold window가 비교 가능하게 남는다.
- [ ] 조기 청산이면 hard exit인지, 노이즈 청산인지, 전략 horizon과 맞는지 artifact에 남는다.
- [ ] 팔고 난 뒤 shadow tracking에 `팔지 않았다면 어떻게 됐는지` 복기 데이터가 남는다.

## 6. Kiwoom Truth

검증 대상:

- `docs/kiwoom_truth`
- broker fill truth
- `kiwoom.ka10077`
- theme strength packet

체크리스트:

- [ ] 첫 live/mock 체결 후 buy/sell fill이 trade artifact와 연결된다.
- [ ] 당일 실현손익 truth source가 `kiwoom.ka10077`로 연결된다.
- [ ] 반복 동일종목 day-PnL tie-breaker가 잘못된 손익을 붙이지 않는다.
- [ ] theme packet이 활성화된 경우 `theme_source`, `theme_source_status`, `theme_strength_packet`이 strategist/scanner에 전달된다.
- [ ] theme live fetch가 비활성이라면 fallback status/reason이 명확히 남는다.

## 7. Trade Report Plan

검증 대상:

- `docs/trade_report_plan`
- `reports/trades/2026-04-28/<trade_id>/reports/ai_trade_report.md`
- `reports/trades/2026-04-28/<trade_id>/reports/ai_trade_report.json`
- `reports/trades/2026-04-28/<trade_id>/reports/ai_trade_report_llm_response.json`

체크리스트:

- [ ] live closed-trade first-write에서는 report LLM이 호출된다.
- [ ] batch/manual 재생성 기본값은 no-LLM deterministic이다.
- [ ] `ai_trade_report.md`가 example처럼 본문 중심으로 읽히고, 작성 지침 문구가 섞이지 않는다.
- [ ] Truth Surface는 broker truth와 monitor 관측을 분리한다.
- [ ] 전략가 출력 근거가 reporter에서 그대로 소비된다.
- [ ] 선택 종목 상세 분석과 스캐너 후보 비교가 중복되지 않는다.
- [ ] LLM 실패 시 deterministic fallback과 skip marker가 stale LLM artifact로 오인되지 않는다.

## First 30-Minute Acceptance Criteria

- [ ] `events.window_total > 0`
- [ ] strategist LLM 호출 또는 명확한 cached/fallback route가 기록됨
- [ ] scanner 후보 top5/topN 기록 확인
- [ ] monitor entry blocker가 있으면 blocker별 count와 commander 대응이 확인됨
- [ ] 첫 주문 발생 시 executor result와 broker/mock result가 연결됨
- [ ] 첫 닫힌 거래 발생 시 ai trade report가 생성되고 LLM status가 확인됨
- [ ] watch health가 계속 `RED`이면 event write path, lock owner, market data fetch를 즉시 점검
