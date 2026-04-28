# AI Trade Report LLM Input + Output Example (2026-04-19)

## 목적
이 문서는 `ai_trade_report` LLM이 현재 어떤 역할을 하고, 어떤 입력을 받고, 어떤 출력 계약을 따르는지 사람이 바로 볼 수 있게 정리한 예시다.

기준:
- 실제 trade artifact:
  - `reports/trades/2026-04-17/TRD_20260417_000660_01/ai_trade_report_input.json`
  - `reports/trades/2026-04-17/TRD_20260417_000660_01/reports/ai_trade_report.json`
  - `reports/trades/2026-04-17/TRD_20260417_000660_01/reports/ai_trade_report_llm_response.json`
- 실제 LLM run id:
  - `32adb3d3856f4916828426d6f8227107`
- 코드 기준 최신 경로:
  - `libs/reporting/trade_report_ai.py`
  - `libs/reporting/trade_read_model.py`
  - `libs/reporting/trade_story_pipeline.py`

주의:
- `reports/llm/2026-04-17/32adb3d3856f4916828426d6f8227107/ai_trade_report/prompt.json`은 구형 저장 형식이라 `system_prompt`, `user_prompt`가 비어 있다.
- 따라서 프롬프트 본문은 현재 코드 기준 `libs/reporting/trade_report_ai.py:_build_messages(...)`를 기준으로 적는다.
- 실제 입력 payload 예시는 `ai_trade_report_input.json` 기준으로 적는다.

## 1. 레포트 LLM 역할
현재 레포트 LLM의 역할은 이거다.

1. deterministic trade report skeleton 위에 retrospective narrative를 채운다
2. strategist -> scanner -> monitor -> supervisor -> executor -> reporter 흐름을 운영자용 문장으로 정리한다
3. 숫자/증거/provenance를 유지한 채 post-trade 설명을 만든다

즉 레포트 LLM은:
- 새 판단을 내리는 agent가 아니다
- scanner나 monitor를 대체하지 않는다
- trade lifecycle을 설명하는 post-trade narrator다

핵심은:
- facts owner: `libs/reporting/trade_read_model.py`
- section seed producer: `libs/reporting/trade_story_pipeline.py`
- narrative adapter / LLM caller: `libs/reporting/trade_report_ai.py`

2026-04-25 update:
- Batch regeneration is deterministic by default and does not call the report LLM.
- Live closed-trade first-write still calls the report LLM through `run_live_execution_bundle_report.py --trade-report-ai`.
- Use `scripts/run_ai_trade_report_batch.py --with-llm` only when the optional operator-facing retrospective narrative is needed.
- The LLM output is not a memory source. Future memory must come from deterministic artifacts and explicit memory/application traces.
- The reporter must consume structured strategist output directly and must not reconstruct a different strategist rationale.
- `strategist_output` is now passed into the report LLM compact input with `strategy_thesis`, `memory_usage_trace`, `news_usage_trace`, `scanner_handoff`, and `monitor_handoff`.
- The report LLM must not say the strategist selected the final symbol. Scanner ranking/selection evidence owns `why_this_symbol_was_chosen`.
- Memory reporting is phase-separated. The report must distinguish strategist-input memory policy, scanner memory application, monitor memory application, and latest commander memory state.

## 2. 호출 경로
live trade-report 기준 호출 경로는 다음과 같다.

1. `graphs/nodes/reporter_node.py`
2. `libs/reporting/intraday_trade_reports.py`
3. `libs/reporting/live_execution_bundle_runner.py`
4. `libs/reporting/trade_story_pipeline.py`
5. `libs/reporting/trade_report_ai.py`
6. LLM router 호출
7. `reports/ai_trade_report.json`, `reports/ai_trade_report.md` 저장

즉 레포트 LLM 본체는 `trade_report_ai.py`다.

## 3. 현재 prompt builder
실제 prompt builder는 `libs/reporting/trade_report_ai.py:_build_messages(story_input)`다.

### system prompt 요지
현재 system prompt는 아래 요구를 강하게 건다.

- trade lifecycle retrospective만 작성
- 숫자, 이벤트, 이유, evidence를 지어내지 말 것
- JSON object 하나만 반환
- markdown, 분석문, 계획문 금지
- 모든 human-readable 문장은 한국어
- 종목 코드, BUY/SELL/HOLD/WAIT, VIX 같은 토큰은 그대로 유지 가능

### user prompt 요지
현재 user prompt는 아래를 강제한다.

- strategist -> scanner -> monitor -> supervisor -> executor -> reporter 순서 유지
- "왜 진입했는가 / 왜 보유했는가 / 왜 청산했는가 / 실행 품질이 어땠는가 / 다음엔 뭘 개선할 것인가"에 답할 것
- market context, strategist evidence, scanner ranking, runner-up, monitor thresholds, exit trigger를 직접 반영할 것
- deterministic skeleton을 덮어쓰지 말고 section narrative만 채울 것

