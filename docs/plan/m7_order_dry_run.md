# M7-2 – Order Client (Dry-run only)

## Purpose
Prepare an order request with Supervisor guardrails, without sending any network request.

## Modules
- `libs/order_client.py`
  - `dry_run_order(prepared_request, intent, risk_context)`
  - Always returns a dry-run payload (never calls HTTP)
- `graphs/nodes/prepare_order_dry_run.py`
  - Validates required params via `ApiRequestBuilder`
  - Applies Supervisor gate
  - Outputs `state['order_dry_run']`

## Safety
- No trading side effects
- Token ensure is executed in dry-run mode by default
- Supervisor must allow before producing allowed=true
