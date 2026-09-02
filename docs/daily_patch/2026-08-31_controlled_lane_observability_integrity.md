# 2026-08-31 Controlled Lane Observability and Test Integrity

## Scope

This patch completes observability around the already implemented Opening Alpha,
Q10 and Q12 controlled mock policies. It does not relax or tighten trading
behavior.

## Existing Behavior Confirmed

- Opening Alpha remains limited to `HIGH_COMMON_DIRECTIONAL` or
  `CONFIRMED_RECURRENT_RANK`.
- The Scanner authority Rank-1 fallback from the earlier point-in-time wiring
  patch remains in force.
- Q10 08:50 and Q12 08:55 point-in-time capture paths remain separate from the
  09:00 intraday loop.
- Q10/Q12 controlled candidates remain independent of Strategist/Scanner early
  termination.

## Observability Fixes

- Opening Alpha now records every evaluated Rank-1 candidate during the first
  20 minutes, including rejected candidates and the exact rejection reason.
- Duplicate evaluation writes for the same `run_id` and symbol are ignored.
- Operator daily summaries now expose Q10 Semiconductor, Q10 Index, Q12
  BTC-Woori and Opening Alpha evaluation, attempt and accepted-submission state.
- The Q12 report now separates ordinary intraday shadow-forward evidence from
  mandatory 08:55 controlled-lane input evidence.

## Artifact Integrity Fix

- `tests/test_execute_from_packet.py` now redirects canonical agent artifacts to
  pytest temporary storage.
- This prevents synthetic executor/supervisor outputs from contaminating the
  live `reports/canonical/YYYY-MM-DD` tree.
- Previously generated directories are eligible for removal only when their
  payload contains an explicit `.pytest-work` path.

## Verification

- Focused controlled-lane, Q10, Q12, operator-summary and execution tests:
  `115 passed`.
- No entry, exit, strategy, threshold, approval or broker behavior was changed.
