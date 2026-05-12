# Daily Profit Guard Policy Draft

작성일: 2026-05-11
상태: 문서화 완료, 코드 미구현
소유권: Commander

## 목적

하루 순수익이 일정 수준을 넘으면 신규 매수를 줄이거나 중단해, 이미 확보한 수익을 불필요한 추가 매매로 반납하지 않도록 한다.

이 정책은 손실 제한이 아니라 수익 보전 장치다.

## 핵심 원칙

- 최종 통제권은 지휘관이 가진다.
- 전략가는 당일 시장 상황을 보고 수익 락 기준을 제안할 수 있다.
- 지휘관은 계좌 총액, 비용, 실현손익, 보유 포지션, 장 마감 시간, 시장 상태를 보고 최종 기준을 계산한다.
- hard lock이 걸려도 보유 종목을 무조건 청산하지 않는다.
- hard lock은 기본적으로 신규 BUY 중단이다.
- 보유 포지션 청산은 기존 모니터 청산 정책이 계속 담당한다.

## 왜 계좌 %만 쓰면 안 되는가

모의투자 계좌는 현재 1억 단위지만, 초기 실계좌는 몇백만원 수준일 가능성이 높다.

예시:

- 1억원의 `0.20%` = 200,000원
- 300만원의 `0.20%` = 6,000원

소액 계좌에서 6,000원은 1회 왕복 비용과 슬리피지에 쉽게 묻힐 수 있다. 따라서 `% 기준`과 `원화 최소 기준`을 함께 써야 한다.

## 권장 정책 구조

```json
{
  "daily_profit_guard": {
    "owner": "commander",
    "status": "planned_not_implemented",
    "basis": "net_realized_pnl_after_fee_tax_slippage",
    "strategist_recommendation_enabled": true,
    "soft_lock": {
      "action": "tighten_new_buy_conditions"
    },
    "hard_lock": {
      "action": "block_new_buy_only"
    },
    "position_management": {
      "force_sell_on_hard_lock": false,
      "exit_owner": "monitor"
    }
  }
}
```

## 전략가 제안 필드 초안

전략가는 당일 장세, 변동성, 시장 강도, 비용 드래그를 보고 추천값만 낸다.

```json
{
  "daily_profit_stop_recommendation": {
    "soft_lock_pct": 0.003,
    "hard_lock_pct": 0.005,
    "confidence": "normal",
    "reason": "시장 방향성은 있지만 비용 드래그가 커서 순수익 확보 후 신규 진입 축소가 필요합니다."
  }
}
```

전략가 출력은 권고다. 그대로 적용하지 않는다.

## 지휘관 최종 계산 초안

지휘관은 전략가 추천값을 계좌/비용 기준으로 다시 계산한다.

```text
soft_lock_amount =
max(
  account_equity * strategist_soft_lock_pct,
  estimated_round_trip_cost * 1.0,
  commander_min_meaningful_profit_krw
)

hard_lock_amount =
max(
  account_equity * strategist_hard_lock_pct,
  estimated_round_trip_cost * 1.5,
  commander_min_meaningful_profit_krw
)
```

최종 출력 예시:

```json
{
  "commander_daily_profit_guard": {
    "owner": "commander",
    "basis": "net_realized_pnl_after_fee_tax_slippage",
    "account_equity": 3000000,
    "soft_lock_pct": 0.003,
    "hard_lock_pct": 0.005,
    "soft_lock_amount_krw": 9000,
    "hard_lock_amount_krw": 15000,
    "current_net_realized_pnl_krw": 0,
    "state": "inactive",
    "action": "allow_new_buy"
  }
}
```

## 계좌 규모별 초기 가이드

### 모의투자 1억원 기준

- soft lock: `+0.10%` 전후
- hard lock: `+0.20%` 전후
- 예시:
  - soft: 100,000원
  - hard: 200,000원

### 초기 실계좌 300만원 기준

- soft lock: `+0.30%` 전후
- hard lock: `+0.50%` 전후
- 예시:
  - soft: 9,000원
  - hard: 15,000원

소액 계좌에서는 `%`가 너무 작아질 수 있으므로 `최소 의미수익금`과 `왕복비용 배수`가 반드시 필요하다.

## 상태 전이

```text
inactive
  -> soft_locked
  -> hard_locked
```

### inactive

- 신규 BUY 허용
- 기존 리스크/비용/모니터 조건만 적용

### soft_locked

- 신규 BUY는 허용하되 조건 강화
- 예시:
  - 비용 차감 기대수익 상향
  - 스캐너 상위 후보만 허용
  - 모니터 confidence/entry quality 기준 상향
  - 장 마감 임박 신규 진입 차단 강화

### hard_locked

- 신규 BUY 중단
- 보유 종목은 모니터 청산 정책 유지
- 신규 전략가/스캐너 호출은 줄이거나 관측-only로 전환 가능

## 중요한 예외

hard lock 후에도 아래는 계속 허용한다.

- 기존 보유 종목 청산
- 부분익절 후 잔량 관리
- 위험 청산
- 브로커/체결 정합성 복구
- 미체결/중복 주문 정리

hard lock 후 기본 차단 대상:

- 신규 BUY
- 신규 종목 선정 목적의 공격적 스캐너 확장
- 수익 락 이후 복수 재진입

## 리포트 표기 초안

일일 요약에는 아래가 보여야 한다.

```markdown
## 일일 수익 락

* 기준: 수수료/세금/슬리피지 반영 순실현손익
* 전략가 제안: soft +0.30%, hard +0.50%
* 지휘관 적용: soft 9,000원, hard 15,000원
* 현재 상태: inactive / soft_locked / hard_locked
* 현재 순실현손익: 0원
* 신규 매수 상태: 허용 / 조건 강화 / 중단
* 보유 종목 청산: 모니터 기존 정책 유지
```

## 구현 보류 이유

현재는 모의투자 런이 아직 충분히 안정되지 않았고, 비용/청산/리포트 정합성 검증이 우선이다.

따라서 이 기능은 바로 개발하지 않는다.

구현 후보 시점:

- 모의투자에서 체결/수수료/세금/실현손익 정합성이 안정됨
- 하루 단위 순손익 집계가 브로커 기준과 리포트 기준에서 일치함
- 전략가/스캐너/모니터 4stage 흐름이 최소 며칠 이상 정상 검증됨

## 향후 구현 체크리스트

- 지휘관 policy schema에 `daily_profit_guard` 추가
- 전략가 출력 schema에 `daily_profit_stop_recommendation` 추가
- 지휘관이 추천값을 계좌/비용 기준으로 클램프
- 실행부 BUY 전 `commander_daily_profit_guard.state` 확인
- daily/operator summary에 적용 기준과 상태 표시
- 테스트:
  - soft lock은 BUY 조건만 강화
  - hard lock은 신규 BUY만 차단
  - hard lock 중 SELL은 허용
  - 계좌 규모가 작아도 최소 의미수익금이 적용됨
  - 비용 기준이 없는 경우 안전한 기본값으로 fallback
