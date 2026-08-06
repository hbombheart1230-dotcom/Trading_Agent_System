# Opening Rank-1 Longitudinal Review

## Purpose

This review tests two separate claims.

1. The Scanner often identified the right symbol, but a later stage failed to
   preserve or execute it.
2. A symbol that looked weak over the first 30 minutes sometimes rallied on
   the next day or within several trading days.

This is offline research only. It does not change Scanner, Strategist,
Monitor, Commander, entry, exit, or order behavior.

## Evidence

- Opening pre-Strategist intrinsic Rank-1 decisions: 65
- Deduplicated Rank-1 symbol-day events: 60
- Rank-1 events with complete D+5 observation: 51
- Same-decision Top-1 through Top-10 candidate paths: 352
- Candidate paths with complete D+5 observation: 305
- Round-trip cost applied to every return: 0.28%
- Daily price authority: Kiwoom `ka10081`
- Intraday price authority: existing point-in-time minute cache

Repeated observations of the same symbol on the same day count once in the
longitudinal Rank-1 result. The candidate-universe control remains
decision-level so that Rank-1 can be compared with the alternatives available
at that exact decision.

## Data Integrity Correction

The first longitudinal pass used operator-summary directory names as a market
calendar. That directory set included a non-trading date and could treat a
missing symbol minute cache as the next trading day.

The authoritative calendar is now the union of dates returned by Kiwoom
`ka10081`. A missing required market day remains missing; the evaluator no
longer skips forward to the next available symbol observation.

After the correction, complete D+5 Rank-1 coverage increased from 22 to 51
events.

## Stage Fate

| Stage | N | Win rate | Average +30m | Median +30m | Profit factor |
|---|---:|---:|---:|---:|---:|
| Intrinsic Rank-1 | 65 | 61.54% | +0.7502% | +0.3546% | 1.7727 |
| Strategist-selected | 65 | 56.92% | +0.4518% | +0.3546% | 1.3925 |
| Monitor candidate | 64 | 57.81% | +0.5075% | +0.3590% | 1.4364 |

Paired within the same decision:

| Comparison | N | Mean delta | Improved | Degraded | Unchanged |
|---|---:|---:|---:|---:|---:|
| Strategist minus intrinsic Rank-1 | 65 | -0.2984%p | 9 | 15 | 41 |
| Monitor candidate minus intrinsic Rank-1 | 64 | -0.2606%p | 10 | 15 | 39 |

Interpretation:

- The intrinsic Rank-1 signal had measurable short-horizon value in this
  retrospective cohort.
- Strategist and Monitor changes did not add average +30m alpha in this
  cohort.
- This is not a causal production verdict. The cohort is selected, and only
  two executions can be linked by exact Q9 decision ID.
- Commander did not independently choose a symbol. It approved or rejected
  the Monitor candidate.

## Scanner Universe Control

| Rank bucket | D+5-complete N | +30m avg | D+5 high avg | D+5 close avg | Negative +30m that later reached +5% |
|---|---:|---:|---:|---:|---:|
| Rank-1 | 55 | +1.0233% | +14.4532% | -2.4310% | 9 / 20, 45.00% |
| Rank 2-3 | 95 | -0.0722% | +7.5947% | -6.7268% | 16 / 41, 39.02% |
| Rank 4-10 | 155 | +1.0117% | +9.9662% | -6.1791% | 28 / 72, 38.89% |

Matched by decision, Rank-1 minus the average of available lower-ranked
candidates:

| Horizon | Paired decisions | Mean delta | Rank-1 better | Rank-1 worse |
|---|---:|---:|---:|---:|
| +30m | 52 | +0.5356%p | 32 | 20 |
| D+5 maximum high | 52 | +7.0242%p | 28 | 24 |
| D+5 close | 52 | +4.2769%p | 28 | 24 |

This supports the user's observation that symbol selection was not random.
Rank-1 was better than its same-decision alternatives on average. It does not
support blindly holding Rank-1 for five days: Rank-1's absolute D+5 average
close was still -2.4310%.

## Delayed Rally Test

A delayed-high opportunity is defined as:

- +30m net return is non-positive, and
- the symbol reaches at least +5% net at a high within D+5.

A durable delayed confirmation is stricter:

- +30m net return is non-positive, and
- the D+5 close is at least +3% net.

Among 19 D+5-complete Rank-1 events with non-positive +30m:

- 8, or 42.11%, later reached a +5% high.
- Only 2, or 10.53%, closed D+5 at +3% or better.
- Only 25% of delayed-high cases retained the move through the D+5 close.
- Two of the eight delayed highs occurred by D+1.

