# Trading Agent System — Detailed Patch Notes Timeline

> UI 노출용 상세 프로젝트 변경 이력. 저장소에 남아 있는 milestone 문서, daily patch, evaluation/research 문서를 시간순으로 재구성했다. Git commit metadata가 ZIP에 포함되지 않은 초기 구간은 정확한 일자를 임의 생성하지 않고 milestone 순서/범위로 표기했다.

총 **45개 릴리즈/변경 구간**을 수록한다. 작은 버그 수정 하나하나를 전부 카드화하기보다, UI에서 의미가 있는 기능·정책·평가 단위로 묶되 각 카드 안에서 실제 세부 변경을 보여주는 방식이다.

## 2026-08-31 · Opening Alpha 및 Q10/Q12 시각 정합성 복구
**Stage:** Controlled Mock Validation
**Tags:** OPENING_ALPHA · Q10 · Q12 · SCHEDULER · KIWOOM_MOCK

### 변경 내용
- Opening Alpha 후보에 Rank가 누락돼도 Scanner 원본 authority가 Rank-1 및 종목 일치를 증명하면 해당 Rank를 사용합니다.
- Q10 선행시장 스냅샷을 09:00 baseline 루프에서 분리하고 기존 08:50 Preopen 예약 작업의 첫 단계에서 불변 파일로 저장합니다.
- Q12 BTC 08:55 스냅샷 전용 스크립트와 평일 08:55 Windows 예약 작업을 추가했습니다.
- Q12 캡처는 짧은 재시도를 지원하고 성공·누락·마감 후 지연을 일별 장부의 시도 이력으로 남깁니다.
- 09:00 이후 Q12 baseline은 동결된 08:55 원본을 재사용하며, 실패한 캡처를 장후 데이터로 소급 복원하지 않습니다.

### 운영 산출물
- `reports/evaluation/baseline_samsung_hynix/YYYY-MM-DD/q10_forward_validation/q10_preopen_signal_snapshot.json`
- `data/logs/q12_btc_0855/YYYY-MM-DD/btc_0855_snapshot.json`
- `data/logs/q12_btc_0855/YYYY-MM-DD/capture_ledger.json`

### 변경의 의미
조건 완화 레인이 후보 객체의 누락 필드나 장중 루프 시작 시각 때문에 무조건 비활성화되는 문제를 제거했습니다. Rank-1 종목 일치, risk-off, 비용, 차트 하드 플로어와 일일 주문 한도는 유지합니다.

---

## 2026-02-07 · v0.1 — 프로젝트 시작 — Traceable Core
**Stage:** Foundation  
**Tags:** CORE · OBSERVABILITY

자동매매 기능보다 먼저 실행 이력을 남길 수 있는 코어와 추적 구조를 만들기 시작한 최초 단계.

### 변경 내용
- 이벤트 로거와 run 단위 추적 개념을 코어 설계에 포함.
- 이후 모든 판단·승인·실행 결과를 run_id 중심으로 재현할 수 있는 방향 설정.
- 단순 주문 스크립트가 아니라 관찰 가능하고 검증 가능한 시스템을 목표로 확정.

### 이 변경의 의미
이후 Reporter, audit, replay, evaluation이 붙을 수 있는 기반이 됨.

### 근거 문서 / 코드
- `libs/event_logger.py`
- `docs/08_observability.md`

---

## 최근 1주일 주요 업데이트 (2026-08-24 ~ 2026-08-28)

기존 패치 이력은 그대로 유지하고, 현재 운영과 연구 방향을 이해하는 데 필요한 주요 변경만 보강합니다.

### 2026-08-24 · Evaluation Integrity + Prospective Board

- 과거 발견 표본과 prospective 표본을 분리했습니다.
- Q 평가와 baseline 산출물의 누락·중복·시간 정합성 검사를 강화했습니다.
- 기존 평가 결과는 Alpha Research Board의 입력 증거로 재사용하며 새 평가 축을 늘리지 않습니다.

### 2026-08-25~26 · Q12 Trend + Opening Snapshot + AI Provenance

- BTC 최근 추세와 신호 가용성을 Q12 증거에 추가했습니다.
- 장초반 국내 지수·야간선물 값, snapshot 시각과 지연을 기록합니다.
- Strategist 단계별 후보·판단·horizon provenance를 연결했습니다.

### 2026-08-27 · Strategist Authority Lineage

- 2차 전략가의 재순위·후보 교체·진입 강화·no-trade 권한을 분리했습니다.
- 3차 전략가의 최초 horizon, 재평가 horizon, 실제 보유시간을 연결했습니다.
- 행동 변경 없이 LLM 기여도를 검증하는 관측 근거를 마련했습니다.

### 2026-08-27 · Web Observability M7

- 메인 런타임, watchdog, health 상태를 읽기 전용 UI에서 확인합니다.
- 호스트 Supervisor와 장전·장후 예약 인텔리전스의 실행 상태를 표시합니다.
- UI 컨테이너는 트레이딩 런타임과 분리되며 데이터 경로는 read-only입니다.

### 2026-08-27~28 · Alpha Board v2 + Q12 Five-Variable Validation

- 장후 판단 기준을 고정된 Alpha Research Board로 통합했습니다.
- Q12는 BTC 08:55 수익률, FIRST_SURGE, BREAKOUT, 우기투 opening gap, 09:03~09:05 수급의 다섯 변수만 검증합니다.
- 09:00·09:03·09:05·09:10·눌림 시점의 forward 성과를 같은 비용 기준으로 비교합니다.
- Q9와 실제 주문·진입·청산 로직은 변경하지 않았습니다.

### 2026-08-28 · Patch Notes Timeline UI

- 누적 패치 이력을 운영 UI에서 검색·stage·type으로 필터할 수 있게 했습니다.
- FastAPI와 React 기능을 독립 모듈로 구성하고 문서 경로만 read-only로 마운트했습니다.
- 앞으로 모든 패치는 JSON과 Markdown 패치 노트를 같은 커밋에서 함께 갱신합니다.

### 2026-08-28 · Q10 Lead-Market Forward Validation

- 기존 삼성전자·SK하이닉스 Q10 기준선은 그대로 유지합니다.
- SOX·Nvidia·Micron·하이닉스 ADR와 08:50 Nasdaq100/S&P500 선물·USD/KRW, US10Y·VIX를 개장 전 불변 스냅샷으로 저장합니다.
- 삼성전자·SK하이닉스·KOSPI·KOSDAQ의 09:00 이후 체크포인트와 gap·MFE·MAE를 기록합니다.
- 고정 예상 상태와 실제 opening gap을 UNDERREACTION·FAIR_REACTION·OVERREACTION·DIVERGENCE로 분류합니다.
- 09:00/09:03/09:05/09:10 및 첫 눌림 진입은 주문 없이 shadow로만 비교합니다.
- `2026-08-31` 이후 데이터만 누적하며 과거 백필·백테스트·threshold 최적화·ML·Executor 연결을 금지합니다.

### 2026-08-28 · Scheduled Intelligence Evidence Detail

- 장전·장후 예약 카드에 접이식 상세 보기를 추가했습니다.
- 전략 프레임·리스크·모델·메모리 적용 방식과 단계별 실행 상태를 표시합니다.
- 브리핑·메모리·Strategist·closeout·통합 인덱스 원본 경로를 확인하고 복사할 수 있습니다.
- 장전 canonical 원본의 날짜 폴더를 UTC가 아닌 KST 거래일 기준으로 바로잡았습니다.
- 읽기 전용 관측 기능이며 예약 실행·전략·메모리·매매 동작은 변경하지 않습니다.

### 2026-08-29~30 · Cloudflare Private Ingress 활성화

- `agentra.win`을 Cloudflare Tunnel의 `web:8080` origin에 연결했습니다.
- Access는 운영자 이메일 allowlist와 One-time PIN으로 보호합니다.
- 인증 없는 요청이 Access 로그인으로 이동하고 API·Trading Runtime은 직접 공개되지 않는 것을 확인했습니다.
- Tunnel token은 Git에서 제외된 로컬 `.env`에만 보관합니다.

### 2026-08-30 · Scheduled Artifact Viewer

- 장전 브리핑·메모리 전달 영수증·전략 메모리·Strategist 원본과 장후 인덱스를 UI에서 직접 엽니다.
- 예약 카드에 실제로 나열된 JSON·Markdown만 읽을 수 있으며 reports 루트 이탈과 미등록 파일은 차단합니다.
- 파일은 포맷된 읽기 전용 모달로 표시하고 변경·실행 기능은 추가하지 않았습니다.
- Trading Runtime과 예약 실행 로직은 변경하지 않았습니다.

