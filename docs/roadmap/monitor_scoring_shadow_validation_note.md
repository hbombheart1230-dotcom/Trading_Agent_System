# Monitor Scoring Shadow Validation Note

## 1. 목적

- 현재 monitor scoring은 실험용/검증용 local scoring이다.
- 이 scoring은 아직 정식 policy ownership 구조가 아니다.
- Phase 5-3 전까지 scoring ownership은 monitor 내부 임시 로직으로 유지한다.
- 이 문서는 정식 설계 문서를 대체하지 않고, pre-5-3 shadow validation 운영 메모만 제공한다.

## 2. 현재 상태

### Disabled

- `MONITOR_SCORING_ENABLED=false`
- `MONITOR_SCORING_SHADOW_MODE=false`
- 실제 진입 판단은 기존 legacy monitor logic 그대로 사용한다.
- scoring 관련 필드는 기본값 또는 disabled 상태로만 기록된다.

### Shadow

- `MONITOR_SCORING_ENABLED=false`
- `MONITOR_SCORING_SHADOW_MODE=true`
- 실제 진입 판단은 기존 legacy monitor logic 그대로 유지한다.
- scoring 결과는 artifact/event에 함께 기록된다.
- 이 모드는 장중 검증 기본 모드로 간주한다.

### Enabled

- `MONITOR_SCORING_ENABLED=true`
- `MONITOR_SCORING_SHADOW_MODE=false`
- hard filter 통과 + score threshold 충족 시 scoring 결과가 실제 진입 판단에 영향을 줄 수 있다.
- 이 모드는 shadow 검증 누적 전에는 기본 운영 모드로 권장하지 않는다.

## 3. 운영 원칙

- 기본 권장 모드는 `shadow`다.
- `enabled`는 장중 제한 검증 전까지 기본 비권장으로 둔다.
- 현재 scoring weights/threshold는 monitor 내부 hardcoded 임시값이다.
- 현재 scoring은 정식 policy source처럼 다루지 않는다.
- strategist/scanner/commander ownership으로 올리는 작업은 Phase 5-3 전에는 진행하지 않는다.
- reporter/operator UI 구조 정리와 scoring ownership 정리는 분리해서 다룬다.

## 4. 장중 검증 체크리스트

- `legacy_entry_decision` vs `scoring_entry_decision` 차이 빈도 확인
- `score_breakdown`, `total_score`, `entry_threshold`, `score_passed`가 정상 기록되는지 확인
- `hard_filter_failed`가 과도하게 많이 발생하는지 확인
- score는 충분한데 legacy가 막는 패턴이 존재하는지 확인
- legacy는 BUY인데 scoring은 WAIT인 케이스가 과도한지 확인
- 주요 no-trade 구간에서 scoring 설명력이 실제 blocker와 맞는지 확인
- enabled 전환 전, shadow 기준으로 BUY 직전/WAIT 직전 케이스 비교 로그를 확보했는지 확인

## 5. Enabled 전환 조건

- shadow 로그가 충분히 누적되어 있을 것
- false positive가 과도하게 증가하지 않을 것
- hard filter가 과도하게 진입을 막지 않을 것
- BUY 직전 케이스에서 score 설명력이 실제 상황과 맞을 것
- score threshold를 넘는 케이스가 일관된 entry quality를 보일 것
- legacy 대비 enabled 차이가 설명 가능하고 재현 가능할 것

## 6. Phase 5-3 연결 메모

- 현재 scoring weights/threshold는 monitor local ownership이다.
- 이 값들은 향후 Phase 5-3에서 strategist/commander policy ownership으로 이전될 수 있다.
- 다만 이번 scoring은 Phase 5-3의 대체 구현이 아니다.
- 본 문서는 pre-5-3 validation note이며, 정식 ownership 설계 변경 문서가 아니다.
- 따라서 기존 Phase 5-2, 5-2-2, 5-3 로드맵 문서는 수정하지 않고 유지한다.
