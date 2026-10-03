# Unified Evaluation Framework — Current-State Integrity Review

Status: **CURRENT-STATE INTEGRITY REVIEW ONLY — NOT A REDESIGN PROPOSAL**

Scope: investigation and documentation only. No evaluation logic, threshold,
report, strategy, or runtime code was modified. No Q100 was introduced, no
Q number was reclassified. All findings are read directly from repository
HEAD source and actual generated artifacts — nothing here is inferred from
program names or documentation claims alone.

Method: three independent read-only fact-finding passes (Q9/Q10/Q12/Q13/Q14;
Q15/Q16/Q17/Q18 + four named diagnostics; the Alpha Research Board package)
plus a hands-on empirical test in which one identical synthetic price
episode was fed directly into two of the actual forward-checkpoint
functions found, and a direct comparison of the real 2026-09-11 artifacts
on disk.

---

## 1. Does a canonical evaluation authority exist?

```
CANONICAL EVALUATION AUTHORITY: PARTIAL
```

A real, genuinely shared core does exist:

| file | function | schema/shape | input | output | 
|---|---|---|---|---|
| `libs/reporting/evaluation/metrics.py:6` | `performance_metrics(values)` | takes a bare `Iterable[float]` | a list of already-net returns | `count, win_count, loss_count, win_rate, average_return_pct, average_gain_pct, average_loss_pct, profit_factor, expectancy_pct, maximum_drawdown_pct` |
| `libs/reporting/quant_shadow_forward_outcomes.py` | `attach_forward_outcomes(...)` | candidate-baseline checkpoint engine, `CHECKPOINT_MINUTES=(3,5,15,30,60)` + EOD | rows with a `baseline_epoch`/`baseline_price`, plus minute candles | per-row `shadow_forward_outcome.checkpoints[label]` (`status`, `return_pct`, `mfe_pct`, `mae_pct`, `observed_epoch`) |

**Confirmed callers of both**: Q9 (`q9_comparison.py`), Q10's baseline-control
variant (`baseline_samsung_hynix/forward_returns.py`), Q12 (inherits Q10's
functions directly), Q13's entry-timing module, Q16, the Q17 block embedded
in Q16, and Monitor-NOOP attribution. That is a genuine, real, multi-program
shared foundation — not merely a naming coincidence.

**But it is not universal.** At least these do **not** use it at all:
Q10's "lead-market forward validation" variant (three of its own independent
statistics functions), Q11 (its own `opportunity_engine/simulator.py`),
Opening Rank1 Shadow / the Short Alpha Discriminator (their own
`post_reclaim_alpha/evaluator.py` engine with its own cost constants), the
dedicated "Horizon/Exit evaluation" pipeline (a wholly separate,
exit-anchored engine), Q18's `post_reclaim_alpha`-adjacent research module,
Strategist Stage2 (`stage2_authority/`, its own local checkpoint reader),
Same-symbol sequence (no checkpoint concept at all), and the Alpha Research
Board itself (its own `sensitivity.py::_metrics()` reimplementation).

**Verdict**: the *ingredients* for a canonical authority exist and are
correctly reused where they are reused — but roughly half of the surfaces
investigated bypass them entirely with independently-written equivalents.
This is PARTIAL, not NO, and PARTIAL, not YES.

---

## 2. Full evaluation inventory

| # | Item | Code module found | Program/schema id |
|---|---|---|---|
| 1 | Q9 | no dedicated module; informal role-comparison logic riding on Q10-baseline (`libs/reporting/baseline_samsung_hynix/q9_comparison.py`, `unified_comparison.py`) | none (informal) |
| 2 | Q10 — baseline control | `libs/reporting/baseline_samsung_hynix/pipeline.py` | `Q10_LARGECAP_BASELINE_CONTROL` |
| 3 | Q10 — lead-market ("Semiconductor"+"Index" combined) | `libs/reporting/baseline_samsung_hynix/forward_validation/` | `Q10_KOREA_LEAD_MARKET_FORWARD_VALIDATION` |
| 4 | Q11 | `libs/research/opportunity_engine/` | `Q11_OPENING_SURGE_MARKET_REVERSAL` |
| 5 | Q12 | `libs/reporting/baseline_btc_woori_tech/` | `Q12_BTC_WOORI_TECH_BASELINE` |
| 6 | Q13 | `libs/reporting/evaluation/attribution_score_{v0,window,range}.py`, `entry_timing_attribution.py` | four separate ids: `Q13_ATTRIBUTION_SCORE_V0/WINDOW/RANGE`, `Q13_ENTRY_TIMING_ATTRIBUTION` |
| 7 | Q14 | `libs/reporting/evaluation/scanner_alignment_root_cause.py` | `Q14_SCANNER_ALIGNMENT_ROOT_CAUSE` (+ `_RANGE`) |
| 8 | Q15 | **none** — a one-off behavior patch (candidate filtering), evaluated retroactively via the already-frozen Q13/Q14 reports; no ongoing evaluation code | none |
| 9 | Q16 | `libs/reporting/evaluation/q16_proxy_rejection_review.py` | `q16_proxy_rejection_review.v1` |
| 10 | Q17 | **not a standalone module** — a field-block embedded inside Q16's own file (`q17_directional_edge_validation` block) | `q17_directional_edge_validation.v1` (sub-schema) |
| 11 | Q18 | `libs/reporting/evaluation/post_reclaim_shadow_review.py` (thin post-processor) + `libs/research/post_reclaim_alpha/` (independent, Q18-adjacent) | `post_reclaim_shadow_review.v1` / `post_reclaim_offline_research.v1` |
| 12 | Opening Rank1 Shadow | `libs/reporting/opening_rank1_shadow/` | `opening_rank1_shadow.v1` |
| 13 | Opening Controlled Probe | `libs/runtime/opening_rank1_controlled_probe.py` | `opening_rank1_controlled_probe.v3` |
| 14 | Short Alpha Discriminator | `libs/reporting/short_alpha_discriminator/` | `short_alpha_discriminator.v1` |
| 15 | Alpha Research Board | `libs/reporting/alpha_research_board/` | 14 registered candidates, `canonicalize_board()` |
| 16 | Strategist Stage2 effectiveness | `libs/reporting/evaluation/stage2_authority/` (+ separate, older `strategist_effectiveness.py`) | `strategist_stage2_authority_review.v3` |
| 17 | No-Trade Attribution | **two separate modules**: `no_trade_attribution.py` (day-level passthrough) and `monitor_noop_attribution/` (episode-level real evaluator) | `no_trade_attribution_report.v1` / `monitor_noop_attribution.v1` |
| 18 | Horizon/Exit evaluation | `horizon_contract.py` + `trade_evaluator.py` + `horizon_compliance_report.py` | `q9_horizon_contract.v1` / `q9_horizon_alignment.v1` / `horizon_compliance_report.v1` |
| 19 | Same-symbol sequence | `libs/reporting/evaluation/same_symbol_sequences/` | `same_symbol_sequence_daily.v1` / `...cumulative.v1` |