| Day | Symbol | Name | +30m | D+1 high / close | D+3 high / close | D+5 high / close | Result |
|---|---|---|---:|---:|---:|---:|---|
| 2026-06-24 | 049800 | 우진플라임 | -0.45% | +3.83% / +2.09% | +3.89% / +3.25% | +7.94% / +3.89% | Durable |
| 2026-06-30 | 095610 | 테스 | -1.01% | +15.09% / +3.62% | +15.09% / -13.79% | +15.09% / -29.55% | High only |
| 2026-06-30 | 089030 | 테크윙 | -4.40% | +17.51% / +9.08% | +17.51% / -13.01% | +17.51% / -23.31% | High only |
| 2026-07-02 | 108320 | LX세미콘 | -2.03% | -1.66% / -2.16% | +1.35% / -2.03% | +5.10% / -6.03% | High only |
| 2026-07-07 | 052860 | 아이앤씨 | -3.82% | +0.52% / -7.81% | +4.40% / +3.37% | +7.03% / -0.39% | High only |
| 2026-07-08 | 084730 | 팅크웨어 | -1.39% | +0.67% / -2.34% | +3.99% / +1.46% | +5.89% / +5.57% | Durable |
| 2026-07-21 | 002140 | 고려산업 | -1.67% | -0.97% / -6.53% | +20.78% / +8.05% | +20.78% / -11.02% | High only |
| 2026-07-21 | 001130 | 대한제분 | -0.65% | +2.57% / +0.55% | +5.52% / +2.66% | +9.75% / +2.11% | High only |

The user's memory of later explosions is supported. The earlier conclusion
that it was only a few isolated symbols was too coarse. Eight of nineteen
initially losing Rank-1 events later printed a meaningful high. The stronger
claim that the system should simply hold them longer is not supported.

## Relationship To Opening Expansion

The immediate opening-expansion cohort and delayed-rally cohort are different.

| Feature | Immediate +30m >= +5% | Delayed +5% high after non-positive +30m |
|---|---:|---:|
| Cases | 3 | 8 |
| Average decision time after open | 6 seconds | 631 seconds |
| Average opening gap | +8.84% | +1.41% |
| Average entry vs prior close | +10.06% | +0.52% |
| Playbook | breakout 3 | pullback 5, defensive 3 |
| Path | immediate expansion 3 | immediate failure 6, early fade 2 |
| Average same-day close | +10.97% | -1.45% |
| Average D+5 close | +20.33% | -7.34% |

Immediate expansion cases:

- 2026-07-10 모나미
- 2026-07-15 모나미
- 2026-07-23 삼화전자

They were all recognized within 14 seconds of the open and framed as
`breakout`. Delayed-rally cases were mostly selected later and framed as
`pullback` or `defensive`.

Therefore the two cohorts share one broad property: the intrinsic Scanner
found symbols with future volatility and attention. They do not share a
single entry mechanism.

The likely architecture is:

1. Opening expansion lane: immediate continuation after a strong opening
   impulse.
2. Latent-attention lane: a selected symbol fails now but remains eligible for
   a fresh trigger on D+1 through D+5.

The second lane must not mean automatic multi-day holding. 테스, 테크윙, and
고려산업 show why: their later highs were large, but the gains subsequently
collapsed.

## What Is Proven

- Intrinsic Rank-1 had positive +30m expectancy in this cohort.
- Rank-1 outperformed same-decision lower-ranked candidates on matched average
  +30m, D+5 high, and D+5 close deltas.
- Downstream candidate changes reduced average +30m return in paired
  retrospective comparison.
- A material fraction of initially losing Rank-1 symbols later produced large
  intraday opportunities.
- Immediate opening expansion and delayed reactivation are separate patterns.

## What Is Not Proven

- That every intrinsic Rank-1 should be traded.
- That Strategist or Monitor should be bypassed.
- That Commander rejection was wrong. Commander evaluated the Monitor
  candidate and policy state, not a hypothetical Rank-1 trade in isolation.
- That holding a losing position for several days is profitable.
- That a D+5 maximum high can be captured without a new trigger.
- That the three immediate expansion cases define a stable production rule.

## Next Evidence To Collect

No execution behavior should be changed from this retrospective result alone.
Prospective observation should preserve two independent records.

Opening expansion:

- decision timestamp and first executable timestamp
- opening gap
- completed-bar volume only
- immediate continuation or failure
- +1m/+3m/+5m/+15m/+30m MFE and MAE

Latent attention:

- failed Rank-1 symbol remains on a research-only watch list for D+5
- daily close and next-day opening gap
- fresh volume expansion
- fresh VWAP or breakout reclaim
- time and return of reactivation
- no automatic carry and no order intent

Promotion must be evaluated separately. Combining these two mechanisms into
one rule would hide the signal that this analysis recovered.

## Reproduction

```powershell
.\venv\Scripts\python.exe scripts\run_opening_rank1_longitudinal.py
```

Generated artifacts:

- `reports/evaluation/offline_alpha/opening_rank1_longitudinal/opening_rank1_longitudinal.json`
- `reports/evaluation/offline_alpha/opening_rank1_longitudinal/opening_rank1_stage_fates.csv`
- `reports/evaluation/offline_alpha/opening_rank1_longitudinal/opening_rank1_longitudinal_events.csv`
- `reports/evaluation/offline_alpha/opening_rank1_longitudinal/opening_rank1_universe_control.csv`
- `reports/evaluation/offline_alpha/opening_rank1_longitudinal/opening_rank1_longitudinal.md`
