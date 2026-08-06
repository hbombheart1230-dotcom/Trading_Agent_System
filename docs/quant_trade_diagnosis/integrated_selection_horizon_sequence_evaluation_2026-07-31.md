# Integrated Selection, Horizon, And Sequence Evaluation

## Decision

The following evidence must be evaluated as one trade-thesis chain:

```text
Scanner intrinsic selection
  -> Strategist scenario and horizon proposal
  -> Commander pinned operational horizon
  -> Monitor entry
  -> Monitor exit
  -> Post-exit path and D+1 through D+5 reactivation
  -> Same-day same-symbol reentry sequence
  -> Broker-authoritative net outcome
```

Do not collapse the chain into one blended score. A single score can hide a
good symbol selection behind a bad exit, or excuse a bad selection because a
late high happened several days later.

The integrated model keeps each attribution axis separate and produces one
final diagnosis label with explicit evidence.

## Why The Existing Surfaces Must Be Joined

### Strategy Horizon Feedback

This layer answers:

- what holding horizon the Strategist proposed
- what operational horizon Commander authorized
- what window was pinned at the BUY fill
- whether Monitor exited before minimum, target, or maximum hold
- whether an early exit was justified by a hard invalidation
- what happened after exit

It does not answer whether Scanner selected the right symbol.

### Quant Trade Diagnosis

This layer answers:

- which symbol each agent handled
- Scanner rank and available score evidence
- Commander constraints
- Monitor entry and exit reasons
- Q13/Q14 attribution
- broker-authoritative outcome
- same-symbol trade sequence

It currently explains one trade at a time. It does not aggregate the full
selection-horizon-sequence chain into a promotion decision.

### Opening Rank-1 Longitudinal Review

This layer answers:

- whether intrinsic Rank-1 beat same-decision alternatives
- whether the selected symbol moved immediately or later
- whether a later rally was a durable close or only an intraday high

It does not prove that the runtime could identify the later reactivation before
the move.

### Same-Symbol Reentry Control

This layer answers:

- whether a full realized loss should block another same-day entry
- whether repeated trading destroyed expectancy

It does not currently protect an initial profit from one additional losing
reentry.

## Current Numeric Evidence

### Selection

| Metric | Result |
|---|---:|
| Intrinsic Rank-1 decisions | 65 |
| Rank-1 +30m average | +0.7502% |
| Strategist-selected +30m average | +0.4518% |
| Monitor candidate +30m average | +0.5075% |
| Paired Strategist minus Rank-1 | -0.2984%p |
| Paired Monitor minus Rank-1 | -0.2606%p |

Same-decision universe control:

| Horizon | Paired N | Rank-1 minus lower-rank mean |
|---|---:|---:|
| +30m | 52 | +0.5356%p |
| D+5 maximum high | 52 | +7.0242%p |
| D+5 close | 52 | +4.2769%p |

The Scanner showed relative selection value in this bounded opening cohort.
That does not mean every Rank-1 was profitable or should be held for D+5.

### Horizon and exit

The 107 generated Quant Trade Diagnosis artifacts contain:

| Item | Count |
|---|---:|
| `scalp` | 60 |
| `intraday` | 44 |
| horizon unavailable | 3 |
| observed horizon alignment | 104 |
| horizon violation candidate | 36 |
| target hold would improve exit | 10 |

Realized return by historical horizon bucket:

| Horizon | Hold bucket | Finite N | Average return | Win rate |
|---|---|---:|---:|---:|
| intraday | before minimum | 13 | -0.9930% | 7.69% |
| intraday | before target | 20 | -1.0831% | 10.00% |
| intraday | within target | 7 | -0.9163% | 0.00% |
| intraday | beyond maximum | 1 | -0.8275% | 0.00% |
| scalp | before minimum | 17 | -0.4312% | 11.76% |
| scalp | before target | 11 | -1.5335% | 9.09% |
| scalp | within target | 10 | -0.4556% | 30.00% |
| scalp | beyond maximum | 20 | -1.1849% | 10.00% |

Every populated bucket was negative. Only 10 of 104 observed horizon cases had
a positive target-hold counterfactual. The evidence does not support a global
"hold everything longer" rule.

The operational horizon contract was corrected on 2026-07-24. There are zero
closed-trade diagnosis artifacts after that date. Historical reports can test
contract interpretation but cannot prove the corrected runtime behavior was
exercised in a live closed trade.

