# Monitor Scoring Defer Note

## 목적

이 문서는 현재 monitor scoring shadow 검증 결과를 바탕으로,
`shadow -> enabled` 전환을 지금 바로 추진하지 않는 이유와
그 상태에서 `5-2` 구조 분리 작업으로 넘어가도 되는지 정리하기 위한 note다.

이 문서는 기존 roadmap을 대체하지 않는다.
또한 현재 monitor scoring을 정식 policy 시스템으로 승격하지 않고,
monitor 내부 local experimental logic으로 유지한다는 전제를 명시한다.

## 현재 판단

현재 monitor scoring은 아래처럼 정리한다.

- `MONITOR_SCORING_ENABLED=false` 유지
- `MONITOR_SCORING_SHADOW_MODE=true` 유지 가능
- 단, shadow는 production 승격 직전 단계가 아니라
  "참고용 관찰/로그 축적" 수준으로 간주한다

즉 지금 scoring은
"곧 enabled로 올릴 예정인 준정식 로직"이 아니라,
"향후 policy ownership 정리 전까지 남겨둘 local experiment"로 본다.

## 왜 지금 enabled로 올리지 않는가

현재까지의 관찰에서 아래 문제가 있었다.

1. `legacy WAIT / scoring BUY`가 존재하더라도,
   이것이 명확한 missed opportunity라고 보기 어려운 사례가 적지 않았다
2. reclaim discipline이 아직 충분히 검증되지 않은 상태에서
   scoring이 상대적으로 이른 BUY를 제안하는 경향이 보였다
3. 장중에 한 종목을 오래 보유하면 entry-eligible sample이 크게 줄어,
   shadow 비교 품질이 쉽게 왜곡된다
4. 일부 세션에서는 go-live 판정에 필요한 비교 필드가
   artifact/event에 완전하게 남지 않아,
   "enabled 승격 판단용 검증 루프"로 보기 어렵다

정리하면,
문제는 scoring 아이디어 자체보다
"지금 이 구현/관찰 상태를 production decision path로 바로 올릴 근거가 충분하지 않다"는 점이다.

## 처음 문제 정의는 유효한가

유효하다.

monitor scoring을 도입한 출발점은 아래 문제를 완화하려는 것이었다.

- no-trade 과잉
- AND 누적형 entry gating의 경직성
- WAIT가 너무 많아지는 구조

즉 scoring 도입의 문제의식은 여전히 맞다.

다만 현재 결론은 다음과 같다.

- 문제의식은 맞음
- shadow 실험도 의미 있었음
- 하지만 현재 형태를 바로 enabled로 전환할 정도로
  충분한 근거가 확보되지는 않음

## 그래서 지금 무엇을 할 것인가

현재 권장 운영은 아래와 같다.

1. live decision은 기존 legacy monitor 유지
2. shadow는 켜두더라도 참고 로그로만 본다
3. shadow를 production 승격 목표로 더 밀지 않는다
4. reclaim / threshold / local scoring weight 추가 튜닝은 보류한다

즉 scoring은 "폐기"가 아니라 "동결"에 가깝다.

## 5-2로 넘어가도 되는가

된다.

이유:

1. `5-2`는 UI data_access / reporting read-model / rendering 구조 분리 단계다
2. 현재 monitor scoring은 local experiment로 동결할 수 있고,
   `5-2`와 직접적으로 강하게 얽히지 않는다
3. 오히려 shadow 승격 여부를 더 밀어 붙이면서 runtime 튜닝을 계속하는 것보다,
   구조 분리를 먼저 진행하는 편이 전체 roadmap 흐름에 더 맞다

즉 현재 시점에서는
`shadow -> enabled`를 강행하기보다
`5-2`로 넘어가는 편이 더 자연스럽다.

## 장중 매매 운영은 의미가 있는가

의미는 있다.

다만 의미를 아래처럼 좁게 본다.

### 의미 있는 것

- 런타임 안정성 확인
- execution / stitching / state 반영 이상 여부 확인
- scanner / monitor / execution 간 운영상 이상 징후 확인
- shadow scoring 로그 참고 축적

### 의미가 약한 것

- 현재 scoring을 enabled로 승격할지 판단하는 핵심 근거로 사용
- 하루 샘플 몇 개만으로 scoring policy 타당성을 확정하는 것

즉 장중 매매 운영은 계속 유효하지만,
지금 시점의 최우선 개발 의사결정은
"shadow를 언제 enabled로 올릴까"가 아니라
"runtime은 유지하면서 다음 구조 단계로 넘어갈 수 있는가"에 더 가깝다.

## 5-3와의 관계

현재 scoring을 더 키우지 않고 local experiment로 동결하면,
`5-3`와 직접 충돌하지 않는다.

이유:

- 현재 scoring weights / threshold는 monitor local ownership이다
- strategist / commander policy object와 직접 연결하지 않는다
- scanner / strategist schema를 변경하지 않는다

반대로,
지금 시점에 scoring을 production 승격 목표로 계속 확장하면
아래 위험이 커진다.

- local hardcoded rule 증가
- reclaim / confidence / threshold 의미가 monitor 내부에 더 고착
- 이후 `5-3` policy ownership 정리 시 재작업 범위 확대

따라서 현재 가장 안전한 선택은:

- scoring은 local experiment로 유지
- `5-2`로 진행
- `5-3`에서 policy ownership 정리 후,
  scoring을 다시 정식 구조 안에서 재평가

## 권장 결론

현재 시점의 권장 결론은 아래와 같다.

1. monitor scoring은 당분간 `shadow` 수준으로 유지
2. `enabled` 전환은 보류
3. 지금부터의 개발 우선순위는 `5-2`
4. scoring 본격 개선/승격 판단은 `5-3` 이후 재검토

한 줄 요약:

monitor scoring의 출발 방향은 맞았지만,
현재는 production 승격보다 local experiment로 동결하는 편이 더 안전하다.
따라서 지금은 `5-2`로 넘어가고,
scoring의 정식 의미 부여는 `5-3` 이후에 다시 다루는 것이 맞다.