## 4. 실제 입력 payload 구조
실제 입력 artifact는:
- `reports/trades/2026-04-17/TRD_20260417_000660_01/ai_trade_report_input.json`

레포트 LLM 입력은 이 `story_input`에서 compact/sparse payload로 축약된다.

### 최상위 입력 섹션
현재 compact input은 대략 아래 구조다.

```json
{
  "trade_id": "TRD_20260417_000660_01",
  "story_id": "TRD_20260417_000660_01",
  "run_id": "32adb3d3856f4916828426d6f8227107",
  "symbol": "000660",
  "action": "SELL",
  "status": "closed",
  "story_type": "simulation",
  "execution_mode_label": "simulation (mock broker)",
  "strategist_output": {
    "strategy_thesis": {...},
    "strategy_delta_trace": {...},
    "memory_usage_trace": {...},
    "news_usage_trace": {...},
    "scanner_handoff": {...},
    "monitor_handoff": {...},
    "responsibility_boundary": {...},
    "direct_consumption_rule": "Use these strategist fields as the strategist rationale. Do not infer final symbol selection from strategist output."
  },
  "entry_summary": {...},
  "holding_summary": {...},
  "exit_summary": {...},
  "lifecycle_summary": {...},
  "market_context_human": {...},
  "commander": {...},
  "scanner_reason_human": {...},
  "filters_human": {...},
  "monitor_reason_human": {...},
  "guard_reason_human": {...},
  "execution_outcome_human": {...},
  "reporter_status_human": {...},
  "operator_conclusion_human": {...},
  "timeline": [...],
  "warnings": [...],
  "improvement_points": [...],
  "strategist_evidence": {...},
  "scanner_selection_trace": {...},
  "monitor_stop_policy_trace": {...},
  "monitor_blocker_trace": {...},
  "evidence_digest": {...},
  "ai_report_diagnostics": {...}
}
```

### 실제 4/17 입력에서 중요한 값
`TRD_20260417_000660_01` 기준으로 실제 입력 특징은 이렇다.

1. 시장/전략가
- `playbook = defensive`
- `market_regime = neutral`
- `global_sentiment_score = 0.0173`
- `vix_level = 17.94`

2. scanner
- `selected_symbol = 000660`
- `selected_rank = 1`
- `universe_size = 5`
- `score_total = 1.284`
- `top_candidates`와 `runner_ups`가 같이 있음
- `news_scanner_contribution`, `selected_symbol_score_drivers`가 있음

3. monitor
- `trigger_type = intraday_low_break`
- `hard_stop_pct = 0.03`
- `effective_stop_loss_pct = 0.03`
- `trailing_stop_pct = 0.032896`
- `take_profit_pct = 0.013067`
- `active_exit_axis = Intraday Low Break`

4. execution / reporter
- `execution_outcome_human.summary` 존재
- `reporter_status_human.summary = same-day reporter analysis 미생성`
- `operator_conclusion_human` 존재

## 5. canonical section seed가 어디서 쓰이나
지금 레포트 LLM은 raw `*_human` 블록만 보지 않는다.

현재 canonical seed chain:

1. `trade_story_pipeline.py`
- `report_section_seeds` 생산

2. `trade_read_model.py`
- `context.report_section_seeds`로 canonicalized

3. `trade_report_ai.py`
- runtime human block이 비거나 약하면 seed를 우선 사용

현재 canonical section seed 범위:
- `market_context_at_entry`
- `strategist_summary`
- `why_this_symbol_was_chosen`
- `entry_decision`
- `holding_monitoring_story`
- `exit_decision`
- `scanner_filters`
- `execution_quality`
- `guard_approval_result`
- `reporter_evaluation`
- `final_operator_conclusion`

즉 레포트 LLM은 이제 단순 raw story-input narrator가 아니라, canonical section seed consumer다.

## 6. 출력 contract
현재 필수 output key는 `libs/reporting/trade_report_ai.py:AI_TRADE_REPORT_REQUIRED_KEYS` 기준으로 아래 12개다.

```json
{
  "executive_summary": {...},
  "market_context_at_entry": {...},
  "why_this_symbol_was_chosen": {...},
  "entry_decision": {...},
  "holding_monitoring_story": {...},
  "exit_decision": {...},
  "execution_quality": {...},
  "scanner_filters": {...},
  "guard_approval_result": {...},
  "reporter_evaluation": {...},
  "errors_weaknesses_improvement_points": {...},
  "final_operator_conclusion": {...}
}
```

실제 저장 output에는 위 필수 섹션 외에도:
- `strategist_summary`
- `full_timeline`
- `generation`
- `shared_facts`
- aliases
가 붙는다.

## 7. 실제 출력 예시
실제 output artifact:
- `reports/trades/2026-04-17/TRD_20260417_000660_01/reports/ai_trade_report.json`

실제 LLM response artifact:
- `reports/trades/2026-04-17/TRD_20260417_000660_01/reports/ai_trade_report_llm_response.json`

