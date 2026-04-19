# Strategist Input + Prompt Example (2026-04-17)

## 목적
이 문서는 전략가(Strategist) LLM이 실제로 어떤 입력을 받고 어떤 프롬프트로 호출되는지, 그리고 repeated-hold refresh 시점에 어떤 컨텍스트가 추가되는지를 사람이 읽기 쉽게 정리한 예시다.

기준:
- 실제 artifact 기준 run: `1e9e8274eddf40a3962640294e65dc78` (2026-04-17 09:53:52 KST 부근 refresh 케이스)
- 코드 기준 최신 prompt/input 경로:
  - `graphs/nodes/strategist_node.py`
  - `graphs/commander_runtime.py`

주의:
- 위 run artifact는 hold-refresh context 패치 전 artifact다.
- 이후 2026-04-17 추가 패치로 아래 3가지가 더 반영됐다.
  1. prompt가 `read_model_facts`와 failure adaptation을 더 강하게 강제
  2. repeated-hold refresh context가 strategist LLM payload에 직접 포함
  3. strategist output에 `policy_adjustment` surface가 추가
- 따라서 아래 문서는
  1. 당시 실제 입력/프롬프트
  2. 현재 코드 기준으로 추가된 refresh 입력
  3. 현재 코드 기준으로 추가된 adjustment surface
  를 분리해서 설명한다.

## 1. 호출 경로
live intraday 기준 strategist 호출 경로는 다음과 같다.

1. `scripts/run_session.py`
2. `scripts/run_m13_live_loop.py`
3. `graphs/commander_runtime.py`
4. `graphs/nodes/strategist_node.py`
5. strategist LLM router 호출
6. 결과를 `commander_applied_policy`로 정리 후 `monitor_node`에 전달

즉 전략가 프롬프트 본체는 `graphs/nodes/strategist_node.py`에서 만들어진다.

## 2. 실제 프롬프트 구성 코드
실제 prompt builder는 `graphs/nodes/strategist_node.py`의 `_build_strategist_llm_messages(payload)`다.

### system prompt
```text
You are the Strategist agent for an automated trading system.
You must output a strategic frame only.
Do not select final stock and do not produce order instructions.
You MUST use the strictly deterministic 'read_model_facts' as a primary constraint.
You MUST NOT ignore or lightly reference it. Strategy must be explicitly adjusted based on it.
Your role is to select ONE playbook, define a clear rationale, and produce a monitor_entry_policy that meaningfully influences downstream behavior.
Return exactly one minified JSON object only.
Do not add analysis, markdown, bullet points, or any text before or after the JSON.
The first character must be { and the last character must be }.
Policy must be realistic, bounded, and actionable.
Policy must include explicit conditions or thresholds, not vague language.
If adjustment_required is true, at least one explicit field in monitor_entry_policy must differ from monitor_entry_policy_baseline or current_monitor_entry_policy_summary.
If adjustment is not justified, explicitly keep conservative baseline.
You MUST analyze dominant failure patterns from read_model_facts.
If a failure reason is dominant, you MUST adjust policy to address it.
If recent behavior shows excessive NOOP or missed entries, you MUST slightly relax entry conditions within safe bounds.
If recent behavior shows overtrading or false entries, you MUST tighten conditions.
If confidence is low, default to conservative baseline.
Do not hallucinate confidence; infer it from consistency of signals and read_model_facts.
You are not allowed to produce passive or generic strategy.
You must produce a decision that has clear downstream impact.
```

