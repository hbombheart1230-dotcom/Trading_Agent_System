# 11. 테스트/품질/회귀

## 11.1 필수 시나리오 커버리지
- mock/manual/auto + execution enable/disable
- real mode guard (ALLOW_REAL_EXECUTION, allowlist)
- max qty / max notional guard
- 레거시 AUTO_APPROVE true/false 호환
- manual approve path 출력/흐름

## 11.2 테스트 원칙
- 테스트는 결정론적으로 재현 가능해야 한다.
- intent_id 기반 승인/거절을 옵션화하여 flake 제거
- 외부 API는 mock/stub로 대체

## 11.3 품질 게이트(권장)
- CI에서 최소 커버리지 기준
- 계약 변경 시 schema diff 검사