### 실제 출력이 보여주는 것
1. `executive_summary`
- 진입가 / 청산가 / 보유시간 / 종료 이유를 operator-facing 문장으로 요약

2. `market_context_at_entry`
- regime, sentiment, VIX, key events, strategist linkage를 요약

3. `why_this_symbol_was_chosen`
- 후보 비교, score gap, confidence, source mix, chart coverage를 정리

4. `holding_monitoring_story`
- effective stop, trailing stop, drawdown, active exit axis를 정리

5. `exit_decision`
- 실제 trigger type과 exit axis를 정리

6. `reporter_evaluation`
- same-day reporter linkage 부재 같은 후속 품질 상태를 정리

## 8. 현재 LLM 재시도/복구
실제 `ai_trade_report_llm_response.json`를 보면:
- `attempts.primary = partial`
- `attempts.retry_1 = partial`
- `attempts.retry_2 = ok`

즉 현재 레포트 LLM은:
1. JSON 파싱
2. required keys 확인
3. 한국어 강제 검사
4. repair/retry
를 거친다.

이건 현재 단계에서 맞는 방어선이다.

## 9. 지금 단계에서 레포트 LLM 확장이 필요한가
내 판단은 **아직 아니다.**

이유:
1. 지금 본선은 LLM 추가가 아니라 canonicalization이다
- `trade_story_pipeline.py`
- `trade_read_model.py`
- `trade_report_ai.py`
를 더 일관되게 맞추는 쪽이 우선이다

2. scanner LLM / monitor LLM 같은 추가 lane은 지금 불필요하다
- scanner는 deterministic ranking이 owner
- monitor는 deterministic executor가 owner

3. 레포트 LLM은 이미 역할이 충분히 넓다
- 시장 설명
- 전략가 요약
- 후보 비교
- 보유/청산 설명
- 실행 품질
- 회고 포인트

즉 지금은 LLM을 더 늘릴 때가 아니라,
**현재 레포트 LLM이 canonical seed를 더 안정적으로 소비하도록 다듬는 단계**다.

## 10. 한 줄 정리
- strategist LLM = 사전 전략 프레임
- report LLM = 사후 trade lifecycle retrospective narrator

현재 report LLM은:
- 새 판단을 하는 agent가 아니라
- `trade_read_model`과 canonical section seed를 받아
- 운영자용 retrospective report를 만드는 adapter다.


## 2026-04-20 Update: Execution Truth Visibility
- `ai_trade_report.md` execution section now explicitly surfaces broker execution truth when available.
- Operator-facing execution visibility now distinguishes:
  - broker fill price
  - broker realized pnl / pnl%
  - broker fee / tax
  - price truth source
  - pnl truth source
- This is additive to `shared_facts`; execution truth is no longer only implicit in JSON facts.


## 2026-04-20 Update: truth_surface
- `ai_trade_report.json` now includes top-level `truth_surface`.
- `truth_surface` is a compact operator-facing view derived from `shared_facts`, not a second truth calculator.
- It groups:
  - `status`
  - `price`
  - `pnl`
  - `availability`
- This makes broker/account/monitor truth easier to inspect without traversing the full `shared_facts` object.

## 2026-04-20 Update: Markdown Truth Surface
- `ai_trade_report.md` now surfaces `truth_surface` near the top of the report.
- Operators can inspect:
  - broker fill price
  - account mark price
  - monitor mark price
  - realized pnl / pnl%
  - fee / tax
  - price truth source
  - pnl truth source
  - truth availability flags
- This reduces the need to drill into `shared_facts` or only rely on the execution section for factual verification.

## 2026-04-21 Validation Update

- Stored `ai_trade_report.json` / `ai_trade_report.md` now render buy/sell broker prices directly when entry-side execution truth is available.
- Verified trade:
  - `reports/trades/2026-04-21/TRD_20260421_005380_01/reports/ai_trade_report.md`
- `Truth Surface` now surfaces:
  - broker buy / sell price pair
  - broker realized pnl / pnl%
  - broker fee / tax
  - broker day match mode / authority state
- Cascade fallback trades are also re-anchored to the actual traded symbol instead of scanner top1.

## 2026-04-27 Update: Memory Application Phase Split

- `ai_trade_report.md` now renders the deterministic memory application section as four separate phase lines:
  - strategist input phase
  - scanner application phase
  - monitor application phase
  - latest commander state
- This prevents a common misread where strategist prompt `active_layers=[]` and later monitor `entry/exit applied=true` appear contradictory.
- The renderer prefers an applied nested `commander_memory_application_trace` when a canonical monitor artifact contains both early disabled traces and later applied traces.
- The LLM may summarize this section, but it must not merge phase-specific facts into a single memory state.
- Representative validation:
  - `reports/trades/2026-04-27/TRD_20260427_005930_05`
  - scanner memory application remained disabled at scanner phase
  - monitor memory application later used `symbol` layer for entry/exit policy adjustment
