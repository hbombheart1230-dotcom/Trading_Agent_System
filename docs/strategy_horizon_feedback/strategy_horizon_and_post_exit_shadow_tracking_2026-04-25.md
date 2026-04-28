# Strategy Horizon and Post-Exit Shadow Tracking

## 목적

현재 시스템은 종목 선택 품질은 나쁘지 않은데, 청산 이후 같은 종목이 다시 상승하거나 다음날 슈팅하는 사례가 있다. 이 문제를 바로 "더 오래 보유"로 해결하면 라이브 검증 샘플이 줄고 손실 리스크가 커진다.

따라서 첫 단계는 매매 행동을 바꾸는 것이 아니라 다음 두 가지를 구조화해서 기록하는 것이다.

- 전략가가 의도한 보유 기간과 청산 기준
- 실제 매도 후 안 팔았으면 어떻게 됐는지에 대한 결정론적 shadow 결과

이 문서는 월요일 2026-04-27 라이브 검증부터 적용할 수 있는 계측 우선 설계를 정의한다.

## 핵심 원칙

1. 보유 강제보다 기록을 먼저 한다.

초기 구현은 monitor exit 로직을 크게 바꾸지 않는다. 대신 매도 시점에 전략 의도와의 일치 여부를 기록한다.

2. Strategist는 종목 선정자가 아니다.

Strategist는 시장/전략 frame과 horizon을 제안한다. 최종 종목 선택은 Scanner 책임이다. Horizon은 선택된 종목을 어떻게 감시하고 청산할지에 대한 downstream guidance다.

3. Post-exit 평가는 LLM memory truth가 아니다.

매도 후 결과는 가격, 고가/저가, 목표가, 손절가, 시간 경과로 계산한다. LLM은 나중에 설명문을 만들 수는 있지만 memory truth를 직접 생성하면 안 된다.

4. "다음날 올랐다"만으로 조기매도라고 판단하지 않는다.

중간에 손절선을 먼저 깼는지, 전략상 버틸 수 있는 변동이었는지, 유동성/호가 리스크가 있었는지까지 같이 봐야 한다.

## Strategy Horizon Contract

Strategist output에는 다음 필드를 추가한다.

```json
{
  "strategy_horizon": "intraday",
  "expected_hold_window": {
    "min_sec": 300,
    "target_sec": 1800,
    "max_sec": 14400
  },
  "exit_guidance": {
    "profit_take_style": "trail_after_first_push",
    "allow_early_exit": true,
    "early_exit_allowed_reasons": [
      "hard_stop",
      "broker_truth_mismatch",
      "liquidity_collapse",
      "theme_breakdown",
      "market_regime_flip"
    ],
    "avoid_early_exit_reasons": [
      "small_noise_pullback",
      "minor_profit_without_momentum_loss"
    ]
  },
  "invalidation_conditions": [
    "selected theme loses breadth",
    "price loses VWAP and cannot reclaim within observation window"
  ],
  "monitor_handoff": {
    "hold_bias": "neutral_to_patient",
    "preferred_exit": "trailing_stop_after_extension",
    "do_not_force_hold": true
  }
}
```

권장 horizon label:

- `scalp`: 수 분 단위 검증. 빠른 손절/익절 허용.
- `intraday`: 당일 안에서 추세와 VWAP 회복을 본다.
- `overnight_probe`: 당일 종가 이후 뉴스/수급 연속성을 일부 기대한다.
- `1_2day_swing`: 1-2거래일 테마/수급 지속성을 본다.

초기 live 검증에서는 `overnight_probe`와 `1_2day_swing`이 나와도 monitor가 강제 보유하지 않는다. 대신 "전략은 길게 보라고 했지만 monitor가 왜 팔았는지"를 기록한다.

## Commander Horizon Ownership

운용 horizon의 최종 소유자는 Commander다. Strategist는 종목을 고르지 않고, 특정 후보/상황에 대해 “이 거래는 어떤 시간축으로 해석할 수 있는가”를 제안한다. Commander는 그 제안을 장 상태, 보유 포지션 상태, runtime phase, memory packet, live validation 정책과 합쳐서 Monitor와 Reporter가 따라야 할 `commander_horizon_policy`로 확정한다.

초기 구현 규칙:

- `strategy_horizon_feedback`: Strategist proposal. 전략가의 해석과 의도 설명을 담는다.
- `commander_horizon_policy`: Commander-owned operational policy. Monitor exit alignment와 Reporter 검수는 이 값을 우선 사용한다.
- `source_strategy_horizon`: Commander가 참고한 원래 Strategist proposal horizon이다.
- `observability_only=true`: 매도 기준, 임계값, 강제 보유를 바꾸지 않는다.
- `do_not_force_hold=true`: horizon이 길게 나와도 Monitor가 강제로 버티지 않는다.
- `allow_behavior_change=false`: post-exit shadow와 live sample이 충분히 쌓이기 전에는 행동 변경을 금지한다.