### user prompt skeleton
```text
Use the provided market context, news/global sentiment, and candidate hints.
You MUST incorporate 'read_model_facts' (recent trades and symbol patterns) as a primary driver of strategy adjustment, not as optional context.
Prioritize resolving repeated failure patterns over maintaining static strategy.
Favor preferred playbooks and avoid discouraged playbooks.
Adapt to current market regime (trend/range/volatility), but do not overfit noise.
monitor_entry_policy must directly influence Monitor behavior.
Avoid vague expressions such as 'slightly', 'moderate', or 'careful'.
Use explicit conditions, thresholds, or structural constraints.
Keep policy bounded and safe with no aggressive loosening.
If repeated NOOP or missed opportunities dominate, relax entry constraints within safe bounds.
If repeated failed entries or drawdowns dominate, tighten conditions.
If mixed signals dominate, keep conservative baseline.
When commander_refresh_context.requested is true, prioritize hold-refresh evidence over generic candidate hints when adjusting monitor_entry_policy.
Choose exactly ONE playbook, provide a short but concrete rationale, and provide a monitor_entry_policy that is implementable and specific.
Reply with JSON only. No prose.

JSON contract:
{...contract...}

Input:
{...payload...}
```

### output contract 핵심
전략가는 대략 아래 구조를 반환해야 한다.

```json
{
  "playbook": "breakout|pullback|reversal|defensive",
  "rationale": "string",
  "monitor_entry_policy": {
    "timeframe_minutes": 1,
    "breakout_lookback": 5,
    "volume_lookback": 5,
    "volume_ratio_min": 0.68,
    "min_extended_from_vwap_pct": -0.02,
    "max_extended_from_vwap_pct": 0.13,
    "pullback_min_pct": 0.008,
    "pullback_max_pct": 0.07,
    "reclaim_tolerance_pct": 0.0015,
    "breakout_buffer_pct": 0.0,
    "intent_cooldown_sec": 60,
    "require_vwap_reclaim": true,
    "require_rebound": true
  },
  "strategy_adjustment_directives": {
    "playbook_action": {
      "action": "maintain|prefer|deprioritize|switch",
      "target": "string|null",
      "reason": "string"
    },
    "entry_policy_action": {
      "action": "maintain|tighten|relax|rebalance",
      "target_fields": ["string"],
      "reason": "string"
    },
    "monitor_focus_action": {
      "action": "maintain|increase_focus|decrease_focus|shift_focus",
      "target_axes": ["reclaim", "pullback", "volume", "breakout", "extension", "exit_axis"],
      "reason": "string"
    },
    "selected_symbol_bias_action": {
      "action": "none|prefer_pullback|avoid_breakout|prefer_reclaim|avoid_extension",
      "reason": "string"
    },
    "refresh_action": {
      "action": "none|refresh_for_holding|refresh_for_repeated_hold|refresh_for_exit_axis_mismatch",
      "reason": "string"
    }
  }
}
```

현재 코드에서는 기존 surface도 그대로 유지된다.
즉 실제 strategist output에는 여전히 아래가 같이 있다.

- `market_regime`
- `market_sentiment`
- `themes`
- `avoid_themes`
- `scanner_bias`
- `scanner_priority`
- `trade_aggressiveness`
- `risk_tone`
- `monitor_guidance`
- `market_regime_summary`
- `policy_rationale`
- `confidence`
- `policy_source`
- `policy_adjustment`
- `report_focus`

이번 변경의 핵심은 기존 필드를 없애는 것이 아니라, `strategy_adjustment_directives`를 additive로 추가해서 memory packet을 행동 지시 surface로 바꾸는 것이다.

## 3. 실제 strategist 입력 payload 예시
실제 artifact:
- `reports/llm/2026-04-17/1e9e8274eddf40a3962640294e65dc78/strategist/prompt.json`
- `reports/llm/2026-04-17/1e9e8274eddf40a3962640294e65dc78/strategist/meta.json`

### payload 최상위 섹션
실제 strategist 입력은 아래 섹션들로 구성된다.

