# Monitor Scoring Shadow Go-Live Criteria

## 1. 목적

- shadow mode에서 monitor scoring 성능을 검증한다.
- production(`enabled`) 전환 시점을 객관적으로 판단한다.
- 기존 legacy decision 대비 scoring decision의 품질을 비교한다.
- 본 문서는 monitor scoring의 운영 판단 기준만 정의하며, scoring ownership 자체를 정식 policy로 승격하지 않는다.

## 2. Shadow Mode 정의

- `legacy decision`
  - 현재 실제 실행 기준이 되는 monitor decision
- `scoring decision`
  - shadow mode에서 병렬 계산되는 scoring 기반 판단
- `shadow mode`
  - scoring 결과를 기록하지만 execution path에는 영향이 없다
  - 실제 BUY/WAIT는 legacy decision이 유지된다

## 3. 핵심 평가 지표

### 3.1 Decision Divergence Rate

정의:

- `legacy_entry_decision != scoring_entry_decision` 비율

판단 기준:

| 지표 | 기준 | 판정 |
|---|---:|---|
| Decision Divergence Rate | 0% ~ 10% | SAFE |
| Decision Divergence Rate | 10% ~ 30% | CAUTION |
| Decision Divergence Rate | 30% 초과 | RISK |

해석:

- divergence가 낮으면 scoring은 legacy와 거의 같은 판단을 내린다.
- divergence가 높으면 scoring이 실거래 판단을 흔들 가능성이 크다.

### 3.2 “Scoring would BUY but legacy blocked” 비율

정의:

- `scoring_entry_decision == "BUY"`
- `legacy_entry_decision == "WAIT"`

확인 항목:

- 전체 run 대비 비율
- 해당 케이스가 실제로 “좋은 진입 기회”였는지 별도 수동 확인

판단 기준:

| 지표 | 기준 | 판정 |
|---|---:|---|
| Scoring BUY / Legacy WAIT | 0% | FAIL |
| Scoring BUY / Legacy WAIT | 1% ~ 9% | 약함 |
| Scoring BUY / Legacy WAIT | 10% ~ 25% | PASS |
| Scoring BUY / Legacy WAIT | 25% ~ 40% | CAUTION |
| Scoring BUY / Legacy WAIT | 40% 초과 | FAIL |

해석:

- 0이면 scoring이 추가 기회를 전혀 못 찾는 상태다.
- 10~25%면 의미 있는 기회 포착 가능성이 있다.
- 과도하면 false positive 위험이 커진다.

### 3.3 “Scoring would WAIT but legacy BUY” 비율

정의:

- `scoring_entry_decision == "WAIT"`
- `legacy_entry_decision == "BUY"`

판단 기준:

| 지표 | 기준 | 판정 |
|---|---:|---|
| Scoring WAIT / Legacy BUY | 0% ~ 20% | PASS |
| Scoring WAIT / Legacy BUY | 20% ~ 30% | CAUTION |
| Scoring WAIT / Legacy BUY | 30% 초과 | FAIL |

해석:

- 이 값이 높으면 scoring이 legacy보다 지나치게 보수적일 수 있다.

### 3.4 Score Distribution

확인 항목:

- `total_score` 분포
- `entry_threshold` 근처 점수 집중 여부

판단 기준:

| 관찰 | 판정 |
|---|---|
| score가 대부분 0 또는 1에 몰림 | FAIL |
| score가 대부분 5 이상에만 몰림 | FAIL |
| score가 threshold 근처(예: 2~4)에 의미 있게 분포 | PASS |

해석:

- score가 너무 낮은 쪽에만 몰리면 feature 설명력이 부족하다.
- score가 너무 높은 쪽에만 몰리면 threshold 설계가 무의미해질 수 있다.
- threshold 근처에 분포가 있어야 decision boundary를 검증할 수 있다.

### 3.5 Hard Filter Rate

정의:

- `hard_filter_passed == false` 비율

판단 기준:

| 지표 | 기준 | 판정 |
|---|---:|---|
| Hard Filter Rate | 0% ~ 10% | PASS |
| Hard Filter Rate | 10% ~ 25% | CAUTION |
| Hard Filter Rate | 25% 초과 | FAIL |

해석:

- hard filter는 최소한의 비정상 데이터 차단용이므로 과도하게 높으면 안 된다.

### 3.6 Logging Completeness

반드시 확인:

- `score_breakdown` 항상 존재
- `total_score` 항상 기록
- `run_id` 누락 없음
- `symbol` 누락 없음
- `legacy_entry_decision` / `scoring_entry_decision` 누락 없음

판단 기준:

| 조건 | 판정 |
|---|---|
| 위 항목 중 하나라도 누락 | FAIL |
| 모든 항목 기록 | PASS |

## 4. 최종 Go-Live 조건

아래 조건을 **모두** 만족하면 `enabled` 전환 가능:

1. Decision Divergence Rate < 30%
2. `scoring BUY / legacy WAIT` 케이스가 0이 아니고, 의미 있는 비율로 존재
3. Hard Filter Rate < 25%
4. Score distribution이 threshold 근처에 분포
5. logging completeness FAIL 없음
6. shadow 로그에서 명확한 `legacy missed opportunity` 패턴이 수동 검토로 확인됨

## 5. 즉시 ENABLED 금지 조건

아래 중 하나라도 해당하면 `enabled` 전환 금지:

- divergence > 40%
- hard filter > 30%
- score가 대부분 0 또는 1
- `scoring BUY / legacy WAIT`가 거의 없음
- logging completeness FAIL

## 6. 적용 체크리스트 요약

| 항목 | PASS 기준 | FAIL 기준 |
|---|---|---|
| Decision Divergence Rate | < 30% | > 40% |
| Scoring BUY / Legacy WAIT | 10% ~ 25% 또는 최소 1건 이상 유의미 | 0% 또는 > 40% |
| Scoring WAIT / Legacy BUY | 0% ~ 20% | > 30% |
| Score Distribution | threshold 근처 분포 존재 | 0/1 또는 5+ 쏠림 |
| Hard Filter Rate | < 25% | > 30% |
| Logging Completeness | 누락 없음 | 하나라도 누락 |

## 7. 실제 로그 적용 방식

shadow 로그 검증 시 최소 아래 필드를 기준으로 집계한다:

- `run_id`
- `symbol`
- `hard_filter_passed`
- `hard_filter_fail_reasons`
- `total_score`
- `score_breakdown`
- `entry_threshold`
- `score_passed`
- `legacy_entry_decision`
- `scoring_entry_decision`
- `primary_reason_code`

권장 분석 순서:

1. 최근 30~50개 run 수집
2. divergence 집계
3. `scoring BUY / legacy WAIT`와 `scoring WAIT / legacy BUY` 분리 집계
4. `hard_filter_passed == false` 비율 계산
5. `total_score` 분포와 threshold 근처 케이스 확인
6. 대표 케이스를 수동 리뷰해서 missed opportunity / false positive 여부 확인

## 8. Phase 5-3 연결 주석

- 현재 scoring은 monitor 내부 local rule이다.
- 향후 strategist/commander policy ownership 구조로 이전될 수 있다.
- 본 문서는 정식 policy 설계 문서가 아니라, 현재 shadow 검증 기반의 임시 운영 판단 기준이다.
