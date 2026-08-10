# Opening Alpha Five-Session Closure

## Decision

- Window: 2026-08-03 through 2026-08-07
- Window status: `CLOSED`
- Valid opening-artifact days: 4 of 5
- Invalid opening-artifact day: 2026-08-05
- Live trades during the window: 0
- Selected live behavior patch: `NONE`
- Whole-window extension: `NO`

The window produced enough evidence to reject broad opening entry and to retain
only narrowly defined conditional observations. It did not produce evidence for
loosening the existing cost, risk, entry, or execution gates.

## Five-Day Broad Control

The valid-day `OPEN_0_20_RANK1_30M` cohort contains 21 independent opening
episodes. Results use the 0.28% live round-trip cost basis.

| Horizon | N | Win rate | Average net | Profit factor |
| --- | ---: | ---: | ---: | ---: |
| +5m | 21 | 28.6% | -0.2966% | 0.6544 |
| +15m | 21 | 33.3% | -0.3482% | 0.6495 |
| +30m | 21 | 28.6% | -0.4354% | 0.6868 |
| +60m | 20 | 35.0% | -0.4409% | 0.7707 |
| EOD | 21 | 52.4% | +1.0521% | 1.9719 |

Broad Rank-1 entry is negative at every intraday checkpoint. The positive EOD
average is accompanied by large intraday adverse movement and does not authorize
unconditional EOD holding.

## Conditional Lanes

| Lane | Primary horizon | N | Win rate | Average net | PF | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `IMMEDIATE_OPENING_PROBE` | +15m | 4 | 25.0% | +0.2887% | 1.4253 | retain shadow only |
| `CONFIRMED_RECURRENT_RANK` | +30m | 1 | 100.0% | +5.5328% | 999.0 | retain shadow only |
| `DISLOCATION_REBOUND` | +60m | 5 | 60.0% | +1.5303% | 2.6223 | historical direction confirmed, no live promotion |

`IMMEDIATE_OPENING_PROBE` is dominated by one 2026-08-03 winner and all four
episodes are the same symbol, 233740. It is not a general opening rule.

`CONFIRMED_RECURRENT_RANK` has the strongest observed path but only one eligible
prospective episode. It remains the highest-quality background observation, not a
behavior patch.

`DISLOCATION_REBOUND` meets the mechanical N=5 and positive-direction checks, but
the five rows come from only two extreme-down sessions and mix leveraged-long and
inverse exposure. The result confirms that the condition deserves continued
observation; it does not define one executable directional policy.

## Daily Evidence

| Day | Status | Episodes | +30m win rate | +30m average net | Immediate | Recurrent | Dislocation |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026-08-03 | VALID | 6 | 66.7% | +1.0677% | 1 | 1 | 3 |
| 2026-08-04 | VALID | 5 | 20.0% | +0.3485% | 1 | 0 | 0 |
| 2026-08-05 | ARTIFACT_INCOMPLETE | 4 | 50.0% | -1.0503% | 0 | 0 | 0 |
| 2026-08-06 | VALID | 4 | 25.0% | -1.0488% | 1 | 0 | 2 |
| 2026-08-07 | VALID | 6 | 0.0% | -2.1826% | 1 | 0 | 0 |

The invalid 2026-08-05 opening data is excluded from the cumulative cohort and
does not cause an extension.

## Main Pipeline and Controls

- Q9 was valid on 2026-08-07 with 541 complete P/A/B/C windows and 99.82% linkage.
- The five-day main pipeline produced zero live trades.
- Across the five days, 2,707 Q9 cycle windows were recorded and Commander approve
  plus Monitor NOOP occurred 363 times. These are repeated cycle observations, not
  363 independent opportunities.
- Q16 exact proxy-only rejection remains `RETAIN`; its +30m live-cost average is
  +0.0238% with PF 1.0449 and does not justify relaxing the cost gate.
- Q11 produced three virtual trades on 2026-08-07 with weak net results under the
  mock cost basis. Q10 and Q12 also remain controls, not promotion candidates.
- Q10/Q11/Q12 reports currently use the approximately 1.036849% mock round-trip
  cost while opening shadow uses the 0.28% live basis. Cross-module comparison must
  show both bases rather than treating them as interchangeable.

## Latent Reactivation

- Initially failed Rank-1 episodes watched: 12
- Later redetected: 7
- Redetected with fresh signal evidence: 6

Fresh-trigger forward reconstruction subsequently excluded three signals from the
`ARTIFACT_INCOMPLETE` 2026-08-05 trigger day. The active evaluation therefore starts
with three eligible triggers and two completed +30m outcomes. See
`active_research_register_2026-08-07.md`.

This supports keeping `LATENT_REACTIVATION_WATCH`, but there is no forward-outcome
contract anchored at the fresh trigger. It cannot yet justify candidate reinjection
or overnight holding.

## Next Work, In Priority Order

### P0: Close and Stabilize the Evidence