### 2026-08-30 · M7.5 Operations Command Center

- 장전·거래·장후 이벤트를 실제 완료 시각과 source를 포함한 운영 타임라인으로 표시합니다.
- 기존 anomaly, 예약 작업 issue와 장중 runtime 불일치를 한곳에서 확인합니다.
- Strategist → Scanner → Monitor → Commander → Execution의 거래 계보를 실제 artifact 기준으로 표시합니다.
- 최신/직전 운영일의 전략 프레임과 closeout 상태, 실제 청산과 post-exit 최선 checkpoint를 비교합니다.
- 모든 API는 GET 전용이며 Trading Runtime과 매매 행동에는 영향을 주지 않습니다.

---

## 2026-02-07 ~ 2026-02-10 · M1–M5 — Kiwoom API Catalog와 요청 파이프라인 골격
**Stage:** Foundation  
**Tags:** CORE · KIWOOM

키움 REST API 원본을 바로 호출하지 않고 Catalog → Discovery → Planner → Request Builder로 정규화.

### 변경 내용
- 공식 API 자료를 data/specs 계층으로 정규화하고 canonical API catalog 구성.
- 자연어/목표에서 필요한 API 후보를 찾는 Discovery와 호출 계획을 만드는 Planner 분리.
- 실제 HTTP 호출 전에 요청 객체를 만드는 Request Builder 계층 구축.
- API raw 응답과 Agent가 소비하는 계약을 분리하기 위한 초기 구조 마련.

### 이 변경의 의미
브로커 API 세부사항이 Agent 로직 전체로 퍼지는 것을 막는 첫 추상화 계층.

### 근거 문서 / 코드
- `docs/plan/archive/m3_api_discovery.md`
- `docs/plan/archive/m4_api_planner.md`
- `docs/plan/archive/m5_prepare_request.md`

---

## 2026-02-09 ~ 2026-02-10 · M6–M7 — Token/HTTP Client, Read-only Account, Dry-run Guard
**Stage:** Execution Skeleton  
**Tags:** KIWOOM · SAFETY · EXECUTION

브로커 연결을 읽기와 실행으로 나누고 주문은 dry-run/guard 뒤에서만 가능하도록 경계를 만들기 시작.

### 변경 내용
- Token client와 공통 HTTP client 도입.
- 계좌 조회를 read-only snapshot 형태로 먼저 구현.
- Supervisor를 거치는 주문 dry-run 경로와 실행 전 guard 도입.
- 실주문보다 모의·검증 경로를 우선하는 mock-first 원칙 고정.

### 이 변경의 의미
'데이터를 읽는 코드'와 '돈을 움직이는 코드'가 분리되기 시작함.

### 근거 문서 / 코드
- `docs/plan/archive/m6_token_client.md`
- `docs/plan/archive/m6_readonly_account.md`
- `docs/plan/archive/m7_order_dry_run.md`
- `docs/plan/archive/m7_supervisor.md`

---

## 2026-02-10 · M8–M10 — Decision Packet → Supervisor → Executor Live Pipeline
**Stage:** Execution Skeleton  
**Tags:** RUNTIME · EXECUTION · SAFETY

판단 결과를 표준 패킷으로 만들고 Supervisor와 Executor를 통해 stateful runtime에 연결.

### 변경 내용
- Decision Packet 계약과 executor wiring 구성.
- 읽기 snapshot과 판단 결과를 실제 실행 계층에 연결하는 live pipeline 골격 구축.
- 실행 전 approval/guard와 실행 후 결과 기록의 책임을 분리.
- 상태를 가진 반복 실행 구조로 확장.

### 이 변경의 의미
단발성 API 호출에서 반복 가능한 trading runtime으로 넘어가는 전환점.

### 근거 문서 / 코드
- `docs/plan/m8_decision_packet.md`
- `docs/plan/m8_wiring.md`
- `docs/plan/m8_executors.md`
- `docs/plan/m10_live_pipeline.md`

---

## 2026-02-11 · M11 — Scanner와 다종목 후보 탐색
**Stage:** Agent Expansion  
**Tags:** SCANNER · AGENT

단일 종목 판단에서 시장 후보를 수집·점수화해 상위 후보를 넘기는 Scanner 계층으로 확장.

### 변경 내용
- Scanner 역할과 후보 수집/랭킹 책임 분리.
- 후보별 데이터와 특징을 정량적으로 비교하는 구조 도입.
- 후속 Strategist가 모든 종목을 직접 탐색하지 않고 압축된 후보군을 받도록 변경.

### 이 변경의 의미
LLM 비용을 줄이고 전략 판단과 데이터 탐색의 책임이 분리됨.

### 근거 문서 / 코드
- `docs/plan/m11_2_scanner.md`
- `docs/plan/m11_4_logging_and_reports.md`

---

## 2026-02-11 ~ 2026-02-12 · M12–M13 — Strategist LLM Provider + Runtime Loop
**Stage:** Agent Expansion  
**Tags:** STRATEGIST · LLM · RUNTIME

LLM Strategist를 provider routing 뒤에 넣고 장중 반복 루프·EOD 보고까지 연결.

### 변경 내용
- rule fallback을 보존한 LLM Strategist HTTP/provider routing 도입.
- OrderIntent schema validation과 AI hook 추가.
- tick → 판단 → 상태 저장 → EOD report로 이어지는 runtime loop 정리.
- LLM 장애 시에도 runtime 전체가 멈추지 않도록 fallback 개념 유지.

### 이 변경의 의미
AI가 포함되지만 AI 자체가 실행 안정성을 소유하지 않는 구조가 만들어짐.

### 근거 문서 / 코드
- `docs/plan/m12_ai_hook.md`
- `docs/plan/m12_1_provider_routing.md`
- `docs/plan/m12_2_llm_strategist_http.md`
- `docs/plan/m13_runtime_loop.md`

---

## 2026-02-12 ~ 2026-02-13 · M14–M16 — 7-Agent Architecture와 Approval Model 확립
**Stage:** Architecture Freeze  
**Tags:** ARCHITECTURE · SAFETY · AGENT

Commander·Strategist·Scanner·Monitor·Supervisor·Executor·Reporter 7개 역할을 공식 구조로 고정.

### 변경 내용
- Agent Layer와 Execution Layer를 구조적으로 분리.
- Monitor는 주문을 직접 실행하지 않고 OrderIntent만 생성하도록 non-negotiable rule 고정.
- SupervisorDecision 이후에만 Executor가 실행할 수 있도록 approval layer 구성.
- intent_id 기반 멱등성과 approve/reject/manual 흐름 도입.
- Guard가 approval보다 항상 우선한다는 실행 우선순위 확립.

### 이 변경의 의미
현재 시스템의 정체성인 'Agents decide, execution is gated'가 완성됨.

### 근거 문서 / 코드
- `README.md`
- `docs/01_overview.md`
- `docs/02_principles.md`
- `docs/05_runtime_flow.md`
- `docs/07_execution_and_guards.md`
- `docs/plan/m16_approval_api.md`

---

## 2026-02-13 ~ 2026-02-14 · M17–M20 — LangGraph Spine, Strategy Signals, News/LLM Reliability
**Stage:** Enterprise Baseline  
**Tags:** LANGGRAPH · LLM · NEWS · OBSERVABILITY

설정·그래프·전략 signal·뉴스·LLM telemetry를 운영 가능한 수준으로 정리.

### 변경 내용
- Settings single-source 방향과 graph spine/risk 구조 정리.
- 시장 후보·Top Picks·Scanner scoring·sentiment/news signal 통합.
- Naver News/OpenRouter provider와 global sentiment 입력 추가.
- LLM smoke/fallback, schema retry telemetry, prompt version, token/cost telemetry 도입.
- circuit breaker safe fallback과 LLM metrics/reporting 기반 구축.

### 이 변경의 의미
LLM을 단순 호출하는 수준에서 실패·비용·버전까지 관리하는 운영 컴포넌트로 승격.

### 근거 문서 / 코드
- `docs/plan/m17_graph_spine_and_risk.md`
- `docs/plan/m18_strategist_signals.md`
- `docs/plan/m19_1_naver_news_provider.md`
- `docs/plan/m19_5_llm_routing_openrouter.md`
- `docs/plan/m20_1_llm_smoke_and_fallback.md`
- `docs/plan/m20_7_token_cost_telemetry.md`

---

## 2026-02-15 ~ 2026-02-21 · M21–M24 — Canonical Runtime, Circuit Breaker, Intent Journal
**Stage:** Production Safety  
**Tags:** RUNTIME · SAFETY · STATE

