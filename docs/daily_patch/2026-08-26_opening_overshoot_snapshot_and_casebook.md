# 2026-08-26 Opening Overshoot Snapshot And Casebook

## Scope Lock

- New research scope is limited to Scanner Rank-1 observations from 09:00 through 09:20 KST.
- Q9-Q18, Q10 Samsung/Hynix, Q11 opportunity, and Q12 BTC/Woori artifacts remain unchanged.
- EOD, latent reactivation, and multi-day horizon results are reference evidence only. They are not classification inputs for this opening-overshoot review.
- No entry, exit, ranking, sizing, approval, or execution behavior changed.

## Opening Snapshot Collector

The existing signal path could write the first post-open macro snapshot after the first Q9 decision. On 2026-08-26, the 09:00:13 decision therefore used the 08:50:41 snapshot, while the next snapshot arrived at 09:00:24.

The independent collector now targets fixed KST slots:

- 08:55
- 08:58
- 08:59
- every minute from 09:00 through 09:20

Artifact:

- `data/logs/macro_indicators/YYYY-MM-DD/opening_capture_manifest.json`

The manifest records scheduled time, actual start and finish, start delay, duration, SLA state, source artifact, and failure. A missed slot is written as `MISSED`; the collector never creates a later snapshot and presents it as historical evidence. Restarts are idempotent per slot.

## Casebook Contract

Source:

- `reports/evaluation/opening_rank1_shadow/opening_rank1_shadow_cumulative.json`
- `reports/evaluation/feature_mart/opening_rank1/feature_mart.json`

Deduplication:

- first Rank-1 episode per day and symbol

Classification uses live round-trip cost 0.28% and only +5m, +15m, and +30m:

- `FIXED_HORIZON_SUCCESS`: best fixed live-net return is at least +1.0%.
- `POSITIVE_SUBTHRESHOLD`: best fixed live-net return is above 0% but below +1.0%.
- `MFE_NEAR_SUCCESS_PROFIT_FADE`: best MFE minus live cost reached +1.0%, but all fixed checkpoints were non-positive.
- `NON_QUALIFYING`: none of the conditions above.

Generated artifacts:

- `reports/evaluation/short_alpha_discriminator/2026-08-26/opening_overshoot_casebook.json`
- `reports/evaluation/short_alpha_discriminator/2026-08-26/opening_overshoot_casebook.md`

## Current Result

| Class | Independent cases | Average best fixed net | Average best MFE net proxy |
|---|---:|---:|---:|
| Fixed-horizon success | 27 | +4.8912% | +6.4712% |
| Positive subthreshold | 9 | +0.4223% | +0.8804% |
| MFE near-success/profit fade | 4 | -0.4137% | +1.6573% |
| Non-qualifying | 18 | -2.3324% | +0.0844% |

The table shows that opening Rank-1 contains exploitable price paths, but it does not yet identify a reliable ex-ante separator. Market snapshot, quote, theme-name, and relative-volume coverage is incomplete. Missing causal evidence remains missing in the casebook and is never inferred.

## Decision Boundary

- Do not promote a trading rule from the 27 successful rows alone.
- Use the fixed collector to improve point-in-time market coverage on future sessions.
- Compare successful and non-qualifying rows using the same fixed casebook contract.
- If a separator is found, assign it to exactly one responsibility: Scanner suitability for symbol quality, or Monitor trigger for entry timing.
- Keep all behavior unchanged until that separator survives prospective observation.
