# 11. Testing / Quality / Regression

## 11.1 Required Coverage Scenarios
- mock/manual/auto + execution enable/disable
- real mode guard (ALLOW_REAL_EXECUTION, allowlist)
- max qty / max notional guard
- legacy AUTO_APPROVE true/false compatibility
- manual approval path output/flow

## 11.2 Testing Principles
- tests must be deterministic and reproducible
- optionize approve/reject by intent_id to remove flakes
- external APIs must be mocked/stubbed

## 11.3 Quality Gates (Recommended)
- minimum coverage threshold in CI
- schema diff checks on contract changes
