# Alpha Research Board Contract - 2026-08-21

## Purpose

The Alpha Research Board consolidates existing research conclusions. It does not
repeat broad historical mining and does not change trading behavior.

The board answers four operator questions:

1. Which discriminator candidates remain alive?
2. Which candidates are closed and must not be renamed or restarted?
3. What evidence exists in historical, validation, and prospective cohorts?
4. What exact evidence is still missing before a decision?

## Fixed Research Tracks

| Track | Question |
|---|---|
| `OPENING_CONDITIONAL` | Which opening setup separates continuation from exhaustion? |
| `SCANNER_REACTIVATION_HORIZON` | Does a previously selected symbol reactivate on a fresh signal, and when? |
| `BTC_WOORI` | Does BTC lead Woori only when local price and volume confirm? |
| `LARGE_CAP_TWO_SYMBOL` | Can a fixed Samsung/Hynix baseline produce repeatable net edge? |

No new Q phase is created. The existing Q artifacts are evidence suppliers.

## Board Buckets

| Bucket | Meaning |
|---|---|
| `ACTION_REVIEW` | The source contract reached a manual review point. It is not automatically promoted. |
| `OBSERVE_FIXED` | Continue only the existing fixed observer and stopping rule. |
| `DATA_REPAIR_BOUNDARY` | Use only measurements generated after the named integrity fix. |
| `CLOSED_NEGATIVE_PROSPECTIVE` | Historical promise failed prospectively; do not retune it. |
| `CLOSED` | The fixed contract is finished and cannot be restarted under another name. |

## Sample Authority

- Independent `day-symbol` or episode counts are the primary sample count.
- Repeated minute windows are retained as measurement windows, not independent trades.
- Gross, 0.28% live-equity research net, and broker-observed mock net remain separate.
- Legacy Q10/Q11/Q13 measurements are not mixed with corrected prospective cohorts.
- Missing artifacts produce `PASS_WITH_MISSING_SOURCES`; values are never guessed.

## Inputs

- Rank-1 feature-mart candidate selection
- fixed prospective candidate comparison
- Fresh Change prospective comparison
- opening Rank-1 cumulative lanes and broad-control decision
- latent-reactivation forward review
- BTC-Woori historical subset review
- corrected daily Samsung/Hynix baseline

The corrected Samsung/Hynix baseline uses one Top-1 average per trading day as
the independent evaluation unit. Repeated intraday windows remain visible as
`window_count` but do not inflate `sample_count`. The cumulative cohort starts
at the 2026-08-21 integrity boundary.

## Outputs

- `reports/evaluation/alpha_research_board/YYYY-MM-DD/alpha_research_board.json`
- `reports/evaluation/alpha_research_board/YYYY-MM-DD/alpha_research_board.md`
- `reports/evaluation/alpha_research_board/YYYY-MM-DD/risk_high_30m_sensitivity.json`
- `reports/evaluation/alpha_research_board/YYYY-MM-DD/risk_high_30m_sensitivity.md`
- `reports/evaluation/alpha_research_board/YYYY-MM-DD/remaining_candidate_reviews.json`
- `reports/evaluation/alpha_research_board/YYYY-MM-DD/remaining_candidate_reviews.md`
- `reports/evaluation/alpha_research_board/YYYY-MM-DD/immediate_opening_runtime_validation.json`
- `reports/evaluation/alpha_research_board/YYYY-MM-DD/immediate_opening_runtime_validation.md`
- `reports/evaluation/alpha_research_board/YYYY-MM-DD/short_alpha_discriminator.json`
- `reports/evaluation/alpha_research_board/YYYY-MM-DD/short_alpha_discriminator.md`

## First Manual Review Result

`R1_SCANNER_RISK_HIGH_30M_V1` reached its source-level manual review point, but the
fixed sensitivity review returned `REJECT_CONTRIBUTOR_DEPENDENCE`.

- base: 21 independent day-symbols, +0.9235% average live-net, PF 1.5964;
- excluding the highest-frequency symbol and day improved the result;
- excluding profit-contributor `003010` reduced the result to +0.0557%, PF 1.0326;
- median return was -0.9011%;
- point-in-time market-regime coverage was only 19.1%.

The generic `risk_band=HIGH` discriminator is therefore closed. The result must not
be used to retune the risk threshold or to create a narrower behavior rule from the
same reviewed sample.

## Additive Short-Alpha Discriminator

The 2026-08-24 offline review found an asset-class interaction inside the already
closed generic HIGH cohort. This does not reopen `R1_SCANNER_RISK_HIGH_30M_V1` and
does not authorize a narrower behavior rule.

`HIGH_COMMON_SHORT_ALPHA_V1` is a new fixed prospective shadow contract:

- conditions: `asset_class=common_stock AND risk_band=HIGH`;
- first eligible prospective day: 2026-08-25;
- independent unit: first observation per day-symbol;
- checkpoints: +5m, +15m, +30m, +60m, EOD;
- historical discovery rows and prospective rows are stored separately;
- Scanner, Strategist, Monitor, Commander, and execution behavior remain unchanged.

The report also stores `TOP_VALUE_VOLUME_NEGATIVE_CONTROL_V1`, candidate-setup
comparisons, score calibration, profit-fade observations, optimistic profit-lock
proxies, and Strategist Stage-2 ROI evidence. Profit-lock proxies are not executable
backtests and cannot authorize a policy.

The independent runner is:

```powershell
python scripts/run_short_alpha_discriminator.py --through-day YYYY-MM-DD
```

## Remaining Offline Decisions

All remaining candidates were reviewed before requesting another runtime window.

| Candidate | Decision |
|---|---|
| `IMMEDIATE_OPENING_PROBE` | `READY_FOR_FIXED_RUNTIME_VALIDATION` |
| `CONFIRMED_RECURRENT_RANK` | `RUNTIME_DATA_REQUIRED`, background only |
| `DISLOCATION_REBOUND` | `REJECT_SYMBOL_CONTRIBUTOR_DEPENDENCE` |
| `POST_CROSS_EXTENDED` | `REJECT_PROSPECTIVE_EFFECT_NOT_CONFIRMED` |
| BTC-Woori v2-only | `REJECT_DAY_CONTRIBUTOR_DEPENDENCE` |
| Samsung/Hynix corrected baseline | `RUNTIME_DATA_REQUIRED`, background only |

The next and only fixed runtime candidate is defined in
`immediate_opening_probe_runtime_validation_2026-08-21.md`.

Run manually:

```powershell
python scripts/run_alpha_research_board.py --through-day YYYY-MM-DD
```

The runner is not connected to live runtime, closeout, orders, or automatic policy
promotion.
