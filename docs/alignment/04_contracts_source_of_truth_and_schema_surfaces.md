# 04. Contracts, Source of Truth, and Schema Surfaces

## 1. 목적

이 문서는 역할 설명만으로는 부족한 “구조화된 handoff surface”를 정리한다.  
즉 어떤 아티팩트와 DTO가 어떤 계층의 truth인지, 어떤 필드 묶음이 어디서 만들어지고 어디서 소비되는지를 설명한다.

---

## 2. canonical artifact 우선순위

현재 시스템에서 downstream이 정보를 읽을 때 권장되는 우선순위는 아래와 같다.

1. canonical run artifact
2. direct run/trade artifact
3. event log / inferred fallback

이 순서는 매우 중요하다.  
왜냐하면 operator UI나 report가 event log를 직접 뒤지기 시작하면 source-of-truth가 흔들리고, 같은 run을 여러 방식으로 재구성하면서 불일치가 생길 수 있기 때문이다.

---

## 3. canonical run artifact

### 3.1 정의
각 노드가 실행 시점에 직접 기록하는 per-run artifact.

### 3.2 위치
`reports/canonical/<YYYY-MM-DD>/<run_id>/`

### 3.3 대표 파일
- commander.json
- strategist.json
- scanner.json
- monitor.json
- supervisor.json
- executor.json

### 3.4 의미
canonical artifact는 “그 노드가 실제 실행 시점에 어떤 판단/출력을 가졌는가”에 대한 1차 truth다.

---

## 4. 주요 DTO / 계약 surface

## 4.1 Strategist Output / TradePlan 계열
핵심 목적:
- 전략 frame과 하위 정책 surface를 구조화하여 downstream에 전달

대표 필드 축:
- market_regime
- market_sentiment
- key_events
- themes / avoid_themes
- playbook
- scanner_bias / scanner_priority
- trade_aggressiveness
- risk_tone
- monitor_guidance
- strategy_policy
- monitor_policy
- macro_stress_overlay
- recent_strategy_feedback
- report_focus
- candidates / candidate hints
- llm_frame_status / applied / low_confidence / model

핵심 해석:
Strategist output은 단순 자연어 의견이 아니라 Scanner와 Monitor가 실제로 읽는 structured frame이다.

---

## 4.2 Scanner Output / ScanResult 계열
핵심 목적:
- 후보군 정량화와 selected symbol 결정

대표 필드 축:
- ranked / ranked_candidates
- selected
- top_stock
- scanner_candidate_pool
- score / top_score / risk_score / confidence
- candidate_count / candidate_pool_size
- scanner_source_policy
- strategist_playbook
- selected_feature_snapshot
- feature_source
- intraday_change_pct 등 관측 필드

핵심 해석:
selected symbol의 source-of-truth는 Scanner다.  
이후 Monitor는 이 selected symbol을 소비해야지 universe를 다시 고르면 안 된다.

---

## 4.3 OrderIntent
핵심 목적:
- Monitor가 execution 직전 표준 패킷으로 의도를 표현

대표 필드 축:
- intent_id
- symbol / side / type / qty / price / tif
- reason / rationale / signal_source
- position_age_sec
- monitor_reason
- exit_confirm_count
- risk_check_inputs
- optional strategy_policy / summary aliases

핵심 해석:
OrderIntent는 Agent Layer와 Approval Layer를 잇는 가장 중요한 계약이다.

---

## 4.4 Monitor Exit Observability
핵심 목적:
- held position에 대한 exit 판단의 근거 surface 제공

대표 필드 축:
- triggered
- reason
- position_age_seconds
- thresholds.*
- peak_drawdown
- vwap_distance
- trend_strength
- exit_signal_detected
- exit_confirm_ticks / count
- min_hold_blocked
- sell_cooldown_blocked
- emergency_exit

핵심 해석:
이 surface는 장중 디버깅과 장후 trade report 모두에 중요하다.

---

## 4.5 SupervisorDecision
핵심 목적:
- intent에 대한 정책적 승인/거절/수정 결과 표현

대표 필드 축:
- intent_id
- approve / reject / modify
- why
- modifications
- strategy_policy_summary
- supervisor_details

핵심 해석:
승인과 실행은 별개다.  
SupervisorDecision은 execution 계층으로 넘어가기 위한 정책적 판단 결과다.

---

## 5. source-of-truth 표

| 대상 | 현재 source-of-truth |
|---|---|
| run route / selected path | Commander |
| applied policy / provenance | Commander |
| strategy frame / policy proposal | Strategist |
| selected symbol | Scanner |
| entry/exit intent | Monitor |
| approval / reject / modify | Supervisor |
| actual broker execution | Executor |
| post-run interpretation | Reporter |
| per-run node truth | canonical run artifacts |

이 표는 설계와 구현이 흔들릴 때 가장 먼저 다시 확인해야 할 기준이다.

---

## 6. policy 관련 source-of-truth

policy는 가장 혼란스러운 영역이므로 별도로 분리해 적는다.

### 6.1 strategy proposal
Strategist가 만든다.

### 6.2 selected / applied policy
Commander가 확정한다.

### 6.3 policy consumption
Monitor가 소비하고 evidence/trace/summary로 표현한다.

### 6.4 fallback safety
legacy threshold/gate가 유지한다.

즉,
- producer: Strategist
- apply/provenance owner: Commander
- consumer: Monitor
- safety fallback: legacy gate

이 구도가 5-4의 핵심이다.

---

## 7. reporting source-of-truth

현재 reporting 계층은 다음 순서를 기준으로 움직이는 것이 가장 건강하다.

### 7.1 1차
canonical artifact

### 7.2 2차
direct trade/report artifact

### 7.3 3차
event log fallback

그리고 이를 직접 여러 군데서 구현하기보다, 가능하면 reporting read model 같은 단일 읽기 계층을 통해 조립하는 것이 ownership을 덜 흔든다.

---

## 8. Monitor 관점에서 본 현재 contract surface

Monitor는 지금 다음 네 가지를 동시에 다뤄야 한다.

1. selected symbol context
2. selected/applied policy context
3. signal evidence
4. legacy threshold safety

이 네 축이 현재는 모두 필요하다.  
그래서 Monitor는 단순 signal checker가 아니라, policy-aware consumer로 준비된 상태라고 보는 것이 맞다.

---

## 9. 장중 평가 때 가장 먼저 확인할 schema surface

장중 평가에서 schema를 볼 때는 아래 순서가 실용적이다.

### 9.1 commander.json
- route/path
- selected/applied policy provenance

### 9.2 strategist.json
- market frame
- playbook
- policy proposal surface
- llm status

### 9.3 scanner.json
- ranked candidates
- selected symbol
- selected_feature_snapshot

### 9.4 monitor.json
- signal evidence
- policy interpretation / trace / summary
- entry/exit observability
- intent 여부

### 9.5 supervisor.json / executor.json
- approval / block / execution 여부

이 순서를 따르면 “왜 안 샀나 / 왜 막혔나 / 왜 실행 안 됐나”를 빠르게 쪼갤 수 있다.
