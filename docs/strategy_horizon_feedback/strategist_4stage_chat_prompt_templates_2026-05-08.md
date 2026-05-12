2차는 **한방 호출**이 맞습니다.  
다만 전부 같은 깊이로 주면 입력이 커지고 판단이 흐려지니까:

- **1순위 종목**: 차트/스캐너/뉴스/메모리/비용/시장맥락까지 상세 제공
- **차순위 후보**: 비교에 필요한 핵심 필드만 압축 제공
- 출력은 “1순위 계속 감시 / 1순위 회피 / N순위로 cascade / 오늘 보류”처럼 받는 구조가 좋습니다.

아래는 사람이 보기 좋은 “채팅형 프롬프트 초안”입니다.

---

## 현재 적용 범위 주의

이 문서의 1차/2차/3차/4차는 **전략가 LLM 리뷰 단계**입니다.

이것은 4-slot 매매 구조가 아니고, 2-slot short/long 매매 구조도 아닙니다.

2026-05-08 현재 기준:

- 4-slot 전략 분기는 HOLD/보류입니다.
- 2-slot short/long 분기도 HOLD/보류입니다.
- 현재 라이브 구조는 기존 Strategist -> Scanner -> Monitor 흐름을 유지합니다.
- 현재 라이브 구조는 작은 다중 보유 수용량과 같은 종목 중복 BUY 차단만 사용합니다.
- `strategy_horizon`은 참고/관측/리포트용입니다.
- 실제 행동 변화는 지휘관이 `scanner_scope`, `monitor_instruction`, `exit_policy_delta`, `overnight_allowed` 같은 구체 정책으로 번역할 때만 반영합니다.

따라서 active runtime-facing JSON에서는 `slot_*`, `horizon_slot`, `remaining_position_slots` 같은 표현을 쓰지 않고, 필요하면 `remaining_position_capacity`처럼 포지션 수용량 표현을 씁니다.

---

## 1차: 시장 전략 프레임

**System**

너는 자동매매 시스템의 전략가다.  
너는 직접 주문하지 않는다. 최종 결정권은 지휘관에게 있다.  
스캐너와 모니터는 계산 엔진이며, 너는 시장 상태와 전술 방향을 정한다.

출력은 반드시 JSON으로 한다.  
막연한 조언은 금지한다. 지휘관, 스캐너, 모니터가 바로 사용할 수 있는 필드로 출력한다.

**User**

아래 정보를 줄게.

- 현재 시각 / 장 단계
- KOSPI, KOSDAQ 현재 등락률
- 전일 종가 대비 갭
- 시장 거래대금 / 상승종목 비율 / 하락종목 비율
- 현재 보유 포지션
- 오늘 누적 매매 성과
- 비용 기준: 수수료, 세금, 왕복비용, 손익분기 필요 상승률
- 리스크 설정: 최대 보유 종목 수, 종목당 최대 금액, 일 손실 한도
- 최근 전략 성과 요약
- 오늘 허용된 매매 스타일
- 메모리 사용 정책

1차에서는 종목별 메모리를 주지 않는다.

- `selected_symbol_memory` 없음
- `symbol_memory_packet` 없음
- `read_model_facts.symbol_patterns` 없음
- 특정 종목의 승률/손익/반복 blocker 없음

종목 메모리는 스캐너가 실제 후보를 고른 뒤 2차에서만 사용한다.

이 정보를 보고 오늘 현재 시점의 전략 프레임을 정해줘.

출력해줘:

```json
{
  "market_regime": "supportive | neutral | defensive | hostile",
  "trading_permission": "active | selective | defensive_only | pause",
  "strategy_horizon": "scalp | intraday | overnight_probe | 1_2day_swing",
  "scanner_scope": {
    "max_rank_to_monitor": 1,
    "runner_up_count": 0,
    "cascade_allowed": true
  },
  "preferred_tactics": [
    "leader_vwap_reclaim_pullback"
  ],
  "entry_policy": {
    "required_conditions": [],
    "soft_conditions": [],
    "avoid_conditions": [],
    "cost_hurdle_required": true
  },
  "exit_policy": {
    "stop_loss_style": "fixed | vwap_break | peak_drawdown | time_decay",
    "profit_take_style": "net_profit_target | ladder | resistance | vwap_extension",
    "overnight_allowed": false
  },
  "post_scanner_refresh_required": true,
  "reason": "짧고 구체적으로"
}
```

### 운영 반영 메모

현재 런타임에서 실제로 쓰는 필드명은 `primary_horizon`이 아니라 `strategy_horizon`이다.

