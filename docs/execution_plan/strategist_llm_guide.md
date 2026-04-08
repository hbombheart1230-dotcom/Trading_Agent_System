# Strategist LLM Configuration Guide (Phase 5-4)

## 紐⑹쟻
??臾몄꽌??Strategist LLM??Primary + Fallback 援ъ“濡??덉젙?곸쑝濡??댁쁺?섍린 ?꾪븳 湲곗? 臾몄꽌?대떎.
Codex????臾몄꽌瑜?湲곗??쇰줈 Strategist LLM ?몄텧 濡쒖쭅 諛?env 援ъ꽦???섏젙?댁빞 ?쒕떎.

---

# 1. ?듭떖 寃곕줎

- Strategist???⑥씪 紐⑤뜽???꾨땲??Primary + Fallback 2??援ъ“濡??댁쁺
- Primary ?ㅽ뙣 ???숈씪 紐⑤뜽 諛섎났???꾨땲???ㅻⅨ 紐⑤뜽濡??꾪솚
- Strict 紐⑤뱶 ?좎? ??fallback? ?꾩닔

---

# 2. ??2紐⑤뜽 援ъ“媛 ?꾩슂?쒓?

?꾩옱 援ъ“:
- ?숈씪 紐⑤뜽 retry

臾몄젣:
- timeout ??怨꾩냽 timeout
- JSON ?ㅻ쪟 ??怨꾩냽 ?숈씪 ?ㅻ쪟
- provider 臾몄젣 ???숈씪 ?ㅽ뙣 諛섎났

?닿껐:
- fallback 紐⑤뜽濡??ㅽ뙣 ?⑦꽩 ?먯껜 蹂寃?
---

# 3. 紐⑤뜽 ??븷

## Primary (DeepSeek V3.2)
- 媛뺥븳 reasoning ?λ젰
- ?꾨왂 ?앹꽦 ?덉쭏 ?듭떖

## Fallback (MiniMax M2.5)
- 鍮좊Ⅴ怨??덉젙?곸씤 ?묐떟
- fallback ?덉젙???뺣낫??
---

# 4. 異붿쿇 env ?ㅼ젙

```env
AI_STRATEGIST_PROVIDER=openai
AI_STRATEGIST_ENDPOINT=https://openrouter.ai/api/v1/chat/completions

AI_STRATEGIST_MODEL_PRIMARY=deepseek/deepseek-v3.2
AI_STRATEGIST_MODEL_FALLBACK=minimax/minimax-m2.5

Commander-owned strategist execution profile:
- `applied_policy.llm.strategist.execution_profile.timeout_sec = 15`
- `applied_policy.llm.strategist.execution_profile.max_tokens = 8192`
- `applied_policy.llm.strategist.execution_profile.retry_max = 2`

# `strategist.runtime.strict_mode` is Commander-owned via `applied_policy`
```

---

# 5. ?몄텧 ?꾨왂

```
1李? primary ?몄텧
2李? primary retry
3李? fallback ?몄텧
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

# 7. ?꾩닔 硫뷀??곗씠??
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

# 8. strict 紐⑤뱶 ?섎?

- LLM ?ㅽ뙣 ??留ㅼ닔 湲덉?
- fallback ?꾩엯 ???쒖뒪???덉젙???뺣낫

---

# 9. 二쇱쓽?ы빆

- fallback 寃곌낵 low confidence ?쒖떆
- final_model 諛섎뱶??湲곕줉
- silent fallback 湲덉?

---

# 10. ?듭떖 ?먯튃

Primary???깅뒫, Fallback? ?덉젙??
