# Controlled Mock Four-Lane Execution

Date: 2026-08-28

## Decision

Four independent validation lanes may submit real orders to the Kiwoom mock
broker. Each lane has a separate one-order-attempt daily limit. The aggregate
maximum is four attempts per trading day, subject to the existing portfolio
maximum of three simultaneous positions.

This is mock execution validation. It does not convert an experimental result
into official production policy.

| Lane | Selection authority | Daily limit |
| --- | --- | ---: |
| Opening Alpha | Existing Strategist, Scanner, Commander and Monitor chain | 1 |
| BTC-Woori | Fixed Q12 five-variable signal | 1 |
| Q10 Semiconductor | Fixed lead-market signal plus local response | 1 |
| Q10 Index | Fixed lead-market signal plus local index response | 1 |

## Opening Alpha

Opening Alpha does not inject a symbol. It only evaluates the final candidate
produced by the existing multi-agent chain.

The candidate must be the same symbol as the pre-Strategist intrinsic Scanner
Rank-1 and satisfy one condition:

- `HIGH_COMMON_DIRECTIONAL`: common stock, Scanner risk score at least `0.7`,
  and `DIRECTIONAL_BREADTH`; or
- `CONFIRMED_RECURRENT_RANK`: the same Rank-1 appeared during the prior five
  minutes and the latest completed one-minute return is positive.

Only the bounded Monitor WAIT/blocker set already owned by the controlled
opening probe can be overridden. Cost evidence with a real negative result,
chart hard floor, risk-off policy, position/order guards, intrinsic Rank-1
mismatch and same-day re-entry remain hard blocks. Quantity remains 25% of the
normal calculated quantity with a one-share practical minimum.

## BTC-Woori

The Q12 lane submits `041190` only when every fixed condition passes:

1. Point-in-time BTC 24-hour return at 08:55 KST is at least `+4%`.
2. Surge state is `FIRST_SURGE`.
3. BTC is in a `20D`, `60D` or all-time-high breakout state.
4. Woori opening gap is below `+10%`.
5. A fresh 09:03 or 09:05 local price/volume confirmation is present.

The signal must be no older than seven minutes and can execute only from 09:03
through 09:30 KST. Quantity is one share.

## Q10 Semiconductor

The Q10 lead-market snapshot must have been captured inside the immutable 08:50
window. A long order is allowed only when:

- Samsung Electronics or SK Hynix has a positive/strong-positive lead signal;
- confidence is `MEDIUM` or `HIGH`;
- a fresh 09:03, 09:05 or 09:10 Korean-market price is above its opening price;
- Samsung-specific event observations are excluded from the pure lead-market
  lane.

The strongest confirmed symbol is selected. `EXTENDED` SK Hynix is penalized in
the lane score but remains observable. Quantity is one share and the entry
window ends at 10:00 KST.

## Q10 Index

The same immutable 08:50 lead-market snapshot produces the Korean index state.
The actual KOSPI or KOSDAQ checkpoint must move in the expected direction. The
strongest aligned index is mapped as follows:

| Target | Direction | Product |
| --- | --- | --- |
| KOSPI | up | `069500` KODEX 200 |
| KOSPI | down | `114800` KODEX Inverse |
| KOSDAQ | up | `229200` KODEX KOSDAQ150 |
| KOSDAQ | down | `251340` KODEX KOSDAQ150 Futures Inverse |

`252670` is not used because historical broker truth contains Kiwoom mock
restriction `RC4007`. Any new symbol-specific rejection is persisted by the
existing restricted-symbol mechanism. Quantity is one share and the entry
window ends at 10:00 KST.

## Shared Safety And Attribution

- `KIWOOM_MODE=mock` and `EXECUTION_MODE=real` are both required.
- Existing Monitor BUY/SELL intents always have priority.
- Q9 P/A/B/C snapshots are written before independent-lane intent injection.
- Existing maximum positions, pending-order, held-symbol, broker restriction,
  and same-symbol loss re-entry controls remain active.
- Independent lanes use the existing OrderIntent, Decision, Executor, broker
  truth, lifecycle and report path.
- Q10/Q12 positions store an independent `intraday` horizon snapshot and do not
  inherit the current Strategist output.
- Stage 3 LLM horizon revision is disabled for Q10/Q12 controlled positions.
- Daily reservations are attempts. A broker rejection still consumes that
  lane's daily limit and remains evidence.

## Artifacts

- Opening submissions:
  `data/logs/opening_rank1_controlled_probe/YYYY-MM-DD/probe_submissions.json`
- Opening Rank-1 recurrence observations:
  `data/logs/opening_alpha_rank_observations/YYYY-MM-DD/rank1_observations.json`
- Independent lane submissions:
  `data/logs/controlled_mock_lanes/YYYY-MM-DD/lane_submissions.json`
- Entry intent metadata:
  `controlled_mock_lane` or `opening_rank1_controlled_probe`

## Rollback

Disable independent lanes with `CONTROLLED_MOCK_LANES_ENABLED=false`. Disable
Opening Alpha with `OPENING_RANK1_CONTROLLED_PROBE_ENABLED=false`.

Immediate rollback is required for real-broker exposure, more than one attempt
per lane/day, position-limit bypass, missing provenance, or a controlled position
inheriting an unrelated Strategist horizon.