Live validation 단계에서는 Strategist가 `overnight_probe` 또는 `1_2day_swing`을 제안하더라도 Commander가 운용 horizon을 `intraday`로 제한할 수 있다. 이때 제안 자체는 버리지 않고 `proposal`과 `source_strategy_horizon`에 보존한다. 즉 “전략가는 더 길게 볼 수 있다고 봤지만, 현재 운용은 장중 검증만 허용했다”는 사실을 artifact에 남긴다.

Refresh 흐름:

- 1차 Strategist 호출 전: Commander는 현재 runtime/memory 기준의 기본 horizon policy를 context에 넣는다.
- Pre-buy refresh: Commander는 cached strategist proposal, scanner 선택 결과, memory를 반영해 refresh context에 `commander_horizon_policy`를 넣는다.
- Open-position refresh: Commander는 보유 종목, 반복 HOLD/WAIT, carry risk, monitor blocker를 반영해 같은 policy를 갱신한다.
- Monitor: `commander_horizon_policy`를 우선 사용하고, 없을 때만 `strategy_horizon_feedback`으로 fallback한다.
- Reporter: 전략가 제안, Commander 확정 horizon, 실제 매도 판단, post-exit shadow를 함께 보여준다.

## Monitor Exit Logging

Monitor가 SELL 또는 exit intent를 만들 때 다음 필드를 남긴다.

```json
{
  "exit_vs_strategy_intent": {
    "strategy_horizon": "intraday",
    "expected_hold_window": {
      "min_sec": 300,
      "target_sec": 1800,
      "max_sec": 14400
    },
    "actual_hold_sec": 420,
    "early_exit_flag": false,
    "exit_alignment": "aligned",
    "alignment_reason": "momentum failed after first push and VWAP reclaim failed",
    "hard_exit": false,
    "hard_exit_reason": ""
  }
}
```

`exit_alignment` 값:

- `aligned`: 전략 의도와 맞는 청산
- `early_but_justified`: 전략보다 빠르지만 hard/quality reason이 있음
- `early_unproven`: 빠른 청산이고 근거가 약함
- `late`: 전략상 더 빨리 정리했어야 했음
- `unknown`: 필요한 입력 부족

Hard exit 예시는 항상 horizon보다 우선한다.

- broker truth 불일치
- 주문/체결 이상
- 손절선 이탈
- 유동성 급락
- 시장 regime 급변
- 감시 데이터 결측

## Post-Exit Shadow Tracking

Closed trade 이후에도 선택 종목을 일정 시간 추적한다. 이 추적은 실제 매매를 하지 않는 shadow 관측이다.

기본 관측 지점:

- `+5m`
- `+15m`
- `+30m`
- `+60m`
- `EOD`
- `T+1`
- `T+2`

저장할 핵심 필드:

```json
{
  "post_exit_shadow": {
    "symbol": "005930",
    "exit_ts": "2026-04-27T10:14:00+09:00",
    "exit_price": 70000,
    "strategy_horizon": "intraday",
    "checkpoints": {
      "+5m": {
        "price": 70100,
        "high_since_exit": 70300,
        "low_since_exit": 69800,
        "max_upside_pct": 0.0043,
        "max_drawdown_pct": -0.0029
      },
      "EOD": {
        "close": 71500,
        "high_since_exit": 72000,
        "low_since_exit": 69700,
        "max_upside_pct": 0.0286,
        "max_drawdown_pct": -0.0043
      }
    },
    "would_hit_target": true,
    "would_hit_stop_first": false,
    "best_exit_offset": "EOD",
    "best_exit_price": 71500,
    "post_exit_label": "early_exit_missed_upside"
  }
}
```

`post_exit_label` 후보:

- `good_exit`: 이후 추가 상승이 제한적이고 하락 리스크가 더 컸음
- `early_exit_missed_upside`: 손절선을 먼저 깨지 않고 의미 있는 추가 상승이 나왔음
- `defensive_exit_saved_loss`: 이후 하락이 커서 방어 청산이 맞았음
- `volatile_unholdable`: 나중에 올랐지만 중간 drawdown이 전략상 버티기 어려웠음
- `inconclusive`: 데이터 부족 또는 상승/하락 신호 혼재

## Memory Aggregation

Post-exit shadow 결과는 개별 trade artifact에 남긴 뒤, runtime memory로 집계한다.

일별 집계:

