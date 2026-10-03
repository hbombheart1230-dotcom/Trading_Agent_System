# UEF-8 — Fair Comparison Validation — Formal Freeze

Status: **FORMALLY FROZEN** (independent final closure audit: `CORE_VERDICT: APPROVE_UEF8`,
`UEF8_COMPLETE: YES`, `UEF8_FORMAL_FREEZE: YES`, CRITICAL 0, HIGH 0, MEDIUM 0, LOW 0). Not to be modified
again unless a reproducible correctness defect, a proven downstream contract contradiction, or an
execution/safety violation is discovered -- never for naming, refactor, performance polish, convenience
output, or new ranking ideas.

UEF-8 answers, given the frozen UEF-7 normalized Alpha Board: **"Can these two candidate rows be fairly
compared under the currently-proven evidence contract?"** It does **not** answer "which candidate is
better," "which strategy should win," or "which strategy should be promoted." Checkpoint commit:
`b91d926`.

## Closure lineage (summary)

1. First delivery: pairwise `COMPARABLE`/`CONDITIONAL`/`NOT_COMPARABLE` classifier over UEF-7's frozen
   normalized rows only -- `N*(N-1)/2` pair universe, hard scope blockers (question/horizon/cohort/metric
   availability), conditional fairness conditions (metric-availability mismatch, sample accounting, source
   overlap, population relation), deterministic reason ordering, no ranking of any kind.
2. Codex bounded correction (1 HIGH): individual UEF-7 `population_identity_status` proof on both sides
   (`DIRECT_POPULATION_IDENTITY_PROVEN`) was wrongly treated as sufficient to reach `COMPARABLE` --
   individual population proof does not establish the RELATION between two populations. Fixed:
   `POPULATION_RELATION_NOT_PROVEN` became unconditional for every pair, since the frozen
   `uef7.alpha_board_normalization.v1` schema exposes no pairwise population-relation field at all --
   `COMPARABLE_REACHABLE_WITH_CURRENT_UEF7_SCHEMA` became a schema-contract property (`NO`), not merely an
   observation about today's data.
3. Codex bounded correction (1 HIGH): `comparison_pair_id` used delimiter concatenation
   (`f"{left}__{right}"`), so `("A", "B__C")` and `("A__B", "C")` collided onto the same id. Fixed: a
   canonical SHA-256 digest over the ordered `{left_candidate_id, right_candidate_id}` structured payload,
   plus a fail-closed `UEF8PairIdentityCollisionError` guard requiring `pair_count == unique pair ids ==
   unique canonical pair tuples` after every pair universe is built.
4. Final independent closure: `CRITICAL 0, HIGH 0, MEDIUM 0, LOW 0`, `CORE_VERDICT: APPROVE_UEF8`,
   `UEF8_COMPLETE: YES`, `UEF8_FORMAL_FREEZE: YES`, `COMPARABLE_REACHABLE_WITH_CURRENT_UEF7_SCHEMA: NO`.

## Final regression state

```
UEF-8: 41 PASS
UEF-7: 38 PASS
TOTAL: 79 PASS
```

## Frozen-predecessor safety

- UEF-1..UEF-3C freeze manifest: `11 / 11 MATCH`.
- UEF-5.1, UEF-5.2, UEF-5.3, UEF-6, UEF-7, and Alpha Board v2: unchanged -- UEF-8 never calls
  `normalize_alpha_board()` differently, never recalculates UEF-7's own source groups, source bundle ids,
  population statuses, or normalized metrics, and never reopens raw Alpha Board sources.

## Authoritative contract

### Purpose boundary

```
comparability != performance superiority
NOT_COMPARABLE != bad strategy
CONDITIONAL     != weak strategy
```

UEF-8 output is comparison-VALIDITY evidence only -- never trading runtime authority, strategy promotion
authority, performance ranking authority, or execution authority.

### Status contract

Exactly three states, no ranking semantics, no score, no tier, no winner: `COMPARABLE`, `CONDITIONAL`,
`NOT_COMPARABLE`.

### Pair universe

For N candidate rows, `pair_count = N*(N-1)/2`, every unordered pair exactly once -- no self-pair, no
directional duplication, no dropped pair. Current real board: `N=14`, `pair_count=91`.

### Pair identity

```
canonical ordered candidate pair -> canonical structured JSON -> SHA-256 -> UEF8PAIR_<digest>
```

`pair_id(A,B) == pair_id(B,A)`, but distinct semantic candidate tuples always produce distinct ids -- the
prior delimiter-concatenation encoding is not authoritative. Required invariant after every pair universe
is built: `pair_count == unique canonical pair tuples == unique comparison_pair_ids`. Any generated
collision fails closed (`UEF8PairIdentityCollisionError`) -- never a silent overwrite, collapse,
first-wins, or last-wins.