### Delayed reactivation

Among 19 D+5-complete Rank-1 events with non-positive +30m:

- 8, or 42.11%, later reached a +5% high.
- 2, or 10.53%, retained at least +3% through the D+5 close.
- 6 were high-only opportunities that later faded.

This supports a reactivation research lane, not automatic overnight holding.

### Same-symbol sequence

| Cohort | N | Win rate | Average return | Profit factor |
|---|---:|---:|---:|---:|
| First trade | 72 | 13.89% | -0.8506% | 0.3072 |
| Repeat trade | 27 | 3.70% | -1.2478% | 0.0026 |
| Repeat after loss | 24 | 4.17% | -1.2756% | 0.0029 |
| Repeat after non-loss | 3 | 0.00% | -1.0252% | 0.0000 |

The loss-reentry block is retained. The still-relevant first-profit reentry
sample contains only two historical sequences. Monami returned 82.1% of its
first realized profit on the second trade.

## Quant Diagnosis Coverage Limits

| Surface | Coverage |
|---|---:|
| Quant diagnosis artifacts | 107 |
| Finite broker/read-model outcomes | 101 |
| Horizon alignment observed | 104 |
| Selection chain consistent | 51 |
| Selection chain inconsistent | 56 |
| Strategy-option score surface available | 0 |
| Root cause `INSUFFICIENT_EVIDENCE` | 60 |

The Quant Trade Diagnosis implementation is useful and must be retained. It is
not yet a complete agent scorecard:

- historical strategy-option scores were not retained
- 60 of 107 primary root causes remain insufficient
- no post-2026-07-24 closed trade validates the corrected horizon runtime
- only two historical executions link to the exact opening Q9 decision ID

Missing evidence must remain missing. Do not backfill invented agent scores.

## Unified Read Model

Create one row per executed trade and one parent row per day-symbol sequence.

### Trade row

Required sections:

```json
{
  "selection": {},
  "strategy_horizon": {},
  "entry": {},
  "exit": {},
  "post_exit": {},
  "cross_day_reactivation": {},
  "same_symbol_sequence": {},
  "agent_attribution": {},
  "broker_outcome": {},
  "evidence_quality": {}
}
```

### Selection

- intrinsic Scanner Rank-1 and Top-10
- same-decision lower-rank forward mean
- Strategist-selected symbol and intrinsic symbol's resulting rank
- Monitor candidate
- Commander approve/reject
- executed symbol and exact Q9 decision ID
- matched +5m/+15m/+30m/+60m/EOD returns for every stage candidate

### Horizon

- Strategist proposal
- Commander authoritative policy
- BUY-time pinned policy
- minimum, target, and maximum seconds
- actual holding seconds
- hard-exit status
- before-minimum, before-target, within-window, or beyond-maximum bucket
- whether target-hold improvement occurred after cost
- whether the path breached the strategy stop before later upside

### Post-exit and reactivation

- +5m/+15m/+30m/+60m/EOD checkpoints
- MFE and MAE with timestamps
- D+1 through D+5 adjusted OHLCV
- fresh reactivation trigger timestamp
- trigger-before-high status
- market, sector, theme, and news state at the fresh trigger
- high-only versus durable-close classification

### Same-symbol sequence

- trade ordinal
- prior exit result
- cumulative symbol-day PnL before and after the trade
- maximum cumulative profit
- first-profit giveback amount and percentage
- prior/current setup episode IDs
- independent new episode status
- current loss-reentry guard result

### Agent attribution

Keep the existing Q13/Q14 axes separate:

- `selection_integrity_score`
- `scanner_alignment_score`
- `entry_timing_score`
- `exit_horizon_score`
- `evidence_quality_score`

Add evidence links, not new blended points. A low Scanner score and a low exit
score must not be averaged into an ambiguous total.

## Final Diagnosis Labels

The integrated evaluator should emit exactly one primary label and optional
secondary labels.

