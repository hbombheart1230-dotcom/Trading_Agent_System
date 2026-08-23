# Immediate Opening Probe Runtime Validation - 2026-08-21

## Decision Authority

This is the only next fixed runtime validation candidate selected by the Alpha
Research Board. It does not change live trading behavior.

- candidate: `IMMEDIATE_OPENING_PROBE`
- target: live-research net return at `+5m`
- observation unit: first eligible observation per day-symbol
- source: existing opening Rank-1 observer artifacts
- behavior: shadow/evaluation only

No new opening lane, threshold, Scanner score, Monitor trigger, order path, size, or
exit rule is added by this validation.

## Why This Candidate Remains

Existing evidence contains 12 independent episodes:

- win rate: 75.0%
- average live-net return: +1.9156%
- median live-net return: +0.9049%
- profit factor: 6.5041
- excluding the largest single winner: +0.8079%, PF 3.1279
- every single-symbol and single-day leave-one-out remains cost-positive with PF at
  or above 1.20

The other reviewed candidates were closed or left as background measurement:

- generic `risk_band=HIGH`: contributor-dependent, closed;
- `POST_CROSS_EXTENDED`: negative prospective result, closed;
- `DISLOCATION_REBOUND`: symbol-contributor-dependent, closed;
- BTC-Woori v2-only: 2026-08-21 day-dependent, closed;
- `CONFIRMED_RECURRENT_RANK`: two episodes, background measurement only;
- Samsung/Hynix corrected baseline: one corrected day, background measurement only.

## Fixed Runtime Window

- duration: next five full valid trading days
- start: first full trading day after this contract
- extension: prohibited
- implementation or artifact-failure days: recorded as invalid; the calendar window
  is not silently retuned
- no opportunity: valid zero-episode day

At the end of the fifth day, the result is finalized even when the sample is small.

## Required Evidence

- at least 5 independent day-symbol episodes;
- at least 90% `+5m` forward coverage;
- average live-net return greater than 0%;
- median live-net return greater than 0%;
- profit factor at least 1.20;
- win rate at least 55%;
- asset-class and point-in-time market metadata coverage at least 80%;
- no single symbol above 40% of independent episodes;
- all single-symbol and single-day leave-one-out results remain average-positive and
  PF at least 1.20.

The live-equity research cost authority is 0.28% round trip. Broker mock cost is
reported separately and cannot replace the live-research basis.

## Final Decisions

| Decision | Meaning | Next action |
|---|---|---|
| `PASS_RUNTIME_VALIDATION` | Every fixed evidence gate passed | Perform one manual behavior-patch review for the opening probe only |
| `FAIL_RUNTIME_EFFECT` | Return, PF, win, median, or sensitivity failed | Close the candidate permanently |
| `FAIL_RUNTIME_INTEGRITY` | Required point-in-time or forward evidence failed | Close as unverified; do not extend automatically |
| `INSUFFICIENT_RUNTIME_SAMPLE` | Fewer than 5 independent episodes after five days | Close insufficient; do not extend automatically |

No result automatically changes policy.

## Background Measurements

The existing observers may continue collecting:

- `CONFIRMED_RECURRENT_RANK`;
- corrected Samsung/Hynix baseline.

They do not delay or modify this five-day decision and cannot become a concurrent
behavior candidate.
