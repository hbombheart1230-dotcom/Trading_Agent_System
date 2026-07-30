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
