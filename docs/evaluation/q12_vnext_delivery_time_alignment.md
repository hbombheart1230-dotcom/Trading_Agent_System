# Q12 input delivery and US time alignment correction

Date: 2026-09-07. Supersedes V1 interpretation, not historical evidence.
New shadow cohort: Q12_CRYPTO_EQUITY_CONFIRM_V2_ALIGNED_SHADOW.

## Incident evidence

BTC capture succeeded at 08:55:01. Main reported INPUT_MISSING at 09:00:07 and
09:03:33, then NO_CANDIDATE at 09:04:58. Root cause: the main reads the hypothesis
report, whose producer preserves the entire old report when Woori candles are
absent; the report runner then sleeps 300 seconds after each completed build.

BTC +0.68266% was below the unchanged 4% live threshold, so the delay did not
cause an otherwise eligible Q12 entry today. Strong-signal days remain at risk
without correcting this producer/consumer dependency.

## Time basis correction

V1 compared Friday COIN/MSTR close-to-close with Sunday-to-Monday BTC 24h return.
It correctly selected Friday but incorrectly treated different intervals as
contemporaneous confirmation. Friday 2026-09-04 close was Saturday 05:00 KST,
51h55m before Monday 08:55. V1 DIVERGENCE is NOT reliable causal confirmation.

V2 records separately:

1. BTC at previous US close -> latest US close, matching equity return interval.
2. BTC at latest US close -> canonical 08:55, including weekend movement.
3. Existing BTC 5m/15m/60m/24h opening signals, unchanged.

Only (1) determines crypto_equity_confirm. Same-sign +/-5% thresholds unchanged.
Matched price references require exact 5-minute OPEN at the scheduled US close;
missing OPEN cannot fall back to a later CLOSE. A bounded five-day 5-minute fetch
is used only for current forward context, never a historical backtest.

exchange-calendars 4.13.2 provides XNYS session-close times including DST and
early closes. It does not authorize use of an older weekday on a US holiday:
such inputs remain UNKNOWN, per the original missing-evidence contract.
Optional calendar/provider failure only affects B, never existing Q12-A.

References: https://github.com/gerrymanoim/exchange_calendars

## Evidence preservation

V1 files are not modified or reclassified in-place. V2 can carry factual V1
preopen daily/equity context with original observed_at and source path. V1 did
not capture the matched US-close BTC prices; today's V2 marks that missing rather
than fetching post-decision values and claiming they were observed preopen.
New V2 observations collected after the decision window are LATE_RECONSTRUCTION,
never pooled with prospective observations. Gap type WEEKEND/OVERNIGHT is a
report grouping in the same existing evaluation, not a new execution lane.

## Input delivery ownership

The existing Q12 runner starts one opening-only background input worker:
The dedicated weekday Q12-Preopen task starts that same runner at 08:45 via
scripts/start_q12_preopen.ps1. Existing 09:00 stack ownership detects the same
day-scoped process instead of launching a second one. The 08:55 BTC task remains
unchanged. This is necessary because a 09:00-only launch misses preopen context.

08:50 warmup, 08:55 read immutable BTC capture, 09:00-09:12 retrieve Woori minute
evidence using the existing provider. One tick followed by a 15-second wait.
This is independent of the report thread, not an exact 15-second SLA: provider
latency and main-loop scheduling remain visible limitations. No broker mutation.

The worker reuses build_hypothesis_features and publishes atomically:
reports/evaluation/baseline_btc_woori_tech/YYYY-MM-DD/q12_candidate_input.json

Main loads this input when present, then overlays canonical 08:55 BTC directly
from its immutable source. Missing/corrupt/stale input is not silently replaced
with an old passing report. Inputs older than 90 seconds have entry methods
cleared. This threshold controls projection freshness, not signal eligibility.
Existing Q12 signal freshness (7 minutes), ranking, thresholds and quantity remain
unchanged. Absent dedicated input retains the old report-compatible path.

Diagnostics distinguish INPUT_MISSING, INPUT_DELAY, LOCAL_CONFIRMATION_PENDING,
and NO_CANDIDATE. Preserved legacy report also receives freshly captured BTC
without erasing existing local evidence. No forward or historical raw evidence
is deleted. Enabling timely inputs can allow an already-eligible candidate that
the old reporting delay missed; this is not a new strategy rule.

## Validation contract

Tests cover Monday mismatch, aligned negative US movement with positive weekend
BTC, US holiday, DST/early close, missing matched references, immutable V1 carry,
BTC visibility without Woori candles, exact 09:03/09:05 candidate parity, corrupt
and stale projection denial, and input worker independence from report generation.
Existing Q12-A candidate function and all Executor/guard implementations unchanged.

## Verification receipt (2026-09-07)

- Isolated worktree focused regressions: 35 passed, exit 0 (including preopen
  registration/launcher contract). PowerShell launcher syntax validation passed.
- Isolated full suite: 3032 passed, 3 failed, 1 skipped, exit 1.
- All three failures reproduce unchanged on baseline HEAD 342060f in a separate
  clean worktree (two M20 exit-policy fixtures and sell-cooldown alias fixture).
- Existing tests also create reports/metrics/metrics_2026-04-08.json and .md in
  the worktree. Reproduced on unchanged HEAD with the 196-test reporting subset.
  This is an existing test-isolation gap, not a clean full regression pass.
  No production cleanup or unrelated exit-policy/test edits were performed.
- V1 preopen context and four immutable decision records retain identical SHA256.
- V2 generated successfully; today's matched BTC references are UNKNOWN and
  reconstructed decisions are LATE_RECONSTRUCTION, not prospective observations.
- Q12 completed normally with empty stderr. Main reload at 18:33 exited with
  market_closed/session_hard_gate, not a runtime exception. No offhours bypass.
- The actual 08:50-09:05 producer/consumer latency still needs next-session
  verification; deterministic tests do not establish a live timing SLA.
- Scheduled Q12-Preopen is Ready, next run 2026-09-08 08:45 KST. Existing
  08:50 preopen, 08:55 capture and 09:00 session schedules remain unchanged.
