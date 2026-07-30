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
