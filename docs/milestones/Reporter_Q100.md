# Reporter / Q100 (Alpha Research & Learning Program)

## Status

**DESIGN STAGE.** No code. Q100-1 through Q100-6 are fully defined as a
research-program design; execution against real canonical metrics is
blocked until UEF-3/UEF-4 exist to read from.

## Frozen Core

Nothing in this workstream is frozen. The Reporter role's own current
(non-Q100) responsibilities — reading the EventLog and producing reports/
improvement suggestions, with no control authority — are defined in
[`docs/ground_rules/AGENT_RULES.md`](../ground_rules/AGENT_RULES.md) §2
and remain unchanged.

## Current

Q100 design work (Research Program Registry, Canonical Evidence Mapping
schema, Reporter/Evaluator design, Knowledge & Memory Layer design,
Retrieval Layer design, Self-Improvement Loop design) proceeds in
parallel with UEF, per
[`docs/en/12_roadmap.md`](../en/12_roadmap.md) priority tier P4. Since
**UEF-3 and UEF-3B/3C are now frozen and UEF-4A (inventory) is complete**,
the "Q100 can only read from UEF canonical output once UEF-3/UEF-4 exist"
precondition is closer to satisfied than at the roadmap's last recorded
snapshot — but Q100 **execution** against live canonical metrics still
additionally requires UEF-4B (adapters) and, per priority tier P5, does
not begin before UEF-9's formal freeze.

## Next

UEF-4B (legacy adapters, see [[UEF]]) is the concrete precondition for
Q100 to move from design to real evidence-mapping work. No Q100
implementation should start ahead of that without revisiting this note.

## Non-negotiables (unchanged)

- **Q100 never recomputes UEF metrics** — its "Canonical Evidence
  Mapping" reads UEF canonical output; it never implements a parallel
  forward-return or cost engine (roadmap prohibition principle 4).
- **No production strategy auto-modification** — the Self-Improvement
  Loop is explicitly capped at maturity Level 4-5 for the foreseeable
  planning horizon; Level 6-7 (autonomous production strategy edits) is
  out of scope for every track (roadmap prohibition principle 7).

## Authority Documents

- [`docs/research/q100_research_and_learning_roadmap.md`](../research/q100_research_and_learning_roadmap.md) — the full Q100-1..Q100-6 design
- [`docs/en/12_roadmap.md`](../en/12_roadmap.md) `### Track C` — current position and dependency graph
- Reporter's own prior evolution history: [`docs/report_plan/`](../report_plan/), [`docs/report_upgrade_plan/`](../report_upgrade_plan/), [`docs/trade_report_plan/`](../trade_report_plan/)

## Related

- [[UEF]] — the canonical evaluation output Q100 depends on and never duplicates
- [[Evidence Memory]] — Q100-4/Q100-5 read/write the Knowledge/Memory layer under their own namespace
- [[Strategy Program Integration]] — Q100's research-program registry must respect the same no-silent-promotion rule
