# M7-1 – Supervisor (Risk Guardrails)

## Purpose
Enforce hard risk guardrails *before* any order can be prepared/executed.

## Inputs
- intent: buy/sell/open/close
- context (dict): daily_pnl_ratio, open_positions, per_trade_risk_ratio, last_order_epoch, now_epoch

## Outputs
- AllowResult(allow, reason, details)

## Rules (env-driven)
- RISK_DAILY_LOSS_LIMIT
- RISK_PER_TRADE_LOSS_LIMIT
- RISK_MAX_POSITIONS
- RISK_ORDER_COOLDOWN_SEC

## Notes
- Supervisor must be deterministic and must not modify env/config.
- AI can only propose changes later; human approval required.