실행 경로를 하나의 canonical runtime으로 모으고 장애·중복실행·운영자 개입을 상태 기반으로 통제.

### 변경 내용
- Commander bridge와 canonical runtime entry를 표준 경로로 통합.
- runtime mode resolution과 agent-chain mapping/parity test 추가.
- Skill-native scanner/monitor와 hydration node, DTO contract 표준화.
- runtime circuit breaker, safe-degrade, cooldown, operator intervention/resume runbook 추가.
- SQLite intent journal/state machine과 duplicate execution claim guard 도입.
- real execution preflight denial reason과 intent state reconciliation tooling 추가.

### 이 변경의 의미
프로세스 재시작·장애·중복 이벤트가 발생해도 주문 상태를 복구·감사할 수 있는 방향으로 강화.

### 근거 문서 / 코드
- `docs/plan/m21_1_canonical_runtime_entry.md`
- `docs/plan/m22_5_skill_hydration_node.md`
- `docs/plan/m23_2_runtime_circuit_breaker_core.md`
- `docs/plan/m23_6_operator_intervention_resume_runbook.md`
- `docs/plan/m24_1_intent_journal_state_machine_sqlite.md`
- `docs/plan/m24_3_duplicate_execution_claim_guard.md`

---

## 2026-02-18 ~ 2026-02-21 · M25–M30 — Metrics·Alerts·Replay·Portfolio Guard·Deployment·Go-Live Gate
**Stage:** Productionization  
**Tags:** OPS · QUALITY · DEPLOYMENT · PORTFOLIO

실전 운영을 위한 모니터링·알림·재현성·포트폴리오 제한·배포·릴리즈 승인 절차를 묶어 완성.

### 변경 내용
- metric schema freeze와 alert threshold/env profile 정의.
- Slack adapter, retry/noise-control, notification event log 구축.
- fixed dataset/replay runner, scorecard, A/B evaluation, promotion gate 추가.
- multi-strategy allocation, intent conflict resolution, portfolio budget guard 도입.
- runtime lifecycle hook, scheduler/worker wrapper, launch templates, rollback procedure 구성.
- audit completeness, log archive integrity, incident timeline reconstruction, disaster recovery drill 추가.
- quality gate와 release signoff/go-live signoff aggregator 구축.

### 이 변경의 의미
코드가 돌아가는 수준에서 '운영 가능한 시스템'으로 넘어간 구간.

### 근거 문서 / 코드
- `docs/plan/m20_to_m30_master_plan.md`
- `docs/plan/m25_1_metric_schema_freeze_v1.md`
- `docs/plan/m26_2_replay_runner_scaffold.md`
- `docs/plan/m27_3_portfolio_budget_boundary_guard.md`
- `docs/plan/m28_3_rollout_checklist_and_rollback_procedure.md`
- `docs/plan/m29_8_disaster_recovery_drill_restore_replay.md`
- `docs/plan/m30_4_final_golive_signoff_aggregator.md`

---

## 2026-03-06 · M31-1~3 — Post-Go-Live 운영 검증 시작
**Stage:** Operational Readiness  
**Tags:** OPS · SLO · QUALITY

SLO·incident review·mock investor exam·weekly health summary로 실제 장중 운영 상태를 계량화.

### 변경 내용
- M31 SLO baseline과 incident review workflow 구현.
- Mock Investor Exam protocol/check와 agent-chain probe 추가.
- Weekly health summary operator script 추가.
- 3/6 세션 기준 319 runs, 1,376 events를 수집해 execution/LLM 품질을 점검.
- Strategist LLM 성공률 93.5%, 높은 p95 latency와 prompt-version 혼재를 즉시 개선 우선순위로 지정.

### 이 변경의 의미
'기능 구현 완료'가 아니라 실제 세션 데이터로 운영 준비도를 평가하기 시작.

### 근거 문서 / 코드
- `docs/plan/m31_plus_progress_summary_2026-03-06.md`

---

## 2026-03-07 · M31 Safety Patch — Portfolio Snapshot Health Guard + EOD 강제청산
**Stage:** Operational Readiness  
**Tags:** SAFETY · PORTFOLIO · EXECUTION

계좌 snapshot 장애 시 blind BUY를 차단하고 당일 청산 정책을 deterministic rule로 보강.

### 변경 내용
- portfolio_snapshot에 reader_ok/error/source/fallback 등의 health metadata 추가.
- real execution에서 snapshot reader 오류 시 BUY를 portfolio_snapshot_reader_error로 차단.
- USE_EOD_FORCE_LIQUIDATION 기반 pre-close SELL rule 추가.
- 관련 snapshot/execute/decision 테스트 보강.

### 이 변경의 의미
브로커 상태를 모르는 상황에서 신규 포지션을 잡는 위험을 구조적으로 줄임.

### 근거 문서 / 코드
- `docs/plan/m31_plus_runtime_safety_patch_2026-03-07.md`

---

## 2026-03-08 · M31 Audit — Operational Readiness: NOT_READY → READY
**Stage:** Operational Readiness  
**Tags:** AUDIT · SAFETY · STRATEGY

운영 감사에서 설정 문제를 수정한 뒤 M31 readiness gate를 통과.

### 변경 내용
- 초기 audit 결과 NOT_READY 확인.
- APPROVAL_MODE=manual로 수정 후 readiness check 재실행.
- Feature/regime engine, Strategy V1, universe/scanner, data-quality propagation, sizing/exit explainability 활성 상태 확인.
- Operator visibility와 readiness scripts의 실제 연결 검증.
- regime_momentum_v1을 Strategy V1 baseline으로 명시.

### 이 변경의 의미
실전 전환 여부를 사람의 느낌이 아니라 체크 가능한 gate로 판정할 수 있게 됨.

### 근거 문서 / 코드
- `docs/plan/m31_operational_readiness_audit_2026-03-08.md`

---

## 2026-04-14 ~ 2026-04-16 · Reporter v2 — AI Trade Report 안정화와 Reporter Agentification
**Stage:** Explainability  
**Tags:** REPORTER · REPORTING · LLM

거래 후 보고서를 단순 로그 요약이 아닌 evidence 기반 agent output으로 재설계.

### 변경 내용
- Reporter fallback audit 후 recovery/stabilization plan 수행.
- AI Trade Report target example과 improvement plan으로 목표 포맷 고정.
- golden trade matrix와 report runtime regression plan 도입.
- execution snapshot observability와 lifecycle linkage를 report에 연결.
- report surface pruning과 Reporter ownership 정리.

### 이 변경의 의미
거래 결과뿐 아니라 '왜 그 판단이 나왔고 실제로 어떻게 체결됐는지'를 한 보고서에서 추적 가능해짐.

### 근거 문서 / 코드
- `docs/debug/reporter_fallback_audit_2026-04-14.md`
- `docs/trade_report_plan/ai_trade_report_improvement_plan_2026-04-15.md`
- `docs/report_upgrade_plan/reporter_agentification_execution_plan_2026-04-15.md`
- `docs/trade_report_plan/golden_trade_matrix_2026-04-16.md`

---

## 2026-04-19 ~ 2026-04-21 · Memory v1 — Market/Symbol/Position Runtime Memory 구축
**Stage:** Agent Memory  
**Tags:** MEMORY · COMMANDER · STRATEGIST

세션 단발 판단을 넘어 과거 시장·종목·포지션 상태를 다음 판단에 전달하는 memory contract 구축.

### 변경 내용
- market_memory, symbol_memory, memory_flow, reports usage contract 정의.
- position refresh contract와 symbol read-model 정렬.
- memory packet schema와 Strategist memory packet visibility 추가.
- Commander memory authority, Scanner memory bias, Monitor memory bias 역할 분리.
- 불필요한 script/report 중복을 줄이는 reduction policy 도입.

### 이 변경의 의미
각 Agent가 제멋대로 과거를 해석하지 않고 정해진 memory packet을 통해 맥락을 공유하게 됨.

### 근거 문서 / 코드
- `docs/runtime_memory/market_memory_contract_2026-04-19.md`
- `docs/runtime_memory/symbol_memory_contract_2026-04-19.md`
- `docs/runtime_memory/memory_packet_schema_2026-04-21.md`
- `docs/commander_control/commander_memory_authority_2026-04-21.md`

---

## 2026-04-20 ~ 2026-04-28 · Truth Alignment — Kiwoom Truth와 Commander Control 정렬
**Stage:** Runtime Integrity  
**Tags:** KIWOOM · COMMANDER · DATA_QUALITY