```json
{
  "global_sentiment_signal": {...},
  "news_context": {...},
  "market_context_inputs": {...},
  "recent_strategy_feedback": {...},
  "reporter_feedback_packet": {...},
  "strategy_memory": {...},
  "macro_stress_overlay_hint": {...},
  "market_regime_hint": "neutral",
  "market_sentiment_hint": "neutral",
  "commander_refresh_context": {...},
  "read_model_facts": {...},
  "market_structure_hint": "range",
  "playbook_hint": "defensive",
  "monitor_entry_policy_baseline": {...},
  "themes_hint": ["broad_market_leaders"],
  "news_query_targets": [...],
  "market_news_sample": {...},
  "candidate_news_sample": {...},
  "candidate_symbols_hint": [...],
  "key_events_hint": [...],
  "recent_monitor_blockers_hint": [...]
}
```

### 당시 실제 값에서 읽히는 핵심
run `1e9e8274eddf40a3962640294e65dc78` 기준 실제 입력 특징은 아래였다.

1. 글로벌/매크로
- `global_sentiment_signal.score = 0.0174`
- `vix_level = 17.94`
- `market_regime_hint = neutral`
- `market_sentiment_hint = neutral`
- `market_structure_hint = range`

2. 뉴스/테마
- `news_context.headline_count = 60`
- `candidate_signal_total = 5`
- `market_signal_total = 7`
- `themes_hint = ["broad_market_leaders"]`

3. 최근 피드백
- `recent_strategy_feedback.top_recent_weaknesses`에
  - overtrading risk
  - rapid buy/sell cycles
  - scanner summary 부족
  이 들어가 있었다.

4. baseline 정책 힌트
- `monitor_entry_policy_baseline`은 당시 conservative/defensive baseline이었다.
- 예:
  - `volume_ratio_min = 0.68`
  - `max_extended_from_vwap_pct = 0.13`
  - `pullback_min_pct = 0.008`
  - `pullback_max_pct = 0.07`
  - `intent_cooldown_sec = 60`

즉 strategist는 완전 빈 상태에서 새 정책을 만드는 게 아니라, 기존 baseline과 최근 feedback, 뉴스, read-model facts를 같이 보고 조정한다.

## 4. 당시 실제 repeated-hold refresh artifact가 보여주는 한계
위 run은 repeated-hold refresh 케이스였지만, artifact 기준 strategist 입력에는 hold-side refresh context가 충분히 직접 노출되지 않았다.

당시 strategist artifact에서 보이는 commander refresh 정보는 대체로 아래 수준이었다.

```json
{
  "commander_refresh_requested": false,
  "commander_refresh_reason": "open_positions_present",
  "commander_refresh_context": {
    "open_position_count": 1,
    "selected_symbol": "",
    "cached_candidate_hints": ["000660", "009150", "005930", "047040", "005380"],
    "current_market_regime": "neutral",
    "cached_market_regime": "neutral",
    "cache_age_sec": 860,
    "reason": "open_positions_present"
  }
}
```

이건 repeated-hold refresh를 설명하기엔 부족했다.
즉:
- 어떤 종목이 문제였는지
- hold가 몇 번 반복됐는지
- 현재 blocking axis가 뭔지
- entry blocker가 뭔지
가 strategist 입력에 직접 약했다.

## 5. 현재 코드 기준으로 추가된 repeated-hold refresh 입력
이후 패치로 `graphs/commander_runtime.py`와 `graphs/nodes/strategist_node.py`가 보강되었다.

### commander 쪽에서 만드는 refresh context
`graphs/commander_runtime.py::_build_open_position_strategist_refresh_context(...)`

현재 repeated-hold refresh가 걸리면 아래 같은 컨텍스트가 만들어진다.

