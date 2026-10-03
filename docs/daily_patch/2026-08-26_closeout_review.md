# 2026-08-26 Closeout Review

## Runtime Integrity

- Q9 day validity: `VALID`, formal day: `true`
- Q9 windows: 481 (`09:00:13` through `15:29:54` KST)
- Forward coverage: 99.18%
- Real trades: 0
- Runtime and Q10/Q11/Q12 stderr: empty
- Closeout artifacts completed at 16:02 KST

The day is valid for no-trade and forward-opportunity analysis. Repeated windows
are not independent trades and must not be interpreted as 481 samples.

## Decision Funnel

| Stage | Result |
| --- | ---: |
| Commander reject | 401 |
| Commander approve | 52 |
| Commander noop | 27 |
| Commander retry scan | 1 |
| Monitor BUY | 0 |
| Monitor NOOP | 481 |

Commander rejection was dominated by `risk_too_high` (391). All 52 approved
windows were subsequently held by Monitor. Monitor NOOP was dominated by
`pullback_not_mature` (241), `below_vwap_reclaim_not_ready` (128),
`cost_adjusted_edge_not_ready` (35), and `volume_confirmation_missing` (28).

Scanner Top-1 was concentrated in `233740` (215 windows) and `252670` (170
windows), together 80.0% of the 481 windows. These repeated leveraged/inverse
ETF windows are a concentration diagnostic, not independent opportunities.

## Scanner Forward Shape

The table uses the stated live-equity round-trip cost basis.

| Horizon | Top-1 | Top-3 | Top-5 | Top-10 |
| --- | ---: | ---: | ---: | ---: |
| +15m | -0.3840% | -0.1374% | -0.0225% | -0.0100% |
| +30m | -0.7694% | -0.2421% | -0.1230% | -0.1730% |
| EOD | +0.4198% | +0.5062% | +0.1533% | -0.0163% |

The Scanner cohort was weak at short horizons but stronger at EOD, especially
Top-1/Top-3. This does not authorize longer holding because the windows are
highly repeated and concentrated. It does identify a horizon mismatch worth
continued observation: the candidate set had directional value later in the
day while the live entry path required an intraday mature pullback.

## Opening Rank-1 Episodes

| Symbol | Name | +5m live net | +30m live net | +60m live net | EOD live net |
| --- | --- | ---: | ---: | ---: | ---: |
| 034020 | Doosan Enerbility | -0.2800% | +0.8096% | +1.7781% | +3.5941% |
| 010640 | Jinyang Poly | -18.0827% | -20.8181% | -21.3114% | -21.2217% |
| 233740 | KODEX KOSDAQ150 Leverage | -1.2659% | -1.1955% | -1.6180% | unavailable |

The positive 034020 episode and catastrophic 010640 episode demonstrate why
blanket Rank-1 entry is invalid. The required discriminator must separate a
liquid directional leader from a single-name opening collapse before any
opening behavior patch is allowed.

`IMMEDIATE_OPENING_PROBE` remains `COLLECTING`: 3 of 5 fixed sessions are
available. No behavior promotion is authorized.

## Q10 / Q11 / Q12

- Q10 Samsung/Hynix Top-1: short horizons were negative after mock cost. The
  best observed horizon was +180m (WR 60.0%, avg +0.2225%, PF 1.4283), while
  EOD was -1.6291%. This supports horizon-specific evaluation, not blanket hold.
- Q11 opening probe: two virtual trades, both net losses; average net -1.4212%,
  average MFE +0.8011%, average MAE -0.4409%. The move did not overcome mock
  friction.
- Q12 base: five shadow entries. Short horizons were negative; EOD was barely
  positive at +0.0357% (WR 60.0%, PF 1.1638).
- Q12 persistent-trend variant: 72 prospective decisions, zero entries. Recent
  BTC state was 69 mixed, 2 accelerating, and 1 persistent. The strong recent
  BTC trend condition was false in all windows, so the new variant correctly
  remained inactive rather than manufacturing a signal.

## Cost Gate and No-Trade Assessment

Q16 remains `RETAIN`. On 2026-08-26, 39 exact proxy-only rejections produced
35 observed +30m outcomes with live-cost net WR 22.86%, average -0.9038%, and
PF 0.1076. Relaxing the cost/rejection control based on this day would have
made results worse.

Therefore today's zero-trade outcome was not an execution failure. The broad
defensive funnel avoided a poor short-horizon opportunity set. The opportunity
cost was concentrated in specific later-horizon cases such as 034020, not in a
broad population that justifies opening the gates.

## Measurement Findings

- Q9 forward coverage passed at 99.18%.
- Opening point-in-time market snapshot coverage remains low in the cumulative
  research board (20.7%, fresh within 300 seconds 17.2%), so promotion remains
  blocked.
- All three opening episodes lacked quote provenance in the Q9 compact
  snapshot. Scanner captured the new fields, but Q9's second compaction layer
  removed them.
- The Q9 live compactor and canonical repair compactor were updated additively
  to retain `quote_payload_available`, `quote_source`, and
  `quote_evidence_status` from the next session onward.
- Historical rows are not guessed or backfilled with future information; the
  2026-08-26 quote status remains honestly missing.

## Decision

1. Retain current cost and risk controls.
2. Do not promote blanket Rank-1 entry, global risk relaxation, or longer hold.
3. Continue the frozen `IMMEDIATE_OPENING_PROBE` prospective validation.
4. Continue Q12 persistent BTC trend as independent shadow only.
5. Use the next sessions to test the common-stock opening discriminator and
   fresh quote/market snapshot coverage. Do not add another evaluation axis.

