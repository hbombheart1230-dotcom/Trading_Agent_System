# Strategist LLM Configuration Guide (Phase 5-4)

## 목적
이 문서는 Strategist LLM을 Primary + Fallback 구조로 안정적으로 운영하기 위한 기준 문서이다.
Codex는 이 문서를 기준으로 Strategist LLM 호출 로직 및 env 구성을 수정해야 한다.

---

# 1. 핵심 결론

- Strategist는 단일 모델이 아니라 Primary + Fallback 2단 구조로 운영
- Primary 실패 시 동일 모델 반복이 아니라 다른 모델로 전환
- Strict 모드 유지 시 fallback은 필수

---

# 2. 왜 2모델 구조가 필요한가

현재 구조:
- 동일 모델 retry

문제:
- timeout → 계속 timeout
- JSON 오류 → 계속 동일 오류
- provider 문제 → 동일 실패 반복

해결:
- fallback 모델로 실패 패턴 자체 변경

---

# 3. 모델 역할

## Primary (DeepSeek V3.2)
- 강한 reasoning 능력
- 전략 생성 품질 핵심

## Fallback (MiniMax M2.5)
- 빠르고 안정적인 응답
- fallback 안정성 확보용

---

# 4. 추천 env 설정

```env
AI_STRATEGIST_PROVIDER=openai
AI_STRATEGIST_ENDPOINT=https://openrouter.ai/api/v1/chat/completions

AI_STRATEGIST_MODEL_PRIMARY=deepseek/deepseek-v3.2
AI_STRATEGIST_MODEL_FALLBACK=minimax/minimax-m2.5

AI_STRATEGIST_TIMEOUT_SEC=15
AI_STRATEGIST_MAX_TOKENS=8192
AI_STRATEGIST_RETRY_MAX=2

AI_STRATEGIST_STRICT=true
```

---

# 5. 호출 전략

```
1차: primary 호출
2차: primary retry
3차: fallback 호출
```

---

# 6. pseudo code

```python
def call_strategist_llm(payload):
    try:
        return call_model(PRIMARY)
    except:
        try:
            return call_model(PRIMARY)
        except:
            return call_model(FALLBACK)
```

---

# 7. 필수 메타데이터

```json
{
  "llm_call_trace": {
    "primary_attempted": true,
    "primary_failed": true,
    "fallback_used": true,
    "final_model": "minimax/minimax-m2.5"
  }
}
```

---

# 8. strict 모드 의미

- LLM 실패 → 매수 금지
- fallback 도입 → 시스템 안정성 확보

---

# 9. 주의사항

- fallback 결과 low confidence 표시
- final_model 반드시 기록
- silent fallback 금지

---

# 10. 핵심 원칙

Primary는 성능, Fallback은 안정성
