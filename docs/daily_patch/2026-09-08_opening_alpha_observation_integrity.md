# 2026-09-08 Opening Alpha Observation Integrity

## Incident

Samyang (145990) entered through CONFIRMED_RECURRENT_RANK at 09:14:53 KST.
15 shares were filled; broker-reported realized PnL was -12,124 KRW (-1.71%).
The first Rank observation at 09:12:31 contained no price. A passing pre-submit
guard result was not retained. Summary text incorrectly described a one-share
trade and repeated unverified LLM causal claims about entry blockers.

## Corrections

- Rank observation capture reuses existing selected price, then a quote observed
  within 90 seconds, then a timestamped minute close within 120 seconds.
  Future/undated/stale fallback candles cannot populate the missing price.
  There are no additional API requests. No unavailable historical price is invented.
- Applicable pre-submit guard decisions are logged before submission and retained
  in execution results and canonical Executor artifacts, whether allowed or blocked.
- Cost narrative no longer hardcodes one share.
- Opening Alpha LLM causal interpretation/actions are withheld from the summary
  pending evidence validation. Original response artifacts remain unchanged.

## Scope

No eligibility, quantity, cost threshold, stop or horizon changes.
Recording a previously missed price enables the existing drift check to use that
observation on later ticks; this is evidence restoration, not a threshold change.
Today's missing initial price and missing passing guard record remain historical
gaps. Regenerated Markdown is not proof those fields existed at submission time.
The running process is not restarted by this correction.

## Verification

- Source-copy validation directory: 336 focused tests passed, process exit 0.
- Full suite in the same separate source directory: 3045 passed, 1 skipped,
  3 failed. This is NOT a clean full regression.
- Failures reproduced independently in the unchanged decide_trade hold/cooldown
  tests, in an environment without the production broker cost profile:
  test_m20_2_decide_trade_exit_policy_max_hold_triggers_sell,
  test_m20_2_decide_trade_blocks_fast_sell_with_min_hold_guard,
  test_sell_cooldown_env_alias_blocks_fast_sell.
- The full-suite manifest also detected reports/metrics/metrics_2026-04-08
  JSON/Markdown creation inside the separate validation directory. This remains
  a test-isolation follow-up; no automatic cleanup was performed.
- The first in-workspace focused run had 211 passing assertions but a nonzero
  exit due to concurrent live artifact writes. It is not counted as a clean run.
- Today's Samyang Markdown was regenerated from existing report/summary JSON.
  Broker truth, raw LLM responses and historical missing-price records were not
  modified. No runtime restart, commit or push was performed.

## Follow-up Corrections (2026-09-09)

- Restored the three stale exit-policy assertions to the current safety contract:
  max-hold emits SELL when no cost floor blocks it; minimum-hold/cooldown converts
  that SELL attempt to NOOP with an explicit sell_guard_min_hold reason.
- Metrics report output now passes through the general pytest write-path resolver.
  Production paths remain unchanged outside pytest, while a default relative
  reports/metrics path cannot escape into the repository during tests.
- Final clean-room full regression after both corrections: 3048 passed,
  1 skipped, 0 failed. The production-path manifest reported no leak.