19 named items, resolving to roughly **22 distinct code-level evaluation
surfaces** once Q13's 4 sub-variants, Q14's 2 sub-variants, Q18's 2
unrelated modules, and No-Trade Attribution's 2 unrelated modules are
counted individually.

```
EVALUATION SYSTEMS FOUND: 22 (distinct code-level evaluation surfaces across 19 named items)
```

---

## 3. Unit of observation per evaluation

| Evaluation | Unit of Observation |
|---|---|
| Q9 | representative candidate per role, per Q9 decision window (requires all 4 roles present) |
| Q10-baseline | per-decision-epoch candidate row (`baseline_decision_id`) |
| Q10-lead-market | per-day, per-target (stock or index) fixed-clock checkpoint |
| Q11 | virtual trade (own opportunity-engine signal → simulated fill) |
| Q12 | decision-candidate row, same shape as Q10-baseline (reused function) |
| Q13-attribution (v0/window/range) | **trade**, scored 0-100 per axis — not a return series at all |
| Q13-entry-timing | trade, using Family-A forward outcomes |
| Q14 | trade, classified into a categorical root-cause label |
| Q15 | n/a (no code) |
| Q16 | candidate/signal event (`top_pick` shadow row) |
| Q17 | same candidate/signal event as Q16 (shared rows) |
| Q18 (`post_reclaim_shadow_review`) | one **pre-aggregated subtype statistic row**, not an observation-level record at all |
| Q18-adjacent (`post_reclaim_alpha`) | episode (own engine) |
| Opening Rank1 Shadow | episode (Scanner rank-1 sighting) |
| Opening Controlled Probe | controlled (mock) execution attempt |
| Short Alpha Discriminator | cohort row (joined episode) |
| Alpha Research Board | candidate/track row (aggregating whichever unit its 14 sources each use) |
| Strategist Stage2 | **paired** rank-1-before / rank-1-after candidate per decision — not a single-observation return series |
| No-Trade Attribution (day) | one day |
| No-Trade Attribution (episode) | blocked-opportunity episode (commander-approve + monitor-NOOP, 300s-gap collapsed) |
| Horizon/Exit evaluation | executed trade |
| Same-symbol sequence | day:symbol trade sequence |

```
COMMON OBSERVATION UNIT: NO
```

At least seven structurally different units are in simultaneous use
(candidate/signal event, day, paired before/after delta, pre-aggregated
statistic, blocked episode, executed trade, day-symbol sequence). "N=10"
means a different kind of thing depending on which evaluation produced it.

---

## 4. Sample definition comparison

| Evaluation | Included in N | Excluded from N |
|---|---|---|
| Q9 | decision windows where all 4 roles (P/A/B/C) present; Commander approve/allow/buy → real return, reject/no-trade/noop/blocked → forced `0.0` | incomplete role windows; any Commander decision string outside the recognized set |
| Q10-baseline | both fixed symbols present AND `features.available` for every candidate | incomplete fixed-universe decisions |
| Q10-lead-market | checkpoint `status=="OBSERVED"`; 09:00 point requires first `volume>0 & open>0` candle in [09:00,09:03]; index checkpoints require collector state `VERIFIED` | placeholder zero-volume candles; unverified index collector states (forced `PENDING`, never substituted) |
| Q11 | signal fires `probe_candidate==True` within 09:00-10:00 on the fixed 3-symbol universe | everything outside that window/universe |
| Q12 | same completeness gates as Q10-baseline, plus its own `policy_variants[...].eligible` flags | same as Q10-baseline |
| Q13-attribution | rows with a `selection_authority_audit.json` entry; entry-timing rows labeled `INSUFFICIENT_EVIDENCE` filtered before scoring | missing audit rows |
| Q14 | any trade, even with missing evidence (force-classified `"Missing Evidence"` rather than dropped) | none dropped outright; only re-labeled |
| Q16 | `shadow_role=="top_pick"`, `triggered`, deduped by `(decision_id, symbol)`/day, `forward_integrity_status=="TRUSTED"` only | non-triggered rows; untrusted baseline/observed-day mismatches |
| Q17 | same Q16 rows, further requiring a `directional_edge_estimate` present and `day >= 2026-07-27` | rows before that date; missing estimate |
| Q18 | the single named subtype row from the upstream Q8 review, promotion additionally requires `observed_count_30m>=20`, `observed_day_count_30m>=10` | everything else |
| Opening Rank1 Shadow | Scanner's real rank-1 candidate within 09:00-09:20 | any non-rank-1 candidate |
| Opening Controlled Probe | rank==1, `HIGH_COMMON_DIRECTIONAL`/`CONFIRMED_RECURRENT_RANK`, cost-edge pass, price-drift within 2%, ≤1/day | everything else (many named reject reasons) |
| Strategist Stage2 | decisions with both a pre-refresh and post-refresh rank-1 row present | decisions missing either side |
| No-Trade Attribution (day) | days with `trade_count<=0` | trading days |
| No-Trade Attribution (episode) | Commander `decision=="approve"` AND `monitor_intent=="NOOP"` | executed trades |
| Horizon/Exit evaluation | `integrity in {PASS,WATCH}`, `net_return is not None`, not an unresolved/duplicate/defect flag | trades failing those integrity gates |
| Same-symbol sequence | actual executed trades with a `trade_read_model.json` | candidates, blocked opportunities |

