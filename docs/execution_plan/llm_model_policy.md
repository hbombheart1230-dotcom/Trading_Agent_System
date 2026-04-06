# LLM Model Selection Policy (Phase 5-4 / 6-1)

## 목적
이 문서는 Trading Agent System에서 LLM을 **역할별로 안정적이고 예측 가능하게 사용하는 기준**을 정의한다.  
Codex는 이 문서를 기준으로 env 설정 및 모델 선택 로직을 구성해야 한다.

---

# 1. 핵심 원칙

## 1.1 예측 가능성이 최우선
- auto / free 모델 사용 금지 (실전 경로)
- 비용보다 **일관성**이 더 중요
- 동일 입력 → 유사 출력 구조 유지

## 1.2 역할 기반 모델 선택
- 모델은 기능이 아니라 **역할 기준으로 분리**
- strategist / brief / report 각각 다르게 사용

## 1.3 LLM 최소 사용
- Commander: 사용 금지
- Scanner: 사용 금지
- Monitor: 사용 금지
- Reporter: 제한적 사용
- Strategist: 핵심 사용

---

# 2. 역할별 모델 정책

## 2.1 Strategist (핵심)
역할:
- 전략 생성
- playbook
- policy proposal

### 설정
- Primary + Fallback 구조 필수

### 추천 모델
- Primary: deepseek/deepseek-v3.2
- Fallback: minimax/minimax-m2.5

### 특징
- reasoning 중요
- 실패 시 trading block 영향 큼

---

## 2.2 Operator Brief (장중)
역할:
- 빠른 상태 요약
- 운영 판단 보조

### 추천 모델
- minimax/minimax-m2.5

### 특징
- 빠름
- 안정성 중요
- hallucination 최소화

---

## 2.3 Trade Report (매매 단위)
역할:
- entry / exit 회고
- lesson 정리

### 추천 모델
- 기본: minimax/minimax-m2.5
- 필요 시: moonshotai/kimi-k2.5

---

## 2.4 Daily / Weekly / Monthly Report
역할:
- 장후 해석
- 전략 피드백

### 추천 모델
- moonshotai/kimi-k2.5

### 특징
- 긴 문맥
- 해석력 중요

---

# 3. 추천 env 설정

```env
OPENROUTER_DEFAULT_MODEL=minimax/minimax-m2.5

# --- Strategist ---
AI_STRATEGIST_PROVIDER=openai
AI_STRATEGIST_ENDPOINT=https://openrouter.ai/api/v1/chat/completions
AI_STRATEGIST_MODEL_PRIMARY=deepseek/deepseek-v3.2
AI_STRATEGIST_MODEL_FALLBACK=minimax/minimax-m2.5
AI_STRATEGIST_TIMEOUT_SEC=15
AI_STRATEGIST_MAX_TOKENS=8192
AI_STRATEGIST_RETRY_MAX=2
AI_STRATEGIST_STRICT=true

# --- Reporter / UI ---
OPENROUTER_MODEL_OPERATOR_UI=minimax/minimax-m2.5
OPENROUTER_MODEL_TRADE_REPORT=minimax/minimax-m2.5
OPENROUTER_MODEL_REPORTER_FINAL=moonshotai/kimi-k2.5
```

---

# 4. 모델 선택 전략 (중요)

## 4.1 Strategist
```
Primary → Retry → Fallback
```

## 4.2 Reporter
```
Deterministic facts → LLM narrative
```

## 4.3 Operator Brief
```
Deterministic 80% + LLM 20%
```

---

# 5. 금지 사항

- auto 모델 사용 금지 (실시간 경로)
- free 모델 의존 금지
- report facts를 LLM으로 생성 금지
- strategist fallback 없이 운영 금지

---

# 6. 향후 확장 방향

현재: env 기반

미래:
```
select_model(role, phase, strict)
```

예:
- strategist → high reasoning
- brief → fast/cheap
- report → narrative strong

---

# 7. 최종 요약

- Strategist는 Primary + Fallback 필수
- Brief는 빠르고 안정적으로
- Report는 해석 중심
- LLM은 최소한으로, 정확하게 사용

---

# 8. 한 줄 결론

LLM은 많을수록 좋은 게 아니라  
**정확한 위치에 정확하게 써야 시스템이 안정된다**