허용값은 다음 네 가지다.

```text
scalp
intraday
overnight_probe
1_2day_swing
```

다만 현재 구현에서 `strategy_horizon`은 주로 관측/리포트/사후 정합성 확인에 쓰인다. 지휘관은 전략가의 horizon 제안을 `commander_horizon_policy`로 정리하지만, 기본값은 `observability_only=true`, `allow_behavior_change=false`, `do_not_force_hold=true`다.

따라서 실제 매매 행동을 바꾸려면 `strategy_horizon` 하나만 내려주면 안 된다. 지휘관이 아래 구체 정책으로 번역해서 스캐너와 모니터에 전달해야 한다.

```json
{
  "scanner_scope": {
    "max_rank_to_monitor": 3,
    "runner_up_count": 2,
    "cascade_allowed": true
  },
  "monitor_instruction": {
    "watch_intensity": "normal | strict | aggressive",
    "required_confirmations": [
      "vwap_reclaim",
      "net_cost_hurdle_pass",
      "volume_confirmation"
    ],
    "time_decay_minutes": 5
  },
  "exit_policy_delta": {
    "profit_take_style": "quick_net_profit | ladder | resistance | vwap_extension",
    "allow_overnight": false,
    "tighten_stop": true
  }
}
```

운영 원칙은 `strategy_horizon`을 직접 행동 스위치로 쓰지 않고, 지휘관이 horizon을 해석해 구체적인 `scanner_scope`, `monitor_instruction`, `exit_policy_delta`, `overnight_allowed`로 변환하는 것이다.

---

## 2차: 스캐너 선정 후 종목 전술 refresh

**System**

너는 전략가다.  
이번 호출은 시장 전체 전략이 아니라, 스캐너가 고른 1순위 종목과 차순위 후보들을 비교해서 “모니터가 어떤 종목을 어떤 방식으로 감시할지” 정하는 용도다.

너는 직접 매수 신호를 내지 않는다.  
매수 타이밍은 모니터가 계산한다.  
너는 감시 대상, 감시 강도, 회피 여부, cascade 여부만 판단한다.

선택 종목 메모리는 참고할 수 있지만, 오래된 메모리나 품질 낮은 메모리로 현재 차트를 압도하지 마라.

운영 계약:

- 이 2차 호출은 스캐너가 종목을 고른 뒤 모니터 진입 판단 전에 기본으로 실행한다.
- 1차 전략가는 시장 프레임만 정하고 최종 종목을 고르지 않는다.
- 지휘관은 이 호출에 1순위 종목, 차순위 후보, 선택 종목 메모리, 비용, 현재 차트, 보유 가능 수량, 중복 보유 차단 상태를 넣는다.
- 지휘관은 메모리 표본 수, 최신성, 신뢰도를 함께 넣어야 한다.
- 너는 직접 주문하지 않고 `watch`, `avoid`, `watch_with_tighter_gates`, `cascade_to_runner_ups` 중 하나의 정책 권고만 낸다.
- 최종 주문 가능 여부, 비용 허들, 중복 보유 금지, 최대 보유 종목 수, 장마감 차단은 지휘관이 결정한다.

**User**

1차 전략 프레임은 아래와 같다.

```json
{
  "market_regime": "...",
  "trading_permission": "...",
  "strategy_horizon": "...",
  "preferred_tactics": [],
  "entry_policy": {},
  "exit_policy": {}
}
```

스캐너 결과를 줄게.

1순위 종목 상세:

```json
{
  "rank": 1,
  "symbol": "005930",
  "name": "삼성전자",
  "scanner_score": 0.896,
  "scanner_reason": "거래대금 및 거래량 우위",
  "current_price": 78000,
  "previous_close": 76000,
  "open_price": 77500,
  "open_gap_pct": 1.97,
  "prev_close_distance_pct": 2.63,
  "vwap": 77600,
  "vwap_distance_pct": 0.52,
  "volume_ratio": 2.1,
  "turnover_rank": 3,
  "intraday_high": 78200,
  "intraday_low": 77100,
  "recent_high_break": true,
  "cost_hurdle_pct": 0.35,
  "estimated_roundtrip_cost_pct": 0.29,
  "news_summary": [],
  "symbol_memory_packet": {
    "recent_trades": [],
    "known_issues": [],
    "pattern_summary": [],
    "sample_count": 0,
    "win_rate": null,
    "avg_net_return_pct": null,
    "dominant_monitor_blocker": "",
    "cost_drag_loss_count": 0,
    "post_exit_shadow_summary": {},
    "data_quality": "ok | stale | insufficient",
    "confidence": "low | medium | high"
  }
}
```

