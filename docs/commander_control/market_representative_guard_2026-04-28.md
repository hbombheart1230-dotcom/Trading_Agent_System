# Market Representative Guard

## 배경

2026-04-28 런 점검에서 초기 후보 힌트와 스캐너 선택이 삼성전자(`005930`), SK하이닉스(`000660`)로 반복되는 경향이 확인됐다. 두 종목은 실제로 시장 주도주일 수 있지만, 선택 근거가 테마/모멘텀/뉴스/추세가 아니라 거래대금 상위 효과에 과도하게 기대면 검증 폭이 좁아진다.

이 문서는 대표주를 금지하지 않는다. Commander가 스캐너에 소프트 가드를 내려서, 대표주가 거래대금 단독 우위에 가깝고 차순위 후보와 점수 차가 작을 때만 대안을 올릴 수 있게 한다.

## 소유권

- Commander가 `scanner_policy.market_representative_guard`를 발행한다.
- Scanner는 해당 정책을 소비해 Top-1 후보에만 소프트 감점을 적용한다.
- Strategist는 테마/플레이북/뉴스/메모리 관점을 제공하지만, 대표주 쏠림 제어의 최종 운용권은 Commander에 둔다.
- `env` 값은 사용하지 않는다.

## 기본 정책

Commander 기본값:

```json
{
  "enabled": true,
  "symbols": ["005930", "000660"],
  "penalty": 0.04,
  "max_penalty": 0.12,
  "near_tie_gap": 0.06,
  "top_value_dominance_min": 0.55,
  "weak_confirmation_max": 1,
  "strong_confirmation_min": 2,
  "bypass_when_strong_confirmation": true,
  "apply_when_top_value_only": true,
  "policy_source": "commander_default"
}
```

## 적용 조건

가드는 아래 조건을 모두 만족할 때만 적용된다.

- 현재 Top-1 후보가 `symbols`에 포함된다.
- Top-1과 Top-2의 점수 차가 `near_tie_gap` 이하이다.
- Top-1 후보의 거래대금 컴포넌트가 `top_value_dominance_min` 이상이고, 비거래대금 확인 신호가 약하다.
- 확인 신호 수가 `weak_confirmation_max` 이하이다.

확인 신호는 `theme`, `momentum`, `trend`, `news`, `volume`, `intraday_strength`로 기록한다.

## 우회 조건

대표주라도 아래 조건이면 감점하지 않는다.

- 테마와 거래량, 모멘텀, 추세, 뉴스 등 확인 신호가 `strong_confirmation_min` 이상이다.
- Top-2와 점수 차가 충분히 커서 단순 근소 우위가 아니다.
- 거래대금 단독 우위가 아니다.

## 아티팩트

Scanner output과 canonical scanner artifact에 아래 필드를 기록한다.

- `market_representative_guard_enabled`
- `market_representative_guard_applied`
- `market_representative_guard_symbol`
- `market_representative_guard_penalty`
- `market_representative_guard_score_gap`
- `market_representative_guard_reason`
- `market_representative_guard_confirmation_sources`
- `market_representative_guard_before_top`
- `market_representative_guard_after_top`

## 의도

이 가드는 매수를 강제하지 않고, 임계점을 낮추지도 않는다. 시장이 실제로 반도체 대형주 중심이면 그대로 통과한다. 다만 거래대금 상위 대표주가 별도 확인 없이 반복 선택되는 경우에는 동점권 대안을 검토하도록 스캐너 랭킹을 소폭 조정한다.
