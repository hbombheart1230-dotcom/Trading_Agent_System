# Agents

## Supervisor (감독관)
- owns risk limits
- validates OrderIntent against policy
- approves / rejects / modifies
- can pause/stop the system

## Strategist (전략가)
- chooses candidates (3~5)
- defines scenarios (entry/add/stop/take-profit)
- decides what features/news to consult

## Scanner (스캐너)
- uses skills to fetch data accurately
- computes features (volatility, momentum, volume spike, etc.)
- returns ranked results + gaps

## Monitor (모니터)
- watches chosen primary (initially 1 symbol)
- emits ActionProposal / OrderIntent
- **never places orders**

## Reporter (리포터)
- reads EventLog
- produces daily report / trade report / improvement suggestions