```json
{
  "refresh_scope": "open_position_monitor_refresh",
  "refresh_summary": "Repeated hold refresh for 000660 after 3 consecutive hold cycles. Current blocking axis is reclaim_readiness. Primary blockers: below_vwap_reclaim_not_ready.",
  "selected_symbol": "000660",
  "open_position_count": 1,
  "hold_repeat_count_max": 3,
  "selected_hold_repeat_count": 3,
  "selected_effective_loss_ratio": -0.004,
  "effective_loss_ratio_min": -0.004,
  "price_anomaly_flag": false,
  "monitor_posture": "hold",
  "monitor_reason": "too_extended_from_vwap",
  "active_exit_axis": "peak_drawdown",
  "position_qty": 3,
  "position_age_seconds": 540,
  "entry_state": {
    "current_blocking_axis": "reclaim_readiness",
    "transition_readiness_score": 0.74,
    "entry_blockers": ["below_vwap_reclaim_not_ready"]
  },
  "reason_chain": ["...override reasons..."]
}
```

### strategist 쪽에서 실제로 surface 되는 위치
`graphs/nodes/strategist_node.py`가 아래 3곳에 이 컨텍스트를 싣는다.

1. `commander_context_summary`
- `strategist_refresh_context`
- `open_position_refresh_context`

2. `strategic_answers.q15_commander_refresh_context`
- `requested`
- `reason`
- `refresh_scope`
- `selected_symbol`
- `hold_repeat_count_max`
- `selected_hold_repeat_count`
- `monitor_reason`
- `active_exit_axis`
- `refresh_summary`
- `entry_state`
- `prior_monitor_entry_policy_summary`
- `current_monitor_entry_policy_summary`

3. `strategist_output`
- `commander_context_ref.open_position_refresh_context`
- `commander_open_position_refresh_context`

### 현재 strategist가 보게 되는 refresh 입력 예시
현재 코드 기준 repeated-hold refresh strategist 입력은 대략 이렇게 읽으면 된다.

```json
{
  "q15_commander_refresh_context": {
    "requested": true,
    "reason": "repeated_hold_monitor_only",
    "refresh_scope": "open_position_monitor_refresh",
    "selected_symbol": "000660",
    "hold_repeat_count_max": 3,
    "selected_hold_repeat_count": 3,
    "monitor_reason": "too_extended_from_vwap",
    "active_exit_axis": "peak_drawdown",
    "refresh_summary": "Repeated hold refresh for 000660 after 3 consecutive hold cycles...",
    "entry_state": {
      "current_blocking_axis": "reclaim_readiness",
      "transition_readiness_score": 0.74,
      "entry_blockers": ["below_vwap_reclaim_not_ready"]
    },
    "prior_monitor_entry_policy_summary": {
      "volume_ratio_min": 0.68,
      "max_extended_from_vwap_pct": 0.13,
      "pullback_min_pct": 0.008,
      "pullback_max_pct": 0.07,
      "intent_cooldown_sec": 60
    },
    "current_monitor_entry_policy_summary": {
      "volume_ratio_min": 0.68,
      "max_extended_from_vwap_pct": 0.13,
      "pullback_min_pct": 0.008,
      "pullback_max_pct": 0.07,
      "intent_cooldown_sec": 60
    }
  }
}
```

이제 이 정보는 artifact surface뿐 아니라 strategist LLM payload에도 직접 포함된다.

이게 핵심이다.
이제 repeated-hold refresh는 단순히 “포지션 있음” 수준이 아니라, 실제 hold-side blocker와 baseline 비교까지 strategist 입력에 들어간다.

## 6. strategist에 들어가는 report artifact는 무엇인가
전략가는 report artifact를 전문 텍스트로 읽지 않는다.

현재 구조는 아래처럼 **압축된 packet**만 strategist 입력으로 넣는다.

### 6-1. trade-level artifact -> `read_model_facts`
source:
- `reports/trades/<day>/<trade_id>/...`
- canonical reader: `libs/reporting/trade_read_model.py`

strategist 입력 위치:
- `read_model_facts`

역할:
- 최근 trade facts
- symbol별 pattern
- dominant failure pattern
- recent success pattern
- symbol read-model excerpt

즉 trade report artifact 원문이 아니라, `trade_read_model -> read_model_facts`로 정규화한 deterministic 사실만 넣는다.

