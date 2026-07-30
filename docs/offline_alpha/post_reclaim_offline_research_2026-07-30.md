# Post-Reclaim Offline Alpha Research

Date: 2026-07-30

## Scope

This is the first offline alpha reconstruction after Q18 closure.

Target:

`confirmed_post_reclaim_pullback`

Range:

`2026-06-01` through `2026-07-30`

Behavior boundary:

- research only
- no Scanner change
- no Strategist change
- no Commander change
- no Monitor change
- no entry or exit change
- no order or execution path

## Reproduction

The offline extractor reproduced the fixed Q18 population exactly.

| Measure | Result |
| --- | ---: |
| Raw candidate rows | 80 |
| Canonically deduplicated rows | 36 |
| Independent 15-minute episodes | 35 |
| Episode days | 21 |
| Distinct symbols | 18 |
| Largest single-day share | 11.43% |
| Largest single-symbol share | 22.86% |

The historical minute provider used paginated Kiwoom `ka10080` reads.

- symbols requested: 18
- symbols with required historical coverage: 18
- all 35 episodes have a reconstructed price path
- cache: `data/research/post_reclaim_alpha/minute_cache`

## Cost-Adjusted Results

Primary deployment assumption:

- live cost and slippage: 0.28%
- mock observed cost: 1.086849%

| Horizon | Observed | Coverage | Gross Avg | Live Net Avg | Live PF | Live MDD | Avg MFE | Avg MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| +5m | 32/35 | 91.43% | +0.3159% | +0.0359% | 1.1243 | -4.4721% | +0.7793% | -0.6608% |
| +15m | 31/35 | 88.57% | +0.4131% | +0.1331% | 1.3060 | -5.0993% | +1.2334% | -0.8083% |
| +30m | 30/35 | 85.71% | +0.6092% | +0.3292% | 1.9656 | -4.4859% | +1.5300% | -0.9555% |
| +60m | 29/35 | 82.86% | +0.3881% | +0.1081% | 1.1505 | -9.4163% | +2.0680% | -1.4636% |
| EOD | 35/35 | 100.00% | -0.2422% | -0.5222% | 0.6563 | -26.7176% | +3.0030% | -2.6953% |

Same 21 episode-day Scanner Rank 1 baseline at +30m:

| Measure | Post-Reclaim | Scanner Rank 1 |
| --- | ---: | ---: |
| Observed count | 30 | 165 |
| Live-net expectancy | +0.3292% | -0.3601% |
| Profit factor | 1.9656 | 0.4385 |
| Win rate | 56.67% | 31.52% |

The +30m positive-day ratio is 68.42%.

## Fixed-Gate Result

Performance gates:

- +15m live expectancy positive: pass
- +30m live expectancy positive: pass
- +30m live profit factor at least 1.20: pass
- +30m positive-day ratio at least 60%: pass
- +30m MDD no worse than -6.0%: pass
- better than Scanner Rank 1: pass

Evidence gates:

- episode count: pass
- day count: pass
- symbol count: pass
- day concentration: pass
- symbol concentration: pass
- +30m forward coverage at least 90%: fail at 85.71%

Five +30m checkpoints exceeded the predeclared 180-second maximum observation
delay because the symbols did not print a new minute trade close near the target
time. The threshold is not changed after seeing the result.

## Decision

`RETAIN_SHADOW`

This is not a failed hypothesis. It is a statistically promising tactical
holding-window candidate that misses one fixed evidence requirement.

The reconstructed shape is specific:

- weak but positive after live costs at +5m
- strongest at +30m
- still positive at +60m, with materially worse drawdown
- clearly negative at EOD

Therefore the evidence supports continued research on a bounded intraday
post-reclaim hold, not an EOD hold and not a broad VWAP-entry relaxation.

## Reproduction Command

```powershell
venv\Scripts\python.exe scripts\run_post_reclaim_offline_research.py --max-pages 24
```

Cached replay without API calls:

```powershell
venv\Scripts\python.exe scripts\run_post_reclaim_offline_research.py --no-fetch
```
