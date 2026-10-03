# Stage 3 Horizon Lineage

Date: 2026-08-27

Status: OBSERVABILITY ONLY

## Purpose

Stage 3 had separate prompt, response, horizon-state, and Monitor artifacts, but
there was no canonical record proving that one review traveled through the
entire runtime chain. This made `tighten_exit`, `exit_now`, and horizon revision
effectiveness impossible to distinguish from Monitor's independent exit rules.

## Additive Artifact

Each relevant open-position run can now write:

```text
reports/canonical/YYYY-MM-DD/<run_id>/stage3_horizon_lineage.json
```

The artifact records:

1. scheduling assessment and review-due state
2. invocation requested or skipped, including the skip reason
3. held target symbol and refresh trigger
4. normalized Stage 3 response
5. Commander application decision
6. active horizon and hold window before and after application
7. whether an exit advisory was forwarded
8. the active horizon actually consumed by Monitor
9. target and adoption consistency issues

## Authority Boundary

This patch does not change trading behavior.

- `tighten_exit`, `exit_now`, and `request_exit` remain advisory.
- No SELL intent is created from Stage 3.
- Existing Commander horizon approval rules are unchanged.
- Existing Monitor and hard-exit rules are unchanged.
- The lineage explicitly emits `exit_advisory_not_forwarded` when that boundary
  is encountered, so reports cannot mistake advice for an applied exit action.

## Historical Boundary

- 489 legacy Stage 3 responses exist across 36 days from 2026-05-11 through
  2026-07-20.
- 486 responses completed successfully.
- Decisions were 326 `tighten_exit`, 70 `wait_until_next_check`, 52 `hold`, and
  38 `exit_now`; three responses had no usable decision.
- The current mutable horizon response contract was introduced after those
  calls. None of the legacy responses contains `horizon_action`,
  `evidence_confidence`, or `data_quality`.
- No post-contract live Stage 3 call has yet been observed because no new held
  position reached the review path.

Legacy responses therefore remain advisory evidence and must not be treated as
causal validation of the current Stage 3 horizon behavior.

## Verification

- deterministic full-lineage artifact test
- explicit cooldown skip-reason test
- explicit unforwarded exit-advisory test
- integrated Commander test:

```text
pre-entry Monitor sweep
-> Stage 3 due
-> Strategist call
-> Commander horizon revision
-> Scanner continuation
-> Monitor consumes revised active horizon
```