### 6-2. recent strategy feedback -> `recent_strategy_feedback`
source:
- 최근 trade-story / report 결과를 rolling feedback으로 압축
- builder: `graphs/nodes/strategist_node.py:_load_recent_strategy_feedback(...)`

strategist 입력 위치:
- `recent_strategy_feedback`

실제 포함:
- `top_recent_strengths`
- `top_recent_weaknesses`
- `recent_reporter_summary`
- `recent_monitor_issues`
- `suggested_report_focus`

역할:
- 최근 몇 런/몇 trade에서 어떤 문제가 반복됐는지 broad advisory를 준다.

### 6-3. reporter feedback packet -> `reporter_feedback_packet`
source:
- builder: `libs/reporting/reporter_feedback.py`
- source material:
  - `reports/metrics/...`
  - 현재 payload mode
  - route analysis / reporter advisory

strategist 입력 위치:
- `reporter_feedback_packet`

실제 포함:
- `available`
- `status`
- `insight_summary`
- `recommendation`
- `route_analysis`
- `dominant_patterns`
- `feedback_gate_reason`

역할:
- deterministic report-side 운영 피드백을 strategist에 advisory packet으로 넣는다.
- 현재는 보조 advisory 축이다.

### 6-4. market memory packet -> `strategy_memory`
source:
- canonical path:
  - `reports/performance/<day>/strategy_memory.json`
- builder:
  - `libs/performance/strategy_memory.py`

strategist 입력 위치:
- `strategy_memory`

실제 포함:
- `best_playbooks`
- `worst_playbooks`
- `recent_failures`
- `recent_success_patterns`
- `playbook_performance_snapshot`
- `reporter_analysis_digest`

여기서 `reporter_analysis_digest`는 다시 아래 artifact를 압축한 것이다.
- `reports/dev/analysis/reporter_analysis/reporter_analysis_<day>.json`

즉 strategist는 daily reporter analysis 본문 전체를 읽는 것이 아니라, `strategy_memory.reporter_analysis_digest`로 압축된 broad memory만 받는다.

### 6-5. long-hold / selected-symbol report-side memory
source:
- `read_model_facts.symbol_patterns`
- `reports/symbols/<SYMBOL>/symbol_memory.json`
- `commander_refresh_context`

strategist 입력 위치:
- `commander_refresh_context.selected_symbol_memory`
- `q15_commander_refresh_context.selected_symbol_memory`

역할:
- selected symbol의 누적 성향
- repeated failure pattern
- dominant playbook / blocker
- long-hold refresh 시 symbol-specific tuning 근거

### 6-6. 지금 strategist에 직접 넣지 않는 것
현재는 아래를 strategist에 전문 그대로 넣지 않는다.

- `ai_trade_report.md`
- `ai_trade_report.json`
- `operator_brief.md/json`
- `trade_explain` 본문
- `decision_story`
- `run_cards`

이유:
- 토큰 대비 효용이 낮고
- post-trade narrator 문체가 strategist broad planning에 그대로 맞지 않고
- deterministic contract로 압축하는 편이 더 안정적이기 때문이다.

### 6-7. 현재 합의된 정리 방향
1. strategist가 직접 읽는 report artifact는 문서가 아니라 packet이다.
2. broad market memory는 `strategy_memory`로 넣는다.
3. trade-level memory는 `read_model_facts`로 넣는다.
4. reporter analysis는 직접 넣지 않고 `reporter_analysis_digest`로 넣는다.
5. symbol-level / long-hold는 `selected_symbol_memory`와 `commander_refresh_context`로 넣는다.

한 줄로 정리하면:
- strategist는 report artifact를 **그대로 읽는 게 아니라**
- `read_model_facts`, `recent_strategy_feedback`, `reporter_feedback_packet`, `strategy_memory`, `selected_symbol_memory`로 압축해서 받는다.

