# Rank-1 Fixed Candidate Prospective Shadow

Date: 2026-08-11

## Purpose

This is Stage 7 of the canonical Rank-1 research plan. It validates two frozen branches on future
trading days without changing Scanner, Strategist, Monitor, Commander, exit, or order behavior.

Stages 1-6 are complete. Stage 8 is deliberately not implemented.

| Priority | Stage | Status | Runtime behavior |
| ---: | --- | --- | --- |
| 1 | Canonical Schema | Complete | None |
| 2 | Historical Backfill | Complete: 96 episodes | None |
| 3 | Horizon Expansion | Complete | None |
| 4 | Integrity Audit | Complete | None |
| 5 | Attribution Analysis | Complete | None |
| 6 | Candidate Selection | Frozen through 2026-08-11 | None |
| 7 | Prospective Shadow | Ready; first eligible day 2026-08-12 | None |
| 8 | Single Behavior Patch | Not started | Future manual decision only |

## Frozen Candidates

### R1_SCANNER_RISK_HIGH_30M_V1

* owner under test: Scanner
* condition: `scanner.risk_band == HIGH`
* target: live-cost-adjusted +30m return
* control: all Rank-1 episodes not matching that state
* any future patch surface: Scanner `lane_suitability` only

This does not mean high-risk candidates should be bought. It tests whether the current risk-band
semantics are aligned with observed forward performance.

### R1_ENTRY_DAILY_MA5_20_EXTENDED_15M_V1

* owner under test: Monitor entry timing
* condition: `chart.daily_ma5_20_cross_state == POST_CROSS_EXTENDED`
* target: live-cost-adjusted +15m return
* control: all Rank-1 episodes not matching that state
* any future patch surface: Monitor entry timing only

## Frozen Contract

* frozen at: 2026-08-11
* first eligible day: 2026-08-12
* validation window: five valid trading days
* minimum independent sample: 10 day-symbols per candidate
* minimum target coverage: 90%
* minimum profit factor: 1.20
* positive net return and positive alpha versus complement are required
* candidate selection ignores every row after 2026-08-11
* same-day repeated decisions count once in the independent metrics

The generated contract includes a SHA-256 hash. A hash change invalidates the prospective window.

## Five-Day Close Rule

After five valid trading days:

* sufficient sample and all gates pass: mark one candidate as manual Stage-8 review eligible
* insufficient candidate sample: retain only that candidate in shadow; do not extend the whole study
* effect is absent or reversed: reject the candidate
* artifact or forward coverage failure: fix observation only; do not change trading behavior

No report can automatically enable a behavior patch. `behavior_patch_allowed` is always false.

## Runtime Generation

The normal closeout flow now performs, in order:

1. generate the existing opening Rank-1 daily artifact
2. rebuild the canonical mart from retained artifacts and local caches
3. evaluate only the two frozen candidates
4. write daily and cumulative prospective reports

The mart merges the existing historical research cache and the current opening-shadow candle cache.
It does not call Kiwoom during normal closeout for this step.

Standalone reproduction:

`venv\\Scripts\\python.exe scripts\\run_rank1_prospective_shadow.py --day YYYY-MM-DD`

Outputs:

* `reports/evaluation/feature_mart/opening_rank1/prospective/frozen_candidate_contract.json`
* `reports/evaluation/feature_mart/opening_rank1/prospective/YYYY-MM-DD/rank1_candidate_shadow_daily.json`
* `reports/evaluation/feature_mart/opening_rank1/prospective/YYYY-MM-DD/rank1_candidate_shadow_daily.md`
* `reports/evaluation/feature_mart/opening_rank1/prospective/rank1_candidate_shadow_cumulative.json`
* `reports/evaluation/feature_mart/opening_rank1/prospective/rank1_candidate_shadow_cumulative.md`

## Validation Checklist

For each eligible closeout verify:

1. closeout step `rank1_fixed_candidate_shadow` is successful
2. contract hash is unchanged
3. daily source status is `VALID` or `VALID_NO_EPISODES`
4. target coverage is at least 90% when a branch matches
5. episode and day-symbol counts are both shown
6. branch and complement use the same horizon and 0.28% cost basis
7. no OrderIntent or execution dependency exists

The first prospective day is the only remaining step that requires a live run for confirmation.