broker truth, theme strength, carry/position 관리, 대표 종목 guard를 실제 runtime 판단과 일치시키는 작업.

### 변경 내용
- Kiwoom role inventory/data target map으로 어떤 API가 어떤 판단에 쓰이는지 정리.
- Kiwoom truth current-state/next-step plan으로 raw broker truth와 derived value 경계 강화.
- Commander carry control model과 position management policy 정립.
- theme strength packet과 theme API strategy selection 추가.
- entry participation control 및 market representative guard 도입.

### 이 변경의 의미
리포트 숫자·Agent 판단·브로커 계좌 상태가 서로 다른 truth를 보는 문제를 줄임.

### 근거 문서 / 코드
- `docs/kiwoom_truth/kiwoom_truth_alignment_plan_2026-04-20.md`
- `docs/commander_control/carry_control_model_2026-04-20.md`
- `docs/kiwoom_truth/kiwoom_theme_strength_packet_2026-04-27.md`
- `docs/commander_control/market_representative_guard_2026-04-28.md`

---

## 2026-04-22 · System Status — Trade Report/Kiwoom/Entrypoint 안정화 상태 점검
**Stage:** Runtime Integrity  
**Tags:** REPORTER · MEMORY · RUNTIME

5개 주요 workstream을 통합 점검해 닫힌 영역과 계속 개발할 영역을 분리.

### 변경 내용
- trade_report_plan, kiwoom_truth, runtime_entrypoint는 거의 안정화 상태로 평가.
- runtime_memory와 commander_control은 계속 active development로 유지.
- AI Trade Report에서 broker truth, fee/tax, memory usage, LLM event flow 검증.
- same-day Reporter feedback을 reporter_evaluation으로 재구성하는 경로 확인.

### 이 변경의 의미
개발 우선순위를 기능 추가에서 남은 불확실성 제거로 전환.

### 근거 문서 / 코드
- `docs/system_status_2026-04-22.md`

---

## 2026-04-25 ~ 2026-04-30 · Strategy/Horizon v1 — 보유시간·사후 Shadow·설명 계약 + 보수성 Guard
**Stage:** Strategy Refinement  
**Tags:** STRATEGIST · HORIZON · GUARD

진입 여부만 보던 전략에서 보유시간, post-exit shadow, 설명 가능성, 중복매수 방지까지 확장.

### 변경 내용
- strategy horizon과 post-exit shadow tracking 계약 추가.
- Strategist explanation contract와 LLM summary artifact 정리.
- news query target flow와 operator-summary memory linkage 연결.
- duplicate buy/closeout guard 및 preopen readiness 점검 추가.
- 전략 과보수성 분석 후 runtime guard와 entry gate/reporting memory defaults 보정.

### 이 변경의 의미
'살까 말까'에서 '왜, 얼마나 들고, 언제 실패로 볼 것인가'로 전략 표현 범위가 확장.

### 근거 문서 / 코드
- `docs/strategy_horizon_feedback/strategy_horizon_and_post_exit_shadow_tracking_2026-04-25.md`
- `docs/strategist_output/strategist_explanation_contract_2026-04-25.md`
- `docs/commander_control/duplicate_buy_and_closeout_guard_2026-04-29.md`
- `docs/daily_patch/2026-04-29_strategy-conservatism-runtime-guards.md`
- `docs/daily_patch/2026-04-30_entry-gate-reporting-memory-defaults.md`

---

## 2026-05-04 ~ 2026-05-07 · Live Truth Stabilization — 장중 Cash/가격 Truth와 Report 일치화
**Stage:** Live Stabilization  
**Tags:** LIVE · REPORTING · DATA_QUALITY

실시간 계좌·체결 가격과 보고서에 보이는 값이 어긋나는 문제를 집중 보정.

### 변경 내용
- intraday cash truth와 AI report를 교차 검증.
- truth surface와 summary 문구 정렬.
- today-run gap review로 누락된 런/아티팩트 확인.
- trade price truth refresh로 오래된 가격 참조 제거.
- live open patch verification으로 실제 장 시작 시 경로 재검증.

### 이 변경의 의미
보고서가 계산상 그럴듯한 값이 아니라 당시 broker/runtime truth를 보여주도록 강화.

### 근거 문서 / 코드
- `docs/daily_patch/2026-05-04_intraday-cash-truth-ai-report-check.md`
- `docs/daily_patch/2026-05-05_truth-surface-summary-alignment.md`
- `docs/daily_patch/2026-05-06_trade-price-truth-refresh.md`
- `docs/daily_patch/2026-05-07_live-open-patch-verification.md`

---

## 2026-05-08 · Strategist 4-Stage Draft — 4단계 Strategist LLM + Horizon Slot 설계
**Stage:** Strategy Refinement  
**Tags:** STRATEGIST · LLM · HORIZON

뉴스/시장 → Scanner 후보 → 보유 판단 → Overnight 판단의 다단계 LLM 구조와 horizon slot 운영안을 설계.

### 변경 내용
- Strategist 4-stage LLM flow draft와 chat prompt template 작성.
- LLM reports 4-stage summary layout 정의.
- two-slot runtime과 multi-position minimal patch plan 작성.
- horizon slot one-symbol policy 및 report layout 정의.
- post-scanner refresh latency hotfix로 최신 후보 데이터 연결 지연 감소.

### 이 변경의 의미
현재 전략가의 다단계 역할 구조가 문서화되고 UI/report에서 단계별 판단을 보여줄 기반 마련.

### 근거 문서 / 코드
- `docs/strategy_horizon_feedback/strategist_4stage_llm_flow_draft_2026-05-08.md`
- `docs/strategy_horizon_feedback/strategist_4stage_chat_prompt_templates_2026-05-08.md`
- `docs/strategy_horizon_feedback/two_slot_runtime_patch_plan_2026-05-08.md`
- `docs/daily_patch/2026-05-08_post-scanner-refresh-latency-fix.md`

---

## 2026-05-11 ~ 2026-05-12 · Live Guard Pack A — Scanner↔Monitor 경계와 장중 Guard 대규모 보강
**Stage:** Live Stabilization  
**Tags:** SCANNER · MONITOR · GUARD · LIVE

실전에서 드러난 stale order, chart-fit, VWAP, closeout, repeat-loss 문제를 집중 보강한 대규모 핫픽스.

### 변경 내용
- pending-order stale guard와 pending-exit/recent-fill settle guard 추가.
- Scanner/Monitor chart reading role boundary와 runtime alignment 정리.
- ETF universe·deviation signal, candidate cascade expansion 추가.
- VWAP exit에서 fresh minute source 사용하도록 수정.
- human-chart guard와 chart-fit/horizon alignment 강화.
- full-close trade report gate, closeout preflight fallback 추가.
- defensive Top3/repeat-loss guard와 monitor crash hotfix 적용.

### 이 변경의 의미
Scanner가 후보를 찾고 Monitor가 진입 타이밍을 감시한다는 책임 경계가 실전 규칙에 반영됨.

### 근거 문서 / 코드
- `docs/strategy_horizon_feedback/scanner_monitor_role_boundary_patch_plan_2026-05-11.md`
- `docs/strategy_horizon_feedback/scanner_monitor_chart_reading_runtime_alignment_2026-05-12.md`
- `docs/daily_patch/2026-05-12_candidate-cascade-expansion-hotfix.md`
- `docs/daily_patch/2026-05-12_human-chart-guard-chartfit-horizon-alignment.md`
- `docs/daily_patch/2026-05-12_vwap-exit-fresh-minute-source-hotfix.md`

---

## 2026-05-13 ~ 2026-05-14 · Live Guard Pack B — Entry/Exit Evidence, Peak Protection, VWAP Reclaim
**Stage:** Live Stabilization  
**Tags:** ENTRY · EXIT · REPORTING · LLM

진입·청산 사유와 실행 결과를 분리하고 수익 보호·VWAP reclaim·LLM 비용까지 세밀하게 조정.

### 변경 내용
- exit trigger와 execution status를 분리해 '팔려고 했다'와 '실제로 팔렸다'를 구분.
- entry/exit evidence line과 operator summary pattern performance 추가.
- pending BUY에 human-chart hard guard 적용.
- chart-positive entry와 cooldown scope 재조정.
- peak-profit protection 및 peak-drawdown profit floor 강화.
- VWAP reclaim strategy와 human-chart entry relaxation 실험.
- Strategist input fingerprint cache gate와 token budget 추가.

### 이 변경의 의미
전략 논리, 실행 상태, 보고서 표현이 섞이는 문제를 크게 줄이고 LLM 비용 통제도 시작.