## 7. strategist 출력은 어떻게 monitor로 연결되나
전략가가 반환한 핵심 출력은 `strategist.json`에 남고, 그 중 monitor와 직접 연결되는 것은 `monitor_entry_policy`다.

예:
```json
{
  "monitor_entry_policy": {
    "breakout_lookback": 5,
    "volume_ratio_min": 0.75,
    "min_extended_from_vwap_pct": -0.01,
    "max_extended_from_vwap_pct": 0.08,
    "pullback_min_pct": 0.01,
    "pullback_max_pct": 0.05,
    "reclaim_tolerance_pct": 0.002,
    "intent_cooldown_sec": 90,
    "require_vwap_reclaim": true,
    "require_rebound": true
  }
}
```

이 값은 commander가 `applied_policy`로 정리한 뒤 monitor가 `received_policy`로 받는다.
즉 repeated-hold refresh에서 봐야 하는 건 아래 3단계다.

1. strategist 입력에 hold-side refresh context가 제대로 들어갔는가
2. strategist 출력 `monitor_entry_policy`가 실제로 바뀌었는가
3. monitor `received_policy`와 `effective_policy`에 그 변화가 반영됐는가

### 현재 추가된 adjustment surface
지금 코드 기준 strategist output에는 아래 surface가 같이 남는다.

```json
{
  "policy_adjustment": {
    "adjustment_required": true,
    "baseline_retained": false,
    "baseline_retained_reason": "",
    "adjustment_direction": "tighten",
    "dominant_failure_pattern": "repeated_hold_monitor_only",
    "addressed_failure_patterns": ["below_vwap_reclaim_not_ready"],
    "delta_fields": ["volume_ratio_min", "pullback_max_pct"],
    "delta_count": 2,
    "hold_refresh_considered": true,
    "baseline_summary": {
      "volume_ratio_min": 0.68,
      "pullback_max_pct": 0.07
    },
    "current_summary": {
      "volume_ratio_min": 0.75,
      "pullback_max_pct": 0.05
    }
  }
}
```

이 필드는 “실제로 전략가가 baseline 대비 뭘 바꿨는가”를 읽기 위한 용도다.

### 현재 추가된 directive surface
이제 strategist output에는 아래 행동 지시 surface도 같이 남는다.

```json
{
  "strategy_adjustment_directives": {
    "playbook_action": {
      "action": "deprioritize",
      "target": "breakout",
      "reason": "최근 메모리에서 breakout 성과가 약해 우선순위를 낮춥니다"
    },
    "entry_policy_action": {
      "action": "tighten",
      "target_fields": ["volume_ratio_min", "pullback_max_pct"],
      "reason": "반복 실패 패턴이 진입 품질 저하로 이어져 조건을 조입니다"
    },
    "monitor_focus_action": {
      "action": "increase_focus",
      "target_axes": ["reclaim", "volume"],
      "reason": "반복 blocker가 reclaim과 volume 축에 집중돼 해당 확인을 강화합니다"
    },
    "selected_symbol_bias_action": {
      "action": "prefer_reclaim",
      "reason": "종목 메모리에서 reclaim 미확인이 반복돼 reclaim 확인을 우선합니다"
    },
    "refresh_action": {
      "action": "refresh_for_repeated_hold",
      "reason": "반복 hold가 누적돼 보유 프레임 재평가가 필요합니다"
    }
  }
}
```

이 필드는 `policy_adjustment`와 역할이 다르다.

- `policy_adjustment`
  - baseline 대비 실제 policy delta를 설명
- `strategy_adjustment_directives`
  - memory packet을 바탕으로 strategist가 어떤 행동을 유지/강화/약화/전환해야 한다고 판단했는지 설명

즉:
- `policy_adjustment`는 “무엇이 바뀌었나”
- `strategy_adjustment_directives`는 “무엇을 하라고 판단했나”
를 읽는 surface다.

