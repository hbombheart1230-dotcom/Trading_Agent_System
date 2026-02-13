# 6. 계약(Contracts): IO + DTO + 안정성 규칙

## 6.1 IO Contracts (핵심)
- OrderIntent: Monitor → Supervisor
- SupervisorDecision: Supervisor → Executor
- RunConfig / TradePlan / ScanResult: pipeline 계약

## 6.2 DTO Contracts (핵심)
- AccountSnapshot
- MarketSnapshot
- CandleSeries
- UniverseResult
- OrderResult / OrderStatus

## 6.3 안정성 규칙
- 필수 필드는 절대 삭제 금지
- 필드 추가는 허용(기본값/optional)
- 의미 변경은 금지(새 필드로 추가)
- raw/extra는 확장용 안전판

## 6.4 스키마 버저닝 정책(권장)
- dto_version: "v1" 고정
- breaking change 필요 시 v2 병렬 도입 후 마이그레이션