- horizon별 trade 수
- early exit 비율
- early exit 이후 평균 추가 상승률
- defensive exit 이후 회피한 평균 하락률
- `would_hit_stop_first` 비율
- inconclusive 비율

주별/월별 집계:

- horizon별 기대값
- symbol별 반복 패턴
- playbook별 조기청산 패턴
- market regime별 holding 성공/실패
- monitor exit reason별 사후 품질

종목별 집계:

- 이 종목은 매도 후 추가 상승이 잦은가
- 이 종목은 중간 drawdown이 커서 실제로는 버티기 어려운가
- 이 종목은 intraday보다 overnight에서 성과가 나는가

## Runtime Usage

초기 사용 방식은 advisory다.

Strategist:

- horizon을 제안한다.
- post-exit memory를 보고 "이 playbook은 너무 빨리 팔리는 경향이 있다" 정도의 전략적 bias를 낸다.
- 종목을 직접 고르지는 않는다.

Scanner:

- 기존처럼 최종 후보를 고른다.
- post-exit memory는 종목 priors로 쓸 수 있지만, Scanner가 horizon을 최종 확정하지 않는다.

Monitor:

- strategist horizon과 exit guidance를 읽는다.
- 초기에는 청산 결정을 바꾸지 않고 alignment를 기록한다.
- 데이터가 쌓이면 soft-exit에서만 hold bias를 적용한다.

Reporter:

- 실제 매도 판단과 전략 의도의 차이를 보여준다.
- post-exit shadow 결과를 별도 섹션으로 보여준다.
- "팔고 나서 올랐다"를 단정하지 않고 stop-first / drawdown / best-exit-time을 같이 보여준다.

Commander:

- 충분한 evidence가 쌓이기 전까지 production hold 변경을 막는다.
- horizon별 live sample 품질과 정책 승격 가능성을 관리한다.

## Rollout Plan

### Phase 0. 문서화

완료 조건:

- strategy horizon contract 정의
- monitor exit-vs-intent logging 정의
- post-exit shadow field 정의
- memory aggregation 방향 정의

### Phase 1. Observability-only

코드 변경 범위:

- Strategist JSON에 horizon/guidance 필드 추가
- Monitor SELL artifact에 `exit_vs_strategy_intent` 추가
- Closed trade artifact에 shadow tracking placeholder 추가
- Reporter가 해당 필드를 표시

정책:

- 실제 청산 로직 변경 없음
- 강제 보유 없음
- 임계값 강제 완화 없음

### Phase 2. Deterministic Shadow Tracker

코드 변경 범위:

- closed trade 이후 checkpoint별 가격 추적
- `would_hit_target`, `would_hit_stop_first`, `best_exit_offset` 계산
- daily/symbol memory 집계

정책:

- 여전히 실매매 변경 없음
- 사후 평가만 누적

### Phase 3. Soft Exit Bias

적용 조건:

- 최소 live sample 확보
- early exit missed upside가 특정 horizon/playbook/symbol에서 반복 확인
- stop-first 비율이 낮음
- defensive exit saved loss 비율과 비교해 기대값이 양호함

적용 방식:

- hard exit은 항상 우선
- soft profit-taking에서만 trailing/hold bias 적용
- scalp horizon에는 보수적으로 적용
- `overnight_probe`, `1_2day_swing`은 별도 승인 전까지 shadow만 유지

## Live Validation Checklist

월요일 2026-04-27부터 확인할 항목:

- Strategist artifact에 `strategy_horizon`이 남는가
- Scanner 선택과 Strategist horizon이 역할상 분리되어 보이는가
- Monitor SELL artifact에 `exit_vs_strategy_intent`가 남는가
- Closed trade report가 horizon과 actual hold time을 보여주는가
- Post-exit shadow placeholder가 생성되는가
- 당일 장마감 후 EOD checkpoint를 채울 수 있는가
- 다음 거래일에 T+1 checkpoint를 채울 수 있는가

## Open Questions

- checkpoint 가격은 Kiwoom minute data를 우선할지, 기존 monitor/event price를 우선할지
- T+1/T+2 추적을 별도 scheduler로 둘지, report regeneration 시 lazy-fill할지
- target/stop 기준은 entry 당시 monitor policy를 저장해 재사용할지, post-exit 시 재계산할지
- overnight/swing horizon을 실제 보유로 승격할 최소 sample 수를 얼마로 둘지

## Initial Implementation Order

1. Strategist output contract 확장
2. Monitor exit artifact logging 추가
3. Closed trade bundle에 post-exit shadow placeholder 추가
4. Reporter markdown/json 표시
5. EOD lazy-fill 또는 batch script 추가
6. daily/symbol memory aggregation 추가
7. soft-exit bias shadow 검증
8. production hold behavior 변경 여부 판단
