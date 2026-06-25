# Q10 Samsung Electronics / SK Hynix Large-Cap Baseline Control

Evaluation program ID: `Q10_LARGECAP_BASELINE_CONTROL`

Q10 is an independent benchmark/control program running in parallel with Q9.
It is not the next execution phase after Q9 and does not modify Q9 behavior.

## Purpose

This module is an independent rule-based benchmark for:

- `005930.KS` Samsung Electronics
- `000660.KS` SK Hynix

It does not replace, modify, or participate in Q9 decisions.

## Isolation

- no LLM
- no Strategist
- no Commander
- no order execution
- shadow and evaluation artifacts only

The implementation lives under:

- `libs/reporting/baseline_samsung_hynix/`

The standalone entrypoint is:

```powershell
venv\Scripts\python.exe scripts\run_baseline_samsung_hynix.py --day YYYY-MM-DD
```

For independent five-minute collection:

```powershell
venv\Scripts\python.exe scripts\run_baseline_samsung_hynix.py --day YYYY-MM-DD --loop --interval-sec 300
```

This process is separate from the Q9 runtime. Stopping it cannot affect order
execution or the multi-agent pipeline.

## Strategy v0

Ranking:

- 5-minute price momentum
- current volume versus recent average

Entry conditions:

1. price is above VWAP or MA5
2. current volume ratio is at least `1.2`
3. KOSPI is not below `-2.0%`

Exit policy:

1. price falls below both VWAP and MA5
2. end of the regular session

The module records fixed `+5m`, `+15m`, `+30m`, and `EOD` forward returns. It
does not submit or simulate broker orders.

## Cost Model

The benchmark reads `data/state/broker_cost_profile.json` and applies the same
conservative round-trip cost used by Q9, plus the Q9 default evaluation
slippage of `0.05%`.

## Artifacts

Artifacts are written to:

`reports/evaluation/baseline_samsung_hynix/YYYY-MM-DD/`

- `baseline_samsung_hynix_decisions.json`
- `baseline_samsung_hynix_forward_returns.json`
- `baseline_samsung_hynix_daily_report.md`
- `q9_vs_samsung_hynix_daily_comparison.json`
- `q9_vs_samsung_hynix_daily_comparison.md`

The report compares:

- baseline Top-1
- equal average of both symbols
- Q9 P/A/B/C forward outcomes

The comparison is diagnostic. It does not authorize policy promotion or
changes to Q9.

The unified comparison uses cost-adjusted forward observations for:

- Q9 P: pre-Strategist universe
- Q9 A: Scanner control
- Q9 B: Strategist-ranked candidates
- Q9 C: Commander final candidates
- Samsung/Hynix baseline Top-1

For each horizon it reports observation count, win rate, average return,
profit factor, maximum drawdown, the best performer, and Commander-final alpha
over the baseline. If either side has no comparable observation, alpha remains
`INSUFFICIENT_EVIDENCE`.

The standalone comparison command is:

```powershell
venv\Scripts\python.exe scripts\run_q9_baseline_comparison.py --day YYYY-MM-DD
```