### 근거 문서 / 코드
- `docs/daily_patch/2026-05-13_exit-trigger-execution-status-separation.md`
- `docs/daily_patch/2026-05-13_trade-summary-entry-exit-evidence-lines.md`
- `docs/daily_patch/2026-05-13_peak-profit-protection-report-evidence.md`
- `docs/daily_patch/2026-05-14_vwap-reclaim-strategy-and-human-chart-entry-relaxation.md`
- `docs/daily_patch/2026-05-14_strategist-llm-token-budget.md`

---

## 2026-05-15 ~ 2026-05-18 · Runtime Refactor — Runtime-first 점진 리팩터링과 Execution/Reporting 경계 분리
**Stage:** Maintainability  
**Tags:** REFACTOR · RUNTIME · REPORTING

거대한 runtime/reporting hotspot을 기능 변경 없이 단계적으로 분리하는 리팩터링 시작.

### 변경 내용
- incremental refactor plan과 revised runtime-first plan 수립.
- 대형 reporting hotspot map 작성 후 단계적 extraction 진행.
- live execution reporting boundary를 명시적으로 분리.
- entry cascade hardblock과 summary average 계산 정리.
- 리팩터링이 실전 행동을 바꾸지 않도록 regression 중심으로 진행.

### 이 변경의 의미
기능을 계속 붙이면서도 runtime이 단일 거대 파일로 붕괴하는 것을 방지.

### 근거 문서 / 코드
- `docs/dev/incremental_refactor_plan_2026-05-15.md`
- `docs/dev/revised_runtime_first_refactor_plan_2026-05-15.md`
- `docs/dev/phase_9_3_large_reporting_hotspot_map_2026-05-17.md`
- `docs/daily_patch/2026-05-18_live-execution-reporting-boundary.md`

---

## 2026-05-20 · Q1–Q7 — Quant Tactic Engine 도입
**Stage:** Quant Evaluation  
**Tags:** QUANT · SHADOW · TACTIC

LLM 판단만 평가하지 않고 규칙 기반 전술 후보를 Q1~Q7 독립 실험으로 비교하는 Quant Tactic Engine 구축.

### 변경 내용
- Q1~Q6를 독립 tactic slice로 추가.
- Q7을 3개 slice로 나눠 세부 조건을 분리 검증.
- 각 tactic의 판단과 결과를 메인 전략과 분리해 shadow/evaluation 가능하게 설계.
- 동일한 시장 데이터에서 전술별 evidence를 비교할 수 있는 기반 마련.

### 이 변경의 의미
'전략가가 맞았나'에서 '어떤 규칙이 실제 수익 edge를 만들었나'로 평가 단위가 확장.

### 근거 문서 / 코드
- `docs/daily_patch/2026-05-20_quant-tactic-engine-q1.md`
- `docs/daily_patch/2026-05-20_quant-tactic-engine-q7-slice3.md`

---

## 2026-05-21 ~ 2026-05-26 · Q8 Bootstrap — Quant Entry Enforcement와 Q8 Shadow Dataset
**Stage:** Quant Evaluation  
**Tags:** Q8 · QUANT · DATA_QUALITY

Q1~Q7 결과를 바탕으로 Q8 검증 루프를 열고 후보·체결·리포트 truth를 고정.

### 변경 내용
- quant entry enforcement로 정량 조건이 실제 진입 gate에 반영되는 경로 구축.
- Q7 residual Strategist context를 남겨 규칙과 LLM 상호작용 관찰.
- close review를 통해 Q8 핵심 질문 정의.
- Q8 report integrity와 bundle latency 점검.
- candidate shadow dataset과 broker alignment at report generation 추가.
- Kiwoom account snapshot archive와 truth-first ka10170 경로 검증.
- opening momentum probe shadow 및 guard count fix 적용.

### 이 변경의 의미
메인 runtime을 계속 바꾸지 않고 shadow evidence를 축적하는 실험 방식이 정착.

### 근거 문서 / 코드
- `docs/daily_patch/2026-05-21_quant-entry-enforcement.md`
- `docs/daily_patch/2026-05-22_q8_report_integrity_and_bundle_latency.md`
- `docs/daily_patch/2026-05-24_q8_candidate_shadow_dataset.md`
- `docs/daily_patch/2026-05-26_opening_momentum_probe_shadow.md`

---

## 2026-06-01 ~ 2026-06-20 · Q8 Validation — Q8 장기 검증 — Cost Edge, Lane Decision, 실패 원인 분해
**Stage:** Evidence Validation  
**Tags:** Q8 · EVALUATION · COST

Q8을 단기 실험으로 끝내지 않고 실제 기간 데이터를 누적해 비용 이후 edge와 lane별 성능을 검증.

### 변경 내용
- Q8 active behavior patch와 cost-edge promotion state 정의.
- daily review와 lane decision table을 날짜별로 누적.
- below-VWAP reclaim subtype 및 historical review 수행.
- 실패 원인을 Scanner, entry blocker, timing, cost 관점으로 분리.
- 6/19 handoff와 6/20 final comprehensive review로 Q8 평가를 공식 종료/이관.

### 이 변경의 의미
한두 번의 성공 거래가 아니라 반복 가능한 증거가 있어야 promotion한다는 원칙이 강화됨.

### 근거 문서 / 코드
- `docs/daily_patch/2026-06-01_q8_active_behavior_patch.md`
- `docs/tactics/q8_lane_decision_table_2026-06-16.md`
- `docs/evaluation/q8_handoff_2026-06-19.md`
- `docs/evaluation/q8_final_comprehensive_review_2026-06-20.md`

---

## 2026-06-22 ~ 2026-06-26 · Q9 — Fixed Forward Window와 Horizon Observability
**Stage:** Forward Evaluation  
**Tags:** Q9 · EVALUATION · HORIZON

사후 최적화 편향을 줄이기 위해 고정된 forward window와 horizon 계약을 도입.

### 변경 내용
- horizon alignment, Q9 component, loss decomposition decision 문서화.
- fixed forward-window protocol로 평가 조건을 사전에 고정.
- Day1 opening calculation review로 산식과 artifact를 검증.
- 5m/15m/30m/EOD horizon observability 계약 추가.
- 후속 baseline과 동일한 평가 축을 사용할 수 있도록 준비.

### 이 변경의 의미
좋은 결과가 나온 뒤 조건을 바꾸는 것을 막고 prospective evaluation 성격을 강화.

### 근거 문서 / 코드
- `docs/evaluation/q9_fixed_forward_window_protocol_2026-06-23.md`
- `docs/evaluation/q9_horizon_contract_observability_2026-06-26.md`

---

## 2026-06-23 이후 · Independent Baselines — Samsung/Hynix + BTC→우리기술투자 독립 비교군
**Stage:** Forward Evaluation  
**Tags:** BASELINE · BTC_WOORI · LARGE_CAP

Q9 자체 성능만 보지 않고 단순하고 독립적인 외부 baseline과 비교하는 평가 구조로 확장.

### 변경 내용
- 삼성전자/하이닉스 고정 baseline을 Q9와 같은 horizon에서 비교.
- Top1, trade count, 승률, 평균수익률, PF, MDD 비교 구조 마련.
- BTC 선행 움직임과 우리기술투자 반응을 별도 baseline 연구 track으로 추가.
- Commander Final이 baseline 대비 실제 alpha를 냈는지 구분 가능하도록 설계.

### 이 변경의 의미
복잡한 Agent 시스템이 단순 전략보다 정말 나은지를 검증하는 기준선 확보.

### 근거 문서 / 코드
- `docs/evaluation`
- `reports/evaluation/baseline_samsung_hynix`
- `reports/evaluation/baseline_btc_woori`

---

## 2026-07-06 · Q13 — Entry Timing Attribution — 왜 틀렸는지 수치화
**Stage:** Attribution  
**Tags:** Q13 · EXPLAINABILITY · EVALUATION

손익 결과만 보지 않고 후보선정→판단→실제 진입까지 어느 단계가 성능을 깎았는지 attribution score로 분해.

### 변경 내용
- Q13 entry timing attribution 정의.
- attribution score v0 및 기간 누적 score 생성.
- Scanner/Strategist/entry timing 사이의 지연과 결과를 연결.
- observability patch로 누락 timestamp/evidence 품질 개선.
- 실패 원인을 '전략이 나쁨' 하나로 몰지 않는 진단 구조 구축.

### 이 변경의 의미
개선해야 할 Agent/단계를 데이터로 특정할 수 있게 됨.

