# Daily Report (2026-04-28)

---

## 운영 요약

- 총 거래: 9건  
- 성과: **2승 / 6패 / 평균 -0.40%**

### 잘된 점
- 체결 및 로그 정상 기록
- 후보 선정(스캐너)은 시장 강세 종목 잘 포착

### 문제점
1. Monitor 단독 경로 100% (구조 편향)
2. pullback_not_mature 과다 → 진입 실패 반복
3. peak_drawdown 조기 청산 → 수익 유지 실패

### 원인 해석
**진입은 늦고, 청산은 빠른 구조**

### 권고 액션
1. exit 정책 완화 (drawdown activation)
2. entry 조건 완화 (pullback / rebound)
3. scanner → monitor alignment 점검

---

## 핵심 패턴

- Monitor-only 비율: 100%
- 차순위 재평가 반복
- threshold 근접 진입 다수

---

## 종목별 요약

- 000660: 손실 (-0.97%) / 진입-청산 구조 문제
- 기타 종목: 유사 패턴 반복

---

## 상세 분석

> 세부 거래 및 로그 기반 분석은 개별 ai_trade_report.md 참조
