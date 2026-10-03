# UEF-2A -- Forward/Checkpoint Calculator Inventory & Canonical Policy Contract

Status: **UEF-2A BOUNDARY CLOSURE (generic core + source-derived semantic profiles, contract
only -- no engine)**. UEF-2B (the actual resolver/calculation engine) is not started. This
document is the input UEF-2B must build against; it does not itself compute anything.

**READ THIS FIRST**: after five rejected/superseded iterations (initial, Fix1, Fix2, Semantic
Authority Reset, Boundary Closure), the current authoritative contract description is **\S17
(Q11 EXIT FINAL FIDELITY PATCH)** at the end of this document -- Calculator 8's forward-horizon
vs. EXIT excursion chains are now correctly separated; **FULLY LOSSLESS PROFILES: 14 / 14**.
\S15 (BOUNDARY CLOSURE) still holds for the required 14-calculator recipe coverage table and
the generic-core/semantic-profile split; \S16 (Q11 FINAL CLOSURE PATCH) is superseded by \S17
(its EXIT excursion fix was itself incomplete). \S1-\S14 below are kept as the historical
record of how the contract got here; several of their specific claims are superseded by later
sections' re-verified findings (notably \S14.4's `RETRACEMENT_SCAN`/`UEF2_FORWARD_ENGINE`
ownership ruling for `FIRST_PULLBACK_ENTRY`, now reversed to `UPSTREAM_REFERENCE_RESOLUTION`;
\S14.6 calculator 1's Q9 EOD chain/excursion; \S14.6 calculator 11's Q12 vnext completeness
gap; \S14.6 calculator 12's Opening Shadow 1A excursion fallback; \S14.6 calculator 14's
Opening Shadow 1C excursion bound; \S14.6 calculator 8's Q11 reference/excursion, corrected
twice more in \S16 and \S17). Do not treat \S1-\S13's `PriceAuthority`/`MfeMaePolicy`/
single-chain framing, or \S14's `RETRACEMENT_SCAN` framing, as current -- the live contract
uses `PriceCandidate` (ordered chains everywhere),
`ExcursionPolicy` (now with optional `DataCompletenessPolicy`), and `ReferenceResolutionPolicy`
(now `EXTERNAL_EVENT_TIMESTAMP`/`PRE_RESOLVED_REFERENCE`) -- see \S15.

**Fix1** closed Codex's first `REJECT_UEF2A` findings (HIGH:6/MEDIUM:1/LOW:1): several
checkpoint-varying semantics (price authority, MFE/MAE window/basis, observation window,
missing-resolution rule) were moved off the whole-`ForwardPolicy` level onto
`HorizonSpec`/`ObservationPolicy`/`MfeMaePolicy` -- see \S5's "Level" column.

**Fix2 (this revision)** closes Codex's SECOND `REJECT_UEF2A` findings (HIGH:7/MEDIUM:1/LOW:1)
-- a different class of problem: several of Fix1's now-correctly-placed fields still
recorded the WRONG value, found by re-reading the real source with the priority order Codex
specified (**real source code > real artifact > any existing UEF test's prior expectation**).
Concretely: (a) a single `PriceAuthority` cannot express Opening Shadow's real OPEN-then-CLOSE
reference-price fallback -- replaced by an ORDERED `PriceResolutionPolicy` chain; (b) Fix1
classified the shared forward engine's (and Opening Shadow's) MFE/MAE window end as "the
matched bar's own observed timestamp" when re-reading the actual code shows it is bounded by
the checkpoint's NOMINAL TARGET timestamp instead -- a real difference whenever the match
lands late; (c) Fix1's Q11 own-outcome checkpoint used an invented `relative_seconds=1` where
the real semantics are the origin instant itself, `relative_seconds=0`; (d)
`USE_SESSION_CLOSE_FALLBACK` had no concrete target -- now requires a `SessionCloseSpec`;
(e) `ExcursionPriceField.CLOSE` had zero real evidence anywhere and was removed, following
Fix1's own "no evidence -> no active canonical semantic" rule (already applied there to
`NEAREST`). See \S13 for the complete, itemized correction list with re-verified file:line
citations. \S2's calculator inventory prose is corrected in place where these findings
apply (marked "Fix2 correction"); nothing else in \S2 changed.

Scope discipline (repeated from the request, kept verbatim as the boundary of this
document): no new record family, no identity redesign, no UEF-2B engine, no cost/metric
implementation, no legacy adapter, no Alpha Board change, no strategy/runtime change, no
production-state change. UEF-1's Record/Identity/Relation/Lineage contract is **unchanged**
by this document -- every enum reused below (`EventOrigin`, `ReturnUnit`,
`Checkpoint.horizon_set_id`) is imported, not redefined.

## 0. Method

Every claim below is grounded in the actual repository source (file:line) or a real,
already-generated artifact under `reports/`/`data/logs/` -- never inferred from a file name
or a Q-number alone. Two calculators sharing a horizon label (e.g. `"+5m"`) were verified
independently; several turned out to mean genuinely different things (different origin,
different tolerance, different price field) even when the label was identical.

## 1. Programs inventoried

| Program | Directory / module |
|---|---|
| Q9 "Horizon/Exit" (post-exit shadow) | `libs/runtime/strategy_horizon_feedback.py`, `libs/reporting/post_exit_shadow_recap.py`, `libs/reporting/evaluation/horizon_contract.py` |
| Q10 Semiconductor (Samsung/Hynix stock-level baseline) | `libs/reporting/baseline_samsung_hynix/{forward_returns,q9_comparison}.py`, shared engine `libs/reporting/quant_shadow_forward_outcomes.py` |
| Q10 Index / lead-market (fixed-clock KOSPI/KOSDAQ + stock reaction) | `libs/reporting/baseline_samsung_hynix/forward_validation/{reaction_reader,shadow_comparison,cumulative}.py` |
| Q11 Opportunity Engine (Opening Surge & Market Reversal) | `libs/research/opportunity_engine/simulator.py` |
| Q12 BTC/Woori Tech (crypto-signal, KRX-equity-priced) | `libs/reporting/baseline_btc_woori_tech/{forward_returns,hypothesis_forward,vnext/outcomes}.py` |
| Opening Shadow (opening rank-1, pure observation) | `libs/reporting/opening_rank1_shadow/latent_forward.py`, `libs/research/opening_rank1_longitudinal/delayed_outcomes.py` |
| Opening Controlled (opening rank-1, real submission/fill) | `libs/runtime/opening_rank1_controlled_probe.py`, `libs/runtime/controlled_mock_lanes/coordinator.py` -- **no forward calculator of its own**, see \S6 |
| Same-Symbol Sequences | `libs/reporting/evaluation/same_symbol_sequences/{builder,pipeline}.py` -- **no forward/checkpoint concept at all**, see \S6 |
| Stage2 Authority | `libs/reporting/evaluation/stage2_authority/{builder,deep_dive,deep_dive_report}.py` -- **reads the same shared engine as Q10 Semiconductor**, does not recompute, see \S6 |

Total: **14 checkpoint calculators** (each independently-implemented target/observation/window
rule that resolves a price/return against real market data, counted once, per \S2) **+ 3
downstream aggregators** (functions that only post-process already-resolved checkpoints --
`summarize_forward_returns`, `build_q9_role_comparison`, `build_cumulative` -- never
themselves computing a new price/target/window). Fix1 correction: the first UEF-2A pass
counted these 17 together as "17 forward calculators"; Codex's audit (L1) correctly
required the two kinds kept distinct, since aggregators consume a calculator's OUTPUT and
must never be counted toward, or mistaken for, UEF-2's forward-calculation-engine scope.
14 checkpoint calculators is close to the order of magnitude the prior integrity review
estimated ("~10"), undercounting because several files each contain more than one
independent implementation -- e.g. Q10 Semiconductor alone has 3 calculators + 2
aggregators.

## 2. Full calculator inventory

Legend for the "Selection" column: `FIRST_AT_OR_AFTER[tol]` = first bar at/after target,
optionally bounded by a tolerance in seconds (`unbounded` = no ceiling at all);
`LAST_AVAILABLE` = last qualifying bar once a wall-clock floor is crossed; `EXACT` = exact
timestamp match only, else missing.

### 2.1 Q9 "Horizon/Exit" -- post-exit shadow (`strategy_horizon_feedback.py::update_post_exit_shadow_with_price_observations`)

