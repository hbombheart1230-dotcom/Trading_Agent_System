# 2026-09-07 Q10, VWAP, and Opening Alpha Integrity

## Scope

This correction fixes evidence routing and report attribution. It does not change
Scanner ranking, Q10 eligibility, normal cost thresholds, or horizon policy.

## Confirmed Defects

1. Opening Alpha recognized `CONFIRMED_RECURRENT_RANK`, but the missing-cost
   fallback looked up evidence by candidate setup only. A recurrent Rank-1 with
   an unclassified or liquidity setup could therefore be rejected even though
   the controlled lane itself had approved evidence.
2. Monitor exit accepted `engine_vwap_distance` as an intraday VWAP input. That
   feature can represent a daily or historical feature-engine window and is not
   valid evidence of a current-session VWAP break.
3. Q10 trades were reported through the main Scanner template, producing rank 0
   and a negative scanner-to-entry delay when the independent Q10 entry preceded
   the next main Scanner decision window.
4. The post-exit recap was complete, but regenerated Q10 summaries did not retain
   the controlled-lane identity needed to explain the result correctly.

## Corrections

- `CONFIRMED_RECURRENT_RANK` resolves its own frozen lane evidence only when the
  normal cost filter failed solely because directional/gross evidence was
  missing. Any explicit negative cost result remains a hard block.
- Intraday VWAP exits now use explicit current-session minute VWAP or a
  deterministic current-session OHLCV/volume-derived VWAP. Daily feature-engine
  VWAP distance is rejected with provenance instead of becoming an exit input.
- Controlled-lane report recovery requires an exact entry order ID or entry run
  ID match. Same-symbol matching alone is prohibited.
- Q10/Q12 controlled trades report Scanner rank as not applicable. Entry timing
  uses the lane signal epoch, while Scanner and Strategist delays remain null.
- Batch regeneration restores the controlled-lane surface before report
  generation and merges the richest post-exit recap afterward.

## 2026-09-07 Q10 Case

| Field | Value |
| --- | --- |
| Symbol | 000660 SK Hynix |
| Lane | Q10 Semiconductor |
| Signal | POSITIVE / HIGH confidence / OVERREACTION / FIRST_MOVE |
| Signal checkpoint | 09:10 KST |
| Entry | 09:11 KST at 1,749,500 |
| Lane-to-entry delay | 60 seconds |
| Actual result | -1.27% broker realized return including costs |
| +5m from entry | -0.1429% |
| +15m from entry | -0.3144% |
| +30m from entry | -0.6002% |
| +60m from entry | -0.4287% |
| EOD from entry | approximately +1.91% gross |
| Post-exit EOD | +2.29% from the actual exit price |

The Q10 immediate-continuation path was weak through 60 minutes. The stock later
recovered into the close. The actual exit used an invalid daily-feature VWAP
distance of about -11.6%, while current-session chart evidence was near or above
VWAP. This is classified as a confirmed execution-input defect, not clean
evidence for changing Q10 entry policy.

The controlled Q10 lane intentionally freezes R3 horizon revision. Therefore
this case is not evidence that R3 made a bad decision. One repaired case is also
insufficient to promote EOD holding. Q10 entry continuation and fixed-horizon
performance remain evaluation-only after excluding the invalid exit decision.

## Regression Contract

- A recurrent Rank-1 can use lane evidence despite an unrelated setup label.
- Explicit negative cost evidence still blocks the recurrent lane.
- A daily `engine_vwap_distance` cannot trigger intraday VWAP liquidation.
- A valid current-session VWAP breakdown can still trigger the existing exit.
- Q10 exact order attribution yields Scanner rank N/A and non-negative lane
  timing.
- Post-exit EOD evidence remains visible after deterministic regeneration.
