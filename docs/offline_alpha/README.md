# Offline Alpha Research

This folder contains research that runs outside the live multi-agent trading
path.

Rules:

- no order execution
- no runtime behavior change
- fixed hypotheses and gates before outcome review
- historical minute reconstruction
- live and mock cost bases kept separate
- only evidence-ready candidates may move to controlled adoption

Current research:

- `post_reclaim_offline_research_2026-07-30.md`
  - target: `confirmed_post_reclaim_pullback`
  - result: `RETAIN_SHADOW`
  - performance gates passed
  - fixed +30m forward coverage gate failed at 85.71%

- `post_reclaim_executable_policy_v0_2026-07-30.md`
  - frozen policy: 12/15 pre-entry print density and +30m exit
  - train: June 2026
  - validation: July 2026
  - result: `REJECT`
  - no live behavior change

- `alpha_hypothesis_competition_v1_contract_2026-07-30.md`
  - frozen comparison contract for three independent hypotheses

- `alpha_hypothesis_competition_v1_result_2026-07-30.md`
  - 102/102 historical symbols complete
  - all three hypotheses rejected
  - no shadow or live integration

- `structural_alpha_batch1_contract_2026-07-30.md`
  - frozen contract for cross-sectional relative strength, sector leadership,
    and volatility contraction breakout
  - Q9 pre-Strategist Top 5 is the point-in-time universe

- `structural_alpha_batch1_result_2026-07-30.md`
  - H4 cross-sectional relative strength: rejected
  - H5 point-in-time sector leader: not testable with current historical
    artifacts
  - H6 volatility contraction breakout: rejected
  - no threshold tuning and no live or shadow integration

- `structural_alpha_batch2_contract_2026-07-30.md`
  - final frozen batch: market-shock reversal, oversold mean reversion, and
    trend pullback resumption

- `structural_alpha_batch2_result_2026-07-30.md`
  - H7, H8, and H9 rejected
  - no threshold tuning and no live or shadow integration

- `structural_alpha_search_closure_2026-07-30.md`
  - finite six-hypothesis search closed
  - zero eligible candidates, five rejects, one not testable

- `existing_evidence_mining_contract_2026-07-31.md`
  - fixed contract for exhausting retained Q9, quant-shadow, minute-cache, and
    actual-trade evidence before collecting another broad live window

- `existing_evidence_mining_result_2026-07-31.md`
  - 13,174 Q9 windows, 5,292 reconstructed episodes, 1,937 quant-shadow
    episodes, and 105 realized trades reviewed
  - entry uses the first minute candle strictly after the decision
  - broad captured candidate universe remains negative after 0.28% cost
  - one bounded discovery candidate retained:
    `OPEN_0_20_RANK1_30M`
  - candidate is future-confirmation-only; no runtime behavior change

- `opening_rank1_prospective_validation_2026-07-31.md`
  - freezes the prospective definition and decision gates for
    `OPEN_0_20_RANK1_30M`
  - first eligible day: 2026-08-03
  - minimum evidence: 25 observed episodes across at least 10 trading days
  - a pass authorizes controlled shadow review only