```
COMMON SAMPLE DEFINITION: NO
```

---

## 5. Forward horizon comparison

| Evaluation | 3m | 5m | 15m | 30m | 60m | 120m | 180m | EOD | T+1/T+2 | fixed clock |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Family A engine itself | ✓ | ✓ | ✓ | ✓ | ✓ | | | ✓ | | |
| Q10-baseline (extends Family A) | | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| Q10-lead-market | | | | | | | | | | ✓ (09:00/09:03/09:05/09:10/09:15/09:30/10:00/CLOSE) |
| Q11 | | ✓ | ✓ | ✓ | ✓ | | | ✓ | | |
| Q12 — main | | ✓ | ✓ | ✓ | | | | ✓ | | |
| Q12 — hypothesis (own second set, disagrees with the first) | | ✓ | ✓ | ✓ | ✓ | | | ✓ | | |
| Q13-entry-timing | | ✓ | ✓ | ✓ | ✓ | | | | | |
| Q16 (main) | | | ✓ | ✓ | | | | | | |
| Q17 (embedded block) | | ✓ | ✓ | ✓ | ✓ | | | | | |
| Q18 | | ✓ | ✓ | ✓ | ✓ | | | | | |
| Opening Rank1 Shadow / Short Alpha Discriminator | | ✓ | ✓ | ✓ | ✓ | | | ✓ | | |
| post_reclaim_alpha (Q18-adjacent) | | ✓ | ✓ | ✓ | ✓ | | | | | |
| Strategist Stage2 | | ✓ | ✓ | ✓ | ✓ | | | ✓ | | |
| Monitor-NOOP attribution | | ✓ | ✓ | ✓ | ✓ | | | ✓ | | |
| Horizon/Exit evaluation (Family B) | | ✓ | ✓ | ✓ | ✓ | | | | | |
| `horizon_revision_backtest` (extra layer over Family B) | | ✓ | ✓ | ✓ | ✓ | | | ✓ | ✓ | |
| Same-symbol sequence | | | | | | | | | | (none — no horizon concept) |

```
COMMON HORIZONS: PARTIAL
```

The label vocabulary `+5m/+15m/+30m/+60m/EOD` recurs constantly, which
creates a strong visual impression of one shared ladder. It is not one:

- **What the offset is measured FROM differs fundamentally by family**:
  - **Family A** (candidate/signal-baseline time) — Q9, Q10-baseline, Q12,
    Q13-entry-timing, Q16, Q17, Monitor-NOOP, Q18's upstream.
  - **Family B** (actual realized exit time) — Horizon/Exit evaluation,
    `horizon_revision_backtest`.
  - **Fixed KST clock time, not an offset at all** — Q10-lead-market.
  - A **third, further independent** candidate-baseline engine exists
    for Opening Rank1 Shadow / Short Alpha Discriminator
    (`post_reclaim_alpha/evaluator.py`) — same label vocabulary as
    Family A, different missing-data/delay-handling code (see §9).
- Q12's own two internal horizon sets (`HORIZONS` vs `HYPOTHESIS_HORIZONS`)
  disagree with each other inside the same module.
- Q10-baseline's `+120m`/`+180m` extension is computed by a **locally
  written third function** (`_extended_checkpoint`) coexisting in the same
  file as an import of the shared Family-A engine for the other horizons.

---

## 6. Entry authority comparison

| Evaluation | Entry Time Authority | Entry Price Authority |
|---|---|---|
| Q9 / Q10-baseline | candidate decision time | `features.baseline_price` at decision time (no fill reconciliation) |
| Q10-lead-market | fixed KST clock time | first candle with `volume>0`/`open>0` in [09:00,09:03] (`open` for 09:00, `close` for later checkpoints); index checkpoints overridden by a dedicated collector when `VERIFIED` |
| Q11 | signal-fire minute | own simulator's candle close at signal time |
| Q12 | candidate decision time (reused Q10-baseline mechanics) | same as Q10-baseline |
| Q13-entry-timing | decision-stage epoch (`_stage_epoch`) | nearest prior minute candle close via its own `_row_at_or_before` (a third independent epoch→price lookup) |
| Q14 | n/a (consumes an already-computed `net_return_pct`) | n/a |
| Q16/Q17 | candidate baseline epoch (Family A) | `baseline_price` (Family A) |
| Opening Rank1 Shadow | Scanner rank-1 naming moment | first minute bar after naming (`baseline_price`, own engine) |
| Opening Controlled Probe | Monitor-blocked-override moment | cached/initial signal price with a 2% drift guard before actual broker submission |
| Strategist Stage2 | decision epoch of the paired candidates | Family A baseline (local reader) |
| Horizon/Exit evaluation | actual realized exit (`holding_seconds`) | actual entry fill (`trade_read_model.entry.price`) |
| Same-symbol sequence | actual trade entry timestamp | actual entry fill |

