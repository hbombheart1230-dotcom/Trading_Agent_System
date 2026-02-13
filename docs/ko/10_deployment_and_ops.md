# 10. 배포/운영/런북

## 10.1 배포 모델(권장)
- 단일 머신(초기): cron/스크립트 기반 실행
- 중기: 컨테이너화 + 스케줄러
- 장기: LangGraph 서버 + 작업 큐 + 관측 스택

## 10.2 운영 체크리스트
- [ ] KIWOOM_MODE 확인(mock/real)
- [ ] EXECUTION_ENABLED 확인
- [ ] ALLOW_REAL_EXECUTION 확인
- [ ] SYMBOL_ALLOWLIST 확인
- [ ] MAX_QTY / MAX_NOTIONAL 확인
- [ ] 로그 경로/권한 확인

## 10.3 사고 대응(런북)
### 실행이 안됨
1) EXECUTION_ENABLED=false 확인
2) real mode guard 차단 여부 확인
3) allowlist mismatch 확인
4) max notional 초과 확인

### 잘못된 실행이 발생할 위험
1) 즉시 EXECUTION_ENABLED=false 전환
2) open orders 조회 후 cancel (승인 정책 적용)
3) run_id 기반으로 영향 범위 파악