### 근거 문서 / 코드
- `docs/q13/q13_entry_timing_attribution_2026-07-06.md`
- `docs/q13/q13_attribution_score_v0_2026-07-06.md`
- `docs/q13/observability_patch_2026-07-06.md`

---

## 2026-07-08 ~ 2026-07-21 · Q14–Q16 — Candidate Filtering과 Cost/Horizon Fit 검증
**Stage:** Policy Validation  
**Tags:** Q14 · Q15 · Q16 · POLICY

Q13 attribution 결과를 실제 개선 후보로 바꾸되 곧바로 live behavior를 수정하지 않고 단계별 검증.

### 변경 내용
- Q15 scanner score component candidate 정의 후 filtering patch 적용.
- 2-day decision tree, close decision, adjustment retest로 단기 과적합 방지.
- Q16 cost-horizon-fit patch로 예상 edge가 거래비용을 넘는지 검증.
- 조정안은 정해진 close/retest 절차를 통과해야 유지하도록 운영.

### 이 변경의 의미
아이디어→패치가 아니라 후보→검증→종료/유지의 연구 절차가 정착.

### 근거 문서 / 코드
- `docs/q13_q14_validation/q15_scanner_score_component_candidate_2026-07-08.md`
- `docs/q13_q14_validation/q15_candidate_filtering_patch_2026-07-10.md`
- `docs/q13_q14_validation/post_q15_adjustment_retest_close_2026-07-21.md`
- `docs/q13_q14_validation/q16_cost_horizon_fit_patch_2026-07-21.md`

---

## 2026-07-22 ~ 2026-07-24 · Measurement Integrity + Q17 — Stale Fill 정합성 수정과 Directional Edge 계약
**Stage:** Evaluation Integrity  
**Tags:** DATA_QUALITY · Q16 · Q17

평가값 자체가 오염될 수 있는 stale fill/measurement 문제를 먼저 고치고 방향성 edge 검증으로 진행.

### 변경 내용
- measurement integrity fix로 평가 산식과 evidence source 경계 보정.
- broker stale fill reconciliation fix로 잘못 연결된 체결 제거.
- Q16 Day1 review 및 close decision 수행.
- Q17 directional edge contract patch 추가.
- horizon operational contract도 runtime 동작과 평가 정의가 일치하도록 수정.

### 이 변경의 의미
잘못된 데이터로 전략을 개선하는 더 큰 오류를 막기 위해 measurement authority를 우선시.

### 근거 문서 / 코드
- `docs/q13_q14_validation/measurement_integrity_fix_2026-07-22.md`
- `docs/q13_q14_validation/broker_stale_fill_reconciliation_fix_2026-07-22.md`
- `docs/q13_q14_validation/q17_directional_edge_contract_patch_2026-07-24.md`
- `docs/strategy_horizon_feedback/horizon_operational_contract_fix_2026-07-24.md`

---

## 2026-07-27 ~ 2026-07-30 · Q8–Q17 Closure — 누적 검증 종료 + Same-Symbol Re-entry Control
**Stage:** Policy Closure  
**Tags:** Q17 · GUARD · EVALUATION

Q8~Q17 누적 결과를 닫고 반복 손실 종목 재진입과 평가 무결성을 별도 통제.

### 변경 내용
- Q8-Q17 cumulative review와 close review 수행.
- same-symbol loss/re-entry control 추가.
- evaluation integrity close로 legacy/수정 후 evidence 경계를 명시.
- canonical final review를 통해 더 이상 이름만 바꿔 같은 실험을 반복하지 않도록 종료 상태 고정.

### 이 변경의 의미
실패한 가설을 계속 재포장해 실험하는 연구 부채를 줄임.

### 근거 문서 / 코드
- `docs/q13_q14_validation/q8_q17_cumulative_review_2026-07-27.md`
- `docs/q13_q14_validation/same_symbol_loss_reentry_control_2026-07-29.md`
- `docs/q13_q14_validation/q8_q17_canonical_final_review_2026-07-30.md`

---

## 2026-07-30 · Structural Alpha v1 — Offline Structural Alpha Search와 Hypothesis Competition
**Stage:** Alpha Research  
**Tags:** ALPHA · OFFLINE · RESEARCH

메인 runtime 변경 없이 기존 evidence에서 구조적 alpha 후보를 찾고 서로 경쟁시키는 offline research layer 구축.

### 변경 내용
- structural alpha batch1/batch2 contract와 result 생성.
- post-reclaim offline research와 executable policy v0 초안 작성.
- alpha hypothesis competition v1으로 여러 설명 가설을 동일한 evidence에서 비교.
- structural alpha search closure로 살아남지 못한 가설을 종료.

### 이 변경의 의미
새 전략을 무작정 코딩하기 전에 기존 데이터에서 조건부 edge가 존재하는지 검증하는 연구 단계 추가.

### 근거 문서 / 코드
- `docs/offline_alpha/structural_alpha_batch1_result_2026-07-30.md`
- `docs/offline_alpha/structural_alpha_batch2_result_2026-07-30.md`
- `docs/offline_alpha/alpha_hypothesis_competition_v1_result_2026-07-30.md`
- `docs/offline_alpha/structural_alpha_search_closure_2026-07-30.md`

---

## 2026-07-31 · Integrated Diagnosis — Opening Rank-1 + Selection/Horizon/Sequence 통합 진단
**Stage:** Alpha Research  
**Tags:** RANK1 · DIAGNOSIS · Q11

Rank-1 후보가 왜 실패/성공하는지 단일 수익률이 아니라 선정·보유시간·동일종목 시퀀스로 통합 분석.

### 변경 내용
- existing evidence mining contract/result 작성.
- opening Rank-1 longitudinal, deep-dive, same-symbol sequence review 수행.
- prospective validation 계약으로 사후 분석과 미래 검증 분리.
- integrated selection-horizon-sequence evaluation 추가.
- Scanner market candidates와 Q11 index sanity도 함께 보강.

### 이 변경의 의미
종목선정 문제와 진입/보유 문제를 한데 섞지 않고 전체 trade lifecycle에서 원인을 찾게 됨.

### 근거 문서 / 코드
- `docs/offline_alpha/opening_rank1_deep_dive_2026-07-31.md`
- `docs/offline_alpha/opening_rank1_same_symbol_sequence_review_2026-07-31.md`
- `docs/quant_trade_diagnosis/integrated_selection_horizon_sequence_evaluation_2026-07-31.md`
- `docs/daily_patch/2026-07-31_scanner_market_candidates_and_q11_index_sanity.md`

---

## 2026-08-05 ~ 2026-08-07 · Canonical Alpha Loop — 조건부 Alpha Findings → Canonical Execution Plan → 5-Session Closure
**Stage:** Alpha Research  
**Tags:** ALPHA · CANONICAL · VALIDATION

흩어진 조건부 발견을 하나의 실행/검증 계획과 active research register로 통합.

### 변경 내용
- position horizon revision contract로 horizon 정의 재정렬.
- conditional alpha diagnosis와 integrated conditional alpha findings 작성.
- canonical execution plan으로 어떤 evidence를 언제 수집할지 고정.
- active research register로 살아있는/종료된 가설을 관리.
- five-session closure에서 broad Rank-1 opening은 intraday에서 음수임을 확인하고 무조건 promotion을 거부.
- 조건부 lane은 shadow-only로 유지.

### 이 변경의 의미
좋아 보이는 발견을 즉시 전략으로 승격하지 않고 prospective evidence를 요구하는 연구 거버넌스가 완성됨.

### 근거 문서 / 코드
- `docs/offline_alpha/conditional_alpha_diagnosis_2026-08-06.md`
- `docs/offline_alpha/canonical_execution_plan_2026-08-06.md`
- `docs/offline_alpha/active_research_register_2026-08-07.md`
- `docs/offline_alpha/five_session_closure_2026-08-07.md`

---

## 2026-08-11 ~ 2026-08-12 · Rank-1 Feature Mart — Canonical Feature Mart + Prospective Shadow + Strategy Choice Observability
**Stage:** Alpha Research  
**Tags:** FEATURE_MART · SHADOW · OBSERVABILITY

Rank-1 후보 연구에 필요한 feature/evidence를 canonical mart로 고정하고 미래 데이터에서 재검증.

### 변경 내용
- canonical Rank-1 feature mart 구축.
- fixed-candidate prospective shadow로 후보 조건을 고정한 채 관찰.
- fresh-change activation shadow로 단순 재등장과 새로운 signal 활성화를 구분.
- strategy-choice observability로 어떤 조건에서 어떤 전략 선택이 일어났는지 기록.