```
COMMON ENTRY AUTHORITY: PARTIAL
```

Genuinely common *within* the ~8 Family-A adopters (candidate baseline
price/epoch). Structurally different for Family B (real fills), Q10-lead-
market (fixed clock + open/close switch), Opening Alpha's own two-layer
design, and Same-symbol sequence.

---

## 7. Exit / checkpoint price authority

| Evaluation | Checkpoint price source | Missing-checkpoint handling |
|---|---|---|
| Family A engine | nearest minute-bar close at/after target, via `bisect` | `"pending"` (not yet reached); `"stale"` with `reason: stale_cross_day_observation` or `stale_forward_gap` beyond `FORWARD_MAX_OBSERVATION_DELAY_SEC` |
| Q10-baseline `_extended_checkpoint` (+120/180m only) | its own tolerance window `target <= ts <= target+90` | different algorithm from the shared engine, in the same file |
| Q10-lead-market | dedicated point/checkpoint resolver + index collector override; if `CLOSE` isn't `OBSERVED`, every horizon is force-downgraded to `PARTIAL` and `return_to_close_pct` nulled | global "no return without a verified close" rule — distinct from Family A's per-horizon staleness rule |
| Q11 | nearest candle in `[target, target+90]` | `"pending"` if none found — simplest of all the implementations |
| `post_reclaim_alpha` (Opening Alpha shadow) | nearest same-day candle at/after target within `FORWARD_MAX_DELAY_SEC=180s`, with an explicit "last price carried forward" fallback mode | distinct delay-tolerance and carry-forward semantics from both Family A and Q11 |
| Horizon/Exit evaluation (Family B) | **nearest**-observed post-exit checkpoint to the target second (`_closest_observed_checkpoint`), not an exact-label lookup | missing → excluded from the candidate pool; if none observed, `target_checkpoint={}`, `early_exit_cost_pct=None` |
| Same-symbol sequence | n/a — no checkpoint concept | n/a |

```
COMMON EXIT/CHECKPOINT AUTHORITY: PARTIAL
```

---

## 8. Cost model comparison