### 현재 상태: artifact-only surface
중요한 점:

- 현재 `strategy_adjustment_directives`는 strategist output artifact에 기록되는 surface다.
- scanner / monitor / commander가 직접 읽는 실행 입력은 아니다.
- 실제 실행 계약은 여전히 `monitor_entry_policy`다.

즉 지금 단계에서의 역할은:
1. memory packet이 실제로 어떤 행동 지시로 변환됐는지 관측
2. repeated-hold / selected-symbol refresh 품질 점검
3. 이후 downstream trace/advisory 연결 후보 확보

한 줄로 정리하면:
- 지금 `strategy_adjustment_directives`는 **artifact-only for now**
- runtime execution input은 아니다.

## 8. strategist 출력은 어떻게 scanner로 연결되나
scanner 쪽은 monitor와 다르게, strategist의 output을 바로 threshold bundle로 쓰는 것이 아니라 `scanner_guidance`와 `strategy_policy.scanner_policy`를 해석해서 후보 풀과 랭킹에 반영한다.

핵심 흐름은 아래다.

1. strategist가 state에 적재
- `graphs/nodes/strategist_node.py`
- strategist 실행 후 아래가 state에 들어간다.
  - `state["scanner_guidance"]`
  - `state["strategy_policy"]`
  - `state["scanner_bias"]`
  - `state["scanner_priority"]`

2. scanner가 strategist guidance 추출
- `graphs/nodes/scanner_node.py::_extract_scanner_guidance(state)`
- scanner는 `state["strategist_output"]`와 `state["strategy_policy"]`에서 아래를 꺼낸다.
  - `themes`
  - `avoid_themes`
  - `playbook`
  - `scanner_priority`
  - `scanner_source_policy`
  - `scanner_bias`
  - `scanner_bias_context`
  - `trade_aggressiveness`
  - `risk_tone`
  - `monitor_guidance`
  - `monitor_policy`
  - `commander_context`
  - `strategist_plan`
  - `policy_provenance`

즉 scanner는 strategist의 결과를 “후보 선정용 guidance packet”으로 다시 읽는다.

### scanner가 실제로 소비하는 strategist 입력 축
`graphs/nodes/scanner_node.py` 기준 scanner는 strategist 출력을 아래 4축으로 쓴다.

1. 후보 소스 구성
- `scanner_source_policy`
- 예:
  - `include_top_value`
  - `include_top_volume`
  - `include_change_rate`
  - `include_condition_search`
  - `include_sector_candidates`
  - `include_watchlist`
  - `top_candidate_pool`
  - `condition_limit`
  - `source_weights`

이 값은 `build_kiwoom_candidate_rows(...)` 이전의 candidate pool 구성에 들어간다.

2. 후보 필터/테마 방향
- `themes`
- `avoid_themes`
- `playbook`

이 값은 theme filter, avoid-theme filter, candidate backfill 판단에 영향을 준다.

3. 랭킹 가중치/바이어스
- `scanner_priority`
- `scanner_bias`
- `scanner_bias_context`
- `trade_aggressiveness`
- `risk_tone`

이 값은 practical scoring과 structured scanner bias에 반영된다.

4. monitor-entry 호환성 프레임
- `monitor_policy`
- `monitor_guidance`

scanner는 이것도 같이 읽어서 “이 종목이 현재 monitor gate를 통과할 가능성이 높은지”를 compatibility bias로 계산한다.
즉 strategist가 준 monitor baseline은 monitor만 쓰는 것이 아니라 scanner의 candidate ranking에도 간접 반영된다.

### scanner trace에 남는 strategist 연결 흔적
`graphs/nodes/scanner_node.py::_build_scanner_policy_trace(...)`

scanner는 strategist와 commander에서 가져온 연결 흔적을 아래처럼 trace로 남긴다.

