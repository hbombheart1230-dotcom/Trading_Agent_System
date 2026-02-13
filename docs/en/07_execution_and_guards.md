# 7. Execution Control / Guards / Approval Model

## 7.1 Approval Modes
- auto: approved intents execute immediately (still must pass guards)
- manual: decisions remain pending until operator approval

Legacy AUTO_APPROVE compatibility:
- true → auto
- false → manual
- "auto"/"manual" strings may also be accepted

## 7.2 Guard Precedence
1) EXECUTION_ENABLED == false → always block
2) KIWOOM_MODE == real AND ALLOW_REAL_EXECUTION != true → block
3) SYMBOL_ALLOWLIST mismatch → block
4) MAX_QTY exceeded → block
5) MAX_NOTIONAL exceeded → block
6) Idempotency (already executed) → block

## 7.3 “Real approve API” (Recommended for M16)
- approve(intent_id) → sets status=approved
- if execution_enabled, proceed to Execution Layer
- enables reproducible manual-approval tests

## 7.4 Safe Operational Defaults
- default: EXECUTION_ENABLED=false
- real mode: require allowlist
- conservative max_notional relative to account size
