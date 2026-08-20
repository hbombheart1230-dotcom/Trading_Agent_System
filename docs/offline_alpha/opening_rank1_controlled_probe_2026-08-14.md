# Opening Rank-1 Controlled Probe

## Decision

- Decision date: 2026-08-14
- First eligible full trading day: 2026-08-17
- Status: `CONTROLLED_ADOPTION`
- Scope: Kiwoom mock broker only
- Official policy: no
- General Scanner, Strategist, Commander, Monitor, and exit behavior: unchanged

This is one bounded behavior experiment. It does not reopen or reverse the closed
five-session decision on broad opening Rank-1 entry. Broad, unconditional opening
entry remains rejected.

## Why This Narrow Experiment Exists

The fixed 2026-08-03 through 2026-08-07 sample rejected broad opening entry at
intraday horizons. Later cumulative evidence through 2026-08-14 reached 49 opening
Rank-1 episodes and became positive at +5m, +15m, and +30m, but still failed the
frozen promotion gate because symbol concentration and observed-day count were not
acceptable.

| Horizon | N | Win rate | Average live-net | Profit factor |
| --- | ---: | ---: | ---: | ---: |
| +5m | 49 | 40.8% | +0.2851% | 1.3896 |
| +15m | 49 | 49.0% | +0.7177% | 1.8333 |
| +30m | 49 | 51.0% | +0.9309% | 1.9547 |

The Rank-1 strategy/setup read model provides a narrower discriminator:

| Strategy/setup | N | +15m average live-net | +30m average live-net |
| --- | ---: | ---: | ---: |
| pullback / vwap_reclaim_pullback / DIRECTIONAL_BREADTH | 18 | +1.6660% | +1.4919% |
| pullback / vwap_reclaim_pullback / FRESH_CHANGE_ACTIVATION | 6 | +7.0757% | +4.8750% |
| pullback / vwap_reclaim_pullback / LIQUIDITY_ONLY | 8 | -0.7875% | -1.2637% |

This does not prove executable alpha. It is enough to justify a small mock-only
probe that measures the execution path directly without relaxing the whole system.

## Frozen Entry Contract

All conditions below are required:

1. Local time is 09:00 through 09:20 KST.
2. The final selected candidate is also the pre-Strategist intrinsic Scanner
   Rank-1. A final Rank-1 label alone is insufficient; the symbols must match.
3. Candidate setup is `DIRECTIONAL_BREADTH` or `FRESH_CHANGE_ACTIVATION`.
4. Kiwoom broker mode is `mock`.
5. The normal cost-adjusted edge filter passes, or it fails only because a
   directional/gross edge estimate is missing and the frozen setup-level net
   evidence defined below passes the same minimum net-return floor.
6. Chart hard-floor checks pass.
7. Existing position, pending order, max-position, cooldown, closeout, and carry
   guards pass.
8. Risk-off defensive policy does not block.
9. No non-overrideable quant blocker is present.
10. The same symbol was not already sold earlier that day.
11. No controlled probe has already been submitted that day.

The only overrideable evidence is:

- Monitor WAIT reasons for VWAP reclaim, pullback maturity, breakout readiness, or
  volume confirmation;
- quant blockers `volume_confirmation_missing` and
  `vwap_pullback_promoted_quality_gate`.

The following remain hard blocks:

- cost-edge failure backed by actual negative/below-floor evidence;
- cost drag above the configured ceiling, price/quantity evidence loss, or any
  non-missing cost failure;
- weak tactic suitability;
- chart hard-floor failure;
- same-symbol open or pending position;
- max positions, cooldown, closeout, or carry recovery;
- risk-off defensive block;
- any real-broker mode.

### 2026-08-18 Cost Evidence Correction

The first live validation showed that the general cost filter could not produce a
symbol-level directional edge estimate for otherwise eligible opening setups. Its
only failures were `directional_edge_evidence_missing` and
`estimated_gross_edge_missing`, so the probe was structurally unable to submit an
order. The original setup evidence was live-net after 0.28% round-trip drag, not
Q9 mock-net. Runtime fallback evidence therefore converts it to the frozen Q9 mock
drag of 1.036849%, including 0.05% evaluation slippage.

