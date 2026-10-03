# Alpha Research Board v2 Contract - 2026-08-27

## Authority

The Alpha Research Board is the sole research authority for daily closeout
explanations. Q8-Q18, offline-alpha reports, horizon reports, agent
attribution, and baseline reports are evidence suppliers only.

This contract changes reporting and observability only. It cannot change
Scanner, Strategist, Monitor, Commander, order, entry, or exit behavior.

## Frozen Questions

| ID | Question |
|---|---|
| A | What separates successful and failed opening Rank-1 candidates? |
| B | Under which conditions does strong BTC momentum lead Woori Technology Investment? |
| C | Why do common stocks and ETFs diverge when Scanner risk is HIGH? |

No fourth question or new Q phase may be introduced by closeout.

## Frozen Candidate Registry

The registry is defined in
`libs/reporting/alpha_research_board/contracts.py`.

- A: 9 candidates
- B: 2 candidates
- C: 3 candidates
- total: 14 candidates

Closeout can update evidence on these rows. It cannot create, rename, or
silently remove a candidate.

## Frozen Row Contract

Each candidate has exactly these columns:

`question_id`, `candidate_id`, `status`, `hypothesis`,
`feature_evidence`, `target_horizon`, `historical_evidence`,
`prospective_evidence`, `sample_quality`, `concentration`,
`net_metrics`, `agent_attribution`, `decision`, `rationale`,
`next_action`, `source_artifacts`, `updated_through_day`.

The feature surface is also fixed:

`market_regime`, `asset_class`, `rank_and_selection`,
`price_structure`, `volume_and_flow`, `external_signal`,
`agent_lineage`, `horizon_and_exit`, `cost_and_quality`.

New observations are values inside these feature columns. They do not create a
new evaluation axis or table column.

## Evidence Separation

- Historical discovery and prospective evidence are separate columns.
- The Board never sums their sample counts.
- `net_metrics.cohort` identifies which cohort supplies the displayed current
  metric.
- Source artifacts remain traceable from every row.
- Existing evaluation calculations are not recomputed by the Board.

## Status Contract

Allowed statuses:

- `DISCOVERY`
- `PROSPECTIVE`
- `REVIEW_READY`
- `PROMOTED`
- `REJECTED`
- `CLOSED`

Terminal research candidates are accumulated as `CLOSED`. A CLOSED candidate
cannot be reopened by changing thresholds, renaming it, or creating an
equivalent row.

## Closeout Integration

Board generation is the final step of
`write_closeout_maintenance_report()`, after Q9 refresh and final artifact
inventory refresh.

Board failure is nonfatal to the trading runtime and other closeout work. The
failure is recorded as `alpha_research_board_final`.

Outputs:

- `reports/evaluation/alpha_research_board/YYYY-MM-DD/alpha_research_board.json`
- `reports/evaluation/alpha_research_board/YYYY-MM-DD/alpha_research_board.md`
- `reports/evaluation/alpha_research_board/latest.json`
- `reports/evaluation/alpha_research_board/latest.md`

Daily human explanations must use the Board JSON or Markdown only. Supporting
evaluation artifacts can be opened to debug provenance, but they cannot supply
an independent closeout conclusion.

## 2026-08-27 Baseline

- schema: `alpha_research_board.v2`
- integrity: `PASS`
- candidate count: 14
- A: 9 candidates
- B: 2 candidates
- C: 3 candidates
- historical/prospective separation: verified
- behavior change authorized: false

From this baseline forward, the table structure remains fixed. Only rows,
samples, metrics, evidence values, and status transitions accumulate.
