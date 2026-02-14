# M7 Closeout

## 목표
주문 실행 이전 단계에서 **안전장치(헌법)** 를 고정하고, 주문 요청을 **dry-run** 형태로만 준비한다.

## 산출물
### M7-1 Supervisor
- env 기반 하드 가드레일 집행
  - RISK_DAILY_LOSS_LIMIT
  - RISK_PER_TRADE_LOSS_LIMIT
  - RISK_MAX_POSITIONS
  - RISK_ORDER_COOLDOWN_SEC
- 입력: intent + risk_context
- 출력: allow/deny + reason

### M7-2 OrderClient (dry-run only)
- Supervisor 승인 없으면 allowed=false
- 승인 시에도 네트워크 호출 없이 요청 형태만 생성
- 토큰 ensure 또한 기본 dry-run

### M7-3 Demo
- 스크립트: `scripts/demo_m7_dry_run_pipeline.py`
- 흐름: Discovery(M3) → Planner(M4) → Prepare(M5) → Supervisor(M7-1) → Order Dry-run(M7-2)

## 사용 방법
```bash
python scripts/demo_m7_dry_run_pipeline.py
```

## 보장
- 실주문/실호출 0%
- 리스크 가드 선집행
- 요청 형태(JSON)로만 결과 확인 가능
