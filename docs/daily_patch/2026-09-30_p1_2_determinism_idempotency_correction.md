# 2026-09-30 — P1.2 Determinism and Idempotency Correction

## Scope

This bounded correction addresses the same-day Daily UEF duplicate-generation
incident. It changes neither trading behavior nor UEF-8/UEF-9 evaluation
semantics, and it does not repair or mutate the preserved 2026-09-30 evidence.

## Deterministic Alpha Board concentration labels

`_prospective_concentrations()` previously selected tied day or symbol maxima
through `Counter.most_common(1)` after set-derived iteration. A tied maximum
could therefore receive a different `largest_day` or `largest_symbol` under a
different Python hash seed. The selection is now canonical: count descending,
then key ascending. Counts, shares, populations, candidate IDs, and source
provenance are unchanged.

## Daily UEF pre-publication decision

After building the Alpha Board once and validating freshness, Daily UEF now
computes the deterministic Board identity and inspects verified COMPLETE
generations before UEF-7 begins:

- no COMPLETE generation: proceed;
- one COMPLETE with the same identity: return `ALREADY_COMPLETE` without
  UEF/pointer/registry writes;
- one COMPLETE with a different identity: fail closed with
  `CANONICAL_SOURCE_CONFLICT`;
- two or more verified COMPLETE generations: fail closed with
  `MULTIPLE_COMPLETE_CONFLICT`.

The preflight protects reruns before UEF-7, UEF-8, UEF-9, generation pointer,
or registry mutation. The two existing 2026-09-30 COMPLETE generations remain
preserved; a read-only invocation identifies them as
`MULTIPLE_COMPLETE_CONFLICT` with zero writes.

## Verification

Focused Alpha Board, UEF-7, and Daily UEF regression covers canonical tie
ordering, separate `PYTHONHASHSEED` replay, all four preflight outcomes, and
pointer/registry immutability on no-op and conflict results.