```json
{
  "commander_priority_ref": {
    "scanner_mission": "...",
    "allowed_playbooks": ["pullback", "defensive", "breakout"],
    "risk_mode": "balanced",
    "command_intent": "OBSERVE_ONLY"
  },
  "strategist_constraints_ref": {
    "selected_playbook": "defensive",
    "candidate_hypotheses": [...],
    "symbol_constraints": {...},
    "strategy_summary": "..."
  },
  "ranking_factors": [
    "leader_quality",
    "trading_value",
    "trend_strength",
    "volume_surge",
    "bias:leader",
    "playbook:defensive"
  ],
  "monitor_entry_policy_summary": {
    "timeframe_minutes": 1,
    "breakout_lookback": 5,
    "volume_ratio_min": 0.75,
    "pullback_min_pct": 0.01,
    "pullback_max_pct": 0.05,
    "max_extended_from_vwap_pct": 0.08
  }
}
```

즉 scanner artifact를 볼 때 아래 필드를 보면 strategist 연결이 보인다.

1. `scanner_selection_reason.commander_priority_ref`
2. `scanner_selection_reason.strategist_constraints_ref`
3. `scanner_selection_reason.ranking_factors`
4. `scanner_selection_reason.monitor_entry_policy_summary`
5. `scanner_selection_reason.policy_provenance_ref`

### scanner에 대한 한 줄 정리
monitor는 strategist의 `monitor_entry_policy`를 직접 받는다.

scanner는 strategist의
- playbook
- themes / avoid_themes
- scanner priority
- scanner bias
- source policy
- monitor policy summary
를 읽어서 candidate pool과 ranking trace에 반영한다.

즉 scanner는 strategist의 output을 “직접 order instruction”으로 쓰는 게 아니라, “후보 추출과 랭킹의 정책 프레임”으로 쓴다.

## 9. 지금 이 문서로 확인할 수 있는 것
이 문서를 보면 아래 질문에 답할 수 있다.

1. 전략가는 실제로 어떤 system/user prompt를 받는가
2. 입력 payload는 어떤 섹션으로 구성되는가
3. repeated-hold refresh 때 왜 기존에는 no-delta가 자주 났는가
4. 지금 패치 후에는 어떤 hold-side context가 추가로 strategist로 넘어가는가
5. strategist 출력 중 monitor에 직접 영향을 주는 필드는 무엇인가
6. strategist 출력 중 scanner에 정책 프레임으로 연결되는 필드는 무엇인가
7. strategist가 report artifact를 전문으로 읽는지, packet으로 읽는지
8. 현재 strategist 입력에 실제로 들어가는 report-side source가 무엇인지

## 10. 바로 다음에 보면 좋은 artifact
현재 패치가 반영된 새 refresh 런이 하나 생기면 아래 파일 3개를 같이 보면 된다.

1. `reports/canonical/<day>/<run_id>/commander.json`
- `strategist_refresh_context`
- `open_position_refresh_context`
- `strategist_refresh_effective`
- `strategist_refresh_policy_delta_fields`

2. `reports/canonical/<day>/<run_id>/strategist.json`
- `commander_context_ref.open_position_refresh_context`
- `strategic_answers.q15_commander_refresh_context`
- `monitor_entry_policy`
- `policy_adjustment`
- `strategy_adjustment_directives`

3. `reports/canonical/<day>/<run_id>/monitor.json`
- `received_policy`
- `effective_policy`

4. `reports/canonical/<day>/<run_id>/scanner.json`
- `selection_summary`
- `selection_reason.commander_priority_ref`
- `selection_reason.strategist_constraints_ref`
- `selection_reason.ranking_factors`
- `selection_reason.monitor_entry_policy_summary`

이 4개를 같이 보면 “입력은 들어갔는데 output이 그대로였는지”, “output은 바뀌었는데 monitor 적용이 달랐는지”, “scanner 랭킹 프레임에 strategist가 실제로 어떻게 반영됐는지”를 바로 판별할 수 있다.