For this controlled mock probe only, the frozen 2026-08-14 setup evidence may
substitute for that missing estimate:

| Setup | Independent N | +15m live-net | +30m live-net | +15m mock-net | +30m mock-net | Conservative mock-net |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `DIRECTIONAL_BREADTH` | 18 | +1.6660% | +1.4919% | +0.8592% | +0.6851% | +0.6851% |
| `FRESH_CHANGE_ACTIVATION` | 6 | +7.0757% | +4.8750% | +6.2689% | +4.0682% | +4.0682% |

The fallback is not used when the normal filter reports an actual below-floor
edge, excessive cost drag, missing price/quantity, or any other failure. Commander
risk, chart hard floor, position/order guards, mock-only scope, one-probe daily
limit, and 25% sizing remain unchanged. Every use is recorded under
`cost_edge_evidence` in Monitor/intent provenance and the daily probe ledger.

### 2026-08-18 Selection Authority Correction

The historical opening evidence uses the pre-Strategist full-universe intrinsic
Rank-1 (`P_SCANNER_PRE_STRATEGIST_UNIVERSE_INTRINSIC_RANK1`). Runtime Monitor sees
the final strategy-weighted candidate. These are different cohorts even when both
rows carry `rank=1`.

The controlled probe now requires exact symbol equality between those two rows.
Missing intrinsic evidence or a symbol mismatch is a hard block and is recorded as
`intrinsic_rank1_evidence_missing` or `intrinsic_rank1_symbol_mismatch`. This gate
does not select, replace, or reorder any candidate; it only constrains probe
eligibility to the cohort that produced the frozen evidence.

## Sizing And Exit

- Maximum probes: one submitted intent per trading day.
- Size target: 25% of normal calculated quantity.
- Minimum practical size: one share when normal quantity is positive.
- Exit policy: unchanged.
- Horizon policy: unchanged.
- No new OrderIntent or executor path exists; Monitor uses its existing BUY intent.

The daily reservation ledger is:

`data/logs/opening_rank1_controlled_probe/YYYY-MM-DD/probe_submissions.json`

The probe contract and reservation are also attached to Monitor entry evidence and
the BUY intent metadata.

## Fixed Validation Window

- Duration: the next five complete trading sessions after the 2026-08-18 contract
  corrections.
- No automatic extension.
- If no eligible setup appears, close as `INSUFFICIENT_ELIGIBLE_SAMPLE`.
- If fewer than three broker-confirmed fills occur, close as
  `INSUFFICIENT_FILL_SAMPLE`.

Review actual fills and counterfactual +5m, +15m, +30m, and EOD returns using the
same mock cost/slippage assumptions already used by Q9 comparison surfaces.

Required review fields:

- candidate setup, Rank-1 score, and source;
- original Monitor WAIT and quant blocker;
- normal quantity and probe quantity;
- broker order/fill truth;
- actual realized mock-net return;
- +5m/+15m/+30m/EOD mock-net forward return;
- MFE, MAE, and exit reason;
- daily and symbol concentration.

## End Decision

The five-day review produces exactly one of these outcomes:

- `RETAIN_CONTROLLED`: at least three fills, positive +15m and +30m average
  mock-net return, profit factor at least 1.2 at either primary horizon, and no
  unresolved integrity issue.
- `REJECT`: sufficient fills but the return gates fail, or actual execution loss
  materially contradicts the forward evidence.
- `INSUFFICIENT_SAMPLE`: fewer than three fills or no eligible setup; do not tune
  thresholds from this result.
- `ROLLBACK`: real-mode exposure, daily-limit failure, hard-guard bypass, or
  evidence corruption.

No outcome automatically changes official trading policy. Any further promotion
must use the tactics promotion framework and select one behavior change only.

## Code Ownership

- Policy, setup classification, sizing cap, and daily ledger:
  `libs/runtime/opening_rank1_controlled_probe.py`
- Minimal integration point: `graphs/nodes/monitor_node.py`
- Contract tests: `tests/test_opening_rank1_controlled_probe.py`
