# 2026-05-29 Weekend Preparation

## Final State

- Trading day: 2026-05-29 Friday
- Runtime stopped after close: yes
- Final account state: flat
- Latest account snapshot: `2026-05-29 16:04:53 KST`
- Broker/local reconciliation: ok
  - local executions: 17
  - broker rows: 17
  - matched by order number: 17
  - missing in local: 0
  - missing in broker: 0
- Daily summary regenerated after final account snapshot.

## Closeout Lesson

The 15:20 area can temporarily show stale residual positions.

On 2026-05-29, `005930` and `122630` looked like residual positions from the
15:27 account snapshot and stale daily summary. The later 16:04 Kiwoom account
snapshot confirmed both were sold and account positions were zero.

Patch applied:

- daily residual position reporting now checks the latest Kiwoom account
  snapshot
- only a same-day snapshot generated after 15:20 is trusted for closeout
  reconciliation
- if that fresh snapshot has no remaining position, stale state positions are
  excluded from residual holdings
- daily summary shows the account snapshot freshness line

Expected final summary line:

```text
account snapshot: fresh_after_1520 / positions 0 / 2026-05-29 16:04:53 KST
```

## Q8 Status

Live-trade evaluation is still sample-limited:

- closed/realized sample: 7
- invalid sample: 0
- missing required fields: none
- tactic mismatch: 0
- exit drift: 2
- live-trade readiness: `hold_sample_insufficient`

Shadow evaluation is ready:

- shadow payloads: 332
- shadow candidates: 908
- evaluated: 854
- evaluation ratio: 94.0%
- would-enter: 15
- Q8 shadow readiness: `ready`
- promotion candidate: `cost_edge`
- confidence: `medium`
- recommended action: `promote_shadow_validated_guard`

Current interpretation:

- keep cost-edge guard promoted
- do not claim live performance improvement yet
- use shadow evidence for pre-entry guard behavior only
- keep real PnL and exit-quality decisions on live trade samples

## Main Tactical Finding

The main issue is no longer data collection. The main issue is strategist lane
selection.

2026-05-29 summary:

- selected primary tactic: `vwap_reclaim_pullback`
- strategist lane quality: `weak_lane_selection`
- tactic performance: 7 trades, win 14.3%, average -0.33%
- overused lane/tactic: `vwap_reclaim_pullback`
- underused shadow lane: `breakout`
- pullback/vwap blocked: 681
- breakout ready-like: 26

Patch applied:

- strategist LLM compact payload now includes `tactic_lane_guidance`
- when `vwap_reclaim_pullback` is weak/overused, strategist must not default to
  it
- when breakout-ready shadow evidence exists, strategist must explicitly score
  `breakout` or `volume_breakout` against pullback before selecting the tactic
- cost-edge guard remains promoted when Q8 shadow readiness recommends it

Expected strategist directives:

```text
downweight_repeated_vwap_reclaim_pullback_unless_cost_volume_and_maturity_are_ready
explicitly_score_breakout_or_volume_breakout_against_pullback_before_selecting_tactic
do_not_default_to_late_pullback_when_shadow_breakout_ready_like_candidates_exist
```

## Weekend Tasks

1. Review 2026-05-29 trade reports.
   - `000660`: carryover/recovered sell handling
   - `005930`: closeout confirmed by 16:04 snapshot
   - `009150`: repeated loss, check entry lane and exit reason
   - `009830`: three repeated trades, check whether repeated same-symbol
     entries were justified
   - `122630`: closeout confirmed by 16:04 snapshot
   - `123860`: only clear win, compare setup against losers

2. Review exit drift.
   - Q8 shows exit drift trades: 2
   - This can blur the relationship between selected tactic and actual exit
     quality
   - Do not promote exit behavior until drift cause is understood

3. Review opening probe.
   - opening momentum would-probe: 0
   - opening largecap surge would-probe: 0
   - Need to decide whether this means no valid opening opportunities existed
     or probe thresholds are too strict

4. Keep cost-edge as-is.
   - Do not loosen it over the weekend
   - Monday review should check whether it blocked bad candidates or missed
     strong movers

5. Do not add another major strategy patch before Monday open.
   - The next observation target is whether strategist LLM actually changes
     lane selection after receiving Q8 lane guidance

## Monday Preopen Checklist

1. Start clean runtime.
2. Confirm no residual account positions.
3. Confirm `macro_indicators/YYYY-MM-DD/latest.json` is generated.
4. Confirm `quant_shadow_candidates/YYYY-MM-DD/latest.json` is generated after
   first monitor cycle.
5. Confirm strategist LLM payload contains `tactic_lane_guidance`.
6. Watch the first strategist output:
   - does it still default to `vwap_reclaim_pullback`?
   - does it compare `breakout` or `volume_breakout`?
   - does it preserve cost-edge?
7. After the first trade/report:
   - confirm broker/local alignment
   - confirm trade summary symbol metadata
   - confirm post-exit shadow recap scheduling

## Monday Success Criteria

- No stale residual-position warning after final account snapshot.
- Q8 shadow data continues to accumulate.
- Strategist no longer blindly repeats `vwap_reclaim_pullback`.
- If `vwap_reclaim_pullback` is selected, the rationale explicitly cites cost,
  volume, and pullback maturity readiness.
- If breakout-ready shadow evidence exists, strategist compares it against
  pullback before final tactic selection.
- Broker/local execution count remains aligned.

## Do Not Do Yet

- Do not promote opening momentum probe to live behavior.
- Do not promote largecap surge probe to live behavior.
- Do not change exit policy based only on the 7-trade live sample.
- Do not loosen cost-edge just to increase trade count.
- Do not add symbol-name penalties for Samsung/SK Hynix style concentration.
