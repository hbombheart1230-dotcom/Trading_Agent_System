# 10. Deployment / Operations / Runbooks

## 10.1 Deployment Models (Recommended)
- single host (early): cron/scripts
- mid: containerization + scheduler
- long term: LangGraph service + job queue + observability stack

## 10.2 Operator Checklist
- [ ] confirm KIWOOM_MODE (mock/real)
- [ ] confirm EXECUTION_ENABLED
- [ ] confirm ALLOW_REAL_EXECUTION
- [ ] confirm SYMBOL_ALLOWLIST
- [ ] confirm MAX_QTY / MAX_NOTIONAL
- [ ] confirm log path/permissions

## 10.3 Incident Runbooks
### Execution is blocked
1) check EXECUTION_ENABLED=false
2) check real mode guard
3) check allowlist mismatch
4) check max notional exceeded

### Risk of unintended execution
1) immediately set EXECUTION_ENABLED=false
2) query open orders and cancel (policy-gated)
3) use run_id to scope and audit the impact
