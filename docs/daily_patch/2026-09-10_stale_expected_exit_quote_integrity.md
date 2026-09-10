# 2026-09-10 Stale Expected Exit Quote Integrity

## Incident

- Opening Alpha bought `024060` at 09:08 and the broker accepted 57 shares.
- The position average was 13,340 and the fresh Kiwoom/account price reached
  15,710, but Monitor continued to hold.
- The cost-aware profit check reused the entry-time best bid of 13,110 as the
  expected exit price. That stale quote incorrectly produced
  `expected_exit_profit_floor_not_met` despite a large gross profit.

## Fix

- Expected-exit bid/ask inputs now require quote freshness and price consistency.
- A quote older than 90 seconds is excluded from expected-exit calculations.
- A quote whose best bid differs from the effective current price by more than
  1.5% is also excluded as conflicting evidence.
- Rejected quote provenance is retained through Monitor observability:
  observed epoch, age, divergence, rejection flag and reason.
- Existing hard-stop price revalidation, entry rules, Scanner ranking, cost
  thresholds and broker submission semantics are unchanged.

## Runtime Verification

- After restart, Monitor evaluated the same position using the fresh account
  price and emitted `SELL / take_profit` at 15,500.
- Broker accepted the 57-share sell with order number `0083909`.
- The following cycle reported zero open positions and generated the completed
  trade report bundle.

## Tests

- Incident regression and hard-stop cross-checks: `4 passed`.
- Monitor exit focused regression: `68 passed`.
- The production-path write warning during the second run was caused by the
  concurrently running live process, not by pytest output escaping isolation.

