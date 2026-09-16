# Q11 / Opening Alpha Forward Validation — Current-State Review

Status: **CURRENT STATE REVIEW ONLY — NOT A MIGRATION SPEC**

Scope: investigation and documentation only. No code, threshold, prompt,
runtime, or file-structure change accompanies this document. All facts
below are read directly from repository HEAD source, config, and actual
report artifacts on disk — nothing here is inferred from names alone.

---

## 1. What Q11 actually is

**Program identity** (from `libs/research/opportunity_engine/contracts.py`):

```
PROGRAM_ID   = "Q11_OPENING_SURGE_MARKET_REVERSAL"
PROGRAM_NAME = "Q11 Opening Surge & Market Reversal Research"
research_window = "09:00-10:00 KST"
DEFAULT_SYMBOLS = ("005930", "000660", "009150")   # fixed, independent universe
```

`libs/research/opportunity_engine/contracts.py` also declares
`PROHIBITED_RUNTIME_DEPENDENCIES`, explicitly forbidding imports from
`graphs.nodes`, `libs.runtime.commander`, `libs.runtime.execution`,
`libs.runtime.quant.shadow_candidates`, and `libs.reporting.evaluation`.
This is a hard, code-level architectural isolation from the live trading
runtime, not just a documentation convention.

| File | Function/Class | Role | Runtime Connected? | Input | Output | State/Persistence | Report Output |
|---|---|---|---|---|---|---|---|
| `libs/research/opportunity_engine/contracts.py` | constants | program identity/config | No | — | `PROGRAM_ID`, `DEFAULT_SYMBOLS`, window bounds | — | — |
| `libs/research/opportunity_engine/data_provider.py` | `load_candles`, `load_market_timeline` | fetch/cache minute candles + market timeline | No (own Kiwoom/state read, not live state) | day, symbols, `state_path` | candle map, timeline rows | reads `data/state.json`, `data/logs/macro_indicators/*` | — |
| `libs/research/opportunity_engine/engine.py` | `build_signal_timeline` | compute opportunity/features signals | No | candles, market timeline | signal rows (`opportunity`, `symbol_features`, `market`) | — | — |
| `libs/research/opportunity_engine/simulator.py` | `simulate_probe_v0`, `summarize_trades`, `_forward_returns` | virtual entry/exit simulation + forward-window measurement | No | signals, cost/slippage | virtual trades + summary | — | — |
| `libs/research/opportunity_engine/report.py` | `render_report` | markdown rendering | No | signals/trades/summary | markdown text | — | — |
| `libs/research/opportunity_engine/pipeline.py` | `build_opportunity_engine_artifacts` | orchestrates the above | No | day, symbols, paths | file paths | writes JSON/MD under `reports/` | `reports/evaluation/opportunity_engine_shadow/<day>/*` |

**What question does Q11 actually test?** Whether an independently
computed intraday "opening surge / market reversal" signal, applied to a
small fixed symbol universe, would have produced a profitable strategy
if it had been allowed to trade — entirely offline, against historical
candle data, with its own signal-generation and its own entry/exit
simulation. It is a **self-contained shadow research/control experiment**,
not a strategy, not an evaluation loop over the live pipeline, and not a
controlled execution lane. Its own generated report literally states:

```
"- Strategist / Commander / Monitor integration: none"
```
(`libs/research/opportunity_engine/report.py:39`)

Historical program status (from `docs/q13_q14_validation/*`,
`docs/evaluation/current_operating_baseline.md`): **CONTROL RETAINED —
not profitable, not promoted.** It has run continuously since June 2026
as a negative-control research program alongside Q9/Q10.

---

## 2. What Opening Alpha Forward Validation actually is

This is **not one module** — it is three connected but structurally
distinct pieces of code that together produce what the user's phrase
names. All three genuinely exist at HEAD; none is a legacy/dead path.

### 2a. `opening_rank1_shadow` — observation-only cohort research

`libs/reporting/opening_rank1_shadow/contracts.py`:

```
SCHEMA_VERSION = "opening_rank1_shadow.v1"
BEHAVIOR_EFFECT = "observation_only"
COHORT_ID = "OPEN_0_20_RANK1_30M"
OPEN_START_MINUTE / OPEN_END_MINUTE = 09:00 - 09:20
PRIMARY_HORIZON = "+30m"
HORIZONS = ("+5m", "+15m", "+30m", "+60m", "EOD")
PROMOTION_GATES = { minimum_observed_count: 25, minimum_win_rate: 0.50, ... }
```

Episodes come from `libs/reporting/opening_rank1_shadow/episodes.py::build_opening_rank1_episodes`,
which reads **persisted Scanner decision windows** and takes the
candidate where `rank == 1`. This is the live Scanner's own Rank-1 pick,
not a separate universe. `decision_epoch`/`baseline_epoch` mark when
Scanner named that candidate Rank-1 — an observation timestamp, not a
trade timestamp.

### 2b. `opening_rank1_controlled_probe` — the live controlled-mock execution lane

`libs/runtime/opening_rank1_controlled_probe.py` (795 lines, read in full)
is genuinely wired into the live runtime: it is imported and called from
`graphs/nodes/execute_from_packet.py` (price-drift guard before broker
submission) and consumes Monitor's own entry-evaluation state
(`entry_info`, `original_wait_reason`, `base_entry_guard_blocked`,
`quant_entry_enforcement`, `risk_off_policy`). It is a **bounded Monitor
entry override**: it only ever activates when Monitor's normal entry path
already produced a specific overridable "wait" reason, and only for two
lane conditions:

```
ALLOWED_LANE_CONDITIONS = {"HIGH_COMMON_DIRECTIONAL", "CONFIRMED_RECURRENT_RANK"}
```

Hard-coded safety gates read directly from the reject-chain in
`evaluate_opening_rank1_controlled_probe()`:

```
reject("mock_broker_required")        # broker_mode must be exactly "mock"
reject("scanner_rank1_required")       # rank must == 1
reject("intrinsic_rank1_symbol_mismatch")
reject("outside_opening_window")       # only within opening_end_minute (default 20)
reject("opening_alpha_condition_not_allowed")
reject("opening_alpha_signal_price_drift_exceeded")
reject("daily_probe_limit_reached")    # max_daily_probes = 1
```

