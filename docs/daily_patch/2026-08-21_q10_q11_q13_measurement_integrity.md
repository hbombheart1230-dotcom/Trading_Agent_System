# Q10/Q11/Q13 Measurement Integrity Fix - 2026-08-21

## Scope

This patch changes shadow/evaluation measurement only. It does not change the main
Scanner, Strategist, Commander, Monitor, order, entry, or exit behavior.

## Q10 Large-Cap Baseline

- Replaced the daily `latest.json` market value with the latest macro snapshot at or
  before each decision epoch.
- Added snapshot epoch, age, source, and availability to each decision.
- Added observation-only 15m, 30m, and 60m momentum features. The v0 ranking formula
  and three entry conditions remain unchanged.
- Expanded forward observations to 5m, 15m, 30m, 60m, 120m, 180m, and EOD.
- EOD is now complete only when a 15:30 or later regular-session candle exists.

## Q11 Opening Opportunity Engine

- The signal-generation window remains 09:00-10:00 KST.
- An open shadow position is now followed with minute candles until stop, signal fade,
  or the 30-minute maximum hold. The end of the signal window no longer forces an exit.
- Stop detection and MFE/MAE use minute low/high instead of close only.
- Each completed shadow trade records cost-adjusted 5m, 15m, 30m, 60m, and EOD
  forward observations.
- Market snapshot age and the count older than 300 seconds are explicit data-quality
  fields. Staleness remains observational and does not change probe eligibility.

## Q13 Attribution

- Scanner time continues to use the Q9 decision snapshot timestamp.
- Strategist and selected-candidate timestamps are no longer copied from the Scanner
  timestamp. They remain empty and are listed as missing unless explicit timestamps
  exist in their source artifacts.
- Added stage timing completeness and a single authoritative
  `decision_window_to_entry_delay_sec` field.
- Added 60-minute forward visibility. Intraday labels use 15m/30m evidence; horizons
  longer than the available observation window resolve to `INSUFFICIENT_EVIDENCE`.
- Fixed weakest-axis selection so `evidence_quality_score` cannot be reported as a
  trading-behavior axis.
- Daily ledger discovery is deterministic.

## Historical Interpretation

- Q10 artifacts generated before this patch may contain a closing/latest market value
  copied across all intraday decisions.
- Q11 artifacts generated before this patch may contain `end_of_data` exits at 10:00
  and close-only MFE/MAE.
- Q13 artifacts generated before this patch may show identical Scanner, Strategist,
  and selected-candidate delays.
- These legacy measurements must not be mixed with corrected prospective results
  without regeneration or an explicit legacy cohort label.

## Verification

- Targeted regression suite: 35 tests passed before final broad regression.
- 2026-08-21 Q10 regeneration produced 70 decisions with 40 distinct point-in-time
  KOSPI values and all seven forward horizons.
- 2026-08-21 Q11 regeneration produced no `end_of_data` exits; completed trades use
  minute high/low and include forward observations.
