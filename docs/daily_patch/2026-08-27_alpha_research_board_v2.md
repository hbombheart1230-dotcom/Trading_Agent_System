# 2026-08-27 Alpha Research Board v2

## Scope

- reporting and observability only
- no trading behavior changes
- no agent prompt or authority changes

## Changes

- froze the Board to top-level questions A/B/C
- froze 14 candidate IDs
- froze row and feature columns
- separated historical and prospective evidence
- added Stage-2 Strategist effectiveness as an A evidence row
- added the liquidity-only negative control as a C evidence row
- retained terminal candidates as CLOSED
- replaced the unreadable main Board Markdown renderer
- added dated and latest Board outputs
- connected Board generation to the final closeout reporting step

## Baseline Result

The 2026-08-27 rebuild produced:

- schema `alpha_research_board.v2`
- integrity `PASS`
- 14 candidates
- A 9 / B 2 / C 3
- no missing source
- no row-column mismatch
- historical/prospective separation verified

## Operational Rule

All future closeout research explanations use the Alpha Research Board only.
Underlying evaluation reports remain traceable inputs and do not publish a
separate operational conclusion.