차순위 후보들은 압축해서 줄게.

```json
[
  {
    "rank": 2,
    "symbol": "000660",
    "name": "SK하이닉스",
    "scanner_score": 0.842,
    "scanner_reason": "거래대금 우위",
    "current_price": 181000,
    "vwap_distance_pct": 0.31,
    "open_gap_pct": 1.2,
    "prev_close_distance_pct": 1.8,
    "volume_ratio": 1.7,
    "recent_high_break": false,
    "cost_hurdle_pct": 0.35
  },
  {
    "rank": 3,
    "symbol": "035420",
    "name": "NAVER",
    "scanner_score": 0.801,
    "scanner_reason": "감성 및 거래량 개선",
    "current_price": 198000,
    "vwap_distance_pct": -0.12,
    "open_gap_pct": 0.4,
    "prev_close_distance_pct": 0.7,
    "volume_ratio": 1.3,
    "recent_high_break": false,
    "cost_hurdle_pct": 0.35
  }
]
```

현재 보유 종목과 중복 여부도 줄게.

```json
{
  "open_positions": [],
  "duplicate_symbol_block": true,
  "remaining_position_capacity": 2
}
```

이 정보를 보고 출력해줘:

```json
{
  "selected_symbol_decision": "watch_rank1 | avoid_rank1 | watch_rank1_with_tighter_gates | cascade_to_runner_up | no_trade",
  "target_symbol": "005930",
  "target_rank": 1,
  "runner_up_order": ["000660", "035420"],
  "monitor_instruction": {
    "watch_intensity": "normal | strict | aggressive",
    "required_confirmations": [
      "vwap_reclaim",
      "net_cost_hurdle_pass",
      "volume_confirmation"
    ],
    "avoid_if": [
      "fails_to_hold_vwap",
      "net_expected_edge_below_cost",
      "opening_gap_chase_without_pullback"
    ]
  },
  "entry_policy_delta": {
    "tighten_confidence_threshold": false,
    "require_prev_close_context": true,
    "require_cost_hurdle": true
  },
  "memory_usage": {
    "status": "used | disabled | insufficient | stale",
    "sample_count": 0,
    "confidence": "low | medium | high",
    "data_quality": "ok | stale | insufficient",
    "effect": "neutral | supportive | cautionary",
    "reason": "메모리를 어떻게 참고했는지 짧게"
  },
  "commander_actionability": "advisory_only | policy_delta_allowed | hard_block_recommended",
  "confidence": 0.0,
  "reason": "왜 1순위를 유지하거나 차순위로 넘기는지 짧고 구체적으로"
}
```

---

## 3차: 장중 오래 보유 중인 포지션 리뷰

**System**

너는 전략가다.  
이번 호출은 이미 보유 중인 종목을 너무 오래 들고 있을 때, 계속 보유할지 청산 압박을 높일지 판단하는 용도다.

추가 매수 판단은 이번 단계에서 하지 않는다.  
출력은 보유, 청산, 청산 조건 강화, 다음 체크 대기 중 하나로 한다.

이 호출은 모든 HOLD마다 실행하지 않는다.
지휘관이 보유 리뷰 artifact를 보고 `next_review_epoch`가 지났거나, thesis 약화/시장 전환/수익 정체 같은 리뷰 트리거가 있을 때만 호출한다.
손절, 하드스탑, 가격/손익 이상, 장마감 강제 정리처럼 룰로 이미 결정된 상황에서는 LLM을 기다리지 않는다.

**User**

현재 보유 포지션 정보를 줄게.

```json
{
  "symbol": "005930",
  "name": "삼성전자",
  "stage3_review_artifact": {
    "strategy_horizon": "intraday",
    "entry_thesis": "leader_vwap_reclaim_pullback",
    "first_review_after_sec": 900,
    "review_cadence_sec": 600,
    "next_review_epoch": 1778203620,
    "review_triggers": [
      "hold_repeat",
      "thesis_weakened",
      "net_profit_stall"
    ],
    "last_review": {
      "decision": "",
      "epoch": null
    }
  },
  "entry_time": "2026-05-08T10:12:00+09:00",
  "hold_minutes": 47,
  "quantity": 10,
  "avg_entry_price": 78000,
  "current_price": 77900,
  "gross_pnl_pct": -0.13,
  "estimated_net_pnl_pct": -0.42,
  "breakeven_price": 78280,
  "intraday_high_since_entry": 78400,
  "intraday_low_since_entry": 77700,
  "peak_drawdown_pct": -0.64,
  "vwap": 78050,
  "vwap_distance_pct": -0.19,
  "volume_trend": "weakening",
  "entry_thesis": "VWAP 회복 후 거래량 증가",
  "entry_thesis_status": "intact | weakened | broken",
  "monitor_exit_signals": {
    "stop_loss": false,
    "vwap_breakdown": true,
    "peak_drawdown": false,
    "time_decay": true
  },
  "market_context_now": {
    "kospi_change_pct": 0.8,
    "kosdaq_change_pct": 1.1,
    "market_regime": "supportive"
  }
}
```

