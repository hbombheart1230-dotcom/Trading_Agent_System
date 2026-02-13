# 6. Contracts: IO + DTO + Stability Rules

## 6.1 IO Contracts (Core)
- OrderIntent: Monitor → Supervisor
- SupervisorDecision: Supervisor → Executor
- RunConfig / TradePlan / ScanResult: pipeline contracts

## 6.2 DTO Contracts (Core)
- AccountSnapshot
- MarketSnapshot
- CandleSeries
- UniverseResult
- OrderResult / OrderStatus

## 6.3 Stability Rules
- required fields must never be removed
- additive changes are allowed (optional/defaults)
- semantic changes are prohibited (add a new field instead)
- raw/extra fields serve as safe extension buffers

## 6.4 Schema Versioning Policy (Recommended)
- dto_version: "v1" fixed
- introduce v2 in parallel for breaking changes, then migrate
