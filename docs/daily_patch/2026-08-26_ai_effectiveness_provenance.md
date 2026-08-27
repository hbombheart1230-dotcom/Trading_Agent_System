# AI Effectiveness Provenance Reinforcement

## Purpose

Strengthen the existing Strategist, memory, and Reporter-feedback evaluation
without changing trading behavior or creating another Q program.

## Added Evidence

### Strategist control eligibility

Each Scanner cycle now records whether its candidate universe was naturally
strategy-neutral. A cycle is eligible only when Kiwoom supplied the universe
and no Strategist source policy, theme filter, backfill, or scan-aggressiveness
expansion affected sourcing.

The existing same-universe intrinsic ranking control remains unchanged.
Eligibility does not claim alpha; it only says a valid neutral Scanner surface
was observed.

### Reporter feedback linkage

Reporter feedback packets receive a stable `feedback_id`. Strategist output
records whether the packet was available, consumed, blocked, and whether a
pre-LLM versus final frame change was observed.

Observed change is labeled as an adoption candidate. It is not attributed to
feedback causally until paired control and forward performance exist.

### Memory linkage

Daily, weekly, monthly, strategy, and symbol memory packets receive stable
content IDs in visibility/usage traces. Applied packet IDs are linked to the
Strategist run and then copied into the Q9 decision window.

The existing memory contamination cohorts remain authoritative. Packet IDs add
exact provenance and do not alter memory policy.

## Evaluation Output

`strategist_effectiveness.json` now reports eligible neutral-control counts and
waits for paired forward outcomes before permitting an economic claim.

`feedback_effectiveness.json` now consumes Q9 feedback provenance, reports
exposure and adoption-candidate counts, and keeps causal claims disabled.

## Behavior Boundary

- no Scanner sourcing or ranking change
- no Strategist prompt or model change
- no memory policy change
- no entry, exit, Commander, or execution change
- no additional market-data or LLM call

## Validation

- Python compilation passed for all changed runtime/evaluation modules.
- Targeted provenance, Q9 snapshot, feedback, memory explanation, and Scanner
  integration tests passed.
