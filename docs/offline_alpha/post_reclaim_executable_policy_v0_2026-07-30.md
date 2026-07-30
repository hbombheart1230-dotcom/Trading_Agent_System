# Post-Reclaim Executable Policy v0 Decision

## Frozen Contract

This is the final offline follow-up to Q18. It is not a new live evaluation
phase.

Target:

- `confirmed_post_reclaim_pullback`

Entry-time filter:

- inspect only the 15 minutes strictly before the candidate timestamp
- require at least 12 distinct one-minute price prints
- do not use forward price, future volume, or outcome-derived thresholds

Exit and cost:

- first valid +30-minute print, with at most 180 seconds of observation delay
- fixed live-account round-trip cost: 0.28%

Split:

- train: 2026-06-01 through 2026-06-30
- validation: 2026-07-01 through 2026-07-30

The thresholds and decision rules were fixed before running this result.

## Result

`REJECT`

| Split | Eligible | Observed | Coverage | Live Net Avg | PF | Win Rate | MDD | Positive Days |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| June train | 5 | 5 | 100.0% | +0.4330% | 3.1540 | 80.00% | -1.0050% | 80.00% |
| July validation | 6 | 6 | 100.0% | -0.1642% | 0.3886 | 33.33% | -1.0793% | 33.33% |

Failed fixed gates:

- train observed count: 5, required 8
- validation observed count: 6, required 15
- validation live-net expectancy must be positive
- validation profit factor must be at least 1.20
- validation positive-day ratio must be at least 55%

The validation failures are performance failures as well as sample failures.
This is not a case where only the evidence count missed promotion.

## Interpretation

The original unfiltered candidate showed a promising +30-minute aggregate.
That result did not survive the predeclared executable-liquidity filter in the
held-out July period.

The filter retained 11 of 35 episodes. July's retained episodes were
cost-negative with a profit factor well below 1.0. The policy is therefore not
eligible for controlled adoption.

The June bootstrap also crossed below zero at the 10th percentile despite its
positive point estimate. July's median bootstrap estimate was negative. The
apparent edge is not stable enough to justify runtime integration.

## Fixed Decision

- do not promote the post-reclaim +30-minute policy
- do not relax the 12/15 liquidity threshold after seeing the outcome
- do not extend Q18 or create another numbered live validation phase
- preserve the module and artifacts as a rejected research baseline
- make no Scanner, Strategist, Commander, Monitor, order, or execution change

Generated research artifacts:

- `reports/evaluation/offline_alpha/post_reclaim/2026-06-01_2026-07-30/post_reclaim_executable_policy_v0.json`
- `reports/evaluation/offline_alpha/post_reclaim/2026-06-01_2026-07-30/post_reclaim_executable_policy_v0.md`
