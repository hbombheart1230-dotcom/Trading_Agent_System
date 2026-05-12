# Scanner / Monitor Role Boundary Patch Plan - 2026-05-11

## Purpose

This document fixes the intended boundary between Scanner and Monitor before a later code patch.

The main question is whether Scanner should also read chart details, even though Monitor already decides the actual entry timing. The answer is yes, but only as a soft ranking signal.

## Working Principle

Scanner selects which symbols are worth watching.

Monitor decides whether the selected symbol can actually be bought or sold now.

Therefore:

- Scanner may use chart context to rank candidates.
- Scanner must not become a second entry gate.
- Monitor remains the hard entry and exit decision engine.
- Any duplicated condition must have different authority:
  - Scanner: score adjustment only
  - Monitor: actionable gate or trigger

## Why Some Overlap Is Necessary

If Scanner ignores chart context completely, it can keep sending candidates that Monitor predictably blocks.

Examples:

- strong turnover but far below VWAP
- high volume but already overextended
- rank #1 by value but no breakout or reclaim readiness
- repeated Monitor block reason on the same symbol

That creates a runtime pattern where the system looks active but produces repeated NOOPs.

Scanner therefore needs a rough chart-fit layer that answers:

> Is this candidate likely worth Monitor attention?

It should not answer:

> Should we buy this candidate now?

## Current Code Direction

The current Scanner already has the right overall shape.

Relevant behavior:

- candidate pool is built from Kiwoom market sources
- each candidate receives `score_total`
- score includes turnover, volume, momentum, trend, intraday strength, theme, sentiment, rank score, and risk penalties
- `entry_compatibility_bias` checks rough Monitor-readiness using VWAP, volume readiness, breakout readiness, and overextension
- final ranking uses:

```text
score_total desc -> confidence desc -> risk_score asc
```

This is directionally correct because Monitor-readiness is already a score adjustment, not the final BUY decision.

## Patch Goal

Keep Scanner chart logic soft and visible.

Do not loosen Monitor gates just to increase trade count.

Instead, improve the quality of candidates sent to Monitor so the runtime spends less time on candidates that are strong in market ranking but structurally poor on the chart.

## Proposed Patch Scope

### 1. Make the role boundary explicit in code fields

Add or standardize Scanner output fields:

```json
{
  "scanner_chart_fit_score": 0.0,
  "scanner_chart_fit_components": {
    "vwap_location": 0.0,
    "overextension_risk": 0.0,
    "volume_readiness": 0.0,
    "breakout_readiness": 0.0,
    "reclaim_readiness": 0.0,
    "gap_context": 0.0
  },
  "scanner_chart_fit_authority": "soft_bias_only"
}
```

This separates Scanner chart-fit from Monitor entry gates.

The existing `entry_compatibility_score` can remain, but report and artifacts should describe it as "Monitor-readiness estimate", not as an entry approval.

### 2. Keep Scanner chart impact capped

Scanner chart-fit should only move rank within a controlled band.

Recommended cap:

```text
scanner_chart_fit_bias_cap = +/-0.05 to +/-0.08
```

Rationale:

- enough to move near-tie candidates
- not enough to override strong liquidity/trend/theme evidence
- prevents Scanner from becoming a hidden hard gate

The current `entry_compatibility_bias` already behaves close to this because it is derived from a bounded score and `bias_scale`.

### 3. Prevent duplicated hard gating

Scanner should not reject a normal equity candidate solely because:

- VWAP reclaim is not ready
- breakout is not ready
- volume confirmation is not ready
- pullback is still forming

Those belong to Monitor as hard gates.

Scanner may reduce score for those conditions, but final rejection should remain limited to true scanner-level exclusions:

- halted / abnormal symbol
- invalid asset class
- restricted mock-broker symbol
- impossible or empty market data
- hard commander risk rule
- explicit selection veto if commander policy enables it

### 4. Strategy-aware soft weighting

Strategist output should tune Scanner soft chart-fit, not force trades.

Examples:

| Strategist frame | Scanner soft effect |
|---|---|
| `breakout` | more weight on breakout readiness, volume surge, intraday strength |
| `pullback` | more weight on VWAP reclaim, shallow pullback, trend continuity |
| `leader` | more weight on trend, liquidity, theme leadership |
| `momentum` | more weight on return strength and volume expansion |
| `defensive` | more penalty for volatility, gap, overextension |

Monitor still decides the actual entry with its own hard path.

### 5. Make reports clearer

Scanner / Monitor explanation should use this wording:

- Scanner: "selected because it ranked highest after liquidity, trend, theme, and soft chart-fit scoring"
- Monitor: "entry approved/blocked because the actionable entry gate passed/failed"

Avoid wording that implies Scanner approved a buy.

Recommended report labels:

- `Scanner chart fit`: soft ranking context
- `Monitor entry decision`: actual BUY/NOOP decision
- `Monitor exit decision`: actual SELL/HOLD decision

### 6. Add tests around authority separation

Minimum tests for the later patch:

1. Candidate below VWAP is not removed by Scanner; it only receives lower chart-fit bias.
2. Candidate with strong scanner score can still rank #1 even with mild chart-fit penalty.
3. Near-tie candidates can flip when one has materially better chart-fit.
4. Monitor can still block Scanner rank #1 after Scanner selects it.
5. Report output does not call Scanner chart-fit an entry approval.

## Non-Goals

Do not add full human-style chart reading to Scanner.

The following should remain Monitor-side or later chart-context work:

- candle body / wick quality hard gates
- support/resistance zone confirmation
- breakout-retake-retest sequencing
- final entry timing
- stop loss / take profit / carry decision

Scanner may receive compact versions of those signals later, but only as soft ranking features.

## Recommended Patch Order

1. Rename and surface Scanner chart-fit fields without changing behavior.
2. Cap and trace `entry_compatibility_bias` more explicitly.
3. Update reports to separate Scanner soft chart-fit from Monitor hard gates.
4. Add authority-separation tests.
5. Only after observation, consider adding richer chart-fit components such as opening range, previous day high/low, and support/resistance distance.

## Decision

The architecture should remain:

```text
Strategist: defines market frame and tactical preference
Scanner: ranks candidates using market strength plus soft chart-fit
Monitor: makes hard entry/exit decisions
Commander: controls authority, capacity, risk, sequencing, and execution
```

This is the cleanest way to reduce repeated NOOPs without making Scanner and Monitor fight each other or silently double-block the same condition.
