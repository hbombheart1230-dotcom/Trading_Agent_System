# LLM Model Selection Policy (Phase 5-4 / 6-1)

## 紐⑹쟻
??臾몄꽌??Trading Agent System?먯꽌 LLM??**??븷蹂꾨줈 ?덉젙?곸씠怨??덉륫 媛?ν븯寃??ъ슜?섎뒗 湲곗?**???뺤쓽?쒕떎.  
Codex????臾몄꽌瑜?湲곗??쇰줈 env ?ㅼ젙 諛?紐⑤뜽 ?좏깮 濡쒖쭅??援ъ꽦?댁빞 ?쒕떎.

---

# 1. ?듭떖 ?먯튃

## 1.1 ?덉륫 媛?μ꽦??理쒖슦??- auto / free 紐⑤뜽 ?ъ슜 湲덉? (?ㅼ쟾 寃쎈줈)
- 鍮꾩슜蹂대떎 **?쇨???*????以묒슂
- ?숈씪 ?낅젰 ???좎궗 異쒕젰 援ъ“ ?좎?

## 1.2 ??븷 湲곕컲 紐⑤뜽 ?좏깮
- 紐⑤뜽? 湲곕뒫???꾨땲??**??븷 湲곗??쇰줈 遺꾨━**
- strategist / brief / report 媛곴컖 ?ㅻⅤ寃??ъ슜

## 1.3 LLM 理쒖냼 ?ъ슜
- Commander: ?ъ슜 湲덉?
- Scanner: ?ъ슜 湲덉?
- Monitor: ?ъ슜 湲덉?
- Reporter: ?쒗븳???ъ슜
- Strategist: ?듭떖 ?ъ슜

---

# 2. ??븷蹂?紐⑤뜽 ?뺤콉

## 2.1 Strategist (?듭떖)
??븷:
- ?꾨왂 ?앹꽦
- playbook
- policy proposal

### ?ㅼ젙
- Primary + Fallback 援ъ“ ?꾩닔

### 異붿쿇 紐⑤뜽
- Primary: deepseek/deepseek-v3.2
- Fallback: minimax/minimax-m2.5

### ?뱀쭠
- reasoning 以묒슂
- ?ㅽ뙣 ??trading block ?곹뼢 ??
---

## 2.2 Operator Brief (?μ쨷)
??븷:
- 鍮좊Ⅸ ?곹깭 ?붿빟
- ?댁쁺 ?먮떒 蹂댁“

### 異붿쿇 紐⑤뜽
- minimax/minimax-m2.5

### ?뱀쭠
- 鍮좊쫫
- ?덉젙??以묒슂
- hallucination 理쒖냼??
---

## 2.3 Trade Report (留ㅻℓ ?⑥쐞)
??븷:
- entry / exit ?뚭퀬
- lesson ?뺣━

### 異붿쿇 紐⑤뜽
- 湲곕낯: minimax/minimax-m2.5
- ?꾩슂 ?? moonshotai/kimi-k2.5

---

## 2.4 Daily / Weekly / Monthly Report
??븷:
- ?ν썑 ?댁꽍
- ?꾨왂 ?쇰뱶諛?
### 異붿쿇 紐⑤뜽
- moonshotai/kimi-k2.5

### ?뱀쭠
- 湲?臾몃㎘
- ?댁꽍??以묒슂

---

# 3. 異붿쿇 env ?ㅼ젙

```env
OPENROUTER_DEFAULT_MODEL=minimax/minimax-m2.5

# --- Strategist ---
AI_STRATEGIST_PROVIDER=openai
AI_STRATEGIST_ENDPOINT=https://openrouter.ai/api/v1/chat/completions
AI_STRATEGIST_MODEL_PRIMARY=deepseek/deepseek-v3.2
AI_STRATEGIST_MODEL_FALLBACK=minimax/minimax-m2.5
Commander-owned strategist execution profile:
- `applied_policy.llm.strategist.execution_profile.timeout_sec = 15`
- `applied_policy.llm.strategist.execution_profile.max_tokens = 8192`
- `applied_policy.llm.strategist.execution_profile.retry_max = 2`
# `strategist.runtime.strict_mode` is Commander-owned via `applied_policy`

# --- Reporter / UI ---
OPENROUTER_MODEL_OPERATOR_UI=minimax/minimax-m2.5
OPENROUTER_MODEL_TRADE_REPORT=minimax/minimax-m2.5
OPENROUTER_MODEL_REPORTER_FINAL=moonshotai/kimi-k2.5
```

---

# 4. 紐⑤뜽 ?좏깮 ?꾨왂 (以묒슂)

## 4.1 Strategist
```
Primary ??Retry ??Fallback
```

## 4.2 Reporter
```
Deterministic facts ??LLM narrative
```

## 4.3 Operator Brief
```
Deterministic 80% + LLM 20%
```

---

# 5. 湲덉? ?ы빆

- auto 紐⑤뜽 ?ъ슜 湲덉? (?ㅼ떆媛?寃쎈줈)
- free 紐⑤뜽 ?섏〈 湲덉?
- report facts瑜?LLM?쇰줈 ?앹꽦 湲덉?
- strategist fallback ?놁씠 ?댁쁺 湲덉?

---

# 6. ?ν썑 ?뺤옣 諛⑺뼢

?꾩옱: env 湲곕컲

誘몃옒:
```
select_model(role, phase, strict)
```

??
- strategist ??high reasoning
- brief ??fast/cheap
- report ??narrative strong

---

# 7. 理쒖쥌 ?붿빟

- Strategist??Primary + Fallback ?꾩닔
- Brief??鍮좊Ⅴ怨??덉젙?곸쑝濡?- Report???댁꽍 以묒떖
- LLM? 理쒖냼?쒖쑝濡? ?뺥솗?섍쾶 ?ъ슜

---

# 8. ??以?寃곕줎

LLM? 留롮쓣?섎줉 醫뗭? 寃??꾨땲?? 
**?뺥솗???꾩튂???뺥솗?섍쾶 ?⑥빞 ?쒖뒪?쒖씠 ?덉젙?쒕떎**