1. Keep this five-session window closed.
2. Do not change Scanner, Strategist, Commander, Monitor, entry, exit, or execution
   from this result alone.
3. Keep live and mock cost bases side by side in all baseline comparisons.
4. Clarify the five-session review wording so a confirmed observer lane is not
   mistaken for an automatically selected behavior patch.

### P1: Offline Monitor-NOOP Attribution

Use the already collected 2026-08-03 through 2026-08-07 artifacts. Do not wait for
another broad live window.

1. Deduplicate repeated Q9 cycles into contiguous day-symbol decision episodes.
2. Restrict the primary cohort to Commander-approved candidates.
3. Group Monitor NOOP by the exact blocker present at that decision:
   `below_vwap_reclaim_not_ready`, `pullback_not_mature`,
   `volume_confirmation_missing`, cost edge, chart sanity, and structure failure.
4. Calculate +5m, +15m, +30m, +60m, EOD, MFE, and MAE on the 0.28% live basis.
5. Compare each blocked cohort with approved BUY/intent episodes when available.

This is the next root-cause analysis because runtime observability now preserves the
blocker detail that was missing from the June-July reconstruction.

#### P1 Completion Result

P1 is complete. The additive implementation is
`libs/reporting/evaluation/monitor_noop_attribution/`, and its frozen output is
`reports/evaluation/offline_alpha/monitor_noop_attribution/`.

- Raw Commander-approved Monitor-NOOP cycles: 363
- Contiguous independent episodes: 188
- Forward-ready episodes: 182
- Forward coverage: 96.81%
- Evidence status: `READY`
- Fresh-fetch and cache-only result hash: identical

The table below uses the first observation for each day-symbol-blocker unit to
reduce repeated-symbol inflation. Returns use the 0.28% live round-trip basis.

| Blocker family | +30m N | Win rate | Average net | PF | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| `BREAKOUT_READINESS` | 3 | 100.0% | +2.5348% | 999.0000 | insufficient N |
| `CHART_STRUCTURE` | 3 | 66.7% | +0.4094% | 2.8878 | insufficient N |
| `COST_EDGE` | 7 | 42.9% | -0.4355% | 0.3184 | retain gate |
| `OTHER` | 9 | 44.4% | -1.2605% | 0.4395 | retain; classification review only |
| `PULLBACK_MATURITY` | 10 | 10.0% | -0.5602% | 0.0144 | retain gate |
| `VOLUME_CONFIRMATION` | 13 | 23.1% | -1.8581% | 0.1103 | retain gate |
| `VWAP_RECLAIM` | 8 | 50.0% | +0.6586% | 5.3676 | insufficient N; no relaxation |

The predeclared relaxation threshold requires at least 12 first-day-symbol
observations, positive live expectancy, PF at least 1.2, and win rate at least
45% at +30m. No blocker passes all requirements. The positive VWAP result is a
research lead, not promotion evidence; its episode-level result is concentrated
in repeated observations on 2026-08-07 and symbol 041830.

### P2: Select Exactly One Action

After P1, choose one result only:

- a blocker repeatedly rejects positive net episodes: adjust that one Monitor gate;
- blockers reject negative or high-MAE episodes: retain all gates;
- dislocation evidence remains strongest after direction/exposure separation:
  create one controlled `DISLOCATION_REBOUND` candidate-preservation patch;
- no cohort has stable positive expectancy: make no behavior patch and close the
  opening-alpha branch.

No broad opening relaxation, unconditional probe, unconditional longer hold, or
cost-gate rollback is permitted.

#### P2 Final Decision

`RETAIN_CURRENT_MONITOR_GATES`

No behavior patch is selected. This is a completed decision, not an extension of
the five-session window. The broad opening-alpha branch is closed. VWAP reclaim,
recurrent-rank, and latent-reactivation observations may continue in the
background, but none blocks normal operation or starts a new general validation
window.

### P3: Validate One Behavior Patch

Only if P2 selects a patch:

- use three full trading days;
- compare pre/post with the frozen Q13/Q14 and opening-shadow contracts;
- do not add new lanes or change scoring during the three days;
- stop after day three with retain, rollback, or deprecate.

P3 is not activated because P2 selected no behavior patch.

### Background Only

- Keep `CONFIRMED_RECURRENT_RANK` and latent reactivation collecting automatically.
- Keep the broad 25-episode/10-day control running, but it does not block P1 or P2.
- Do not count repeated 30-second windows as independent samples.

## Final Conclusion

The Scanner shows evidence of finding symbols that may move later, but Rank-1 alone
does not provide a profitable intraday entry rule. Monitor-NOOP attribution confirms
that cost, pullback maturity, and especially volume confirmation are filtering
negative cohorts. No gate has enough robust evidence for relaxation. The fixed
five-day branch and its P1/P2 follow-up are therefore closed without a behavior
patch. Future work must start from a separately specified hypothesis rather than
extending or retuning this result.
