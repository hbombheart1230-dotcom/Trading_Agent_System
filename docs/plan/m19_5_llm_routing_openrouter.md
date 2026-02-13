# M19-5: OpenRouter LLM 라우팅(역할별 모델) 표준화

## 목적
- 에이전트(지휘자/전략가/스캐너/모니터/리포터/감독관)가 **서로 다른 모델**을 사용할 수 있도록 라우팅을 표준화한다.
- 지금은 OpenRouter를 사용하지만, 나중에 OpenAI/사내 게이트웨이/로컬 모델로 교체해도 **내부 인터페이스를 유지**한다.
- 테스트 우선: `DRY_RUN=1`에서는 절대 외부 호출을 하지 않는다.

## 핵심 구성
- `libs/llm/openrouter_client.py` : OpenRouter HTTP 호출 클라이언트
- `libs/llm/llm_router.py` : 역할(Role) → 모델(Model) 라우팅 + text 반환
- `libs/llm/__init__.py` : 표준 import 진입점 (`from libs.llm import LLMRouter`)

> ⚠️ `libs/llm/router.py`는 과거 호환용으로 유지(legacy). 신규 코드는 `libs.llm.LLMRouter`를 사용.

## 환경변수(권장)
- `OPENROUTER_API_KEY`
- `OPENROUTER_DEFAULT_MODEL`
- `OPENROUTER_MODEL_<ROLE>` (역할별 모델)
  - 예: `OPENROUTER_MODEL_STRATEGIST`, `OPENROUTER_MODEL_SCANNER`, `OPENROUTER_MODEL_REPORTER`
- (옵션) `OPENROUTER_DEFAULT_TEMPERATURE`, `OPENROUTER_DEFAULT_MAX_TOKENS`

## 라우팅 우선순위
`LLMRouter.resolve(role, policy)`에서 모델 결정 우선순위:
1. `policy['openrouter_model']` 또는 `policy['model']`
2. `OPENROUTER_MODEL_<ROLE>`
3. `OPENROUTER_DEFAULT_MODEL`
4. fallback: `openai/gpt-4o-mini`

## 사용 예시
```python
from libs.llm import LLMRouter

router = LLMRouter.from_env()
text = router.chat(
    role="STRATEGIST",
    messages=[
        {"role": "system", "content": "You are a trading strategist."},
        {"role": "user", "content": "Pick 3 candidates."},
    ],
    policy={"temperature": 0.2, "max_tokens": 256},
)
```

## DRY_RUN 규칙
- `DRY_RUN=1`이면 노드/스코어러가 외부 네트워크 호출을 하지 않도록 설계한다.
- LLM 호출이 필요한 경우에도 테스트는 `mock_*` 상태값으로 주입해 검증한다.

## 다음 단계(M20 후보)
- (선택) 역할별 프롬프트 템플릿/스키마(전략가/스캐너/리포터) 추가
- (선택) 모델별 비용/latency 관측치 로깅 + 캐시(동일 프롬프트 재사용)