Probe size is `qty_fraction=0.25` of the normal order size
(`_probe_qty`). This lane genuinely calls the real Executor under a mock
broker session — it is not shadow simulation, but it is currently
**structurally incapable of reaching a real broker** through this
function (the `broker_mode != "mock"` check rejects unconditionally
before any other logic runs).

### 2c. `short_alpha_discriminator` — the actual "forward validation" comparison

`libs/reporting/short_alpha_discriminator/contracts.py`:

```
HORIZONS = ("+5m", "+15m", "+30m", "+60m", "EOD")   # identical tuple to 2a
PRIMARY_COHORT_ID = "HIGH_COMMON_SHORT_ALPHA_V1"
```

`libs/reporting/short_alpha_discriminator/opening_policy_matrix.py::build_opening_policy_matrix`
groups episodes by `asset_family`, `lane_condition`, `risk_band`,
`candidate_setup`, and `entry_horizon`, and computes forward-window
performance (`+5m/+15m/+30m/+60m/EOD`) per group. This is the piece that
literally does what "Opening Alpha Forward Validation" names — comparing
outcomes across fixed forward windows, segmented by discriminator cells.
Its own render function's title is literally `"# Opening Alpha Policy
Matrix"`.

### Combined table

| File | Function/Class | Role | Runtime Connected? | Input | Output | State/Persistence | Report Output |
|---|---|---|---|---|---|---|---|
| `libs/reporting/opening_rank1_shadow/episodes.py` | `build_opening_rank1_episodes` | build observation episodes from live Scanner Rank-1 windows | Reads persisted live state | Scanner decision windows, minute candles | episode records | — | feeds `opening_rank1_shadow_cumulative.json/.md` |
| `libs/reporting/opening_rank1_shadow/pipeline.py` | pipeline orchestration | daily/cumulative build | Reads persisted live state | episodes, market snapshots | cumulative summary | — | `reports/evaluation/opening_rank1_shadow/*` |
| `libs/reporting/opening_rank1_shadow/five_session_review.py` | five-session rollup | periodic review | No (batch over persisted data) | cumulative json | review json/md | — | `.../five_session_review/opening_alpha_five_session_review.{json,md}` |
| `libs/runtime/opening_rank1_controlled_probe.py` | `evaluate_opening_rank1_controlled_probe`, `evaluate_opening_alpha_execution_price_guard`, `record_probe_submission`, `record_probe_evaluation`, `record_rank1_observation` | **live** bounded entry-override + execution price guard | **Yes** — called from `execute_from_packet.py`, `monitor_node.py` | Scanner candidate, Monitor entry state, quant/cost gates | eligibility decision, execution price guard | `data/logs/opening_rank1_controlled_probe/<day>/*.json`, `data/logs/opening_alpha_rank_observations/<day>/*.json` | operator daily summary fields |
| `libs/runtime/opening_rank1_probe_discriminator.py` | `build_opening_probe_discriminator` | stable pre-outcome cell identity | Yes (called by the above) | lane/asset/risk/setup/**strategy_horizon** | discriminator cell dict | — | embedded in probe ledgers |
| `libs/runtime/opening_rank1_probe_cost_edge.py` | `evaluate_opening_probe_cost_edge` | cost-adjusted edge gate | Yes | candidate setup, lane, cost filter | pass/fail + fallback flag | — | embedded in probe ledgers |
| `libs/reporting/short_alpha_discriminator/opening_policy_matrix.py` | `build_opening_policy_matrix`, `render_opening_policy_matrix` | forward-window comparison by discriminator cell | No (post-hoc batch report) | joined opening+feature-mart episodes | matrix json/md | — | `libs/reporting/short_alpha_discriminator` output paths, surfaced via daily patches |
| `libs/reporting/short_alpha_discriminator/cohorts.py` | `join_opening_to_feature_mart`, `build_cohort_review` | cohort statistics, leave-one-out sensitivity | No | opening episodes + `rank1_feature_mart` | cohort review json | — | — |

---

## 3. Q11 runtime flow (actual)

Q11 has **no live runtime flow** — it never touches Commander/Strategist/
Scanner/Monitor/Executor. Its actual call path is a standalone batch job:

```
(cron/manual) -> build_opportunity_engine_artifacts(day=...)
  -> load_candles() / load_market_timeline()        [data_provider.py]
  -> build_signal_timeline(candles, timeline)        [engine.py]
  -> simulate_probe_v0(signals, cost_pct, slippage)  [simulator.py]
       -> _forward_returns(...)  computes +5m/+15m/+30m/+60m/EOD
  -> summarize_trades(trades)                        [simulator.py]
  -> render_report(...)                              [report.py]
  -> write JSON/MD                                    [pipeline.py]
```

- input: `day`, `symbols=DEFAULT_SYMBOLS`, candle map, market timeline
- output: `reports/evaluation/opportunity_engine_shadow/<day>/opportunity_engine_{signals,virtual_trades,daily_report}.{json,md}`
- No Commander/Strategist/Scanner/Monitor node ever calls into this
  path; it is invoked only by its own pipeline entry (there is a legacy
  `reports/runtime/q11_opportunity_engine_recover_*.log` from a past
  manual/cron recovery run, confirming it is operated as an independent
  scheduled job, not part of the trading graph).

## 4. Opening Alpha runtime flow (actual)

Opening Alpha genuinely sits inside the live per-tick trading graph:

```
Commander
  -> Strategist   (produces strategy_horizon: one of scalp/intraday/overnight_probe/1_2day_swing)
  -> Scanner      (produces ranked candidates; rank==1 candidate is the one Opening Alpha can ever touch)
  -> Monitor      (graphs/nodes/monitor_node.py: normal entry evaluation;
                    may produce a specific "wait" reason -- base_entry_guard_blocked)
       -> evaluate_opening_rank1_controlled_probe(selected, entry_info, ..., strategy_horizon=...)
            -> classify_opening_alpha_condition(...)     [same file]
            -> build_opening_probe_discriminator(...)    [opening_rank1_probe_discriminator.py]
            -> evaluate_opening_probe_cost_edge(...)      [opening_rank1_probe_cost_edge.py]
       -> if eligible+applied: record_probe_submission(...) ledger write
  -> execute_from_packet.py
       -> evaluate_opening_alpha_execution_price_guard(...)  [price-drift guard immediately before broker call]
       -> Executor -> mock broker (Kiwoom mock session)
  -> record_probe_evaluation(...) always recorded, regardless of eligibility
  -> record_rank1_observation(...) records every Rank-1 sighting for the recurrence check
(separately, offline)
  opening_rank1_shadow/pipeline.py -> cumulative episode statistics
  short_alpha_discriminator/opening_policy_matrix.py -> forward-window comparison by cell
```

Opening Alpha and Q11 share **no function, no collector, and no
reporter**. The only structural thing they share is the literal tuple
`("+5m", "+15m", "+30m", "+60m", "EOD")`, independently defined in three
separate files (see §9/§10).

---

## 5. Candidate source comparison

| 항목 | Q11 | Opening Alpha |
|---|---|---|
| Universe | Fixed, independent: `("005930", "000660", "009150")` | The live Scanner candidate universe (whatever Scanner ranks that day) |
| Candidate source | Its own `engine.py::build_signal_timeline` opportunity score | Scanner's canonical rank-1 pick (`selected_rank`/`effective_selected_rank`) |
| Rank source | None (no ranking concept; fixed symbol list) | `scanner_rank` (canonical field), with legacy fallbacks and an `intrinsic_rank1` cross-check authority |
| Rank position | N/A | Must be exactly rank 1 (`reject("scanner_rank1_required")`) |
| Scanner dependency | None | Hard dependency — cannot run without a real Scanner rank-1 candidate |
| Strategist dependency | None | Indirect only, via `strategy_horizon` passthrough label (see §7) |
| Monitor dependency | None | Hard dependency — only activates on a specific Monitor-blocked wait state |

**Verdict: candidates are not the same and are not produced the same
way.** Q11's candidates come from an isolated offline signal engine over
a fixed 3-symbol list; Opening Alpha's "candidate" is definitionally the
live Scanner's real rank-1 pick for that day, whatever symbol that is.

---

## 6. Entry model comparison

- **Q11 entry**: a variable, signal-driven event — whenever
  `simulate_probe_v0` sees `opportunity.probe_candidate == True` at a
  given minute bar for a given symbol, inside the fixed 09:00-10:00
  window. This is a purely simulated fill against historical minute
  candles; no broker, no Monitor, no real clock-driven decision boundary.
- **Opening Alpha entry** has two distinct timestamps that must not be
  confused:
  - `opening_rank1_shadow` episode timestamp (`decision_epoch`): the
    moment Scanner *named* the symbol rank-1 within 09:00-09:20 — an
    **observation** timestamp, not a trade timestamp.
  - `opening_rank1_controlled_probe` decision timestamp: the moment
    Monitor's normal entry path is blocked/waiting AND all the override
    conditions above pass — this is a genuine (mock) **broker submission
    attempt** timestamp, bounded to `minutes_since_open <= opening_end_minute`
    (default 20 minutes from open), i.e. inside 09:00-09:20 by default.

No fixed clock times like "09:03"/"09:05"/"09:10" exist as named constants
anywhere in either system; the only fixed clock boundary found is the
09:00-09:20 opening window (`OPEN_START_MINUTE`/`OPEN_END_MINUTE` in
`opening_rank1_shadow/contracts.py`, and `opening_end_minute=20` default
parameter in `opening_rank1_controlled_probe.py`). "First pullback" /
"immediate opening probe" concepts survive today specifically as the
Alpha Research Board's `IMMEDIATE_OPENING_PROBE` track_id
(`libs/reporting/alpha_research_board/canonical.py`), which is sourced
from Opening Alpha's controlled-probe episodes, not from Q11.

---

## 7. Strategist connection

| Strategist Field | Q11 | Opening Alpha | 실제 사용 여부 |
|---|--:|--:|---|
| Regime | — | — | not read by either |
| Direction | — | — | not read by either |
| Confidence | — | — | not read by either |
| Scenario | — | — | not read by either |
| Holding horizon (`strategy_horizon`) | — | present as one of five discriminator dimensions | `PASSTHROUGH_ONLY` — labels the observability cell only; `build_opening_probe_discriminator` sets `"eligibility_effect": "NONE"` explicitly, so it never changes whether the probe is eligible or applied |
| Overnight | — | — | not read by either (Opening Alpha is opening-window-only by construction) |
| 기타 | none (own report states "Strategist / Commander / Monitor integration: none") | Scanner's `risk_band`/`asset_class`/`candidate_setup` genuinely drive eligibility (not Strategist fields) | — |

**Neither system currently uses Strategist's market-reasoning fields
(regime/direction/confidence/scenario) for candidate selection or entry
timing.** Opening Alpha's only Strategist touchpoint is the categorical
`strategy_horizon` label, and it is confirmed passthrough-only by the
discriminator module's own `eligibility_effect: NONE` field.

---

## 8. Holding Horizon — detailed investigation (most important section)

### A. Does Strategist currently generate a holding horizon? **YES, with a deterministic fallback.**

- Canonical field: `strategy_horizon` (also accepts a legacy alias
  `horizon`), read via `libs/runtime/strategy_horizon_feedback.py::_normalize_strategy_horizon_value`
  from `state["strategist_output"]` / `strategy_policy` / `entry_strategy_context`.
- `libs/strategies/contracts.py` (the formal `StrategistOutput` DTO) does
  **not** declare `strategy_horizon` as a typed field — it travels as an
  additive/loose key on the strategist output surface, not as part of the
  frozen canonical contract.
- The Strategist LLM prompt in `graphs/nodes/strategist_node.py` (Stage 3
  hold-review, lines ~1126-1128) does explicitly define and request an
  enum:
  ```
  "current_horizon": "scalp|intraday|overnight_probe|1_2day_swing",
  "proposed_horizon": "scalp|intraday|overnight_probe|1_2day_swing",
  ```
  So the LLM does actively choose one of these four values in the
  post-entry hold-review path. At initial framing, if the LLM does not
  supply a usable value, `_choose_default_horizon()` deterministically
  derives one from `playbook`/`monitor_guidance`/`trade_aggressiveness`
  (e.g. "quick_take_profit" or high aggressiveness → `scalp`; anything
  else defaults to `intraday`). So it is genuinely **LLM-influenced at
  least in the hold-review stage, and deterministic-fallback everywhere
  else** — not purely one or the other.

### B/C. How many horizon categories exist, and is it exactly 4?

**YES — exactly 4**, defined in `libs/runtime/strategy_horizon_feedback.py`:

```python
_ALLOWED_HORIZONS = {"scalp", "intraday", "overnight_probe", "1_2day_swing"}
```

Each has a default window (`min_sec`/`target_sec`/`max_sec`) and a full
behavior translation (scanner scope bias, monitor review cadence, hold
control bias, exit policy bias, `overnight_allowed`).

### D. Is this a prediction or an evaluation bucket? **It is a categorical, forward-looking holding-intent classification (closer to "prediction"), and it is architecturally distinct from the fixed-time evaluation buckets used everywhere else.**

This is the single most load-bearing finding of this review:

```
Axis 1 -- ENTRY / HOLDING-INTENT POLICY (categorical, "prediction"-like)
  scalp | intraday | overnight_probe | 1_2day_swing
  -> drives Monitor review cadence, hold-control bias, exit-policy bias
  -> owned by strategy_horizon_feedback.py / monitor_strategy_frame.py
  -> exactly 4 values

Axis 2 -- FORWARD EVALUATION BUCKETS (fixed wall-clock offsets from entry/decision, measured post-hoc, unconditionally)
  +5m | +15m | +30m | +60m | EOD   (sometimes also T+1 | T+2)
  -> measures what happened after entry, regardless of which Axis-1 horizon was in effect
  -> independently implemented in Q11, opening_rank1_shadow, short_alpha_discriminator, and post_exit_shadow
  -> exactly 5 values (or 7 including T+1/T+2)
```

These two axes are never merged anywhere in the current code, but they
do share the English word "horizon," which is a real, pre-existing
source of ambiguity independent of anything Q11/Opening Alpha specific.

---

## 9. Q11 horizon evaluation

`libs/research/opportunity_engine/simulator.py::_forward_returns` stores,
per virtual trade:

```
fields per bucket: status, return_pct, net_return_pct, mfe_pct, mae_pct, observed_epoch
buckets: +5m, +15m, +30m, +60m, EOD
```

Plus at the trade level (not per-bucket): `entry_price`, `exit_price`,
`entry_epoch`, `exit_epoch`, `mfe_pct`, `mae_pct`, `gross_return_pct`,
`net_return_pct`, `held_minutes`, `exit_reason`.

Capture timing: computed once, at pipeline build time, directly from
already-persisted minute candles (`data_provider.load_candles`) — there
is no live/intraday scheduler and no separate closeout collector; the
whole thing is one batch function call. There is no explicit
restart/gap-recovery logic beyond re-running the same day's build (a past
manual recovery is evidenced by
`reports/runtime/q11_opportunity_engine_recover_20260626_142604.{out,err}.log`).

## 10. Opening Alpha horizon evaluation

Two independent implementations exist for the *same* fixed-bucket concept:

1. `libs/reporting/opening_rank1_shadow/contracts.py::HORIZONS = ("+5m","+15m","+30m","+60m","EOD")`,
   consumed by that package's own episode evaluator
   (`libs/research/post_reclaim_alpha/evaluator.py::evaluate_episodes`,
   referenced from `episodes.py`) — computes checkpoints keyed by these
   same five labels, stored per-episode as `checkpoints.<label>` with a
   `live_net_return_pct` field.
2. `libs/reporting/short_alpha_discriminator/contracts.py::HORIZONS = ("+5m","+15m","+30m","+60m","EOD")`
   (byte-for-byte identical tuple) + `metrics.py::checkpoint_return`
   reads `episode["checkpoints"][horizon]["live_net_return_pct"]` — this
   is the exact same checkpoint shape as (1), consumed downstream for the
   policy-matrix comparison.
3. A third, separately-implemented instance exists in
   `libs/runtime/strategy_horizon_feedback.py::update_post_exit_shadow_with_price_observations`,
   which computes `+5m/+15m/+30m/+60m/EOD` (plus `T+1`/`T+2`) checkpoints
   from raw minute rows completely independently (its own
   `_PRICE_CHECKPOINT_MINUTES` dict and its own EOD-detection logic),
   for the unrelated post-exit shadow-tracking feature.

**Verdict: `DUPLICATE IMPLEMENTATION`.** The exact same five-bucket
concept (`+5m/+15m/+30m/+60m/EOD`) is computed by at least four
independently written functions across Q11
(`opportunity_engine/simulator.py`), Opening Alpha's two layers
(`opening_rank1_shadow`'s evaluator and `short_alpha_discriminator`'s
`metrics.py`), and the unrelated post-exit shadow feature
(`strategy_horizon_feedback.py`). None of them share a function or import
from one another; each re-derives entry/high/low/close windowing logic
independently.

---

## 11. Monitor's role

| | Q11 | Opening Alpha |
|---|---|---|
| Classification | `NO_MONITOR` | `MONITOR_ENTRY_TRIGGER` (bounded override, not full decision authority) |
| Evidence | Zero references to `monitor_node`/`Monitor` outputs anywhere in `libs/research/opportunity_engine/*.py`; own report states integration is "none" | `evaluate_opening_rank1_controlled_probe` takes Monitor's own `entry_info`, `original_wait_reason`, `base_entry_guard_blocked` as direct inputs and can only activate on specific Monitor-blocked wait states; Monitor's normal entry/exit logic remains authoritative outside those narrow conditions |

Opening Alpha does not replace Monitor's decision — it is a narrow,
enumerable override applied *after* Monitor has already decided to wait,
and only under two lane conditions, capped at once per day.

---

## 12. Relationship to real order execution

| Execution Type | Q11 | Opening Alpha |
|---|--:|--:|
| Observation only | — | Yes (the `opening_rank1_shadow` cohort layer, before any probe applies) |
| Shadow | Yes (`order_execution_allowed: False` on every trade, always) | — (it does not run a separate pure-shadow simulation of its own; the shadow layer above is observation of *real* Scanner picks, not a virtual fill) |
| Controlled mock | No | **Yes** — `evaluate_opening_rank1_controlled_probe` genuinely dispatches through the real Executor into a mock-broker Kiwoom session, capped at 1 probe/day, `qty_fraction=0.25` |
| Broker mutation | No | Yes, but only against the **mock** broker; `broker_mode != "mock"` is rejected unconditionally in code |
| Production-enabled | No | **No** — the current code has no path from this function to a real broker; `reject("mock_broker_required")` is unconditional |

This is the sharpest structural difference between the two systems: Q11
can never place any kind of order under any configuration; Opening Alpha
already places real (mock-broker) orders today, through the same
Executor used by normal live trading, under a tightly bounded and
audited set of conditions.

---

## 13. Reporter output comparison

**Q11** — one self-contained daily bundle:
```
reports/evaluation/opportunity_engine_shadow/<day>/opportunity_engine_signals.json
reports/evaluation/opportunity_engine_shadow/<day>/opportunity_engine_virtual_trades.json
reports/evaluation/opportunity_engine_shadow/<day>/opportunity_engine_daily_report.md
reports/evaluation/opportunity_engine_shadow/<day>/opportunity_engine_daily_report.json
```

**Opening Alpha** — a multi-layer reporting surface spanning several
independent artifacts:
```
data/logs/opening_alpha_rank_observations/<day>/rank1_observations.json      (rank sighting ledger)
data/logs/opening_rank1_controlled_probe/<day>/probe_submissions.json         (execution ledger, capped at 1/day)
data/logs/opening_rank1_controlled_probe/<day>/probe_evaluations.json         (every evaluation, eligible or not)
reports/evaluation/opening_rank1_shadow/opening_rank1_shadow_cumulative.json/.md   (cumulative cohort research)
reports/evaluation/opening_rank1_shadow/five_session_review/opening_alpha_five_session_review.{json,md}
short_alpha_discriminator opening_policy_matrix output (forward-window comparison by cell)
Alpha Research Board (OPENING_CONDITIONAL track: IMMEDIATE_OPENING_PROBE / CONFIRMED_RECURRENT_RANK / DISLOCATION_REBOUND rows)
operator daily summary (libs/reporting/controlled_validation_daily.py "opening_alpha" block: evaluation_count/applied_count)
```

Neither system duplicates the *other's* report file; they never write to
the same path. But within Opening Alpha itself, the same underlying
episodes are surfaced through at least four separate report layers
(cumulative cohort, five-session review, policy matrix, Alpha Board),
which is an internal-to-Opening-Alpha reporting proliferation, not a
Q11/Opening-Alpha overlap.

---

## 14. Persistence comparison

| | Q11 | Opening Alpha |
|---|---|---|
| Candidate | not persisted separately (recomputed each run from candles) | `data/logs/opening_alpha_rank_observations/<day>/rank1_observations.json` |
| Entry | embedded in `opportunity_engine_virtual_trades.json` | embedded in `probe_submissions.json` (only when actually applied, capped at 1/day) |
| Horizon observation | embedded per-trade in `opportunity_engine_virtual_trades.json` (`forward_returns`) | embedded per-episode in `opening_rank1_shadow_cumulative.json` (`checkpoints`) |
| Exit/result | embedded in the same trades file | same as above; controlled-probe side also records `probe_evaluations.json` regardless of outcome |
| Status | `behavior_effect: shadow_only` tag in every artifact | `behavior_effect: observation_only` (shadow layer) vs `controlled_mock_entry_probe` (probe layer) — both explicitly tagged |
| Validation state | none (a permanent negative control, not gated for promotion) | `PROMOTION_GATES` thresholds defined in `opening_rank1_shadow/contracts.py` (min observed count/day count/coverage/win rate/profit factor/day-and-symbol concentration caps) |

Storage medium for both: plain JSON files under `data/logs/` and
`reports/evaluation/`, atomically written via a temp-file-then-replace
pattern in Opening Alpha's runtime writers; no SQLite, no database.

---

## 15. Alpha Research Board relationship

`libs/reporting/alpha_research_board/canonical.py` confirms:

- **Opening Alpha appears on the Alpha Board** under `track_id="OPENING_CONDITIONAL"`,
  with named candidate rows `IMMEDIATE_OPENING_PROBE`,
  `CONFIRMED_RECURRENT_RANK`, and `DISLOCATION_REBOUND`, explicitly sourced
  from `opening_rank1_shadow_cumulative.json`'s controlled-probe episodes.
  A code comment there explicitly flags that these rows are "actually
  backed by `opening_rank1_controlled_probe.py`'s real mock-order-executing
  mechanism" — i.e. the Board's own maintainers already treat this as a
  live-adjacent source requiring care, not a plain observation row.
- **Q11 does not appear on the Alpha Research Board at all.** No
  `Q11`/`opportunity_engine` reference exists anywhere under
  `libs/reporting/alpha_research_board/`. Q11 remains a fully separate,
  Board-invisible control study.

---

## 16. Recent artifact evidence (actual files on disk, not just code)

**Q11** — `reports/evaluation/opportunity_engine_shadow/2026-09-11/opportunity_engine_daily_report.json`:
```json
{
  "schema_version": "opportunity_engine_daily_report.v1",
  "evaluation_program_id": "Q11_OPENING_SURGE_MARKET_REVERSAL",
  "behavior_effect": "shadow_only",
  "research_window": "09:00-10:00 KST",
  "day": "2026-09-11"
}
```
Directories present for 2026-09-07 through 2026-09-11 (5 most recent
days checked) — matches the code contract exactly, continuously
maintained.

**Opening Alpha** — `reports/evaluation/opening_rank1_shadow/opening_rank1_shadow_cumulative.json`:
```json
{
  "schema_version": "opening_rank1_shadow.v1",
  "behavior_effect": "observation_only",
  "cohort_id": "OPEN_0_20_RANK1_30M",
  "first_eligible_day": "2026-08-03",
  "through_day": "2026-09-11",
  "summary": {
    "episode_count": 117,
    "observed_day_count": 26,
    "conditional_lane_summaries": {
      "CONFIRMED_RECURRENT_RANK": { "horizons": { "+5m": { "win_rate": 0.25, ... } } }
    }
  }
}
```
Both artifacts are current through the same day (2026-09-11) and match
their respective source contracts exactly — code definitions and real
generated output agree.

---

## 17. Common ground

| Dimension | Q11 | Opening Alpha | Same / Different |
|---|---|---|---|
| Candidate | fixed 3-symbol independent list, own signal engine | live Scanner rank-1 pick | **Different** |
| Direction | its own opportunity score (surge/reversal) | Scanner's directional score/quant gates | **Different mechanism, similar intent** |
| Entry | signal-triggered virtual fill, own simulator | Monitor-blocked-override, real mock-broker submission | **Different** |
| Holding horizon (bucket) | `+5m/+15m/+30m/+60m/EOD` | `+5m/+15m/+30m/+60m/EOD` | **Same tuple, independently implemented** |
| Observation | own signal timeline | Scanner Rank-1 sighting ledger | **Different data, same general shape** |
| MFE/MAE | Yes, computed per trade | present in `opening_rank1_shadow` episode evaluator (not directly read here but same episode shape) | **Similar concept** |
| Return | `net_return_pct` w/ own cost/slippage model | `live_net_return_pct` w/ `LIVE_ROUND_TRIP_COST_PCT` | **Similar concept, separate cost model constants** |
| Reporter | one self-contained daily bundle | 4+ separate report layers | **Different scale** |
| Persistence | JSON under `reports/evaluation/opportunity_engine_shadow/` | JSON under `data/logs/opening_*` and `reports/evaluation/opening_rank1_shadow/` | **Different paths, same medium (JSON)** |
| Strategist context | none | passthrough-only label | **Both effectively unused for decisions** |
| Scanner context | none | hard dependency (rank-1 required) | **Different** |
| Monitor context | none | bounded override input | **Different** |
| Execution | never (`order_execution_allowed: False` always) | real mock-broker submission, capped 1/day | **Different** |

---

## 18. Key differences (experimental meaning, not just implementation)

- **Q11's hypothesis, in one sentence**: "Does an independently-detected
  intraday opening-surge/reversal pattern on a small fixed universe
  produce a profitable trading rule, net of cost, if allowed to trade on
  its own?" It is a **candidate-generation and entry-timing** hypothesis,
  fully decoupled from the live pipeline.
- **Opening Alpha's hypothesis, in one sentence**: "When the live
  Scanner's own rank-1 pick is blocked from a normal entry for a specific
  overridable reason, does allowing a small, tightly-bounded override
  entry under two specific alpha conditions produce a favorable
  forward-return distribution, segmented by asset/risk/setup/horizon?" It
  is an **entry-override / policy-validation** hypothesis layered
  directly on the live pipeline's own candidate.

**Verdict: these are different questions**, not the same question
implemented twice. They happen to reuse the identical vocabulary word
"opening," the identical fixed-window evaluation-bucket tuple, and a
loosely overlapping symbol universe by coincidence (Samsung/Hynix show up
in both because they are frequently Scanner's actual rank-1 picks, not
because Q11 targets Scanner's picks).

---

## 19. Overlap assessment

| Overlap axis | Estimate | Basis |
|---|---:|---|
| Candidate overlap | ~10% | Different universes/mechanisms; only coincidental symbol overlap |
| Entry overlap | ~15% | Different trigger mechanisms and different timestamp semantics |
| Horizon (evaluation bucket) overlap | ~90% | Byte-identical `("+5m","+15m","+30m","+60m","EOD")` tuple, independently implemented at least twice more (four times total across the whole codebase) |
| Evaluation (metric) overlap | ~70% | Both compute win_rate/avg_net_return/profit_factor/MFE/MAE-equivalent statistics over the same bucket shape, via separately written code |
| Reporting overlap | ~30% | Same general purpose (daily/cumulative evaluation artifact), no shared file, schema, or renderer |
| Runtime overlap | ~0% | Q11 is code-level isolated from the runtime (`PROHIBITED_RUNTIME_DEPENDENCIES`); Opening Alpha is deeply runtime-integrated |

```
OVERLAP VERDICT: MEDIUM
```

The duplication is real and concentrated almost entirely in the
**evaluation-bucket mechanism** (the fixed `+5m/+15m/+30m/+60m/EOD`
checkpoint math, independently written at least four times across the
whole codebase). The **experimental purpose, candidate source, entry
model, and runtime posture are substantially different**, which is why
this is `MEDIUM` rather than `HIGH` or `NEAR_DUPLICATE`.

---

## 20. Integration possibilities — analysis only, not implemented

### Option A — Keep both

- **장점**: zero risk to either program's historical evidence trail or
  its published `PROGRAM_ID`/`COHORT_ID` identifiers, which are cited by
  name across many closure/audit documents (`docs/q13_q14_validation/*`,
  `docs/daily_patch/*`); zero migration complexity; zero runtime impact.
- **단점**: the evaluation-bucket duplication persists; anyone auditing
  "how does this system measure forward returns" must read four separate
  implementations to be sure they agree.
- **잃는 evidence**: none.
- **migration complexity**: none (status quo).
- **runtime impact**: none.
- **report impact**: none.

### Option B — Q11 absorbed into Opening Alpha (or vice versa)

- **장점**: one fewer program to maintain conceptually; would force a
  single shared horizon-evaluation implementation.
- **단점**: Q11's candidate universe, entry model, and runtime isolation
  are fundamentally different from Opening Alpha's live-Scanner-coupled,
  runtime-integrated design. Absorbing one into the other means either
  (a) forcing Q11's fixed 3-symbol independent research onto Scanner's
  live rank-1 pick (destroying the thing Q11 is actually testing), or
  (b) forcing Opening Alpha's live-execution-coupled probe into Q11's
  runtime-isolated batch-only world (destroying Opening Alpha's real
  execution/price-guard function). Either direction changes what is
  being measured, not just how.
- **잃는 evidence**: Q11's `PROGRAM_ID`/negative-control framing (cited
  across five+ historical closure documents) would need explicit
  re-labeling to avoid being silently reinterpreted as something it
  never was; Opening Alpha's live cost-edge/price-drift guard evidence
  has no equivalent concept in Q11's world and would need a new home.
  This is exactly the class of risk the system's own
  `docs/daily_patch/2026-08-21_q10_q11_q13_measurement_integrity.md` was
  written to guard against (conflating independently-collected evidence
  streams under one label).
- **migration complexity**: high.
- **runtime impact**: would require deciding whether the merged program
  is runtime-isolated (losing Opening Alpha's live-execution capability)
  or runtime-integrated (breaking Q11's architectural isolation
  guarantee) — not a decision this review makes.
- **report impact**: would require re-deriving every historical
  cumulative statistic under a new combined schema, or accepting a
  discontinuity in both evidence trails at the merge point.

### Option C — Shared forward-validation/evaluation engine only

- **장점**: targets exactly the part that is genuinely duplicated (the
  `+5m/+15m/+30m/+60m/EOD` checkpoint math) without touching either
  program's candidate source, entry model, or runtime posture. Both
  programs keep their own `PROGRAM_ID`/`COHORT_ID`, their own report
  trees, and their own historical evidence untouched; they would simply
  call one shared, tested checkpoint function instead of four
  independently-written ones.
- **단점**: does not resolve the Axis-1/Axis-2 "horizon" naming ambiguity
  (§8); is a smaller, less dramatic change than a full merge, so it does
  not simplify the "why are there two opening-related programs" question
  a reader might still have.
- **잃는 evidence**: none, if implemented as a pure refactor with
  regression tests confirming identical output before/after.
- **migration complexity**: low-to-medium (four call sites to redirect,
  each with its own existing test coverage to protect).
- **runtime impact**: none, if the shared function lives outside
  `PROHIBITED_RUNTIME_DEPENDENCIES` scope (i.e. as a pure data-in/data-out
  utility Q11's isolation rule would still permit importing).
- **report impact**: none, if output is byte-identical to current.

*(No option is implemented in this review. This section is comparative
analysis only.)*

---

## 21. Feasibility of the user's proposed future direction

Proposed direction: merge Opening Alpha Forward Validation into Q11, and
have Q11 validate exactly the Strategist-provided 4 holding horizons.

| Question | Answer |
|---|---|
| 현재 Strategist가 이미 4 horizon 정보를 제공하는가? | **YES** — `scalp/intraday/overnight_probe/1_2day_swing`, confirmed in `strategy_horizon_feedback.py` and in the Strategist LLM's own Stage-3 hold-review prompt enum. |
| 현재 Q11이 4 horizon evaluation을 이미 지원하는가? | **NO, and not the same axis** — Q11 evaluates 5 *fixed-time* buckets (`+5m/+15m/+30m/+60m/EOD`), which is a different concept from Strategist's 4 *categorical holding-intent* labels. Q11 has zero code path that reads `strategy_horizon` today. |
| Opening Alpha가 별도 유지해야 할 고유 정보가 있는가? | **YES** — live Scanner rank-1 coupling, the cost-edge/price-drift execution guards, the real (mock) broker submission ledger, and the `PROMOTION_GATES` cohort-promotion criteria all have no equivalent in Q11 and no meaning outside the live runtime. |
| 동일 entry 기준으로 4 horizon만 비교할 수 있는가? | Only if "horizon" is *redefined*, for this comparison, to mean Strategist's 4 categorical labels used as a **grouping dimension** over existing entries (the way `short_alpha_discriminator` already groups by `entry_horizon` as one of five discriminator dimensions) — not as a replacement for the current 5 fixed-time evaluation buckets, which measure a different thing and would still be needed to know *what happened* within any given categorical horizon. |
| 현재 코드에서 삭제/흡수해야 할 부분은 무엇인가? | Not assessed as "needing" removal by this review; if pursued, the most defensible target is consolidating the four independent `+5m/+15m/+30m/+60m/EOD` implementations (Option C), not deleting either program outright. |
| 기존 historical evidence는 어떻게 보존할 수 있는가? | By keeping `PROGRAM_ID="Q11_OPENING_SURGE_MARKET_REVERSAL"` and `COHORT_ID="OPEN_0_20_RANK1_30M"` as permanent historical identifiers even if a future shared engine is introduced underneath them — this review takes no position on whether that is the right call, only that it is the mechanism available. |

```
USER PROPOSED Q11 INTEGRATION FEASIBILITY: PARTIAL
FOUR-HORIZON-ONLY FEASIBILITY: NOT_CURRENTLY_SUPPORTED (as a replacement for the existing 5-bucket evaluation; PARTIAL as an additional grouping dimension)
```

---

## 22. Entry policy vs. holding-horizon evaluation — are they currently conflated?

**They are named with the same word ("horizon") but are not currently
conflated in logic** — no code path uses the categorical
`scalp/intraday/overnight_probe/1_2day_swing` value as if it were a
fixed-time checkpoint, and no code path uses `+5m/+15m/+30m/+60m/EOD` as
if it were a holding-intent classification. The one place they touch is
`opening_rank1_probe_discriminator.py`, where `strategy_horizon`
(Axis 1) is used purely as a **label** on a discriminator cell that also
happens to be evaluated across Axis-2 buckets in
`short_alpha_discriminator`'s policy matrix — this is a legitimate,
already-existing pattern of "group by Axis 1, measure across Axis 2,"
not a conflation.

The real risk this review surfaces is **terminological**, not
architectural: a future reader (or a future prompt to an LLM) asked to
"validate 4 horizons" could easily reach for the wrong axis, since both
are called "horizon" in different parts of this codebase today. This is
worth fixing regardless of any Q11/Opening-Alpha decision, and is called
out here as a standalone observation.

---

## 23. Current-state diagram

```
                         Commander
                             |
                             v
                        Strategist
                    (produces strategy_horizon:
                     scalp|intraday|overnight_probe|1_2day_swing
                     -- ADVISORY, not consumed by either system below
                     except as a passthrough label in Opening Alpha)
                             |
                             v
                          Scanner
                    (ranked candidates, rank-1 pick)
                             |
              ______________|______________
             |                              |
             |                              v
             |                          Monitor
             |                    (normal entry/exit logic;
             |                     may emit an overridable
             |                     "wait" reason)
             |                              |
             |                              v
             |          opening_rank1_controlled_probe.py
             |          (bounded override: rank==1 AND
             |           HIGH_COMMON_DIRECTIONAL or
             |           CONFIRMED_RECURRENT_RANK AND
             |           cost-edge pass AND price-drift OK
             |           AND daily-probe-limit not reached)
             |                              |
             |                    eligible? -> execute_from_packet.py
             |                              |         -> mock broker (Executor)
             |                              v
             |                   opening_rank1_shadow (observation
             |                    of every rank-1 sighting, 09:00-09:20,
             |                    +5m/+15m/+30m/+60m/EOD checkpoints)
             |                              |
             |                              v
             |                   short_alpha_discriminator
             |                   (opening_policy_matrix: forward-window
             |                    comparison by asset/risk/setup/horizon)
             |                              |
             |                              v
             |                     Alpha Research Board
             |                     (OPENING_CONDITIONAL track)
             |
             v
  (independent, isolated batch job -- no arrow from any live node)
        Q11 opportunity_engine
   (own signal engine, fixed 3-symbol
    universe, own virtual entry/exit,
    own +5m/+15m/+30m/+60m/EOD checkpoints)
             |
             v
   reports/evaluation/opportunity_engine_shadow/<day>/*
   (never reaches the Alpha Research Board)
```

They never merge and never split from a common node today — Q11 simply
never connects to the live chain at all, while Opening Alpha is fully
embedded in it from Scanner through Monitor through Executor through to
its own dedicated evaluation/reporting stack.

---

## 24. Potential target diagram (conceptual only — not recommended for or against here)

If a future Option-C-style shared engine were pursued, and if Strategist's
4 categorical horizons were added as a genuine grouping dimension
alongside (not replacing) the existing 5 fixed-time buckets, the shape
might look like this. This is **conceptual only**; this review does not
recommend implementing it, only shows what it would look like if
pursued, per the "do not force a fit against the actual investigation
findings" instruction:

```
Strategist
  |
  ├─ market context (still unused by both programs' eligibility logic)
  └─ strategy_horizon (4 categories) ──────────────┐
                                                     │ grouping dimension only,
                                                     │ never an eligibility input
                                                     v
Scanner (live rank-1)              Q11 (independent, fixed universe)
        |                                    |
        v                                    v
Monitor entry evaluation          Q11 own signal/entry engine
        |                                    |
        v                                    v
Opening Alpha bounded override      +-------------------------+
        |                           | SHARED forward-validation |
        v                           |   engine (Option C):      |
   mock broker execution   ───────► |   +5m/+15m/+30m/+60m/EOD  |
        |                          |   checkpoint computation,  |
        v                          |   grouped optionally by    |
  opening evaluation layers  ────► |   strategy_horizon cell    |
        |                          +-------------------------+
        v                                    |
  Alpha Research Board            reports (each program keeps
                                    its own PROGRAM_ID/COHORT_ID)
```

Both programs would keep their own candidate source, entry model, and
runtime posture; only the checkpoint math would be shared, and
Strategist's categorical horizon would become an optional grouping key
rather than a new axis conflated with the existing one.

---

## 25. Files reviewed (primary)

```
libs/research/opportunity_engine/contracts.py
libs/research/opportunity_engine/pipeline.py
libs/research/opportunity_engine/simulator.py
libs/research/opportunity_engine/report.py
libs/research/opportunity_engine/data_provider.py
libs/runtime/opening_rank1_controlled_probe.py
libs/runtime/opening_rank1_probe_discriminator.py
libs/runtime/opening_rank1_probe_cost_edge.py
libs/reporting/opening_rank1_shadow/contracts.py
libs/reporting/opening_rank1_shadow/episodes.py
libs/reporting/short_alpha_discriminator/contracts.py
libs/reporting/short_alpha_discriminator/opening_policy_matrix.py
libs/reporting/short_alpha_discriminator/cohorts.py
libs/reporting/short_alpha_discriminator/metrics.py
libs/reporting/alpha_research_board/canonical.py
libs/reporting/alpha_research_board/builder.py
libs/runtime/strategy_horizon_feedback.py
graphs/nodes/strategist_node.py
libs/strategies/contracts.py
reports/evaluation/opportunity_engine_shadow/2026-09-07..2026-09-11/*
reports/evaluation/opening_rank1_shadow/opening_rank1_shadow_cumulative.json
docs/q13_q14_validation/*.md
docs/evaluation/opportunity_engine_shadow_plan.md
docs/evaluation/current_operating_baseline.md
docs/evaluation/controlled_mock_four_lane_execution_2026-08-28.md
docs/daily_patch/2026-08-21_q10_q11_q13_measurement_integrity.md
docs/daily_patch/2026-09-*_opening_alpha_*.md
```

No file was moved, deleted, or edited in the course of this review.

---

## 26. What was explicitly not done

No code modification, no threshold change, no runtime change, no prompt
change, no Q11/Opening Alpha integration implementation, no file
rename/delete, no commit, no push, no live restart, no production-state
change.