### 이 변경의 의미
연구 데이터셋이 코드마다 달라지는 문제를 줄이고 prospective comparison의 재현성을 높임.

### 근거 문서 / 코드
- `docs/offline_alpha/canonical_rank1_feature_mart_2026-08-11.md`
- `docs/offline_alpha/rank1_fixed_candidate_prospective_shadow_2026-08-11.md`
- `docs/offline_alpha/rank1_fresh_change_activation_shadow_2026-08-12.md`
- `docs/offline_alpha/rank1_strategy_choice_observability_2026-08-12.md`

---

## 2026-08-13 · Memory Integrity Review — Historical Memory 영향 재검증
**Stage:** Agent Memory  
**Tags:** MEMORY · EVALUATION

과거 memory가 실제 의사결정에 도움을 주는지, 잘못된 기억이 누적되지 않는지 별도 integrity review 수행.

### 변경 내용
- memory integrity correction으로 잘못된/오염된 memory 연결 수정.
- historical memory impact review로 memory 사용 전후 판단 영향 평가.
- Memory를 무조건 많이 넣는 것이 아니라 evidence가 있는 정보만 유지하는 방향 강화.

### 이 변경의 의미
Agent memory가 설명용 장식이 아니라 성능/편향을 측정해야 하는 독립 컴포넌트가 됨.

### 근거 문서 / 코드
- `docs/runtime_memory/memory_integrity_correction_2026-08-13.md`
- `docs/runtime_memory/historical_memory_impact_review_2026-08-13.md`

---

## 2026-08-14 · Web Observability M0–M6 — Read-only FastAPI + React/Vite 운영 UI MVP
**Stage:** Productization  
**Tags:** WEB_UI · API · OBSERVABILITY

trading runtime과 완전히 분리된 read-only 웹 관측 계층을 구축해 포트폴리오에서도 시스템 상태를 보여줄 수 있게 됨.

### 변경 내용
- M0 product/data contract와 truth/time/cost/availability 계약 고정.
- M1 isolated FastAPI health/config/path/bounded-read foundation 구축.
- M2 Performance, M3 Trades/Reports, M4 Opportunities/Strategies/Market API 완성.
- M5 React/Vite 기반 9-domain operating console 완성.
- M5.1 OpenRouter role/model/stage/status/latency를 보여주는 LLM Operations 추가.
- M6 public profile과 anomaly surface를 server-side sanitized read model로 구현.
- API 계층은 Trading Core import 0, write call 0, non-GET route 0으로 격리 검증.

### 이 변경의 의미
자동매매 내부 개발 프로젝트에서 외부에 설명 가능한 운영 제품/포트폴리오 형태로 전환.

### 근거 문서 / 코드
- `docs/web_observability/implementation_status_2026-08-14.md`
- `docs/web_observability/m5_web_ui_implementation_2026-08-14.md`
- `docs/web_observability/m6_anomaly_public_profile_implementation_2026-08-14.md`

---

## 2026-08-14 · Opening Probe — Opening Rank-1 Controlled Probe
**Stage:** Alpha Research  
**Tags:** RANK1 · PROSPECTIVE · SHADOW

오프닝 Rank-1 조건을 통제된 probe로 좁혀 live promotion 없이 prospective evidence를 수집.

### 변경 내용
- broad opening rule을 재도입하지 않고 제한된 controlled probe 정의.
- independent episode/day-symbol 단위 표본을 우선하도록 유지.
- 비용 기준을 명시해 gross와 live-net을 분리.
- 조건부 성능이 나와도 자동 promotion하지 않는 shadow-only 원칙 유지.

### 이 변경의 의미
과거 성과가 좋아 보이는 조건을 live rule로 즉시 되살리는 것을 방지.

### 근거 문서 / 코드
- `docs/offline_alpha/opening_rank1_controlled_probe_2026-08-14.md`

---

## 2026-08-18 · Web M7 — Docker Compose 배포 계층
**Stage:** Deployment  
**Tags:** DOCKER · WEB_UI · DEPLOYMENT

private/public Web UI와 API를 컨테이너로 띄우기 위한 M7 배포 코드 완성.

### 변경 내용
- API/UI image와 private/public Compose 구성.
- trading runtime과 web observability의 isolation 유지.
- local Docker engine 검증을 다음 gate로 설정.
- M8 Kubernetes local overlay는 Compose 통과 이후로 순서를 고정.

### 이 변경의 의미
개발 PC 로컬 실행에서 재현 가능한 배포 단위로 확장.

### 근거 문서 / 코드
- `docs/web_observability/m7_docker_compose_implementation_2026-08-18.md`

---

## 2026-08-21 · Measurement Integrity v2 — Q10/Q11/Q13/Q14–Q18 측정 권위 재정립
**Stage:** Evaluation Integrity  
**Tags:** Q10 · Q11 · Q13 · Q18 · DATA_QUALITY

legacy 평가값과 수정 후 prospective cohort가 섞이지 않도록 point-in-time·timestamp·horizon 계약을 재정의.

### 변경 내용
- Q10 point-in-time market snapshot 정합성 보강.
- Q11 shadow-position follow-through와 index sanity 보정.
- Q13 stage timestamp와 decision-to-entry delay를 실제 evidence 기반으로 수정.
- Q14 outcome-conditioned diagnosis와 structural root cause 분리.
- Q16 day-integrity, Q17 intended horizon, Q18 horizon-specific coverage 추가.
- 수정 전 legacy 측정은 corrected prospective cohort와 합산하지 않도록 authority boundary 고정.

### 이 변경의 의미
평가 시스템 자체의 신뢰도를 전략 성능만큼 중요하게 취급하는 단계로 진화.

### 근거 문서 / 코드
- `docs/daily_patch/2026-08-21_q10_q11_q13_measurement_integrity.md`
- `docs/daily_patch/2026-08-21_q14_q18_measurement_integrity.md`

---

## 2026-08-21 · Alpha Research Board — 살아있는 가설/종료 가설을 한 화면에서 관리
**Stage:** Research Governance  
**Tags:** ALPHA · BOARD · RESEARCH

기존 Q와 offline research를 반복하지 않고, 살아있는 discriminator와 폐기된 가설을 하나의 board 계약으로 통합.

### 변경 내용
- OPENING_CONDITIONAL, SCANNER_REACTIVATION_HORIZON, BTC_WOORI, LARGE_CAP_TWO_SYMBOL 4개 fixed research track 정의.
- ACTION_REVIEW, OBSERVE_FIXED, DATA_REPAIR_BOUNDARY, CLOSED_NEGATIVE_PROSPECTIVE, CLOSED bucket 도입.
- 독립 day-symbol/episode를 primary sample count로 고정.
- gross, 0.28% live research net, broker-observed mock net을 분리.
- R1_SCANNER_RISK_HIGH_30M_V1은 contributor dependence로 reject하여 generic HIGH risk discriminator를 폐기.
- Q phase를 새로 만들지 않고 기존 evidence를 board supplier로 재사용.

### 이 변경의 의미
연구가 Q번호만 늘어나는 구조에서 '무엇이 살아 있고 무엇이 폐기됐는가'를 관리하는 포트폴리오형 연구 운영으로 전환.

### 근거 문서 / 코드
- `docs/offline_alpha/alpha_research_board_contract_2026-08-21.md`

---

## 2026-08-21 · Immediate Opening Runtime Validation — 오프닝 Probe의 Runtime Evidence 검증
**Stage:** Research Governance  
**Tags:** OPENING · RUNTIME · VALIDATION

offline에서 정의한 오프닝 조건이 실제 runtime artifact에서 같은 의미로 관찰되는지 검증.

### 변경 내용
- controlled opening probe와 runtime artifact의 필드/시간 정합성 확인.
- missing source는 추정값으로 채우지 않고 missing evidence로 유지.
- promotion이 아니라 measurement path 검증에 초점을 둠.

### 이 변경의 의미
offline research와 실제 runtime 사이의 semantic drift를 줄임.

### 근거 문서 / 코드
- `docs/offline_alpha/immediate_opening_probe_runtime_validation_2026-08-21.md`

---

## 2026-08-27 · Current — 현재 — 7-Agent + Guarded Execution + Evidence Research + Web Observability
**Stage:** Current  
**Tags:** CURRENT · AGENT · ALPHA · WEB_UI

자동주문 스크립트를 넘어 판단·실행·평가·연구·운영 UI가 서로 분리된 포트폴리오급 Agentic Trading System 상태.