| Field | Value | Evidence |
|---|---|---|
| Origin | `exit_ts` (the trade's own real exit/fill event) | `strategy_horizon_feedback.py:898` |
| Horizons | `+5m,+15m,+30m,+60m,EOD` (`T+1`/`T+2` declared in the placeholder schema, never computed) | `:97-102`, `:865-873` |
| Target rule | `exit_epoch + minutes*60` | `:940` |
| Selection | `FIRST_AT_OR_AFTER[unbounded]` | `:942` |
| EOD | last row with KST `HHMM >= "1530"` | `:980` |
| Missing | explicit `"pending"`, reasons `missing_exit_time_or_price`/`no_minute_rows`/`no_rows_after_exit`/`checkpoint_targets_not_reached` | `:900-935`, `:1008-1009` |
| Price authority | `close` (fallback `price`/`current_price`/`cur_price`) | `:914`, `_row_price` |
| MFE/MAE window | **growing per-checkpoint**: `[exit_epoch, this checkpoint's own observed_ts]`, both ends inclusive | `:929`, `:955` |
| Gross return | `(price/exit_price) - 1` -- **FRACTION**, no `*100` | `:970` |
| Cost | NOT PRESENT | -- |
| Status vocabulary | `"pending"`/`"observed"` (2-state) | throughout |
| Real artifact | `reports/trades/2026-05-15/0900/TRD_20260515_066570_01/reports/post_exit_shadow_recap.json` (symbol 066570) | -- |

### 2.2 Q10 Semiconductor (5 independently-implemented calculators, all under `baseline_samsung_hynix/`)

| Calc | File:fn | Origin | Horizons | Selection | Tolerance | EOD | Price | MFE/MAE window | Gross formula | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| A | `quant_shadow_forward_outcomes.py::attach_forward_outcomes` | decision-time baseline candle (`baseline_epoch`) | `+3m,+5m,+15m,+30m,+60m,EOD` | `FIRST_AT_OR_AFTER` via `bisect_left`, else stale cross-day fallback | 180s (`FORWARD_MAX_OBSERVATION_DELAY_SEC`, `q8_evaluation_contract.py:13`) | last same-day row `>= (15,20)` | `close` | `[base_epoch, target]` inclusive both ends -- **Fix2: `target` here is the NOMINAL target epoch (`future_end = bisect_right(same_day_epochs, target)`, line 295), never the matched row's own epoch (`MfeMaeWindowEnd.TARGET_TIMESTAMP`)** | `(close/base-1)*100` | `+3m` computed but dropped by `HORIZONS` (`contracts.py:9` omits it) |
| B | `baseline_samsung_hynix/forward_returns.py::_extended_checkpoint` | same `base_epoch` | `+120m,+180m` | `FIRST_AT_OR_AFTER[90s]`, separate re-implementation | 90s inline literal | n/a | `close` | `(base_epoch, observed]` -- **excludes origin bar** | same formula | Different inclusivity from A |
| C | `forward_returns.py` inline EOD override | same | `EOD` | `LAST_AVAILABLE`, unconditionally **overwrites A's EOD** | n/a | last row `>= (15,30)` -- **different from A's 15:20** | `close` | full `same_day_rows` | same formula | Two conflicting EOD gates in one pipeline (\S5.2) |
| D | `forward_returns.py::summarize_forward_returns` | -- (aggregation only) | -- | -- | -- | -- | -- | -- | `value - (cost_pct+slippage_pct)` | cost mixed in here only |
| E | `q9_comparison.py::build_q9_role_comparison` | -- (aggregation only) | -- | -- | -- | -- | -- | -- | Commander-reject rows scored as `0.0` (cash) -- a **deliberate policy choice**, not a missing-observation default | labeled `"commander_policy_return_approved_candidate_else_cash_zero"` |

Real artifact: `reports/evaluation/baseline_samsung_hynix/2026-09-11/baseline_samsung_hynix_forward_returns.json` (symbol 005930, all 7 horizons observed).

### 2.3 Q10 Index / lead-market (4 independently-implemented calculators, `forward_validation/`)

| Calc | File:fn | Origin | Horizons | Selection | Price | MFE/MAE window | Gross formula | Notes |
|---|---|---|---|---|---|---|---|---|
| F | `reaction_reader.py::_stock_reaction`/`_forward_window` | fixed wall-clock label epoch (`"09:00".."10:00"`, `"CLOSE"=15:30`) | `CHECKPOINTS=("09:00","09:03","09:05","09:10","09:15","09:30","10:00","CLOSE")` | `"09:00"`: first positive-volume/positive-open row in `[09:00,09:03]`; `"CLOSE"`: last row in `[close-600s, close+60s]`; else `FIRST_AT_OR_AFTER[90s]` | `open` at `"09:00"`, `close` elsewhere -- single authority each, no fallback evidence found (`price_field = "open" if label == "09:00" else "close"`, `:184`) | `[entry_ts, end-of-available-rows]` inclusive -- `MfeMaeWindowEnd.UNBOUNDED_FORWARD` (`future = [row for row in rows if row["ts"] >= entry_ts]`, `_forward_window:117`, no upper bound computed at all) | `(current/base-1)*100` | Three different selection rules by label, in one function |
| G | `reaction_reader.py::_index_reaction` | same, plus a **collector-verified override** for `{"09:30","10:00","CLOSE"}` that reads a live index snapshot's `"current"` field directly (no tolerance at all) | same | tri-state: ABSENT→fallback to F, INVALID→forced PENDING (never falls back), VERIFIED→direct snapshot | `current` (QUOTE, not a candle) for the override path -- both `"open"`/`"close"` of the synthetic collector row are set to the SAME `current` value (`:412-413`), so there is no real open/close distinction inside a VERIFIED point; else delegates to F | delegates to F | delegates to F | Explicitly documented prior defect: an unverified collector state used to silently fall through to the legacy value (fixed; comment at `reaction_reader.py:156-171`) |
| H | `shadow_comparison.py::build_shadow_comparison` | whichever fixed-clock checkpoint (F/G) resolved as entry | `ENTRY_0900/0903/0905/0910` + `FIRST_PULLBACK_ENTRY` | inherited from F/G; pullback entry = first >=50% retrace within 60min of open | `close`/`open` per F's rule | `[entry_ts, end-of-path]`, **signed** by `direction` | `direction*(close/entry-1)*100`, `direction in {+1,-1,0}` from pre-open expected-signal state | **The one real short/inverse formula found in the whole inventory** |
| I | `cumulative.py::build_cumulative` | -- (aggregation of H's already-net rows) | -- | -- | -- | -- | -- | -- |

Real artifact: `reports/evaluation/baseline_samsung_hynix/2026-09-11/q10_forward_validation/q10_actual_market_reactions.json` (`targets.samsung`, symbol 005930).

### 2.4 Q11 Opportunity Engine (`opportunity_engine/simulator.py`)

| Field | Value | Evidence |
|---|---|---|
| Origin (forward checkpoints) | `entry_epoch` -- a **simulated/shadow** entry (a minute candle matching a live `probe_candidate` signal); UEF-1's own representability test (`test_real_q11_opportunity_engine_roundtrip`) classifies this as `EventOrigin.SIGNAL`, not `ENTRY`, because the position is never real (`execution_mode=SHADOW`) | `simulator.py:117-143`; `tests/test_uef1_work_package_a_canonical_contract.py:1189` |
| Origin (own realized outcome) | the trade's own `exit_epoch` -- `EventOrigin.ACTUAL_EXIT`, genuinely different anchor from the five SIGNAL checkpoints on the same episode | `simulator.py:177-184` |
| Horizons | `+5m,+15m,+30m,+60m,EOD` | `simulator.py:24` |
| Target rule | `entry_epoch + minutes*60` | `:25` |
| Selection | `FIRST_AT_OR_AFTER[90s]` | `:26-29` |
| EOD | last row with `raw_ts[8:12] >= "1530"` | `:52` |
| Price authority | `close` | `:34,39` |
| MFE/MAE (forward checkpoints) | growing window `[entry_epoch, this checkpoint's ts]` inclusive | `:33,35-36` |
| MFE/MAE (own outcome) | fixed window `[entry_epoch, exit_epoch]`, running max/min per candle | `:147-150` |
| Gross return | `(close/entry-1)*100` -- **PERCENTAGE_POINTS** | `:39,44-45,181` |
| Cost | mixed in: `_net_return_pct(entry, exit, cost_pct, slippage_pct)` | `:6-8` |
| Real artifact | `reports/evaluation/opportunity_engine_shadow/2026-09-11/opportunity_engine_virtual_trades.json` (symbol 009150) | already load-bearing in UEF-1's own suite |

### 2.5 Q12 BTC/Woori Tech (3 calculators + 4 distinct horizon-set constants)

The underlying priced instrument is **always Woori Technology Investment (KRX equity,
`041190`) minute candles** -- BTC is only a signal input, never the priced leg, in any of
the three calculators below.

| Horizon set | Contents | Consumer |
|---|---|---|
| `HORIZONS` (`contracts.py:9`) | `("+5m","+15m","+30m","EOD")` | `comparison.py`, `historical_review.py`, `forward_returns.py` (via the shared Q10-Semiconductor engine, \S2.2-A, plus its own `+120m/+180m` extension) |
| `HYPOTHESIS_HORIZONS` (`contracts.py:10`) | `("+5m","+15m","+30m","+60m","EOD")` -- superset of `HORIZONS`, adds `+60m` | `hypothesis_forward.py` only |
| vnext literal tuple | `('09:30','10:00','EOD')` -- clock-time labels, disjoint labeling scheme | `vnext/outcomes.py` |
| shared-engine `CHECKPOINT_MINUTES` | `(3,5,15,30,60)` | `quant_shadow_forward_outcomes.py` -- the engine `HORIZONS` itself draws from |

| Calc | Origin | Selection | Price | Missing states | Gross formula | Notes |
|---|---|---|---|---|---|---|
| Calculator 1 (`forward_returns.py`, via shared Q10 engine) | decision-time baseline candle | `FIRST_AT_OR_AFTER` (`bisect_left`) + 180s tolerance (shared) / 90s (own `+120m/+180m` extension) | `close` | `pending`/`stale` (lowercase) | `(close/base-1)*100` | Identical engine to Q10 Semiconductor Calc A |
| Calculator 2 (`hypothesis_forward.py`) | fixed candidate-entry snapshot (`"09:00"`,`"09:03"`,`"09:05"`,`"09:10"`,`"PULLBACK"`) | `FIRST_AT_OR_AFTER[90s]`; EOD = last row `>= 15:30` | `close` | `MISSING`/`PENDING`/`OBSERVED` (**uppercase** -- distinct casing from Calc 1) | `(close/entry-1)*100` | Sole consumer of `HYPOTHESIS_HORIZONS` |
| Calculator 3 (`vnext/outcomes.py`) | fixed candidate-entry snapshot | `EXACT` only, no fallback (`r['ts']==target`) | `open` for `09:30/10:00`, `close` for EOD | `OBSERVED`/`MISSING_EVIDENCE` (third vocabulary); separate `path_status: COMPLETE/MISSING_EVIDENCE` for MFE/MAE | `pct(exit_price, entry_price)` | MFE floored at 0, MAE capped at 0 -- **directional excursions, not raw high/low**; window `[t, target)` exclusive-end except EOD, which appends the target bar |

Real artifact: `reports/evaluation/baseline_btc_woori_tech/2026-09-11/q12_candidate_input.json` (already load-bearing in UEF-1's `test_real_q12_dual_horizon_set_preserved`).

### 2.6 Opening Shadow (3 calculators, pure observation -- `"behavior_effect": "observation_only"` in every artifact)

| Calc | Origin | Horizons | Selection | EOD | Price | MFE/MAE | Gross formula | Notes |
|---|---|---|---|---|---|---|---|---|
| 1A `opening_rank1_shadow/latent_forward.py::_observe` | first candle strictly after trigger (`"next_available_minute_open"`) | `+5m,+15m,+30m,+60m,EOD` | `FIRST_AT_OR_AFTER[180s]` | last row `>= 15:20` | reference/entry price: `open` then `close` fallback (`latent_forward.py:101`, `PriceResolutionPolicy(BAR_OPEN, BAR_CLOSE)`) -- SEPARATE from the forward checkpoint's own price: single `close` authority (`:120`) | `[entry_ts, target_ts]` inclusive -- **Fix2: bounded by the nominal TARGET epoch (`MfeMaeWindowEnd.TARGET_TIMESTAMP`), not the matched bar's own observed epoch** | Real artifact below |
| 1B `opening_rank1_longitudinal/delayed_outcomes.py::forward_30m_net` | upstream Q9 **decision_epoch** (not a fill) | single `+30m` (hardcoded `+1800`) | `FIRST_AT_OR_AFTER[unbounded]` | n/a | `open`/`close` | none | Output is already cost-net, no separate gross field |
| 1C `delayed_outcomes.py::delayed_path` | a `virtual_buy_time_kst` field (never a real fill) | same-day (+30m start) plus `d1/d3/d5` -- **Fix1 item 20 naming correction: these are "the 1st/3rd/5th next session PRESENT IN THE CALLER'S trading_calendar list", never "T+1/T+2"** -- the two terms must not be conflated (see \S9.1) | aggregate over all rows in window (no single-bar pick) | implicit (last row present for a day) | `high`/`close` | MFE only (running max high) -- **no MAE anywhere in this calculator** | `d1/d3/d5` counted via an artifact-presence-derived `trading_calendar` list (`ForwardSessionResolverAuthority.ARTIFACT_AVAILABLE_SESSIONS`), **never** a market-calendar library -- the ONLY calculator in the whole inventory that implements any forward-session count |

Real artifact: `reports/evaluation/opening_rank1_shadow/2026-09-11/opening_rank1_shadow_daily.json`, episode `OPEN_0_20_RANK1_30M:20260911:032820:1789084812` (symbol 032820), all five `+5m/+15m/+30m/+60m/EOD` checkpoints `"status":"observed"`, `"observation_method":"at_or_after_target"` -- directly confirming Calculator 1A's rule in real data.

### 2.7 Opening Controlled -- no forward calculator of its own (see \S6)

## 3. Semantic clusters

Grouped by **meaning**, not by Q-number, per the request's explicit instruction:

- **Cluster A -- relative-from-signal/candidate/decision** (`RELATIVE_SECONDS`, origin
  usually `SIGNAL`/`CANDIDATE`): Q9's upstream candidate baseline (via the shared
  `quant_shadow_forward_outcomes.py` engine used by Q10 Semiconductor \S2.2-A and Stage2
  Authority), Q11's five forward checkpoints, Q12 Calculators 1-2, Opening Shadow 1A/1B.
- **Cluster B -- relative-from-actual-exit** (`RELATIVE_SECONDS`, origin `ACTUAL_EXIT`):
  Q9 "Horizon/Exit" post-exit shadow (\S2.1), Q11's own realized-outcome checkpoint.
  Genuinely distinct from Cluster A even when horizon labels coincide (`"+5m"` means
  "5 minutes after the SIGNAL" in one and "5 minutes after the EXIT" in the other).
- **Cluster C -- fixed-clock** (`FIXED_CLOCK_TARGET`, origin `FIXED_CLOCK`): Q10
  Index/lead-market's `CHECKPOINTS` labels, Q12 vnext's `('09:30','10:00','EOD')`.
- **Cluster D -- candidate/signal observation with directional (short/inverse) return**:
  Q10 Index's `shadow_comparison.py` (the one calculator with a real `direction` multiplier)
  -- a specialization of Cluster C, kept separate because no other cluster has direction.
- **Cluster E -- forward-session** (`FORWARD_SESSION`): Opening Shadow 1C's `d1/d3/d5`
  only -- an artifact-observed-session count (`ForwardSessionResolverAuthority
  .ARTIFACT_AVAILABLE_SESSIONS`), never "T+1/T+2" (see \S9.1). The only real
  forward-session implementation found; no other calculator implements one at all.
- **Cluster F -- no forward/checkpoint concept** (out of UEF-2's representable scope by
  definition, not a defect): Same-Symbol Sequences (cumulative already-realized-return
  sequencing only), Opening Controlled's own two designated files (submission/fill ledger
  state only -- see \S6).

## 4. Origin model (reusing UEF-1's `EventOrigin` -- no new enum)

| `EventOrigin` member | Used by | Evidence |
|---|---|---|
| `SIGNAL` | Q11 forward checkpoints (per UEF-1's own precedent) | \S2.4 |
| `CANDIDATE` | Q10 Semiconductor/Q12 Calculator-1 baseline, Stage2 Authority | \S2.2, \S2.5 |
| `ACTUAL_EXIT` | Q9 Horizon/Exit, Q11's own outcome checkpoint | \S2.1, \S2.4 |
| `ACTUAL_FILL` / `ENTRY` | Opening Controlled's generic downstream horizon math (`trade_read_model.py`), anchored on `entry.filled_price`, never on submission | \S6 |
| `FIXED_CLOCK` | Q10 Index/lead-market, Q12 vnext | \S2.3, \S2.5 |
| `MONITOR_DECISION` | Not found in any inventoried forward calculator (reserved, unused here) | -- |
| `OPEN` | Not found as a horizon *origin* (though `open` is a *price authority* in several calculators -- a different axis) | -- |

Every real origin found in this inventory already has an `EventOrigin` member. **No UEF-1
change is needed or made** -- confirming item 6/37's "check existing field combinations
before touching UEF-1" instruction was satisfiable without any contract defect.

## 5. Conflict matrix (Fix1: checkpoint-level, not policy-level)

Differences are made **explicit** below, never silently unified. Fix1's core correction
(Codex H2/H3/H4): every dimension that the inventory shows varying **within one program's
own checkpoints** -- not just between programs -- is now carried on `HorizonSpec`/
`ObservationPolicy`/`MfeMaePolicy`, never on `ForwardPolicy` itself. Each row is
representable as distinct per-`HorizonSpec` values inside ONE policy.

| Dimension | Found values | Representation | Level |
|---|---|---|---|
| Price authority (ordered chain) | `close` (majority, single-authority) / `open` (Q10-F's `"09:00"`, Q12-3's `09:30`/`10:00`, single-authority) / `current` quote snapshot (Q10-G's collector-verified path, single-authority) / **`open` THEN `close`** (Opening Shadow's own reference/entry price -- the one real length-2+ chain found) -- all coexist within one policy | `HorizonSpec.observation.price_resolution: PriceResolutionPolicy` (per-checkpoint) + `ForwardPolicy.reference_price_resolution` (episode-wide, for the origin's own reference price) | **per-checkpoint** (chain moved off `ForwardPolicy` in Fix1; ORDERED in Fix2) |
| Observation window shape | symmetric tolerance (majority) vs **asymmetric** `[-600s,+60s]` (Q10-F's `"CLOSE"`) vs `[09:00,09:03]` bounded-ahead-only (Q10-F's `"09:00"`) | `ObservationPolicy.lookback_seconds`/`lookahead_seconds` (independent, not one `tolerance_seconds`) | **per-checkpoint** |
| Validity constraint on the candidate bar | none (majority) vs positive-volume AND positive-open required (Q10-F's `"09:00"` opening point) | `ObservationPolicy.require_positive_volume`/`require_positive_price` (two bools, no DSL) | **per-checkpoint** |
| Evidence-verification gate | none (majority) vs `ABSENT`/`INVALID`/`VERIFIED` tri-state (Q10-G's collector path) | `EvidenceVerificationState` + `ObservationPolicy.evidence_requirement`, represented as two `HorizonSpec` variants sharing one label under distinct `horizon_set_id`s (reusing the Q12 dual-set mechanism, not a new recursive field) | **per-checkpoint** |
| Missing-resolution rule vs. result status | conflated in Fix0 | `MissingResolutionPolicy` (the RULE: `KEEP_PENDING`/`EXPIRE_AFTER_TOLERANCE`/`MARK_MISSING_IMMEDIATELY`/`USE_SESSION_CLOSE_FALLBACK`) kept strictly separate from `MissingObservationStatus` (the RESULT) | **per-checkpoint** (rule) / conceptual (result) |
| Observation-selection tolerance | `unbounded` (Q9 Horizon/Exit, `KEEP_PENDING`) / `90s` (Q11, Q10-B, Q10-F non-special, Q12-2, `EXPIRE_AFTER_TOLERANCE`) / `180s` (Q10-A/Q12-1, named `FORWARD_MAX_OBSERVATION_DELAY_SEC`) / exact-only (Q12-3, `MARK_MISSING_IMMEDIATELY`) | `ObservationPolicy.lookahead_seconds` + `missing_resolution` | **per-checkpoint** |
| EOD model | `15:20` (shared engine, Q9/Q11/Opening-Shadow) vs `15:30` (Q10 Semiconductor's own override, Q10 Index/lead-market, Q12 vnext) -- **never special-cased**: EOD is `HorizonKind.SESSION_CLOSE` + the SAME `FixedClockSpec` + `ObservationSelectionMode.LAST_AVAILABLE` machinery FIXED_CLOCK_TARGET checkpoints use | `HorizonSpec.fixed_clock: FixedClockSpec` (`clock_label` canonicalized via UEF-1's own `canonicalize_fixed_clock_label`) | **per-checkpoint** |
| Fixed-clock label validity | `"09:00"`/`"09:00:00"` (equivalent) vs `"25:99"`/`"not-a-clock"` (must reject) | `FixedClockSpec.__post_init__` calls UEF-1's `canonicalize_fixed_clock_label` directly -- no new validation logic written | **per-checkpoint** |
| Fixed-clock timezone/session context | every real fixed-clock checkpoint found is within the KRX regular session, `Asia/Seoul` | `FixedClockSpec.timezone` (defaults to UEF-1's own `MARKET_TIMEZONE`, reused) + `FixedClockSpec.session` (`"KRX_REGULAR_SESSION"` -- the only evidenced value; no session enum exists elsewhere in this repo to reuse, so a plain required string was used, not a speculative enum) | **per-checkpoint** |
| Forward-session resolver authority | ONLY real implementation (Opening Shadow's `d1/d3/d5`) uses an artifact-presence-derived day list, never a market-calendar library | `HorizonKind.FORWARD_SESSION` requires `ForwardSessionResolverAuthority.ARTIFACT_AVAILABLE_SESSIONS` -- the type's ONLY member; construction is impossible without it (no "unresolved" production value exists, Fix1 item 19) | **per-checkpoint** |
| Return unit | FRACTION (Q9 Horizon/Exit) vs PERCENTAGE_POINTS (everyone else, always `*100.0`) | `GrossReturnPolicy.return_unit` reuses UEF-1's `ReturnUnit` | episode/program-level (unchanged from Fix0 -- never found varying within one program) |
| Direction | long-only (13 of 14 checkpoint calculators) vs signed `{+1,-1,0}` (Q10-H `shadow_comparison.py`) | `GrossReturnPolicy.direction: TradeDirection` | episode/program-level (uniform per real evidence) |
| MFE/MAE window end | bounded by the NOMINAL TARGET epoch (Q10-A shared engine, Opening Shadow 1A, Q12 shared-engine horizons, Q12 vnext) vs bounded by the checkpoint's own OBSERVED epoch (Q9, Q11-forward, Q10-B, exclusive-start) vs unbounded through remaining available rows (Q10 Index's `_forward_window`) vs fixed origin-to-exit (Q11-outcome) -- **four distinct shapes, not two** (Fix2 Finding 4 correction) | `HorizonSpec.mfe_mae.window_end: MfeMaeWindowEnd.{TARGET_TIMESTAMP,OWN_CHECKPOINT_OBSERVATION,UNBOUNDED_FORWARD,ACTUAL_EXIT}` + required `start_inclusive`/`end_inclusive` | **per-checkpoint** |
| MFE/MAE price basis | `high` for MFE / `low` for MAE (every real calculator that computes either) -- `CLOSE` removed entirely (Fix2: zero real evidence found) | `MfeMaePolicy.mfe_price_field`/`mae_price_field: ExcursionPriceField.{HIGH,LOW}` | **per-checkpoint** |
| MFE/MAE direction-awareness | raw excursions (majority) vs signed by `direction` (Q10-H) | `MfeMaePolicy.direction_aware: bool` | **per-checkpoint** |
| MFE/MAE zero floor/cap | unclamped (majority) vs `MFE=max(0,...)`/`MAE=min(0,...)` (Q12 vnext) | `MfeMaePolicy.mfe_floor_zero`/`mae_cap_zero: bool` | **per-checkpoint** |
| MFE-only vs MFE+MAE | both (majority, when computed at all) vs MFE-only, MAE never computed (Opening Shadow's `delayed_path`) | `MfeMaePolicy.compute_mfe`/`compute_mae: bool` | **per-checkpoint** |
| Observation-selection mode | first-at-or-after (majority) vs last-available (EOD, Q10-G's collector snapshot) vs exact-only (Q12-3) -- **`NEAREST` removed** (Codex M1: no legacy evidence, `UNSUPPORTED_ACTIVE`) | `ObservationSelectionMode.{EXACT,FIRST_AT_OR_AFTER,LAST_AVAILABLE}` -- exactly 3 members | **per-checkpoint** |
| Missing-status vocabulary (legacy casing) | lowercase `pending/observed/stale` (Q9/Q10-A/Q11) vs uppercase `MISSING/PENDING/OBSERVED` (Q12-2) vs `OBSERVED/MISSING_EVIDENCE` (Q12-3) vs `OBSERVED/PENDING/PARTIAL` (Q10-F/G) | `MissingObservationStatus` names the *reason*, not the legacy casing; UEF-2B maps each legacy vocabulary onto it | conceptual (result) |
| Q12 horizon-set membership | `HORIZONS` vs `HYPOTHESIS_HORIZONS` vs vnext's own tuple -- overlapping, never identical | `HorizonSpec.horizon_set_id`, mirroring `Checkpoint.horizon_set_id` (Fix2 #30/#31) -- **not re-solved here, already solved by UEF-1**; re-verified not regressed (\S8) | per-checkpoint identity tag |

No dimension above required inventing a value that isn't in the real code -- every cell
has a file:line citation in \S2.

## 6. Programs with no forward-checkpoint calculator (verified, not assumed)

- **Same-Symbol Sequences**: `builder.py`/`pipeline.py` read already-realized
  `net_return_pct` from `trade_read_model.json` and compute a same-day **cumulative sum**
  (`running += value`) plus a "profit giveback" (`peak - running`). No horizon, no target
  timestamp, no bar lookup, no MFE/MAE anywhere. Confirmed independently by this repo's own
  prior audit: `docs/research/unified_evaluation_framework_integrity_review.md:46-48`
  states "Same-symbol sequence (no checkpoint concept at all)". `libs/runtime/same_symbol_loss_reentry.py`
  is a separate, same-day broker-PnL blocking gate sharing no code with the pipeline.
- **Stage2 Authority**: `deep_dive.py`/`deep_dive_report.py`/`builder.py` never compute a
  forward price themselves -- they read `shadow_forward_outcome.checkpoints` produced by
  the exact same shared engine Q10 Semiconductor uses
  (`quant_shadow_forward_outcomes.py::attach_forward_outcomes`), then aggregate
  `before_return_pct`/`after_return_pct`/`delta_pct`. Confirmed by the same integrity-review
  doc: "Strategist Stage2 (`stage2_authority/`, its own local checkpoint reader)".
- **Opening Controlled**: neither `opening_rank1_controlled_probe.py` nor
  `controlled_mock_lanes/coordinator.py` contains a horizon/target-timestamp/MFE-MAE
  calculation -- both files compute submission/fill **ledger status** only
  (`PENDING_BROKER_RESULT`, `BROKER_ACCEPTED`, `FILLED`, etc.). Once a controlled probe's
  order is accepted, its eventual forward/hold-time figures are produced by the exact same
  **generic**, program-agnostic path every trade uses:
  `trade_read_model.py::_holding_seconds`/`horizon_contract.py::evaluate_horizon_contract`,
  anchored on `entry.filled_price`/`entry_ts` -- fields explicitly preferred over any bare
  order/submission price (`trade_read_model.py:401-407`, checks `filled_price`/`avg_price`
  before `price`). This directly answers the request's item 30 concern: **the forward
  origin for a controlled-probe fill is the fill/entry timestamp, never the submission
  timestamp** -- verified against the real 2026-09-10/024060 artifact pair UEF-1 already
  uses (`probe_submissions.json` vs `trade_read_model.json` for `TRD_20260910_024060_01`):
  the submission's `recorded_at` (epoch 1788998887) and the fill's `entry.timestamp`
  (epoch 1788998888) are numerically only 1 second apart in this specific real artifact --
  too close to distinguish by clock alone -- but they remain two genuinely different
  `EventRef`s (`SUBMITTED_INTENT` vs `MOCK_FILL` authority, different `canonical_event_id`),
  exactly as UEF-1's own `SUBMISSION_TO_FILL` provenance model already established. A
  `ForwardPolicy`'s origin must be pinned to the **fill's own EventRef**, never the
  submission's, regardless of how close the two clocks happen to land in any one artifact.

None of the three above is a defect. They are correctly reported here as "no
forward-checkpoint semantics to inventory for this program" rather than a calculator being
force-fit where none exists.

## 7. Q12 dual/triple horizon-set regression check

UEF-1's own `test_real_q12_dual_horizon_set_preserved` already proves `HORIZONS` and
`HYPOTHESIS_HORIZONS` survive as separate `Checkpoint.horizon_set_id` entries, never merged.
This inventory adds one more real fact found only during UEF-2A research: Q12 vnext's own
`('09:30','10:00','EOD')` tuple is a **third**, disjoint-labeling-scheme set (clock-time
labels, not relative-minute labels), and the shared engine's own `CHECKPOINT_MINUTES=(3,5,15,30,60)`
is effectively a **fourth**. `HorizonSpec.horizon_set_id` generalizes UEF-1's pattern to all
four without collapsing any of them -- see \S8's `test_forward_policy_represents_q12_four_horizon_sets_without_collapsing`.

## 8. Actual-artifact representability results

| Program | Real artifact | Result |
|---|---|---|
| Q10 Semiconductor | `reports/evaluation/baseline_samsung_hynix/2026-09-11/baseline_samsung_hynix_forward_returns.json` (005930) | PASS |
| Q10 Index | `reports/evaluation/baseline_samsung_hynix/2026-09-11/q10_forward_validation/q10_actual_market_reactions.json` (`targets.samsung`, 005930) | PASS |
| Q11 | `reports/evaluation/opportunity_engine_shadow/2026-09-11/opportunity_engine_virtual_trades.json` (009150) | PASS |
| Q12 | `reports/evaluation/baseline_btc_woori_tech/2026-09-11/q12_candidate_input.json` | PASS |
| Opening Shadow | `reports/evaluation/opening_rank1_shadow/2026-09-11/opening_rank1_shadow_daily.json` (episode `...032820:1789084812`) | PASS |
| Opening Controlled | `data/logs/opening_rank1_controlled_probe/2026-09-10/probe_submissions.json` + `reports/evaluation/trades/2026-09-10/TRD_20260910_024060_01/trade_read_model.json` (024060) | PASS |
| Horizon/Exit | `reports/trades/2026-05-15/0900/TRD_20260515_066570_01/reports/post_exit_shadow_recap.json` (066570) | PASS |

All seven: the canonical `ForwardPolicy`/`HorizonSpec` schema can losslessly describe the
real semantics found -- see `tests/test_uef2a_forward_policy_contract.py`. **No recomputation
was performed**; these tests only prove representability, per item 27's explicit boundary.

## 9. Blocking semantic conflicts

**None.** Every difference found in \S5 is representable as an explicit, distinct
per-checkpoint value -- no dimension required silently picking a winner, inventing a value
absent from the code, or changing UEF-1.

### 9.1 Forward-session resolver authority (resolved, not left open)

Fix1 correction (Codex H1/items 17-21): the Fix0 pass introduced a `SessionUnit.UNRESOLVED`
escape hatch for T+1/T+2, which Codex correctly rejected -- a production-constructible
"unresolved" value is not a closed contract. The actual resolution:

- No calculator in this inventory computes a real "T+1/T+2" forward checkpoint in the
  generic sense (Q9's placeholder keys stay "pending" forever; this term is retired from
  this document's own vocabulary, per item 21, to avoid implying an implementation that
  does not exist).
- The ONE real forward-session implementation -- Opening Shadow's `delayed_path`
  `d1`/`d3`/`d5` -- counts the Nth next calendar day **present in the caller's own
  `trading_calendar` list**, itself built from whichever `reports/operator_summary/daily`
  folders exist or from daily-cache row dates (`libs/research/opening_rank1_longitudinal/
  pipeline.py:96-105,203-204`) -- an artifact-presence-derived list, never a market-calendar
  library call.
- `HorizonKind.FORWARD_SESSION` now REQUIRES `ForwardSessionResolverAuthority
  .ARTIFACT_AVAILABLE_SESSIONS` to construct at all (`HorizonSpec.__post_init__` rejects
  construction without it) -- there is no way to build a production `HorizonSpec` of this
  kind without naming this one, real, evidenced authority. This is a closed decision, not a
  deferred one: `ForwardSessionResolverAuthority` has exactly one member.
- Q12's separate `vnext/time_alignment.py` use of the `exchange_calendars` package (to
  align a BTC signal to the KRX session) is a different concept entirely -- it never
  computes a forward-session checkpoint -- and is noted here only so it is never confused
  with `d1/d3/d5`'s own resolver.
- If a real calculator using an official KRX trading-calendar authority is found or built
  later, it is added as a SECOND, separately-versioned `ForwardSessionResolverAuthority`
  member then -- never by silently redefining `ARTIFACT_AVAILABLE_SESSIONS`'s meaning.

## 10. UEF-2B IMPLEMENTATION INPUT

The following is fixed by this document; UEF-2B's implementer should not need to re-read
any legacy calculator to begin, and should not need to guess between OPEN/CLOSE, between
TARGET/OBSERVED, or between the origin instant and an offset from it.

- **Canonical schema**: `libs/reporting/evaluation/canonical/forward/policy.py` --
  `ForwardPolicy` (episode/program-wide: `legacy_program`, `horizons`, `gross_return`,
  `reference_price_resolution`, `cost_included`/`cost_note`), `HorizonSpec` (per-checkpoint:
  `kind`, `origin`, `observation`, `mfe_mae`, plus kind-specific fields, under a STRICT
  per-kind field-exclusivity matrix), `ObservationPolicy` (per-checkpoint resolution rule,
  now carrying an ORDERED `price_resolution` chain rather than one value), `MfeMaePolicy`
  (per-checkpoint excursion contract, `start_inclusive`/`end_inclusive` now REQUIRED, no
  default), `FixedClockSpec` (validated wall-clock target + timezone + session),
  `PriceResolutionPolicy` (ordered, non-empty, duplicate-free price-authority chain),
  `SessionCloseSpec` (the concrete target a session-close fallback substitutes),
  `GrossReturnPolicy` (episode-wide direction/unit). All frozen, serializable
  (`to_dict`/`from_dict`), self-validating, content-derived `policy_id`.
- **Reference price vs. forward-observation price** (Fix2 Finding 1/4): kept as two
  SEPARATE concepts -- `ForwardPolicy.reference_price_resolution` (the origin's own
  denominator price, episode-wide, e.g. Opening Shadow's `open→close`) vs.
  `HorizonSpec.observation.price_resolution` (each checkpoint's OWN forward-observation
  price chain). Never conflated.
- **Ordered price-authority chain** (Fix2 Finding 1/2/3 -- H2/H3 closure): every
  `ObservationPolicy`/reference price is a `PriceResolutionPolicy(authorities=(...))`, an
  ORDERED, non-empty, duplicate-free tuple. A checkpoint with one real authority (the
  overwhelming majority) is a length-1 chain; only Opening Shadow's own reference price has
  real length-2 evidence (`BAR_OPEN, BAR_CLOSE`). No fallback is invented where none was
  found -- e.g. Q10 Index's `"09:00"`/later checkpoints and Q12 vnext's `"09:30"`/`"10:00"`/
  `EOD` all stay single-authority chains, confirmed by re-reading their source.
- **Supported horizon semantics**: `HorizonKind.{RELATIVE_SECONDS,SESSION_CLOSE,FORWARD_SESSION,FIXED_CLOCK_TARGET}`,
  each with a STRICT field-exclusivity matrix (Fix2 Finding on mutually-exclusive fields,
  items 25/26) -- a `RELATIVE_SECONDS` `HorizonSpec` can never carry `fixed_clock`; a
  `FIXED_CLOCK_TARGET`/`SESSION_CLOSE` one can never carry `relative_seconds`; a
  `FORWARD_SESSION` one can never carry either -- enforced at construction, not left for
  UEF-2B to arbitrate. `relative_seconds` may be `0` (the origin instant itself is a
  legitimate checkpoint -- Q11's own realized-outcome checkpoint). `SESSION_CLOSE` (EOD) is
  never special-cased: it uses the SAME `FixedClockSpec` + `LAST_AVAILABLE` machinery as
  `FIXED_CLOCK_TARGET`, just with a different `origin` requirement.
- **Supported origin semantics**: UEF-1's own `EventOrigin`, per-`HorizonSpec` -- reused
  verbatim, no new enum (\S4).
- **Observation selection semantics**: `ObservationSelectionMode.{EXACT,FIRST_AT_OR_AFTER,LAST_AVAILABLE}`
  -- exactly 3 members; `NEAREST` has zero legacy evidence and was removed.
- **Observation window semantics**: `ObservationPolicy.lookback_seconds`/`lookahead_seconds`
  -- independent, asymmetric (Q10 Index's `"CLOSE"`: `lookback=600, lookahead=60`).
- **Validity constraint semantics**: `ObservationPolicy.require_positive_volume`/
  `require_positive_price` -- the only two real constraints found (Q10 Index's `"09:00"`).
- **Evidence-verification gate semantics**: `EvidenceVerificationState.{ABSENT,INVALID,VERIFIED}`
  + `ObservationPolicy.evidence_requirement` -- a gated checkpoint is up to THREE
  `HorizonSpec` entries sharing one label under distinct `horizon_set_id`s (one per real
  collector state, all three independently tested for Q10 Index's `"09:30"`/`"10:00"`/
  `"CLOSE"`); `INVALID` is enforced to always resolve via
  `MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY`, never a fallback.
- **Missing-resolution semantics** (the RULE): `MissingResolutionPolicy.{KEEP_PENDING,EXPIRE_AFTER_TOLERANCE,MARK_MISSING_IMMEDIATELY,USE_SESSION_CLOSE_FALLBACK}`,
  per-`HorizonSpec`, kept strictly separate from `MissingObservationStatus` (the RESULT).
  `USE_SESSION_CLOSE_FALLBACK` now REQUIRES a concrete `ObservationPolicy.session_close_fallback: SessionCloseSpec`
  (Fix2 Finding 6/H-close: an action with no target described nothing) -- validated at
  construction, never accepted bare.
- **Price authority values**: `PriceAuthority.{BAR_CLOSE,BAR_OPEN,QUOTE,FIXED_OBSERVED_PRICE}`
  -- consulted IN ORDER via `PriceResolutionPolicy`, never singly. No bid/ask/mid `QuoteSide`
  subtype added; the one real QUOTE consumer (Q10 Index's collector snapshot) reads a
  single generic `"current"` field for BOTH its synthetic open and close, so there is no
  real open/close distinction inside a VERIFIED point either.
- **EOD model**: `HorizonKind.SESSION_CLOSE` + `HorizonSpec.fixed_clock: FixedClockSpec`
  (validated wall-clock label, e.g. `"15:20"` or `"15:30"` -- both real, never unified) +
  `ObservationSelectionMode.LAST_AVAILABLE`.
- **Fixed-clock validation**: `FixedClockSpec.__post_init__` calls UEF-1's OWN
  `canonicalize_fixed_clock_label` directly, AND validates `timezone`/`session` against the
  only production-supported values found (`MARKET_TIMEZONE`/`"KRX_REGULAR_SESSION"`) --
  Fix2 correction: Fix1 accepted any non-empty string for either field; `timezone="UTC"` or
  `session="ANYTHING"` is now rejected outright.
- **Forward-session resolver authority**: `ForwardSessionResolverAuthority.ARTIFACT_AVAILABLE_SESSIONS`
  -- the ONLY member; required (non-optional) on every `FORWARD_SESSION` `HorizonSpec` (\S9.1
  -- resolved, not deferred). Confirmed for all three of Opening Shadow's real `d1`/`d3`/`d5`
  checkpoints, not just `d1`.
- **MFE/MAE window contract**: `MfeMaeWindowEnd.{TARGET_TIMESTAMP,OWN_CHECKPOINT_OBSERVATION,UNBOUNDED_FORWARD,ACTUAL_EXIT}`
  (Fix2 Finding 4/10/11 -- `TARGET_TIMESTAMP`/`UNBOUNDED_FORWARD` are NEW; re-reading the
  shared forward engine and Opening Shadow's own code shows their window is bounded by the
  NOMINAL target epoch, not by whichever epoch the matched bar actually carries -- a real
  difference whenever a checkpoint's observation lands late) + `start_offset_seconds`/
  `start_inclusive`/`end_inclusive`/`end_offset_seconds`, per-`HorizonSpec`.
  `start_inclusive`/`end_inclusive` have NO DEFAULT (Fix2 item 13) -- every construction
  site must state them explicitly (Q12 vnext's `"09:30"` is genuinely end-EXCLUSIVE; its
  own EOD checkpoint is end-INCLUSIVE -- a default would have silently picked one).
- **MFE/MAE basis/direction/clamp**: `ExcursionPriceField.{HIGH,LOW}` (basis -- `CLOSE` was
  REMOVED, zero real evidence anywhere) + `direction_aware: bool` (consumes
  `GrossReturnPolicy.direction`) + `mfe_floor_zero`/`mae_cap_zero: bool` (Q12 vnext's real
  clamp) + `compute_mfe`/`compute_mae: bool` (Opening Shadow's real MFE-only case, verified
  for all of `d1`/`d3`/`d5`) -- all per-`HorizonSpec` via `MfeMaePolicy`.
- **Gross return boundary**: fixed formula shape `(observed_price/reference_price - 1)` +
  `TradeDirection.{LONG,SHORT}` (the real Q10-H inversion case, episode-wide) + `ReturnUnit`
  (UEF-1's own enum, reused for the FRACTION-vs-PERCENTAGE_POINTS split \S5 found) -- both
  kept at `ForwardPolicy`/`GrossReturnPolicy` level because no evidence was found of either
  varying checkpoint-to-checkpoint within one program.
- **Cost/net**: out of scope -- `ForwardPolicy.cost_included: bool` + `cost_note: str` only
  *record* whether the legacy calculator this policy describes mixed cost in; UEF-2B/UEF-3
  computes nothing here.

Per Fix2 item 28/30's completeness check, every `HorizonSpec` now answers all nine questions
without UEF-2B re-reading legacy source: which price, IN WHAT ORDER
(`observation.price_resolution.authorities`); which bar
(`observation.selection_mode`); how far forward/back
(`observation.lookback_seconds`/`lookahead_seconds`); any validity gate
(`require_positive_volume`/`require_positive_price`); what happens if missing, and with what
concrete fallback target (`observation.missing_resolution` +
`observation.session_close_fallback`); origin-bar inclusion and window-end authority
(`mfe_mae.start_inclusive`/`end_inclusive`/`window_end`); fixed-clock timezone/session
(`fixed_clock.timezone`/`session`); and forward-session resolution
(`session_resolver`).

## 11. Self-review (item 40)

1. Every calculator's semantics were confirmed in real code (\S2), not assumed from a name. YES.
2. No "+5m" label was assumed identical across programs -- Q9 Horizon/Exit's `+5m` (exit-anchored,
   FRACTION unit, unbounded tolerance) and Q11's `+5m` (signal-anchored, PERCENTAGE_POINTS,
   90s tolerance) are both named and kept distinct. YES.
3. Actual-exit-origin (Cluster B) was never flattened into entry/signal-origin (Cluster A)
   -- both live as separate `EventOrigin` values on separate `HorizonSpec` entries, matching
   UEF-1's own Family-A/Family-B precedent. YES.
4. Fixed-clock (Cluster C) was represented as its own `HorizonKind`, not a relative-seconds
   hack with a suspiciously specific offset. YES.
5. Missing observations are never coerced to a return of 0 anywhere in this document or the
   accompanying code -- every legacy calculator inventoried in \S2 was independently
   confirmed to use an explicit pending/stale/missing status, and `MissingObservationStatus`
   has no "zero" member. YES.
6. Cost/net/WR/PF/MDD were recorded only as file:line locations (\S2's "Cost" rows, \S10's
   `cost_included`/`cost_note`) -- no cost arithmetic was implemented anywhere in this
   package. YES.
7. UEF-1's Record/Identity/Relation/Lineage contract files were not modified by this work
   (`git status` scope confirms only new `forward/` files and this doc were added). YES.
8. No full legacy adapter was built -- no existing Q9-Q18 report generator's output path was
   changed, and this package is not imported by any of them. YES.
9. Could UEF-2B implement the canonical forward engine from \S10 alone, without re-reading
   any legacy calculator? YES -- every enum/field in \S10 traces to a specific, cited piece
   of evidence in \S2/\S5, and \S9.1's forward-session authority is now resolved (not left
   open), so 2B has no remaining open decision to make on its own.

All nine: YES.

## 12. Fix1 self-review against Codex's exact findings

- H1 (FORWARD_SESSION calendar authority unresolved): CLOSED -- \S9.1,
  `ForwardSessionResolverAuthority.ARTIFACT_AVAILABLE_SESSIONS` is the sole, required member.
- H2 (price_authority not expressible per-checkpoint): CLOSED -- \S5, `HorizonSpec.observation.price_authority`;
  proven by `test_one_policy_mixes_open_close_and_quote_price_authority_per_checkpoint_and_roundtrips`
  and the Q10 Index representability test.
- H3 (Q10 special observation semantics unrepresented): CLOSED -- `ObservationPolicy.lookback_seconds`/
  `lookahead_seconds` (asymmetric window), `require_positive_volume`/`require_positive_price`,
  `EvidenceVerificationState` + `evidence_requirement` (collector tri-state).
- H4 (MFE/MAE semantics insufficient): CLOSED -- `MfeMaePolicy.{mfe_price_field,mae_price_field,
  direction_aware,mfe_floor_zero,mae_cap_zero,compute_mfe,compute_mae}`, all per-`HorizonSpec`.
- H5 (missing-resolution policy absent): CLOSED -- `MissingResolutionPolicy` (the rule) kept
  separate from `MissingObservationStatus` (the result), per-`HorizonSpec` via
  `ObservationPolicy.missing_resolution`.
- H6 (fixed-clock contract too loose): CLOSED -- `FixedClockSpec` reuses UEF-1's
  `canonicalize_fixed_clock_label` (rejects `"not-a-clock"`/`"25:99"`) and carries
  `timezone`/`session`.
- M1 (NEAREST unsupported-active): CLOSED -- removed from `ObservationSelectionMode` entirely
  (3 members remain).
- L1 (inventory count naming): CLOSED -- \S1, "14 checkpoint calculators + 3 downstream
  aggregators", never merged into one count again.
- Additional finding (Q10 Semiconductor fixture: 180s/inclusive instead of the real
  90s/exclusive for `+120m/+180m`): CLOSED -- `test_q10_semiconductor_real_artifact_is_representable`
  now asserts `lookahead_seconds == 90` and `start_inclusive is False` for those two horizons
  specifically, distinct from the `+5m..+60m` group's `180`/`True`.

`STATUS: PASS` is warranted (as of Fix1; superseded by \S13's Fix2 review below).

## 13. Fix2 self-review against Codex's exact findings

- Finding 1/2 (single price authority cannot express a real ordered fallback): CLOSED --
  `PriceResolutionPolicy(authorities=(...))`, ordered/non-empty/duplicate-free, replaces
  `ObservationPolicy.price_authority` everywhere. Opening Shadow's real `open→close`
  reference-price fallback (`latent_forward.py:101`) is the one real length-2+ chain found;
  proven in `test_opening_shadow_exact_fidelity_entry_fallback_and_all_forward_sessions`.
- Finding 3 (collector tri-state under-tested): CLOSED --
  `test_q10_index_exact_fidelity_all_collector_states` builds and asserts THREE independent
  `HorizonSpec` variants (ABSENT/INVALID/VERIFIED) for each of `"09:30"`/`"10:00"`/`"CLOSE"`,
  never a single synthetic stand-in for all three.
- Finding 4 (MFE/MAE window end is the nominal TARGET, not the OBSERVED bar, in the shared
  engine and Opening Shadow): CLOSED -- `MfeMaeWindowEnd.TARGET_TIMESTAMP` added, re-verified
  against `quant_shadow_forward_outcomes.py:295` (`bisect_right(..., target)`) and
  `latent_forward.py:116` (`<= target_epoch`); Q10 Semiconductor Calc A, Opening Shadow's
  forward checkpoints, and Q12's shared-engine horizons corrected from the Fix1 pass's wrong
  `OWN_CHECKPOINT_OBSERVATION` classification. Q9 Horizon/Exit, Q11's forward checkpoints,
  and Q10 Semiconductor Calc B remain `OWN_CHECKPOINT_OBSERVATION` (re-verified correct).
- Finding 5 (Q11 actual-exit modeled with an invented `+1 second`): CLOSED --
  `relative_seconds=0` is now legal (validation changed from `> 0` to `>= 0`);
  `test_q11_exact_fidelity_zero_offset_own_outcome` asserts `target_timestamp ==
  trade["exit_epoch"]` exactly, and `test_q11_actual_exit_plus_one_second_regression_forbidden`
  guards against the regression returning.
- Finding 6 (`USE_SESSION_CLOSE_FALLBACK` had no concrete target): CLOSED -- `SessionCloseSpec`
  (`close_clock: FixedClockSpec` + `price_resolution: PriceResolutionPolicy`) is now REQUIRED
  whenever `missing_resolution=USE_SESSION_CLOSE_FALLBACK`; proven against Q9 Horizon/Exit's
  real `_fill_regular_close_bound_pending_checkpoints` (15:30 KST boundary) in
  `test_horizon_exit_exact_fidelity_with_session_close_fallback_and_eod`.
- Finding 7 (`FixedClockSpec` accepted arbitrary timezone/session strings): CLOSED --
  validated against `_SUPPORTED_TIMEZONES`/`_SUPPORTED_SESSIONS` (currently
  `{MARKET_TIMEZONE}`/`{"KRX_REGULAR_SESSION"}`, the only real values found); `timezone="UTC"`
  and `session="ANYTHING"` both rejected (`test_unsupported_timezone_rejected`,
  `test_unsupported_session_rejected`).
- Finding 9 (Q12 vnext's real end-exclusive `09:30`/`10:00` interval not enforced): CLOSED --
  `MfeMaePolicy.start_inclusive`/`end_inclusive` now REQUIRED (no default), and
  `test_q12_exact_fidelity_end_exclusive_and_four_horizon_sets` asserts `end_inclusive is
  False` for `"09:30"` specifically (vs. `True` for its own EOD checkpoint).
- Finding 10 (Opening Controlled representability built a contradictory fake generic
  ForwardPolicy while claiming "no forward calculator exists"): CLOSED --
  `test_opening_controlled_has_no_program_specific_forward_policy` constructs no
  `HorizonSpec`/`ForwardPolicy` at all; it only asserts the real submission/fill identity
  facts, and documents (in-test comment) that any eventual generic forward figure is proven
  separately by the Horizon/Exit test, never by a policy specific to this program.
- Mutually-exclusive-fields matrix (items 25/26): CLOSED -- `HorizonSpec.__post_init__` now
  enumerates every kind-specific field and rejects any `HorizonSpec` carrying a field that
  belongs to a different `HorizonKind` (`test_relative_horizon_with_fixed_clock_rejected`,
  `test_fixed_clock_target_with_relative_seconds_rejected`,
  `test_forward_session_with_fixed_clock_rejected`).
- `ExcursionPriceField.CLOSE` unsupported-active removal (item 6/41): CLOSED -- removed
  entirely after a full re-search of every MFE/MAE computation in the inventory found zero
  real usage; `test_excursion_price_field_has_no_close_member`.
- Opening Shadow `d1`/`d3`/`d5` (item 30): CLOSED -- all three built and asserted in
  `test_opening_shadow_exact_fidelity_entry_fallback_and_all_forward_sessions`, not just `d1`.
- Entry/reference price vs. forward-checkpoint price separation (item 4): CLOSED --
  `ForwardPolicy.reference_price_resolution` (episode-wide) vs.
  `HorizonSpec.observation.price_resolution` (per-checkpoint), never conflated.

`STATUS: PASS` is warranted (as of Fix2; superseded by \S14's Reset review below).

## 14. SEMANTIC AUTHORITY RESET (current authoritative contract)

Codex's third audit (CRITICAL:0/HIGH:6/MEDIUM:1/LOW:0, `READY_FOR_UEF2B: NO`) found that
Fix1/Fix2, while structurally correct (checkpoint-varying fields at the right level), still
recorded several WRONG or INCOMPLETE recipes: a single `PriceAuthority` where the real code
has a multi-step fallback chain; an MFE/MAE basis (`ExcursionPriceField.CLOSE`) removed before
a full re-search actually found real usage; a whole calculator (Q10 Index's directional
shadow) never given its own recipe at all; and a Q12 checkpoint set undercounted by ignoring
which module's constant a shared function's free variables actually resolve against. This
section is the Reset's answer: three explicitly separated resolution layers (Reference /
Observation / Excursion), one reused ordered-price-chain primitive (`PriceCandidate` +
`PriceResolutionPolicy`) for all three layers, and an explicit ownership determination for the
one case where the forward calculator itself must search market data for its own reference
point.

### 14.1 The three layers (design principle)

| Layer | Contract type | Scope | Answers |
|---|---|---|---|
| A. Reference / Origin Resolution | `ReferenceResolutionPolicy` | episode/program-wide (`ForwardPolicy.reference_resolution`) | How was THIS episode's own t=0 timestamp and reference price established? |
| B. Checkpoint Observation Resolution | `ObservationPolicy` | per-checkpoint (`HorizonSpec.observation`) | How does THIS checkpoint find its own target bar and price? |
| C. Excursion Resolution | `ExcursionPolicy` | per-checkpoint (`HorizonSpec.excursion`, optional) | How (if at all) does THIS checkpoint scan for MFE/MAE? |

All three reuse ONE chain primitive, `PriceResolutionPolicy(authorities: tuple[PriceCandidate, ...])`
-- ordered, non-empty, duplicate-free. A checkpoint's own price, an episode's reference price,
and an excursion's high/low price are all "try these `PriceCandidate`s in this order" chains;
there is no second mechanism.

### 14.2 `PriceCandidate` vocabulary (superseding \S10's `PriceAuthority`)

| Member | Evidence |
|---|---|
| `BAR_OPEN`/`BAR_CLOSE`/`BAR_HIGH`/`BAR_LOW` | the candle's own OHLC fields -- the majority |
| `QUOTE` | Q10 Index collector's live `"current"` snapshot field, not a candle |
| `REFERENCE_PRICE` | the episode's own already-established reference/baseline price, used ONLY as a fallback TARGET, never tried first -- Q10 Semiconductor/Q12 shared engine (`close = ... or base_price`, `quant_shadow_forward_outcomes.py:337`), Opening Shadow's own forward checkpoint (`close = ... or entry_price`, `latent_forward.py:120`) |
| `SOURCE_FIELD_PRICE`/`SOURCE_FIELD_CURRENT_PRICE`/`SOURCE_FIELD_CUR_PRICE` | Q9 Horizon/Exit's 4-deep alias chain for the SAME "current/last" concept under different upstream field names (`_row_price(raw, "close","price","current_price","cur_price")`, `strategy_horizon_feedback.py:914`) |
| `SOURCE_FIELD_HIGH_PRICE`/`SOURCE_FIELD_LOW_PRICE` | the same alias pattern for Q9's own excursion fields (`_row_price(raw,"high","high_price")`/`(...,"low","low_price")`, `:917-918`) |
| `PRIMARY_PRICE_FALLBACK` | a chain terminator meaning "reuse THIS row's own already-resolved primary price" -- Q9's excursion chains both end `or close` (`:917-918`), falling back to the ROW's own close, never the episode's reference price (a genuinely different fallback target from `REFERENCE_PRICE`) |
| `FIXED_OBSERVED_PRICE` | a pre-resolved value carried forward with no lookup at all (Q11's zero-offset ACTUAL_EXIT outcome checkpoint) |

No bid/ask/mid `QuoteSide` subtype exists: the one real QUOTE consumer's synthetic row sets
BOTH its `"open"` and `"close"` to the identical `current` value (`reaction_reader.py:412-413`),
so there is no real open/close distinction inside a VERIFIED point either.

### 14.3 `ExcursionPriceField.CLOSE` -- restored, not re-removed

Fix1 removed `CLOSE` after finding zero MFE/MAE calculators using it. The Reset's own
re-search (prompted by re-reading Q10 Index's directional shadow calculator, \S14.6 below)
found real usage: `shadow_comparison.py::build_shadow_comparison` computes MFE/MAE from a
**close-only** price series (`prices = [float(row.get("close") or 0.0) for row in future ...]`,
`signed_moves = [direction * (price/entry_price - 1)*100 for price in prices]`, `mfe_pct =
max(signed_moves)`, `mae_pct = min(signed_moves)` -- `:96-99,114-115`) -- no high/low field is
read anywhere in that function. `CLOSE` is restored (3 members: HIGH/LOW/CLOSE). The "no
evidence -> no active semantic" rule cuts both ways: evidence found later must be represented,
never omitted for consistency with an earlier, incomplete search.

### 14.4 FIRST_PULLBACK_ENTRY ownership determination

```text
FIRST_PULLBACK_ENTRY OWNERSHIP:
UEF2_FORWARD_ENGINE

Evidence: shadow_comparison.py::_first_pullback_entry(reaction, direction)
reads reaction.get("path") -- the SAME day's candle series
_stock_reaction/_forward_window (Calculator F/Calc 5) already produced
inside THIS SAME evaluation package (reaction_reader.py:264, "path": regular).
It is never fed a signal from any external strategy/scanner module --
the retracement scan (first >=50%-of-threshold retrace from the day's
own running extreme, within 60 minutes of the opening bar) is computed
entirely from already-fetched market data, by the forward/shadow-
comparison calculator's OWN code.
```

Represented as `ReferenceResolutionKind.RETRACEMENT_SCAN` (`ReferenceResolutionPolicy.kind`),
with `retracement_lookback_seconds=3600` (60 minutes, `shadow_comparison.py:51`) and
`retracement_threshold_fraction=0.005` -- the EFFECTIVE runtime fraction after
`THRESHOLDS["pullback_retrace_pct"] / 100.0` = `0.50 / 100.0` (`:48`, `forward_validation/contracts.py:59`);
the raw `THRESHOLDS` constant (`0.50`) is quoted here only as the source citation, the
EFFECTIVE value actually consumed at runtime (`0.005`) is what the contract stores, since that
is what determines behavior. UEF-2B must implement this scan itself for this ONE calculator --
it is not a pre-resolved upstream input like every other checkpoint's origin.

### 14.5 Q12's real checkpoint set -- corrected

Fix0-Fix2 treated Q12's own 4-element `contracts.HORIZONS` as the checkpoint set its shared-
engine calculator produces. Re-reading `baseline_btc_woori_tech/forward_returns.py::
attach_forward_returns` shows it calls `attach_baseline_forward_returns` DIRECTLY (imported
from `baseline_samsung_hynix.forward_returns`) -- and that function's own `HORIZONS` free
variable resolves against ITS OWN DEFINING MODULE's namespace
(`baseline_samsung_hynix.contracts.HORIZONS`, 7 labels), never the CALLER's module-level
`HORIZONS` (Python free-variable resolution is by defining scope, not by caller). Confirmed
against the real artifact: `reports/evaluation/baseline_btc_woori_tech/2026-09-11/
baseline_btc_woori_forward_returns.json` rows carry all 7 keys
(`+5m,+15m,+30m,+60m,+120m,+180m,EOD`), a STRICT SUPERSET of Q12's own declared `HORIZONS`
(4 elements) -- that constant is only a downstream SELECTION filter used by
`comparison.py`/`historical_review.py`, never a bound on what this calculator itself computes.
`HYPOTHESIS_HORIZONS` (Calculator 10/`hypothesis_forward.py`) and vnext's own 3-clock set
(Calculator 11) remain independent, correctly-scoped calculators, unaffected by this
correction.

### 14.6 14-calculator recipe coverage table

| # | Calculator | Source | Recipe test | Coverage |
|---|---|---|---|---|
| 1 | Q9 Horizon/Exit | `strategy_horizon_feedback.py::update_post_exit_shadow_with_price_observations` | `test_calculator_1_horizon_exit_exact_price_chain_and_session_close_fallback` | PASS |
| 2 | Q10 Semiconductor Calc A | `quant_shadow_forward_outcomes.py::attach_forward_outcomes` | `test_calculators_2_3_4_q10_semiconductor_reference_fallback_and_exact_windows` | PASS |
| 3 | Q10 Semiconductor Calc B (+120m/+180m) | `baseline_samsung_hynix/forward_returns.py::_extended_checkpoint` | (same) | PASS |
| 4 | Q10 Semiconductor Calc C (EOD override) | `baseline_samsung_hynix/forward_returns.py` (inline) | (same) | PASS |
| 5 | Q10 Index Calc F | `forward_validation/reaction_reader.py::_stock_reaction`/`_forward_window` | `test_calculators_5_6_q10_index_single_authorities_and_collector_three_states` | PASS |
| 6 | Q10 Index Calc G (collector) | `forward_validation/reaction_reader.py::_index_reaction` | (same) | PASS |
| 7 | Q10 Index Calc H (directional shadow) | `forward_validation/shadow_comparison.py::build_shadow_comparison` | `test_calculator_7_q10_index_directional_shadow_first_pullback_ownership_and_close_excursion` | PASS -- previously MISSING, now included |
| 8 | Q11 Opportunity Engine | `opportunity_engine/simulator.py` | `test_calculator_8_q11_zero_offset_eod_no_excursion_and_cost_semantics` | PASS |
| 9 | Q12 Calc1 (shared-engine reuse) | `baseline_btc_woori_tech/forward_returns.py::attach_forward_returns` | `test_calculator_9_q12_shared_engine_reuse_produces_all_seven_checkpoints` | PASS -- corrected to 7 checkpoints |
| 10 | Q12 Calc2 | `baseline_btc_woori_tech/hypothesis_forward.py` | `test_calculator_10_q12_hypothesis_forward_five_labels` | PASS |
| 11 | Q12 Calc3 (vnext) | `baseline_btc_woori_tech/vnext/outcomes.py` | `test_calculator_11_q12_vnext_end_exclusive_and_completeness` | PASS |
| 12 | Opening Shadow 1A | `opening_rank1_shadow/latent_forward.py::_observe` | `test_calculator_12_opening_shadow_entry_and_forward_price_chains_differ` | PASS |
| 13 | Opening Shadow 1B | `opening_rank1_longitudinal/delayed_outcomes.py::forward_30m_net` | `test_calculator_13_opening_shadow_forward_30m_net_single_unbounded_checkpoint` | PASS |
| 14 | Opening Shadow 1C (d1/d3/d5) | `opening_rank1_longitudinal/delayed_outcomes.py::delayed_path` | `test_calculator_14_opening_shadow_d1_d3_d5_bounded_sessions_and_insufficient_future` | PASS |

**14/14 checkpoint calculators covered.** 3 downstream aggregators
(`baseline_samsung_hynix/forward_returns.py::summarize_forward_returns`,
`::q9_comparison.py::build_q9_role_comparison`, `forward_validation/cumulative.py::build_cumulative`)
remain explicitly out of scope (Reset item 2). Opening Controlled (0 calculators, re-confirmed
via `test_opening_controlled_has_no_program_specific_forward_policy` -- no `HorizonSpec`/
`ForwardPolicy` constructed) and Same-Symbol Sequences/Stage2 Authority (0 calculators,
unchanged since the original inventory pass) remain excluded from the 14 by design, not by
omission.

### 14.7 `ForwardSessionSpec` -- bounded traversal, not `UNBOUNDED_FORWARD`

Opening Shadow's `d1`/`d3`/`d5` are represented via `ForwardSessionSpec(resolver_authority=
ARTIFACT_AVAILABLE_SESSIONS, session_offset=N, required_available_sessions=N)` -- re-reading
`delayed_path` confirms `d3` requires ALL of the first 3 future sessions present in the
artifact-derived calendar to be genuinely observed, not merely the 3rd one
(`missing_days = [day for day in selected_days if day not in grouped]`,
`delayed_outcomes.py:126`), and the real status string on shortfall is literally
`"INSUFFICIENT_FUTURE_DAYS"` -- represented canonically as
`MissingObservationStatus.INSUFFICIENT_FUTURE_SESSIONS`. Proven against a real event row with
`available_future_day_count=4`: `d1_status`/`d3_status` are `OBSERVED` (1 and 3 both ≤ 4), `d5_status`
is `INSUFFICIENT_FUTURE_DAYS` (5 > 4) -- `opening_rank1_longitudinal.json`'s own event array.
`UNBOUNDED_FORWARD` (an `MfeMaeWindowEnd` member, a different axis entirely) is never used to
express this bound.

### 14.8 Source-result cost semantics (descriptive only)

`SourceResultCostSemantics.{GROSS_ONLY,NET_OR_COST_INCLUDED,UNKNOWN}` records whether the
LEGACY calculator's own result already carries a cost adjustment -- purely descriptive
provenance, never triggering any cost computation in this package. Q11's `simulator.py` and
Opening Shadow's `forward_30m_net` are both `NET_OR_COST_INCLUDED` (each populates a
cost-adjusted return figure directly in its own result). UEF-2B computes GROSS movement only;
UEF-3 remains the sole cost/net authority, unchanged.

### 14.9 UEF-2B input contract (unchanged scope, restated)

UEF-2B receives a resolved origin (`EventOrigin`/timestamp), this package's `ForwardPolicy`
(all three layers), and market observation data; it implements exactly ten generic primitives
-- `resolve_target`, `resolve_observation`, `resolve_ordered_price_candidates`,
`validate_evidence`, `validate_data_completeness`, `resolve_missing`, `resolve_session_close`,
`resolve_forward_session`, `resolve_excursion`, `calculate_gross_return` -- with ONE
calculator-specific exception UEF-2B must also implement because Layer A assigns it there:
the `RETRACEMENT_SCAN` reference-resolution algorithm for Q10 Index's `FIRST_PULLBACK_ENTRY`
(\S14.4). No other program-specific logic belongs in UEF-2B; if implementing any OTHER
calculator requires re-reading its legacy source to answer a semantic question, this Reset has
failed at that calculator.

### 14.10 Self-review against Codex's exact Reset findings

1. Ordered price fallback losslessly expressible (single `PriceAuthority` → `PriceCandidate`
   chains): YES -- `PriceResolutionPolicy`, reused across all three layers.
2. Opening Shadow reference (`OPEN→CLOSE`) vs. forward checkpoint (`CLOSE→REFERENCE_PRICE`)
   kept distinct: YES -- \S14.6 calculator 12.
3. Q10 shared-engine checkpoint (`CLOSE→REFERENCE_PRICE`) and excursion
   (`HIGH→REFERENCE_PRICE`/`LOW→REFERENCE_PRICE`) fallback: YES -- \S14.6 calculators 2-4.
4. Q10 Index directional shadow included as its own calculator, with explicit
   `FIRST_PULLBACK_ENTRY` ownership: YES -- \S14.4/\S14.6 calculator 7.
5. Collector `ABSENT`/`INVALID`/`VERIFIED` each independently modeled, with unsupported
   cross-combinations (`VERIFIED`+non-QUOTE, `ABSENT`+`QUOTE`) rejected at construction: YES.
6. `ExcursionPriceField.CLOSE` restored on real evidence: YES -- \S14.3.
7. Q9 Horizon/Exit's real 4-deep price chain / 2-deep excursion chains represented, not
   collapsed to `BAR_CLOSE`: YES -- \S14.2/\S14.6 calculator 1.
8. Q11's EOD checkpoint carries no `ExcursionPolicy` at all (real source computes neither
   MFE nor MAE for EOD): YES -- \S14.6 calculator 8.
9. Q11's own-outcome checkpoint uses `relative_seconds=0` (the origin instant itself), target
   timestamp exactly equal to `exit_epoch`: YES.
10. Q12's real 7-checkpoint output (not 4) represented, with the module-scoping root cause
    documented: YES -- \S14.5.
11. Opening Shadow `d1`/`d3`/`d5` each bounded via `ForwardSessionSpec.required_available_sessions`,
    proven against a real `INSUFFICIENT_FUTURE_DAYS` event: YES -- \S14.7.
12. Opening Controlled still builds no program-specific `ForwardPolicy`: YES.
13. Every `HorizonKind` enforces strict field exclusivity (no HorizonSpec can carry fields from
    two different kinds): YES.
14. `UEF-2B` requires no program-specific semantic guessing beyond the one explicitly-assigned
    `RETRACEMENT_SCAN` algorithm: YES -- \S14.9.

All 14: YES. `STATUS: PASS`.

---

## §15. BOUNDARY CLOSURE (current, authoritative)

Closes Codex's Semantic Authority Reset audit (CRITICAL:0/HIGH:5/MEDIUM:1/LOW:0). Two
structural changes, plus five targeted semantic fixes re-derived by re-reading real source
(never trusting a prior test's recorded value).

### 15.1 Generic Core / Semantic Profile split (structural)

The package now has two explicit layers:

- `contracts.py` + `policy.py` -- the GENERIC FORWARD CORE. Every symbol is
  program-name-agnostic (no Q9/Q10/Q11/Q12/Opening anywhere in a class name, enum member, or
  field name -- enforced by `tests/test_uef2a_boundary_closure_profiles.py::
  test_generic_core_public_symbols_never_encode_a_program_name`). Docstrings still cite real
  file:line evidence (required by every prior audit), but that is prose, not structure.
- `profiles.py` -- the SOURCE-DERIVED SEMANTIC PROFILE layer: 14 builder functions, one per
  real checkpoint calculator, each returning a `ForwardPolicy` built purely by composing the
  generic core. `PROFILE_REGISTRY: dict[int, CalculatorProfile]` (keys 1-14) is the reproducible
  registry (`profile_id`/`profile_version`/`source` per entry). A profile is declarative
  specification only -- never legacy-artifact-parsing/migration/adapter logic (that is UEF-4's
  job, not this package's).

Ownership boundary for UEF-2B (restated, unchanged from the Reset except the removed
`RETRACEMENT_SCAN` exception -- see 15.2): `resolve_target`, `resolve_observation`,
`resolve_ordered_price_candidates`, `validate_evidence`, `validate_data_completeness`,
`resolve_missing`, `resolve_session_close`, `resolve_forward_session`, `resolve_excursion`,
`calculate_gross_return` -- ten generic primitives, zero program-specific exceptions. UEF-2B's
own source code never needs to import `profiles.py`'s builder functions, only consume
`CalculatorProfile.policy` objects generically.

### 15.2 H1 -- FIRST_PULLBACK_ENTRY ownership reversed to UPSTREAM_REFERENCE_RESOLUTION

Codex's Boundary Closure ruling reverses the Semantic Authority Reset's own conclusion.
`shadow_comparison.py::_first_pullback_entry` (:43-64) physically reads
`reaction.get("path")` -- a candle series produced inside this SAME evaluation package by
Calculator F/G -- but its 0.5% `pullback_retrace_pct` threshold, 60-minute lookback window, and
direction/OVERREACTION-gated retracement-detection ALGORITHM are a program-specific research
technique, not a generic forward-measurement primitive. "Which package produced the input
row" and "whose algorithm resolves the reference" are different questions; ownership follows
the latter.

`ReferenceResolutionKind.RETRACEMENT_SCAN` is removed, along with its dedicated
`retracement_lookback_seconds`/`retracement_threshold_fraction` fields on
`ReferenceResolutionPolicy` -- those numeric parameters belong to the upstream algorithm's own
concern, never to the generic engine's input contract. Replaced by
`ReferenceResolutionKind.PRE_RESOLVED_REFERENCE`: the reference timestamp+price were already
resolved upstream; the engine only consumes the result
(`price_resolution=PriceResolutionPolicy.single(FIXED_OBSERVED_PRICE)`,
`provenance="FIRST_PULLBACK_ENTRY"`), enforced at construction (`ReferenceResolutionPolicy.
__post_init__`). Calculator 7 (Q10 Index Calc H) now declares this. UEF2 PROGRAM-SPECIFIC
REFERENCE LOGIC: NONE -- UEF-2B never implements a retracement scan.

### 15.3 H2 -- Q12 continuous-minute completeness represented

`outcomes.py::forward` (Q12 vnext, `vnext/outcomes.py:14-30`) gates MFE/MAE entirely on a
continuous-minute-bar completeness check: `window = [r for r in candles if t <= r['ts'] <
target]` (end-exclusive; EOD appends `point`, making it end-inclusive), `expected = (target -
t) // 60 + (1 if horizon == 'EOD' else 0)`, `complete = len(window) == expected`, and
`mfe_pct`/`mae_pct` are `None` unless `complete` -- the checkpoint's own `gross_return_pct` is
reported regardless. New generic primitive `DataCompletenessPolicy(kind=
DataCompletenessKind.CONTIGUOUS_INTERVAL, interval_seconds=60.0,
require_all_expected_observations=True)`, attached as `ExcursionPolicy.completeness` (optional
-- `None` for every other calculator, since this gap-check is unique to Q12 vnext in the whole
inventory). Calculator 11's profile now declares three exact checkpoints (09:30/10:00/EOD, per
the request's item 14), each with `completeness` set.

### 15.4 H3 -- Opening d1/d3/d5 excursion bound fixed

`delayed_path` (`delayed_outcomes.py:117-146`) scans MFE (`d{n}_max_high_net_pct`) over
`selected_rows = [row for day in selected_days for row in grouped.get(day) or []]` where
`selected_days = future_days[:horizon]` -- exactly the same bounded session-count window as the
checkpoint's own `ForwardSessionSpec`, never an unbounded forward scan. New
`MfeMaeWindowEnd.FORWARD_SESSION_BOUND` member replaces the incorrect `UNBOUNDED_FORWARD` for
calculator 14; enforced at construction that a `HorizonSpec` using it must be
`kind=FORWARD_SESSION` (`HorizonSpec.__post_init__`) -- the bound always reuses the horizon's
own `forward_session`, never a separately-specified count.

Separately, `d{n}_status = "INSUFFICIENT_FUTURE_DAYS"` fires immediately in the same pass
whenever `len(selected_days) < horizon or missing_days` (:125-130) -- it never waits or
expires. `HorizonSpec.__post_init__` now requires `kind=FORWARD_SESSION` horizons to declare
`missing_resolution=MissingResolutionPolicy.MARK_MISSING_IMMEDIATELY` -- this is the link
(previously missing) that canonically produces
`MissingObservationStatus.INSUFFICIENT_FUTURE_SESSIONS` for this horizon kind. Calculator 14
previously declared `KEEP_PENDING`, under which that status was dangling/unreachable.

### 15.5 H4 -- price fallback profiles corrected to match source exactly

Two calculators had an incomplete fallback chain, found by re-reading source from scratch:

- Calculator 1 (Q9 Horizon/Exit) EOD: `update_post_exit_shadow_with_price_observations`
  normalizes every row -- intraday AND the EOD `close_row` -- through the same 4-deep alias
  chain (`_row_price(raw,"close","price","current_price","cur_price")`,
  `strategy_horizon_feedback.py:914`) before either checkpoint reads `row["price"]`/
  `row["high"]`/`row["low"]` (:958,966-967 intraday; :981-1000 EOD, `high_since_exit`/
  `low_since_exit` computed identically). The prior profile gave EOD a bare `BAR_CLOSE`-only
  chain with `excursion=None` -- both wrong. Fixed: EOD now carries the full 4-deep checkpoint
  chain AND an `OWN_CHECKPOINT_OBSERVATION`-bounded excursion, identical in shape to the
  intraday checkpoints.
- Calculator 12 (Opening Shadow 1A): `_observe`'s excursion computation is `high =
  max(_number(value.get("high")) or entry_price for value in window)` / `low = min(...) or
  entry_price` (`latent_forward.py:122-123`) -- BAR_HIGH/BAR_LOW fall back to the episode's own
  `entry_price` (REFERENCE_PRICE) when a candle's high/low is missing/zero, for both intraday
  and EOD (same loop body). The prior profile used bare BAR_HIGH/BAR_LOW with no fallback at
  all. Fixed: both now chain to REFERENCE_PRICE.

Q9/Q10/Opening's other fallback chains were re-verified against source and found already
correct (Q10 shared-engine BAR_CLOSE->REFERENCE_PRICE / BAR_HIGH->REFERENCE_PRICE /
BAR_LOW->REFERENCE_PRICE) -- unchanged. Q11's own fallback chains were NOT yet correct at this
point in the audit history -- see \S16 (Q11 FINAL CLOSURE PATCH), which corrects this section's
own prior claim that Q11 was "already correct."

### 15.6 H5 -- Source cost provenance made explicit for all 14 (no dangling UNKNOWN)

Re-verified against source for every calculator (grep for net_return/net_pct/_net( in each
real module). Two calculators previously defaulting to UNKNOWN were found to have real
evidence:

| # | Calculator | Source | Cost semantics | Evidence |
|---|---|---|---|---|
| 1 | Q9 Horizon/Exit | strategy_horizon_feedback.py | GROSS_ONLY | only return_pct, no net field anywhere |
| 2 | Q10 Semiconductor Calc A | quant_shadow_forward_outcomes.py | GROSS_ONLY | no net field |
| 3 | Q10 Semiconductor Calc B | same engine | GROSS_ONLY | no net field |
| 4 | Q10 Semiconductor Calc C | same engine | GROSS_ONLY | no net field |
| 5 | Q10 Index Calc F | reaction_reader.py | GROSS_ONLY | raw OHLCV capture only, no return computed |
| 6 | Q10 Index Calc G | reaction_reader.py | GROSS_ONLY | collector snapshot only |
| 7 | Q10 Index Calc H | shadow_comparison.py | NET_OR_COST_INCLUDED | gross_eod_return_pct AND net_eod_return_pct=gross-total_cost both present (:112-113) -- found in this closure, was UNKNOWN |
| 8 | Q11 Opportunity Engine | simulator.py | NET_OR_COST_INCLUDED | gross_return_pct AND net_return_pct both present |
| 9 | Q12 Calc1 (shared engine) | quant_shadow_forward_outcomes.py | GROSS_ONLY | same engine as Calc A/B/C |
| 10 | Q12 Calc2 hypothesis_forward | hypothesis_forward.py | NET_OR_COST_INCLUDED | gross_return_pct AND net_return_pct=gross-drag_pct both present (:73-78) -- found in this closure, was UNKNOWN |
| 11 | Q12 Calc3 vnext | vnext/outcomes.py | NET_OR_COST_INCLUDED | gross_return_pct AND net_return_pct=gross-drag_pct both present (:25-27) |
| 12 | Opening Shadow 1A | latent_forward.py | GROSS_ONLY | checkpoints only carry gross_return_pct; cost applied downstream in _summary(), not per-episode |
| 13 | Opening Shadow 1B | delayed_outcomes.py::forward_30m_net | NET_OR_COST_INCLUDED | _net() bakes ROUND_TRIP_COST_PCT=0.28 in, no gross field exists |
| 14 | Opening Shadow 1C | delayed_outcomes.py::delayed_path | NET_OR_COST_INCLUDED | same _net() helper, every d{n}_*_net_pct field is cost-baked, no gross field exists |

Totals: GROSS_ONLY=8, NET_OR_COST_INCLUDED=6, UNKNOWN=0. No calculator is left with an
unjustified UNKNOWN (`SourceResultCostSemantics.UNKNOWN` remains a legal enum member for a
future 15th calculator genuinely too ambiguous to classify, but none of the current 14 needs
it). CANONICAL COST CALCULATION: ABSENT -- this package still computes zero cost/net figures
itself; `source_result_cost_semantics` is provenance metadata only, consumed by nothing.

### 15.7 MEDIUM -- direct-constructor type safety

`_require_enum_member()` (`policy.py`) guards every enum-typed field's `__post_init__` across
`PriceResolutionPolicy`, `ObservationPolicy`, `ExcursionPolicy`, `ReferenceResolutionPolicy`,
`HorizonSpec`, `ForwardSessionSpec`, `GrossReturnPolicy`, and `ForwardPolicy` -- a raw string
(even one that equals a real member's `.value`, e.g. "BAR_CLOSE") now raises
`ForwardPolicyValidationError` at the public constructor, not only through `from_dict`.
Previously `PriceResolutionPolicy(authorities=("BOGUS",))` was silently accepted.

### 15.8 14-calculator coverage table (profile registry)

| # | Calculator | Profile builder | Fix applied this closure |
|---|---|---|---|
| 1 | Q9 Horizon/Exit | build_q9_horizon_exit_profile | H4: EOD chain+excursion (15.5); H5: GROSS_ONLY explicit |
| 2 | Q10 Semiconductor Calc A | build_q10_semiconductor_calc_a_profile | H5: GROSS_ONLY explicit |
| 3 | Q10 Semiconductor Calc B | build_q10_semiconductor_calc_b_profile | H5: GROSS_ONLY explicit |
| 4 | Q10 Semiconductor Calc C | build_q10_semiconductor_calc_c_profile | H5: GROSS_ONLY explicit |
| 5 | Q10 Index Calc F | build_q10_index_calc_f_profile | H5: GROSS_ONLY explicit |
| 6 | Q10 Index Calc G | build_q10_index_calc_g_profile | H5: GROSS_ONLY explicit |
| 7 | Q10 Index Calc H | build_q10_index_calc_h_profile | H1: PRE_RESOLVED_REFERENCE (15.2); H5: NET_OR_COST_INCLUDED found |
| 8 | Q11 Opportunity Engine | build_q11_opportunity_engine_profile | reference/entry BAR_CLOSE->SOURCE_FIELD_PRICE; forward-horizon excursion BAR_HIGH/LOW->BAR_CLOSE; EXIT excursion BAR_HIGH/LOW->BAR_CLOSE->SOURCE_FIELD_PRICE (one level deeper than forward, both fixed) -- see \S17 (Q11 EXIT FINAL FIDELITY PATCH), which also corrects \S16's own claim that EXIT shared the forward horizons' chain |
| 9 | Q12 Calc1 (shared engine) | build_q12_calc1_shared_engine_profile | H5: GROSS_ONLY explicit |
| 10 | Q12 Calc2 hypothesis_forward | build_q12_calc2_hypothesis_forward_profile | H5: NET_OR_COST_INCLUDED found |
| 11 | Q12 Calc3 vnext | build_q12_calc3_vnext_profile | H2: completeness (15.3); 09:30/10:00/EOD each exact; H5 explicit |
| 12 | Opening Shadow 1A | build_opening_shadow_1a_profile | H4: excursion->REFERENCE_PRICE (15.5); H5 explicit |
| 13 | Opening Shadow 1B | build_opening_shadow_1b_profile | unchanged (already correct) |
| 14 | Opening Shadow 1C | build_opening_shadow_1c_profile | H3: FORWARD_SESSION_BOUND + MARK_MISSING_IMMEDIATELY (15.4); H5 explicit |

FULLY LOSSLESS PROFILES: 14 / 14. Each profile is individually tested in
`tests/test_uef2a_boundary_closure_profiles.py` (per-profile parametrized construction test +
one targeted test per H1-H5 fix), in addition to the pre-existing real-artifact
representability tests in `tests/test_uef2a_forward_policy_contract.py` (surgically updated for
the same 5 fixes, never rewritten wholesale).

### 15.9 Self-review (verbatim answers)

1. UEF-2B 안에 Q10-specific algorithm이 남았나? 아니다 -- RETRACEMENT_SCAN 제거로 0.5%
   threshold/OVERREACTION 알고리즘은 profile의 provenance 문자열로만 존재하며, 엔진은 이를
   실행하지 않는다.
2. FIRST_PULLBACK algorithm을 canonical engine이 구현해야 하나? 아니다 -- PRE_RESOLVED_REFERENCE는
   이미 resolved된 값을 consume하는 것으로 충분하다.
3. Q12 completeness를 engine이 추측해야 하나? 아니다 -- DataCompletenessPolicy가 explicit generic
   primitive로 존재한다.
4. d1/d3/d5 excursion limit을 engine이 추측해야 하나? 아니다 -- MfeMaeWindowEnd.FORWARD_SESSION_BOUND가
   해당 horizon 자신의 forward_session을 재사용하도록 구조적으로 강제된다.
5. missing result mapping이 profile 밖에 숨어 있나? 아니다 -- FORWARD_SESSION + MARK_MISSING_IMMEDIATELY
   조합이 HorizonSpec.__post_init__에서 강제되고, INSUFFICIENT_FUTURE_SESSIONS로의 매핑이
   문서화되어 있다.
6. fallback chain이 source보다 짧은 profile이 있나? 아니다 -- 14개 전부 재확인, 2건(calculator 1
   EOD, calculator 12)의 누락을 발견하여 수정했다.
7. 실제 cost semantics가 UNKNOWN으로 남은 calculator가 있나? 아니다 -- 14/14 explicit (GROSS_ONLY
   8, NET_OR_COST_INCLUDED 6, UNKNOWN 0).
8. direct constructor에 invalid raw string을 넣을 수 있나? 아니다 -- _require_enum_member()가 모든
   enum 필드에서 이를 차단한다 (테스트로 검증됨).
9. 14개 calculator 중 source를 다시 읽어야 구현 가능한 것이 있나? 아니다 -- 각 profile은 generic
   primitive 조합만으로 self-contained하다.

1-9 전부 문제 없음 -> PASS.

---

## §16. Q11 FINAL CLOSURE PATCH (current, authoritative for Calculator 8)

Closes Codex's final REJECT_UEF2A (CRITICAL:0/HIGH:1/MEDIUM:0/LOW:0, "Q11 profile fidelity
mismatch", 13/14 -> 14/14). This closure's own \S15.5/\S15.8 claim that Q11 was "already
correct" was itself wrong -- re-reading `opportunity_engine/simulator.py` from scratch (never
trusting the prior profile/test) found two real mismatches:

- **Reference/entry price**: `simulate_probe_v0` -- `price = float(candle.get("close") or
  features.get("price") or 0.0)` (`simulator.py:125`), carried into `position["entry_price"]`
  (`:138`) and read back as `entry_price` at trade-close time (`:163`). This is
  `BAR_CLOSE -> SOURCE_FIELD_PRICE` -- the prior profile declared a bare `BAR_OPEN`, which has
  zero support in source (Q11 never reads an "open" field anywhere in this function).
- **Excursion (MFE/MAE)**, in BOTH places it is computed:
  - Forward-checkpoint (+5/15/30/60m): `_forward_returns` -- `high = max(row.get("high") or
    row.get("close") or 0.0 ...)` / `low = min(row.get("low") or row.get("close") or 0.0 ...)`
    (`:35-36`) -- `BAR_HIGH -> BAR_CLOSE` / `BAR_LOW -> BAR_CLOSE`.
  - EXIT checkpoint (position tracking): `high = float(candle.get("high") or price)` / `low =
    float(candle.get("low") or price)` (`:147-148`), where `price` is that same row's own
    `BAR_CLOSE`-resolved value recomputed every loop iteration (`:125`) -- same shape,
    `BAR_HIGH -> BAR_CLOSE` / `BAR_LOW -> BAR_CLOSE`. The prior profile declared bare
    `BAR_HIGH`/`BAR_LOW` in both places, with no fallback at all.

Unchanged (re-confirmed, not touched by this patch): EOD (`:48-77`) still has no `mfe_pct`/
`mae_pct` key at all -- `excursion=None`, ABSENT. `source_result_cost_semantics` remains
`NET_OR_COST_INCLUDED` (`return_pct`/`gross_return_pct` and `net_return_pct` both still present
in the same result dicts). No other calculator's profile, and neither `contracts.py` nor
`policy.py` (the generic core), required any change -- the fix used only the existing
`PriceResolutionPolicy` ordered-chain primitive and existing `PriceCandidate` members
(`BAR_CLOSE`, `SOURCE_FIELD_PRICE`, `BAR_HIGH`, `BAR_LOW`); no `UNEXPECTED_CORE_BLOCKER`.

Regression coverage added: `test_uef2a_forward_policy_contract.py::
test_calculator_8_q11_zero_offset_eod_no_excursion_and_cost_semantics` (exact-tuple assertions
+ explicit negative-regression checks against the removed bare-`BAR_OPEN`/bare-`BAR_HIGH`/
bare-`BAR_LOW` states), plus six new profile-registry tests in
`tests/test_uef2a_boundary_closure_profiles.py` (`test_profile_8_q11_*`).

**FULLY LOSSLESS PROFILES: 14 / 14** (all 14 calculators, no remaining findings from this
audit cycle) -- superseded by \S17: EXIT's own excursion chain was still wrong at this point.

---

## §17. Q11 EXIT FINAL FIDELITY PATCH (current, authoritative for Calculator 8)

Closes Codex's Q11 Final Recheck (CRITICAL:0/HIGH:1/MEDIUM:0/LOW:0, "Q11 forward horizon and
EXIT excursion fallback semantics differ, but the profile represents them as one collapsed
chain", 13/14 -> 14/14). \S16's own fix was incomplete: it corrected the reference price and
gave BOTH excursion sites the same 2-deep `BAR_HIGH/LOW -> BAR_CLOSE` chain, but re-reading
`simulator.py` once more shows the two excursion sites are NOT the same depth:

- **Q11_FORWARD_EXCURSION** (+5/15/30/60m, unchanged from \S16, still correct): `_forward_
  returns` -- `high = max(row.get("high") or row.get("close") or 0.0 ...)` / `low = min(row.
  get("low") or row.get("close") or 0.0 ...)` (`:35-36`). This function receives only raw
  `rows`, never `features` -- its fallback terminates at `BAR_CLOSE`. `BAR_HIGH -> BAR_CLOSE` /
  `BAR_LOW -> BAR_CLOSE`.
- **Q11_EXIT_EXCURSION** (position tracking, FIXED this patch): `high = float(candle.get
  ("high") or price)` / `low = float(candle.get("low") or price)` (`:147-148`), where `price =
  float(candle.get("close") or features.get("price") or 0.0)` is recomputed for that SAME row
  every loop iteration (`:125`). Because `price` itself already carries the
  `features.get("price")` fallback, the EXIT excursion's true resolution chain is one level
  DEEPER than the forward horizons': `BAR_HIGH -> BAR_CLOSE -> SOURCE_FIELD_PRICE` / `BAR_LOW
  -> BAR_CLOSE -> SOURCE_FIELD_PRICE`.

Fixed in `profiles.py::build_q11_opportunity_engine_profile` by splitting the previously-shared
chain variables into two distinct, independently-named chains --
`q11_forward_excursion_mfe`/`q11_forward_excursion_mae` (2-deep, used only by the +5/15/30/60m
`HorizonSpec`s) and `q11_exit_excursion_mfe`/`q11_exit_excursion_mae` (3-deep, used only by the
`EXIT` `HorizonSpec`). No new generic primitive was needed -- the existing
`PriceResolutionPolicy` ordered-chain primitive already supports arbitrary length and was
simply applied with the correct, DIFFERENT length at each site. EOD (`excursion=None`)
untouched; `source_result_cost_semantics` (`NET_OR_COST_INCLUDED`) untouched; no other
calculator's profile, and neither `contracts.py` nor `policy.py`, required any change.

Regression coverage strengthened: `test_uef2a_forward_policy_contract.py::
test_calculator_8_q11_zero_offset_eod_no_excursion_and_cost_semantics` now asserts the forward
and EXIT chains separately with exact tuples, plus an explicit
`forward != exit` inequality assertion. `tests/test_uef2a_boundary_closure_profiles.py` gained
`test_profile_8_q11_forward_excursion_is_high_low_then_close`,
`test_profile_8_q11_exit_excursion_is_high_low_close_then_source_field_price`,
`test_profile_8_q11_exit_excursion_never_regresses_to_forward_length`, and
`test_profile_8_q11_forward_and_exit_excursion_chains_explicitly_differ` -- the last two exist
specifically so this exact bug (EXIT silently collapsing onto the forward horizons' shorter
chain) cannot return unnoticed.

**FULLY LOSSLESS PROFILES: 14 / 14** (all 14 calculators, forward/EXIT excursion now correctly
separated for Calculator 8).
