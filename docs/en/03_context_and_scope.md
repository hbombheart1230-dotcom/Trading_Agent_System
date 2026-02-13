# 3. Scope / Non-scope / Assumptions

## 3.1 In Scope
- Kiwoom REST routing for mock/real
- Approval (manual/auto) and guard framework
- Intent-centric execution model (OrderIntent)
- Observability/reporting driven by event logs
- Unified artifacts across M1~M15

## 3.2 Out of Scope
- HFT / ultra-low-latency optimization
- Full multi-broker support beyond Kiwoom (future extension)
- News crawling and model-quality optimization (agent intelligence domain)

## 3.3 Operational Assumptions
- Operators can manage env/config.
- Secrets are never committed to Git.
- Real mode is used only after sufficient mock validation.