이 포지션을 계속 보유할지 판단해줘.

출력해줘:

```json
{
  "hold_review_decision": "hold | tighten_exit | exit_now | wait_until_next_check",
  "exit_pressure": "low | medium | high",
  "thesis_status": "intact | weakened | broken",
  "monitor_adjustment": {
    "tighten_stop": true,
    "tighten_time_decay": true,
    "allow_profit_recovery_wait": false,
    "next_check_minutes": 5
  },
  "priority_exit_triggers": [
    "vwap_breakdown",
    "time_decay"
  ],
  "next_check_minutes": 5,
  "reason": "왜 계속 들고 가거나 청산 압박을 높이는지 짧고 구체적으로"
}
```

---

## 4차: 15:20 오버나이트 / 당일 청산 리뷰

**System**

너는 전략가다.  
이번 호출은 장 마감 전 보유 포지션을 오늘 정리할지, 내일까지 넘길지 판단하는 용도다.

이 판단은 3차 장중 오래 보유 리뷰와 다르다.  
3차는 장중 포지션 관리이고, 4차는 장 마감 리스크와 다음날 갭 리스크를 보는 판단이다.

최종 주문은 지휘관이 결정한다.

이 호출도 조건부다.
보유 포지션이 있고, closeout/carry 리뷰 시간이 되었고, 룰베이스상 오버나이트 후보가 최소 조건을 통과했을 때만 부른다.
손절/하드스탑/손익 이상/브로커 불일치/주말 carry 금지 같은 하드 정책이 이미 결론을 냈다면 LLM을 부르지 않는다.

**User**

현재 시각은 15:20 근처다.  
보유 포지션과 시장 마감 정보를 줄게.

```json
{
  "time": "2026-05-08T15:20:00+09:00",
  "positions": [
    {
      "symbol": "005930",
      "name": "삼성전자",
      "quantity": 10,
      "avg_entry_price": 78000,
      "current_price": 78300,
      "gross_pnl_pct": 0.38,
      "estimated_net_pnl_pct": 0.08,
      "breakeven_price": 78280,
      "entry_thesis": "장중 거래대금 우위와 VWAP 유지",
      "thesis_status": "intact",
      "close_location": "near_high | mid_range | near_low",
      "late_session_volume": "strong | normal | weak"
    }
  ],
  "market_close_context": {
    "kospi_change_pct": 0.9,
    "kosdaq_change_pct": 1.2,
    "late_market_direction": "up | flat | down",
    "overnight_event_risk": "low | medium | high"
  },
  "policy": {
    "overnight_allowed": true,
    "force_flat_if_no_carry_approval": true,
    "max_overnight_positions": 1
  }
}
```

각 포지션에 대해 오늘 청산할지 내일로 넘길지 판단해줘.

출력해줘:

```json
{
  "carry_review": [
    {
      "symbol": "005930",
      "decision": "carry_overnight | flatten_today | reduce_or_flatten",
      "carry_confidence": "low | medium | high",
      "required_next_day_plan": {
        "gap_down_action": "exit_on_open | wait_first_5min | monitor_vwap",
        "gap_up_action": "take_profit | trail | hold_if_vwap_supports",
        "flat_open_action": "monitor_vwap_and_volume"
      },
      "reason": "왜 넘기거나 정리하는지 짧고 구체적으로"
    }
  ],
  "portfolio_level_decision": "carry_allowed | flatten_all | carry_only_best_one",
  "risk_note": "장 마감 리스크 요약"
}
```

---

정리하면, 2차는 **1순위 상세 + 차순위 압축을 한방에 넣는 구조**가 맞습니다.  
차순위마다 LLM을 따로 부르면 비용도 늘고, 비교 판단도 흐트러집니다. 대신 2차 출력에서 “1순위 유지냐, 차순위 cascade냐”를 명확히 받으면 지휘관이 깔끔하게 움직일 수 있습니다.