| Label | Definition | Next action |
|---|---|---|
| `SELECTION_EDGE_ABSENT` | intrinsic candidate did not beat controls after cost | Scanner research |
| `SELECTION_RIGHT_EXECUTION_MISSED` | intrinsic candidate had edge but was not preserved/executed | stage-lineage review |
| `ENTRY_TIMING_LOST_EDGE` | selected symbol had edge but actual entry was materially late/early | Monitor entry review |
| `EXIT_TOO_EARLY_SUPPORTED` | before target, no valid hard exit, target path improved after cost without stop-first breach | horizon-specific exit candidate |
| `EXIT_DEFENSIVE_VALID` | exit avoided a larger strategy-valid loss | retain exit |
| `DELAYED_REACTIVATION` | original trade failed, then a fresh observable trigger preceded later upside | reactivation shadow |
| `HIGH_ONLY_NOT_CAPTURABLE` | later high occurred without an observable prior trigger or after unholdable drawdown | reject hold extension |
| `SAME_SYMBOL_REPEAT_GIVEBACK` | repeat reduced cumulative day-symbol PnL without a new episode | reentry-control candidate |
| `INSUFFICIENT_EVIDENCE` | required authority or path is missing | repair artifact only |

## Decision Examples

### Good selection, immediate opportunity

```text
Monami intrinsic Rank-1 at 09:00:06
+30m virtual path +16.34%
```

If not preserved at the same decision, this is
`SELECTION_RIGHT_EXECUTION_MISSED`. It is not an exit-horizon problem because
the opportunity existed immediately.

### Good selection, later opportunity

```text
Woojin Plaimm +30m -0.45%
D+5 high/close +7.94% / +3.89%
```

This becomes `DELAYED_REACTIVATION` only if a timestamped fresh signal preceded
the later rise. Otherwise it remains insufficient.

### Future high but bad hold

```text
Techwing +30m -4.40%
D+1 high/close +17.51% / +9.08%
D+5 close -23.31%
```

Automatic holding is rejected. A fresh-trigger shadow may still evaluate the
D+1 opportunity.

### First profit returned by a repeat

```text
Monami trade 1 +1.7776%
Monami trade 2 -1.4589%
day-symbol cumulative +0.3187%
giveback 82.1%
```

This is `SAME_SYMBOL_REPEAT_GIVEBACK`, separate from the opening selection and
the original horizon.

## Keep, Integrate, Or Retire

### Keep as active authority

- Commander-owned operational horizon contract
- BUY-time pinned position horizon
- hard-exit override rules
- post-exit deterministic price tracking
- Q13/Q14 attribution axes
- Quant Trade Diagnosis JSON/Markdown
- intrinsic Rank-1 universe control
- same-symbol loss reentry block

### Integrate into the unified read model

- horizon compliance
- post-exit shadow
- D+1 through D+5 reactivation
- selection stage lineage
- same-symbol cumulative sequence
- broker cost and realized truth

### Remove from active decision-making

- four-slot and two-slot horizon designs
- historical `observability_only` horizon interpretation
- D+5 maximum high by itself as evidence to hold
- a single blended agent blame score
- strategy-option score comparisons when the source score surface is absent
- automatic policy extension because a small sample appears promising

The deprecated designs may remain as historical documents but must not be cited
as current policy.

## Implementation Order

### U1 - Unified read model

Reporting-only. Join existing artifacts without changing runtime behavior.

Outputs:

- `reports/evaluation/integrated_trade_thesis/YYYY-MM-DD/trade_thesis_rows.json`
- `reports/evaluation/integrated_trade_thesis/YYYY-MM-DD/symbol_day_sequences.json`

### U2 - Integrated range report

Backfill 2026-06-01 onward and report counts, returns, and evidence quality by
final diagnosis label.

Output:

- `reports/evaluation/integrated_trade_thesis/range/.../integrated_attribution_report.md`

### U3 - Counterfactual shadows

Compare:

- actual exit versus horizon-valid target exit
- actual same-symbol sequence versus stop-after-first and fresh-episode-only
- original failed Rank-1 versus fresh-trigger reactivation

### U4 - One behavior decision

Choose one action only after U1-U3:

- horizon-specific exit adjustment, or
- profit-protection reentry control, or
- fresh-trigger reactivation lane, or
- Scanner/selection change

Do not patch multiple layers simultaneously.

## Current Decision

1. Do not delete Strategy Horizon Feedback. Its operational contract is needed.
2. Do not delete Quant Trade Diagnosis. It is the per-trade evidence adapter.
3. Stop treating either folder as an independent evaluation program.
4. Build the unified read model and range report first.
5. Do not globally extend holding time.
6. Keep the current same-symbol loss block unchanged.
7. Evaluate profit protection and delayed reactivation as separate shadows.

This closes the conceptual split: selection, horizon, exit, and reentry become
one diagnosis chain while retaining separate causal axes.