### 변경 내용
- Commander/Strategist/Scanner/Monitor/Supervisor/Executor/Reporter 7-Agent 역할 유지.
- 실행은 approval + deterministic guards + idempotency 뒤에서만 허용.
- Q8~Q18, Rank-1, Alpha Research Board를 통해 evidence-driven 개선 루프 운영.
- Samsung/Hynix와 BTC→우리기술투자 같은 독립 baseline/research track 보유.
- Runtime Memory와 Reporter feedback/effectiveness를 통해 장기 개선 영향 분석 가능.
- FastAPI/React Web Observability와 public sanitized profile로 외부 시연 가능.
- 다음 제품화 과제는 patch-note timeline 자체를 UI에 추가하고, 배포 URL/운영 화면을 하나의 showcase로 묶는 것.

### 이 변경의 의미
현재 시스템의 핵심 가치는 'AI가 매매한다'가 아니라 'AI 판단을 안전하게 실행하고, 그 결과를 다시 검증해 다음 정책을 개선하는 폐쇄루프'에 있음.

### 근거 문서 / 코드
- `README.md`
- `docs/01_overview.md`
- `docs/offline_alpha/alpha_research_board_contract_2026-08-21.md`
- `docs/web_observability/implementation_status_2026-08-14.md`

---

## UI 구현 권장 구조

이 상세본은 기본 화면에서 모든 내용을 펼쳐놓기보다 **날짜 + 버전 + 제목 + 1줄 summary**를 먼저 보여주고, 클릭/Expand 시 `변경 내용`, `이 변경의 의미`, `근거 문서`를 펼치는 방식이 적합하다.

권장 필터: `ALL / CORE / AGENT / STRATEGY / LIVE / SAFETY / QUANT / ALPHA / MEMORY / REPORTER / WEB UI / DEPLOYMENT`.

최신 항목에는 `CURRENT` 배지를 표시하고, M/Q/웹 마일스톤은 작은 version chip으로 따로 표시한다. 날짜가 범위인 초기 기록은 범위 그대로 노출하며 임의의 하루로 축약하지 않는다.

### JSON 필드

- `date`: 대표 날짜 또는 날짜 범위
- `version`: M/Q/기능 버전
- `title`: 카드 제목
- `stage`: 프로젝트 단계
- `types`: UI 필터용 태그 배열
- `summary`: 접힌 상태에서 보이는 1줄 요약
- `details`: 펼쳤을 때 보이는 실제 변경 목록
- `impact`: 왜 중요한 변경인지
- `sources`: 저장소 내부 근거 경로
- `status`: historical/current
# 2026-08-28 - Controlled Mock Four-Lane Execution

- Opening Alpha now executes only for `HIGH_COMMON_DIRECTIONAL` or
  `CONFIRMED_RECURRENT_RANK`, using the existing multi-agent selected candidate.
- Q12 BTC-Woori, Q10 Semiconductor and Q10 Index can submit one Kiwoom mock order
  attempt per lane/day through the existing Executor.
- Independent lanes preserve Q9 attribution boundaries and store their own
  strategy/horizon provenance.
- Added lane reservation and opening recurrence artifacts under `data/logs/`.

# 2026-08-28 - Controlled Lane Report Evidence

- Q10/Q12 trade reports show the lane, signal ID, fixed hypothesis evidence,
  score, hold window and mock-only execution scope.
- Closed trades recover the original lane evidence from the position strategy
  frame and daily reservation ledger instead of guessing from the exit cycle.
- Reports show whether R3 horizon revision was allowed for the position.
- Q10/Q12 controlled lanes keep R3 revision disabled so fixed-horizon validation
  remains comparable; normal positions keep the existing R3-to-Monitor path.

# 2026-08-29 - M7.4 Cloudflare Private Ingress

- Added an optional `cloudflared` Compose overlay for `https://agentra.win`.
- The existing Web Nginx is the only origin; API and Trading Runtime ports remain
  private.
- The connector is pinned, non-root, read-only and resource bounded.
- Cloudflare Access must allow only the operator email with OTP before startup.
- Normal local Compose operation does not load or start the Tunnel.

# 2026-08-31 - Q10/Q12 Point-in-Time and Execution Wiring

- Q10 lead-market inputs are frozen at 08:50 before the intraday loop, and Q12
  BTC inputs are captured by a separate 08:55 scheduled task with a daily
  submission ledger.
- Q10/Q12 controlled candidate evaluation now runs before Strategist/Scanner,
  so their early returns cannot suppress an otherwise valid fixed-lane signal.
- Controlled lane evidence is split into evaluation, broker-attempt and
  broker-accepted submission ledgers.
- The daily lane limit is consumed only after broker acceptance or fill. Missing
  input, no candidate and broker rejection remain visible without falsely using
  the daily allowance.
- Added an end-to-end mock integration test from candidate through persisted
  fill state.

# 2026-08-31 - Pre-Claude Refactoring Provenance Baseline

- Fixed the pre-Claude refactoring source baseline at
  `6aa4e398e2e1c33482cab3dbf2518e7b03c18a10`; its recorded verification is
  `2701 passed, 1 skipped`.
- Added an evidence-indexed development history while preserving existing
  historical and patch-note records without reinterpretation or rewriting.
- Marked pre-Git M1-M13 chronology and attribution as inferred, and applied
  `VERIFIED`, `SUPPORTED`, `UNCERTAIN`, and `UNKNOWN` provenance levels.
- Separated Historical Architecture, Target Architecture, and Current AS-IS.
- Described the period from 2026-04-07 as a supported Codex-centered workflow
  without attributing individual commits to Codex when direct evidence is
  absent.
- Recorded current architecture mismatches only as known debt or audit
  findings. No source, runtime, strategy, execution, guard, DTO, test, or
  trading behavior was changed.
- Added the reusable provenance record template and evidence index under
  `docs/development/` for future Claude Code work and Codex cross-review.

# 2026-08-31 - Controlled Lane Observability and Test Integrity

- Confirmed the existing Opening Alpha relaxation and Q10/Q12 point-in-time
  wiring without changing trading policy.
- Added rejected-candidate evidence for Opening Alpha and surfaced Q10, Q12 and
  Opening Alpha status in the operator daily summary.
- Split Q12 intraday shadow evidence from the mandatory 08:55 controlled-lane
  input status so missing snapshots cannot appear generally available.
- Isolated execution tests from the live canonical report tree and identified
  prior `.pytest-work` artifacts for evidence-based cleanup.

# 2026-09-01 - Q12 Capture Rehydration and Trade Report Truth Alignment

- Q12 now rehydrates every baseline payload from the immutable 08:55 capture,
  including processes that were already holding a pre-capture in-memory payload.
- Q12 hypothesis evaluation reads the dedicated captured source instead of a
  newer provider row whose 24-hour momentum is not ready yet.
- Closed-trade summaries derive hold duration from entry/exit execution
  timestamps and keep broker realized PnL authoritative over monitor marks.
- Deterministic, horizon, final conclusion and LLM display sections now use the
  same execution duration and realized result.
- Trading behavior, thresholds, order routing and lane eligibility were not
  changed.

# 2026-09-01 - Opening Alpha Price Integrity

- Open positions are included in every market-quote hydration pass even when
  their symbol falls outside the current Scanner candidate limit.
- Every hydrated quote carries an observation timestamp. A quote older than 90
  seconds is replaced by the current account-position price, or rejected when
  no trustworthy fallback exists.
- Opening Alpha records the first Rank-1 signal price and rejects a delayed
  controlled-probe entry after positive signal-to-entry drift exceeds 2%.
- Immediately before broker submission, Opening Alpha independently compares
  the same initial signal price with the latest available best ask. A drift
  above 2% is recorded as `opening_alpha_execution_price_drift` and exits as
  `NOT_SENT` without calling the broker order API.
- A held-symbol quote older than the expected refresh cadence is cross-checked
  against the account current price when the two sources disagree on whether a
  hard stop has fired. The validated current source wins in either direction;
  a cached quote alone cannot force liquidation.
- Exit artifacts retain quote age, divergence and replacement evidence for
  later report reconstruction.
- Post-exit recap reuses an observed Opening Rank-1 EOD checkpoint when minute
  data cannot reach the regular close, and Alpha Board runtime validation is
  generated directly instead of being lost during canonicalization.
- If the 16:00 Opening Rank-1 closeout refresh cannot reach Kiwoom, it retries
  once in offline/local-artifact mode and records the degraded source instead of
  failing the entire closeout job.
- The 2026-09-01 recap was regenerated with all +5/+15/+30/+60/EOD checkpoints
  observed. No Scanner ranking, Strategist prompt or normal entry/exit threshold
  was changed.
