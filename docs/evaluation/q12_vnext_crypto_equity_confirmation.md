# Q12 vNext Crypto Equity Confirmation

Version: Q12_CRYPTO_EQUITY_CONFIRM_V1_SHADOW. Forward start: 2026-09-07.

## Existing flow and ownership

Q12 captures BTC at 08:55 independently, computes five-variable hypothesis
features, and publishes the existing hypothesis contract. The live pure candidate
function uses BTC 24h >=4%, FIRST_SURGE, breakout, opening gap <10%, and local
confirmation at 09:03/09:05. Commander/Executor consume that original contract.
The independent Q12 baseline also has multihorizon and persistent-trend variants.
Those variants must not be mislabeled as the current live controlled policy.

Existing BTC feature, local confirmation and first VWAP pullback calculations
are reused. No existing decision, threshold, prompt or execution path changes.
vNext is invoked only after original reports have been written. Errors return
INSUFFICIENT_EVIDENCE in runner output, not a veto on Q12-A.

## Additive scope

Modules under libs/reporting/baseline_btc_woori_tech/vnext separate contract,
equity provider, feature projection, outcomes, persistence, and reporting.
pipeline.py has only an optional final reporting hook. No new LLM or framework.

- COIN/MSTR: bounded one-month daily regular-session closes, close-to-close.
- Expected US date: previous calendar weekday before the Korean day. An absent
  expected session is UNKNOWN (holiday OR missing feed); an older session never
  silently substitutes. Monday can use Friday, with the exact session displayed.
  This conservative policy is not an exchange holiday calendar and deliberately
  abstains on a holiday. No guessed return is generated.
- Confirmation: both same sign as BTC => CONFIRM; both abs returns >=5% => STRONG;
  both opposite => DIVERGENCE; other complete combinations => MIXED; missing => UNKNOWN.
- BTC short returns reuse the immutable 08:55 capture. No new capture time.
- FIRST_SURGE reuses existing >=3%/seven closed daily bars definition. EXTENDED
  means at least one prior daily gain >=3% in those seven days. No threshold search.
- BTC 3d/7d context is current 08:55 price relative to third/seventh completed
  daily close, explicitly NOT an exact rolling 72h/168h return.
- High distances require complete contiguous 20/60/120 UTC daily windows.
  120-day high is available equivalent, never ATH. Important-price breakout UNKNOWN.
- Woori positive BTC reaction: negative gap DIVERGENCE; [0,3)% UNDERREACTION;
  [3,10)% FAIR_REACTION; >=10% OVERREACTION. Negative/missing BTC => UNKNOWN.
- Local confirmation uses existing price OR volume rule, prior completed minutes
  only. Gaps in confirmation minutes => UNKNOWN. Exact entry minute OPEN required.
- Structured company event input requires symbol, boolean adverse, source,
  event_id, and observed_epoch <= decision time. Otherwise UNKNOWN, not no-event.
- Event adverse => B NO_TRADE_CANDIDATE only, never a new live veto.

## A/B and evidence

A is the unchanged pure build_q12_candidate function applied to the original
hypothesis payload at the entry timestamp; record preserves source hash and
candidate fields. This measures candidate-policy eligibility, NOT actual approval,
submission or fill. 09:00/09:10 are opportunity comparators, not fabricated live A entries.
B uses the fixed definitions in contract.RULES. Fast candidates require BTC >=4%,
FIRST_SURGE, breakout, non-overreaction, equity confirmation and local confirmation.
Extended + overreaction + BTC/equity confirmation gives WAIT_PULLBACK_CANDIDATE.
Missing required evidence never becomes a passing B candidate.

All outcomes are hypothetical LONG returns. 09:30/10:00 use exact minute OPEN;
EOD uses exact 15:30 minute CLOSE only after that bar completes. No interpolation.
MFE/MAE require a complete minute path and exclude future portions of exit bars.
Use the same cost profile and slippage supplied by existing Q12/Q9.

## Persistence and cadence

Root: reports/evaluation/baseline_btc_woori_tech/vnext/VERSION/YYYY-MM-DD/

- preopen_context.json: immutable equity and bounded existing daily inputs,
  collected before 08:59:59; late process without it reports missing, no backfill.
- observations/0900.json, 0903.json, 0905.json, 0910.json, PULLBACK.json:
  immutable A/B observations. First publication wins atomically across processes.
- forward/*.json: immutable endpoint results. *_complete.json may add a fully
  observed path without replacing an earlier incomplete-path result.
- validation.json and comparison.json: regenerable projections, cumulative within
  the exact same version. Never read historical Q12 cohorts into this population.
- daily_report.md: current features and cumulative arm/dimension/method/horizon table.

Existing Q12 runner retains its five-minute loop. Observations first persisted
within five minutes of their decision are PROSPECTIVE point-in-time reconstructions;
later ones are LATE_RECONSTRUCTION and reported separately. This is not proof of
an executable fill at the historical minute open. A/B snapshots cannot use feature
bars later than their own entry timestamp, even when run after the close.

Preopen context does not replace the canonical BTC snapshot. If missing or
corrupted it is not repaired from post-decision information. Existing evidence
files are not deleted or rewritten by this extension.

## Metrics and gates

Per unique day and method: signal/evaluable/missing counts, win rate, average,
median, PF and average MFE/MAE. Opportunity rows include blocked hypotheses to avoid
survivorship bias. Zero evidence is not zero profit. Multiple entry methods on one
day are correlated and must not be pooled as independent samples.

N <10 anecdotal; 10-19 preliminary; 20-29 insufficient for promotion; >=30 review
eligible. These are operational gates, not statistical significance or automatic
promotion. Group by surge, breakout, reaction, equity, surge x equity, local state.

No strategy/execution/broker-call-path change. No historical backtest, grid search,
new LLM, ML, or new Executor connection. All rule changes require a new cohort.

## Verification and deployment receipt

2026-09-07: initial focused Q12 suite 38 passed. Final full repository suite
3026 passed, 1 skipped, exit 0. Includes equity agreement/divergence/missing,
holiday abstention, deterministic surge/breakout, exact opening and forward prices,
MFE/MAE/cost, immutable restart records, A/B isolation, structured event timing,
corrupt context preservation and broker execute trap tests.

Q12 loop launched at 08:38 KST using existing runner and 300-second cadence.
First successful projection and preopen context persisted at 08:38:33.
US session 2026-09-04: COIN -4.182666%, MSTR -1.394838% (provider snapshot,
not independently exchange-certified). BTC and Woori forward evidence pending.
Existing 08:55 capture task remains scheduled. No main/Q10/Q11 restart performed.