| Evaluation | Live round-trip cost | Slippage | Source |
|---|---|---|---|
| Shared `cost_basis_comparison.py` | computed: `(0.00015+0.00015+0.002)*100 ≈ 0.23%`; mock fallback `0.9%` | `0.05%` (`DEFAULT_EVALUATION_SLIPPAGE_PCT`) | one real shared function, used by Q16/Q17/Q18's caller/Monitor-NOOP |
| Q10-baseline / Q9 / Q12 (older path) | dynamic: `load_broker_cost_profile()["conservative_round_trip_cost_pct"]` | `0.05%`, but as **three separately typed literals** (`baseline_samsung_hynix/contracts.py`, `baseline_btc_woori_tech/contracts.py`, `full_chain_component_review.py`) — same value, not one shared constant | — |
| Short Alpha Discriminator | hardcoded `LIVE_ROUND_TRIP_COST_PCT = 0.28%` | — | own `contracts.py` |
| Opening Rank1 Shadow / `post_reclaim_alpha` | hardcoded `LIVE_COST_PCT = 0.28%`, **separately** `MOCK_COST_PCT = 1.086849%` | — | own `contracts.py` |
| Strategist Stage2 (`deep_dive.py` only) | hardcoded `LIVE_ROUND_TRIP_COST_PCT = 0.28%` (its own `builder.py`'s delta metrics apply **no cost at all**) | — | own `contracts.py` |
| Alpha Research Board | not its own — but two spots (`_btc_review`, `large_cap_review.py`) **subtract a hardcoded `0.28` literal** from an upstream gross figure | — | Board-package code, not imported from any of the above |
| Horizon/Exit evaluation | **none** — treats input as already net | — | absence confirmed |
| Same-symbol sequence | **none** — already net | — | absence confirmed |

```
COMMON COST MODEL: NO
```

At least **five distinct live-cost percentages** are simultaneously in
circulation (≈0.23% computed, 0.28% hardcoded independently in **four**
separate files, 1.086849% "mock," plus whatever the dynamic broker-cost
profile happens to return), and two entire evaluation families apply no
cost adjustment at all. The 0.28% figure recurring in four files is the
**same number**, independently typed each time — not one shared constant;
nothing imports a single `LIVE_ROUND_TRIP_COST_PCT` from one place.

Q11 net_return_pct / Opening Alpha return / Q10 return / Q12 return /
Board metric — **not the same cost model**, confirmed above.

---

## 9. MFE / MAE comparison

| Evaluation | Computed? | Window |
|---|---|---|
| Family A engine (Q9/Q10-baseline/Q12/Q16/Q17/Monitor-NOOP) | Yes | entry(baseline) → each horizon target, max/min of high/low over the intervening candles |
| Q10-lead-market | Yes | entry(checkpoint) → close, via its own `signed_moves` mechanism |
| Q11 | Yes | entry → each horizon target (own simulator) |
| `post_reclaim_alpha` (Opening Alpha) | Yes | baseline → checkpoint, same-day restricted (an explicit constraint Family A's own code does not enforce) |
| Q13/Q18/Stage2/Same-symbol sequence | **No** | not computed at all |
| Horizon/Exit evaluation | reads `max_post_exit_upside_pct`/`max_post_exit_drawdown_pct` already computed by `post_exit_shadow_recap.py` — a different lineage entirely from Family A's own MFE/MAE | whatever window that module used, not re-derived here |

```
COMMON MFE/MAE: PARTIAL
```

---

## 10. Win/loss definition comparison

- **Dominant convention** (via shared `performance_metrics()`): `net_return_pct > 0` → win, `< 0` → loss, `== 0` → flat. Used by Q9, Q10-baseline, Q12-comparison, Q14, Q16, Q17, Monitor-NOOP, `horizon_alignment`, `horizon_compliance_report` (aggregation stage only).
- **Q10-lead-market**: the *same threshold logic*, but **two separately
  written functions** (`shadow_comparison.py::_metric`, `cumulative.py::build_cumulative`)
  rather than a call into `metrics.py`.
- **Horizon/Exit evaluation**: hand-written locally in `trade_evaluator.py`
  (`net_return>0→"win"`, etc.) — same threshold, not the shared function.
- **Strategist Stage2**: no per-observation win/loss at all — its analogue
  is a *paired-delta materiality test* (`VALUE_ADD`/`DEGRADING`/`NEUTRAL`),
  a categorically different question.
- **Q13** (score modules): no return-based win/loss concept exists.
- **Q18**: no win/loss field in its own output at all (only pre-aggregated
  expectancy figures).
- **Same-symbol sequence**: no win/loss concept — computes cumulative-return
  and "profit giveback" instead.

```
COMMON WIN DEFINITION: PARTIAL
```

---

## 11. Profit factor comparison

| Source | Formula | Zero-loss convention |
|---|---|---|
| Shared `metrics.py::performance_metrics` | `gross_gain / gross_loss` | float `999.0` if any gain else `0.0` |
| Q10-lead-market `shadow_comparison.py::_metric` | `gains/losses` | **string** `"INF"`, or `None` if no gains |
| Q10-lead-market `cumulative.py::build_cumulative` | identical `gains/losses` | same **string** `"INF"` convention (a second, independent copy) |
| Alpha Board `sensitivity.py::_metrics` | `gross_gain/gross_loss` | own copy of the `999.0`/`0.0` convention (a sixth independently-written implementation of the same formula, coincidentally matching #1's convention) |
| Q13, Q18, Stage2, Same-symbol sequence | **not computed** | n/a |

```
COMMON PF DEFINITION: NO
```

This is a genuine type-incompatible divergence, not just a stylistic one:
the same zero-loss situation resolves to a **float `999.0`** in one module
and a **string `"INF"`** in another, both labeled "profit_factor," inside
the same overall "Q10" program.

---

## 12. Average return comparison

Every module that computes a return average uses a **simple arithmetic
mean** — none use a weighted mean. What varies is the *unit* being
averaged: per candidate-horizon observation (Family A programs), per
day-symbol-target-group (Q10-lead-market), per trade (Q14, Horizon/Exit
evaluation), per paired before/after delta (Stage2 — the only one not
averaging a return at all, but a *difference* of two returns), and per
0-100 score, not a return, in Q13's attribution modules.

```
(no single verdict requested for this section by the report template — folded into COMMON WIN/PF DEFINITION verdicts above)
```

---

## 13. Status vocabulary comparison

Dozens of independently-invented literal status strings were found, e.g.:
`PROSPECTIVE`, `COLLECTING`, `READY`, `RETAIN`, `ROLL_BACK`, `CLOSED`,
`INSUFFICIENT_EVIDENCE`, `TRUSTED`/`INVALID`, `OBSERVED`/`PENDING`/`STALE`,
`WAITING`/`MISSED`/`CAPTURED`, `VALUE_ADD`/`DEGRADING`/`NEUTRAL`/`NOT_MEASURABLE`,
`DIRECTIONAL_ADMITTED`, `MISSING_Q9_EVIDENCE`, `POSSIBLE_OVER_FILTERING`,
`Scanner Ranking Failure`/`Rank Drift`/`Strategist Override`, `IN_PROGRESS`/`GO`/`NO_GO`,
`READY_FOR_FIXED_RUNTIME_VALIDATION`/`FAIL_RUNTIME_EFFECT`, and the Alpha
Board's own three-way split (`operation_status`/`fixed_validation_status`/
`production_promotion_status`) introduced specifically because a single
status field was found to conflate three different questions (see §14).

The only recurring pair is the informal `AVAILABLE`/`INSUFFICIENT_EVIDENCE`
idiom — reused casually across many modules as a literal string, never as
a shared enum/constant.

```
COMMON STATUS MODEL: NO
```

---

## 14. Is the Alpha Research Board a calculation authority or an aggregation layer?

**Mixed — confirmed by direct code audit, not assumption.**

- **It never recomputes return/MFE/MAE/checkpoints from raw candles.**
  Every `net_return_pct` it displays traces to a field an upstream module
  already computed and wrote to a JSON artifact.
- **But it is not a pure display layer either.** It:
  1. Re-aggregates already-per-episode net returns into win-rate/PF/mean/
     median/drawdown via its own `sensitivity.py::_metrics()` — the sixth
     independent implementation of that formula found in this review.
  2. **Directly computes two "net" figures itself** by subtracting a
     hardcoded `0.28` literal from an upstream gross figure
     (`remaining_reviews.py::_btc_review` line 107;
     `large_cap_review.py::collect_large_cap_daily_rows` line 42).
  3. Applies its **own** promotion-gate thresholds
     (`MIN_SAMPLE=10`, `MIN_PROFIT_FACTOR=1.20`, forward-coverage ≥0.90,
     win-rate ≥0.55, leave-one-out sensitivity, symbol/day concentration
     caps) that are not read from any source artifact.
  4. Re-derives its own status vocabulary
     (`DISCOVERY/PROSPECTIVE/REVIEW_READY/PROMOTED/CLOSED`,
     `SHADOW_CONTINUES/CONTROLLED_MOCK_CONTINUES/...`) from upstream
     free-text fields via its own string-matching rules — with the
     package's own code comments (`canonical.py:142-189`) documenting
     that this status logic was **patched three times** after repeated
     internal audits found it conflating "is the shadow experiment still
     running," "did the fixed-window runtime validation already fail,"
     and "is production promotion allowed" into one field.

```
ALPHA BOARD ROLE: MIXED
```

Board = one table ≠ evaluation basis = one standard.

### Real Board contents (verified against `reports/evaluation/alpha_research_board/2026-09-11/alpha_research_board.json`)

14 candidates confirmed live (`"candidate_count": 14`):

| candidate_id | source artifact | target_horizon | N | win_rate | avg_net_return_pct | profit_factor |
|---|---|---:|--:|--:|--:|--:|
| `IMMEDIATE_OPENING_PROBE` | `opening_rank1_shadow_cumulative.json` | +5m | 26 | 0.6538 | 1.3975 | 3.5317 |
| `CONFIRMED_RECURRENT_RANK` | same file | +30m | 4 | 0.75 | 4.0405 | 58.7218 |
| `DISLOCATION_REBOUND` | same file | +60m | — | — | — | — |
| `OPEN_0_20_RANK1_30M` | same file (aggregate) | +30m | 117 | 0.4872 | 0.3869 | 1.2535 |
| `SAMSUNG_HYNIX_FIXED_UNIVERSE_TOP1` | `baseline_samsung_hynix_forward_returns.json` | +180m | 15 | 0.6667 | 0.0236 | 1.0509 |
| `STRATEGIST_STAGE2_REFRESH_AUTHORITY_V1` | `strategist_stage2_effectiveness_deep_dive.json` | +30m | 124 | 0.3468 | -0.005 | null |
| `HIGH_COMMON_SHORT_ALPHA_V1` | `short_alpha_discriminator.json` | +5m | 19 | 0.3158 | -0.9032 | 0.532 |
| `TOP_VALUE_VOLUME_NEGATIVE_CONTROL_V1` | same file | +5m | 37 | 0.4324 | -0.5258 | 0.5309 |
| `R1_SCANNER_RISK_HIGH_30M_V1` (CLOSED) | `opening_cumulative` + feature mart | +30m | 54 | 0.4815 | 0.281 | 1.1384 |
| (5 more registered candidates — fresh-change activation, MA5/20 extended, latent reactivation, BTC v2, BTC strong-bull — see `contracts.py::CANDIDATE_REGISTRY`) | various | various | — | — | — | — |

**Every registered candidate is normalized into one frozen row schema**
(`ROW_COLUMNS` in `contracts.py`, enforced by an explicit column-equality
check in `canonicalize_board()` — a genuine, working canonical *display*
record) — but the metric sub-objects tolerate missing fields per source
(e.g. `STRATEGIST_STAGE2_REFRESH_AUTHORITY_V1`'s `profit_factor` is
hardcoded `None` because its source never had that concept).

**Horizon is not uniform across rows** — each candidate_id is pinned to
exactly one horizon in `TARGET_HORIZONS` (ranging from `+5m` to `+180m`
across the 14 rows); there is no shared horizon ladder applied board-wide.

**Confirmed episode-overlap risk**: rows `IMMEDIATE_OPENING_PROBE`,
`CONFIRMED_RECURRENT_RANK`, `DISLOCATION_REBOUND`, `OPEN_0_20_RANK1_30M`,
and `R1_SCANNER_RISK_HIGH_30M_V1` all provably read from the **same**
underlying `opening_rank1_shadow_cumulative.json` episode population, with
**no cross-row de-duplication logic anywhere in the package**. A single
real-world episode eligible for more than one lane condition is not
prevented from being counted inside more than one Board row's `N`.

---

## 15. Q9's actual role

**Not a canonical cross-pipeline comparator.** `q9_comparison.py` and
`unified_comparison.py` only ever read Q10-baseline's own in-memory summary
(passed as a function parameter from the same pipeline run) — they never
open a Q10-lead-market, Q11, or Q12 output file. **The real side-by-side,
multi-program comparator is Q12's own `comparison.py`**, which explicitly
reads Q10-baseline's artifact file **and separately re-invokes Q9's own
comparison function itself** to assemble one combined table
(`q12_confirmed_entry`, `woori_buy_and_hold`, `btc_momentum_only`,
`samsung_hynix_top1`, `q9_roles`). Q9 is a diagnostic layered onto Q10;
Q12 is the actual comparator, not Q9.

## 16. Q13/Q14's actual role

**Independent bespoke diagnostics**, bridged only by a non-calculating
aggregator (`q13_q14_validation.py`) that reads both modules' already-
written JSON output and layers a GO/NO_GO stability decision on top,
performing no calculation of its own. That aggregator's own
`validation_rules` explicitly state: **"Q13/Q14 axes and score formulas
are frozen."** By the system's own stated design, Q13/Q14 are point-in-time
diagnostic snapshots, not components of a live, continuously-comparable
evaluation framework.

## 17. Q17 vs. "Horizon/Exit evaluation" — resolving a plausible confusion

Q17 is **not** the same thing as the dedicated "Horizon/Exit evaluation"
pipeline, and the two share no code:

- **Q17** = a field-block embedded inside Q16's own file, reusing Q16's
  same candidate rows and the shared Family-A engine.
- **"Horizon/Exit evaluation"** (`horizon_contract.py`/`trade_evaluator.py`/
  `horizon_compliance_report.py`) = a wholly separate, exit-anchored
  (Family B) pipeline over **executed trades**, with no import of
  `quant_shadow_forward_outcomes` anywhere in its chain, and with **no cost
  model of its own at all** (treats input as already net).

A plausible prior assumption that "Horizon/Exit evaluation" is Q17's
implementation is **not corroborated by any constant or docstring in
either module** and is contradicted by the import graph.

---

## 18. Full inventory of independent calculation functions

### Forward-checkpoint / MFE-MAE calculators (raw-candle-consuming)

| Function | Used by | Horizons | Entry authority | Cost model |
|---|---|---|---|---|
| `quant_shadow_forward_outcomes.py::attach_forward_outcomes` | Q9, Q10-baseline, Q12(inherited), Q13-entry-timing, Q16, Q17, Monitor-NOOP | +3/5/15/30/60m, EOD | candidate baseline | caller-supplied |
| `baseline_samsung_hynix/forward_returns.py::_extended_checkpoint` | Q10-baseline (+120/180m only) | +120m,+180m | candidate baseline | caller-supplied |
| `opportunity_engine/simulator.py::_forward_returns` | Q11 | +5/15/30/60m, EOD | own signal fill | caller-supplied |
| `post_reclaim_alpha/evaluator.py::_checkpoint`/`_eod_checkpoint` | Opening Rank1 Shadow, Short Alpha Discriminator (indirectly) | +5/15/30/60m, EOD | candidate baseline (own delay/carry-forward logic) | own `LIVE_COST_PCT=0.28`/`MOCK_COST_PCT=1.086849` |
| `baseline_samsung_hynix/forward_validation/reaction_reader.py` | Q10-lead-market | fixed clock times | fixed clock (open/close) | own cost_model dict |
| `evaluation/entry_timing_attribution.py::_row_at_or_before` | Q13-entry-timing | +5/15/30/60m (via Family A) | decision-stage epoch | n/a (price lookup only) |
| `post_exit_shadow_recap.py` (Family B engine) | Horizon/Exit evaluation | +5/15/30/60m, EOD | actual exit time | none |
| `libs/runtime/strategy_horizon_feedback.py::update_post_exit_shadow_with_price_observations` | post-exit shadow tracking (separate feature, outside this review's 19 named items but structurally the same class of function) | +5/15/30/60m, EOD, T+1, T+2 | actual exit time | none |
| `horizon_revision_backtest/analysis.py` | (research tool over Family B) | actual_exit, +5/15/30/60m, EOD, T+1, T+2 | actual exit time | none |
| `short_alpha_discriminator/metrics.py::checkpoint_return` | Short Alpha Discriminator | reads pre-built episode shape | n/a (pure reader) | n/a (pure reader) |

**10 independently-written forward-checkpoint functions.**

### Aggregate-statistics (win/PF/avg/MDD) calculators

| Function | Used by | Zero-loss convention |
|---|---|---|
| `libs/reporting/evaluation/metrics.py::performance_metrics` | Q9, Q10-baseline, Q12-comparison, Q14, Q16, Q17, `horizon_alignment`, `loss_decomposition`, `strategist_effectiveness`, `horizon_compliance_report`, Monitor-NOOP, `post_reclaim_alpha` (imports it), `horizon_revision_backtest` | float `999.0`/`0.0` |
| `libs/reporting/short_alpha_discriminator/metrics.py::performance` | Short Alpha Discriminator | float `999.0`/`0.0` (own copy) |
| `libs/research/opportunity_engine/simulator.py::summarize_trades` | Q11 | no explicit zero-loss branch shown |
| `baseline_samsung_hynix/forward_validation/shadow_comparison.py::_metric` | Q10-lead-market | **string** `"INF"` / `None` |
| `baseline_samsung_hynix/forward_validation/cumulative.py::build_cumulative` | Q10-lead-market (second copy) | **string** `"INF"` / `None` |
| `libs/reporting/alpha_research_board/sensitivity.py::_metrics` | Alpha Research Board | float `999.0`/`0.0` (own copy) |

**6 independently-written aggregate-statistics functions.**

```
FORWARD CALCULATORS FOUND: 16 (10 forward-checkpoint + 6 aggregate-statistics), independently written
```

---

## 19. Empirical cross-evaluator consistency test

A single synthetic minute-candle episode (entry 09:00, +1%/+2%/+3%/+4%/+5%
at the +5m/+15m/+30m/+60m/EOD marks respectively) was fed directly into
Q11's `_forward_returns` and Opening Alpha shadow's `_checkpoint`/
`_eod_checkpoint` functions (both imported live from the actual repo, no
modification):

```
horizon   Q11 gross    OpeningAlpha gross
+5m           1.0            1.0
+15m          2.0            2.0
+30m          3.0            3.0
+60m          4.0            4.0
EOD           5.0            5.0
```

Gross return and MFE/MAE matched exactly for this clean, no-gap synthetic
case — the underlying formula (`close/baseline - 1`) is trivial enough
that it does not diverge under ideal conditions. **Net return only matched
because the test manually forced Q11's cost parameter to equal Opening
Alpha's hardcoded `0.28%`** — in real operation Q11 uses a dynamically
loaded broker-cost-profile value while Opening Alpha uses the hardcoded
`0.28%`/`1.086849%` pair, so real net returns would diverge whenever those
values differ (which, per §8, they routinely do). Missing/delayed-price
handling logic also differs by design (Q11's simple ±90s window vs. Opening
Alpha's 180s-tolerance carry-forward semantics) and would diverge under
any less-clean, real-world gap pattern not exercised by this idealized test.

```
CROSS-EVALUATOR SAME-INPUT RESULT: PARTIAL_MATCH
```
(Identical on gross return/MFE/MAE for a clean input; genuinely divergent
on net return, cost application, and missing-data handling.)

---

## 20. Real 2026-09-11 cross-report check

Q11's actual 2026-09-11 trades: symbol `009150` only (its own fixed
universe member). Opening Alpha's actual episodes that day: `024060`,
`032820`, `462330` (Scanner's real rank-1 picks) — **zero symbol overlap**.
Checked across Opening Alpha's entire 117-episode history: symbol `009150`
has **never once** appeared as a Scanner rank-1 pick.

```
2026-09-11 CROSS-REPORT CONSISTENCY: FAIL
```

Not because any two reports disagree on a shared fact — because **no
shared fact currently exists to check**. The two systems' candidate
universes have not overlapped even once in the available history, so a
same-episode numeric cross-check between Q11 and Opening Alpha is not
currently possible from real artifacts. Separately, within the Alpha
Board itself, rows 1/2/3/4/12 (§14) do share the same underlying episode
pool — but since they all read the identical pre-computed field, any
single episode's *value* would agree across those rows by construction;
the real risk there is double-counting in aggregate `N`, not value
disagreement.

---

## 21. Is "parallel accumulation" actually happening?

| Question | Verdict |
|---|---|
| 매 거래일 동일한 cadence로 평가되는가? | PARTIAL — Q11 and Opening Alpha both run continuously and are current through 2026-09-11; several diagnostics (Q13/Q14/Q15/Q18) run once or intermittently, not on a daily cadence |
| 동일한 data completeness rule을 사용하는가? | NO — completeness gates are bespoke per module (§4) |
| 동일한 horizon completion rule을 사용하는가? | NO — at least 3 distinct missing-data/delay algorithms exist (§7, §9) |
| 동일한 missing-data policy를 사용하는가? | NO — `pending`/`stale`/`PARTIAL`/exclude-from-pool are different modules' different answers to the same situation |
| 동일한 cost model을 사용하는가? | NO — §8 |

```
PARALLEL DAILY ACCUMULATION: PARTIAL
```
(True in calendar terms for the still-active programs; not true in any
comparability sense.)

---

## 22. Is "equal comparison" actually happening?

Comparing `IMMEDIATE_OPENING_PROBE` (65.4% win rate) vs. `Q11` (0% win
rate on 2026-09-11's two trades) vs. `BTC_STRONG_BULL` (71.4% win rate)
directly, as the Board's own table layout invites:

- different universe (Scanner-live vs. fixed 3-symbol vs. BTC/Woori),
- different observation unit (episode vs. trade vs. episode),
- different entry authority (§6),
- different horizons (each pinned to its own single value, §14),
- different (or absent) cost model (§8),
- different sample maturity (26 vs. 2 vs. an unspecified BTC N),
- different execution mode (observation-only vs. shadow vs. controlled-mock).

```
DIRECT COMPARABILITY OF ACTIVE ALPHA CANDIDATES: NOT_DIRECTLY_COMPARABLE
```

---

## 23. Linear evaluation — is the original goal actually met?

```
LINEAR EVIDENCE ACCUMULATION: PARTIALLY_IMPLEMENTED
```

Each individual program does accumulate its own evidence linearly over
calendar time within itself (Opening Alpha: 117 episodes since 2026-08-03;
Q11: continuous daily reports). What does **not** exist is the
cross-program axis alignment (same metric set, same horizon, same cost,
same sample definition) that would make that accumulated evidence directly,
fairly comparable on one shared axis — which was the original stated goal.

---

## 24. Canonical metric set

No metric set is held in common by all active candidates. `profit_factor`
is `None` for at least one Board row (`STRATEGIST_STAGE2_REFRESH_AUTHORITY_V1`)
by construction, since its source concept never had one. MFE/MAE is absent
from Q13/Q18/Stage2/Same-symbol-sequence entirely. The only fields present
across nearly everything that computes a return at all are `N` and some
form of average return — even `win_rate` is absent from Q18's own output.

## 25. Canonical evaluation record

```
CANONICAL EVALUATION RECORD: NO
```

No shared `experiment_id/candidate_id/episode_id/entry_time/entry_price/
horizon/gross_return/net_return/mfe/mae/cost/status` schema exists that
all Q's populate at the source. The **one** genuine canonical record in
the whole system is the Alpha Research Board's own `ROW_COLUMNS` display
schema (§14) — but that is a display-time normalization applied to a
subset of programs after each has already computed things its own way; it
is not a source-level contract any Q writes to directly.

## 26. Historical evidence continuity

Not exhaustively re-verified in this pass beyond what's implied by §2's
schema-version strings (`.v1`, `.v2`, `.v3` suffixes recur across nearly
every module, confirming each module tracks its *own* schema evolution
independently) and by the Alpha Board's own documented history of three
successive status-logic patches (§14) — i.e. even the one place that tries
to hold a canonical record has had to revise its own contract multiple
times as new conflations were discovered.

---

## 27. Final judgment (five axes)

```
A. EVALUATION TABLE UNIFIED: PARTIAL     -- one display table exists (Alpha Board), the numbers feeding it are not computed the same way
B. FORMULAS UNIFIED: NO                  -- 16 independent calculation functions, including a float/string type mismatch in profit factor
C. HORIZONS UNIFIED: PARTIAL             -- shared label vocabulary, at least 3 structurally different base-timestamp families underneath it
D. SAMPLE DEFINITIONS UNIFIED: NO        -- at least 7 structurally different observation units in simultaneous use
E. FAIR DIRECT COMPARISON: NO            -- confirmed NOT_DIRECTLY_COMPARABLE in §22
```

---

## 28. What was explicitly not done

No evaluation logic, threshold, report, strategy, or runtime code was
modified. No Q100 was introduced or designed. No Q number was reclassified.
No new evaluation framework was designed. No commit, no push, no live
restart, no production-state change.