### Hard comparison blockers (→ `NOT_COMPARABLE`)

```
DIFFERENT_RESEARCH_QUESTION
DIFFERENT_TARGET_HORIZON
DIFFERENT_EVIDENCE_COHORT
EVIDENCE_COHORT_NOT_AVAILABLE
NO_SHARED_OUTCOME_METRIC
```

No winner comparison is authorized across any of these boundaries.

### Conditional fairness conditions (→ `CONDITIONAL`, absent a hard blocker)

```
METRIC_AVAILABILITY_MISMATCH
INSUFFICIENT_SAMPLE_ACCOUNTING
POPULATION_RELATION_NOT_PROVEN
SHARED_SOURCE_PROVENANCE
```

`sample_count` `None`/`0` is reported as unresolved accounting -- UEF-8 never invents an arbitrary
statistical threshold (`N >= 10`, `N >= 30`, or any other minimum-N policy).

### Population authority boundary (core invariant)

```
individual population identity proven != pair population relation proven
```

The frozen `uef7.alpha_board_normalization.v1` schema provides no pairwise population relation authority
(no `population_id` relation, canonical population comparison relation, or same/distinct population
authority field of any kind). Therefore `POPULATION_RELATION_NOT_PROVEN` is unconditional for every valid
current-schema pair, real or synthetic.

### COMPARABLE reachability

```
COMPARABLE_REACHABLE_WITH_CURRENT_UEF7_SCHEMA: NO
```

This is a SCHEMA CONTRACT property, not merely today's observed-data result -- verified against both the
real production pipeline and a synthetic best-case fixture (every dimension aligned, both sides
individually `DIRECT_POPULATION_IDENTITY_PROVEN`). `COMPARABLE` remains reserved in the UEF-8 enum/schema
for a future explicitly frozen upstream schema extension that supplies pairwise population comparison
authority -- UEF-8 itself must never invent that authority.

### Source provenance boundary

```
shared source provenance    != same population
different source provenance != independent population
```

`SHARED_SOURCE_PROVENANCE` is descriptive comparison-risk evidence only; no source group or source bundle
ever becomes population authority in either direction.

### Metric authority

UEF-8 only checks availability (non-null) of frozen UEF-7 outcome metrics -- never recomputes them:
`win_rate`, `avg_net_return_pct`, `profit_factor`, `max_drawdown_pct`, `coverage`, `avg_mfe_pct`,
`avg_mae_pct`. Accounting dimensions (`sample_count`, `window_count`) are never treated as performance
outcomes. No `return_delta`, `PF_delta`, or `winner` is ever produced.

### Reason semantics and status precedence

All observed reasons are preserved even when the final status is determined by the strongest reason.
Precedence:

```
hard scope blocker present                       -> NOT_COMPARABLE
otherwise, any unresolved fairness condition      -> CONDITIONAL
all required comparison authority proven          -> COMPARABLE (unreachable under current schema)
```

Reason ordering is one fixed, deterministic sequence -- never dependent on set/dict iteration order.

### UEF-7 authority boundary

UEF-8 consumes the frozen `uef7.alpha_board_normalization.v1` payload only. It never recalculates source
groups, source bundle ids, population status, normalized metrics, raw Alpha Board evidence, or UEF-6
lineage -- UEF-7 remains upstream authority.

### Run identity

`UEF8_RUN_ID` binds: the source UEF-7 run id, an order-independent semantic digest over UEF-7's own
normalized rows, UEF-8's own semantic implementation digest, the UEF-8 schema version, and the
fair-comparison policy version. No wall-clock timestamp. Candidate input ordering is non-semantic (same
pair ids, pair contents, summary, and run id under any row permutation); a genuine semantic or
implementation-digest change always changes the run id.

## Real board result (measured, not hardcoded)

```
candidate_count: 14
pair_count: 91
COMPARABLE: 0
CONDITIONAL: 7
NOT_COMPARABLE: 84
unique pair IDs: 91
POPULATION_RELATION_NOT_PROVEN: 91
```

The 7 structurally-surviving `CONDITIONAL` pairs are pairs whose harder scope dimensions (question,
horizon, cohort, shared metric) all happen to align -- they are not "best" candidates, and UEF-8 makes no
such claim.

## Output authority

UEF-8 output is derived fair-comparison validity evidence. It is **not** trading runtime authority,
strategy promotion authority, performance ranking authority, or execution authority.

## Related

- [UEF milestones](../milestones/UEF.md)
- [UEF-7 Alpha Board Normalization Freeze](uef7_alpha_board_normalization_freeze.md)
- [UEF freeze manifest](uef_freeze_manifest.md)
