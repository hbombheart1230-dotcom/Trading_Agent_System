# Step5C: durable execution owner

Cleanup prerequisite: c77f830 (2998 passed, 1 skipped).

## Boundary and identity

The canonical packet path and legacy execute_order path retain all existing
guards and Supervisor decisions. Only after approval does the execution-owner
adapter claim approved -> executing in SQLite, before any executor call. This
placement records real approval rather than pretending that an unapproved
packet has been approved. CAS never substitutes for policy approval.

Explicit intent_id is preserved. Conflicting explicit IDs fail closed. Missing
IDs are deterministic hashes of execution scope, run_id, symbol, action and
original broker reference. Scope includes execution/broker mode and a digest of
account identity. Two distinct same-symbol/same-action intents in one run must
provide distinct explicit intent_id values. A changed payload under one ID is
an identity conflict, not permission to submit again.

Automatically generated cancellations use a deterministic child intent_id from
scope, original broker reference and cancel/modify terms, independent of polling
tick. No execution_intent_id/decision_id/execution_id is introduced. Earlier
Monitor artifacts may legitimately predate ID assignment; packet/order,
Supervisor input, execution artifact and store share the assigned ID thereafter.
No historical artifact is rewritten.

## Storage and lifecycle

SQLiteIntentStateStore remains the single state owner. Its existing database is
used, defaulting to repository-root/data/state/intent_state.db; the optional
INTENT_STATE_DB_PATH must be identical for every participating process and on a
local durable filesystem. Tests receive a per-test isolated path, inherited by
subprocesses. An additive binding table records payload digest and private owner
capability in that same database, not a second execution state store.

### Canonical database authority (Fix1, 2026-09-11)

Codex's independent Red-Team audit of 342060f found that this default was
computed independently by two call sites -- `intent_execution_owner._store()`
(repository-root-anchored absolute path) and `ApprovalService.__init__`'s own
fallback (`store.path.with_suffix(".db")`, i.e. data/logs/intents.db when
INTENT_STATE_DB_PATH was unset) -- so the automated packet path and the manual
approval path resolved to two *different* physical files under the actual
project `.env` (verified empirically, not merely asserted: the two defaults
diverge; `INTENT_STATE_DB_PATH` was not set). Two independent live order-mutation
entry points each believing they hold sole ownership is exactly the failure
mode this component exists to prevent.

Fixed by introducing `libs.supervisor.intent_state_store.resolve_intent_state_db_path()`
as the single canonical resolver (explicit path argument > INTENT_STATE_DB_PATH
env var > repository-root-anchored default, never a bare relative literal).
`SQLiteIntentStateStore.__init__`'s own no-argument default now calls it, and
every other consumer (`intent_execution_owner._store()`, `ApprovalService`,
`scripts/approval_cli.py` via `ToolFacade`/`ExecutorAgent`, and every test that
does not pass an explicit path) goes through the same class default -- there is
no second, independently-computed fallback path left anywhere in this
codebase. The resolver is anchored to the repository root (derived from
`__file__`, never `Path.cwd()`), so the default is identical regardless of the
process's working directory in production (`resolve_runtime_write_path` is a
no-op outside pytest, so this repository-root anchoring is what actually makes
production cwd-independent, not pytest's own isolation).

### Manual vs automatic execution ownership (Fix1, 2026-09-11)

A second, independent gap existed alongside the database split: `libs/skills/
runner.py::CompositeSkillRunner.run()` -- the mutation path reached via
`scripts/approval_cli.py approve` -> `ToolFacade`/`ExecutorAgent.approve` ->
`ApprovalService.approve` -> `ExecutorAgent.execute_order` -> this runner's
`order.place` skill, and also reached directly, with no CAS at all, by
`ExecutorAgent.submit_order_intent(approval_mode="auto", execution_enabled=True)`
-- called `executor.execute()` directly, never through `execute_owned_order`/
`bind_intent`. `ApprovalService.approve()`'s own pre-existing (M24) atomic
`approved -> executing` CAS transition covers ordinary approve() calls once it
shares the canonical database (above), but the `APPROVAL_MODE=auto` shortcut
bypasses `ApprovalService.approve()` entirely and had no ownership gate of any
kind.

Fixed, without touching ApprovalService's own transition or Step5B semantics:
`CompositeSkillRunner.run()` now checks, immediately before dispatching a
recognized mutation api_id (kt10000/kt10001 today; kt10002/kt10003 remain
unwired into any live skill, per `libs/execution/guards/broker_mutation.py`),
whether the intent_id passed in `args["intent_id"]` already holds a canonical
EXECUTING claim (i.e. `ApprovalService.approve()`'s own CAS already ran). If
so, the pre-established claim is trusted and the executor is called directly
-- this runner does not re-claim on top of an already-granted claim, which
would incorrectly deny the very first legitimate dispatch (the state would no
longer read `approved`). If no such claim exists (the `auto`-mode bypass, or
any other caller reaching this runner without prior approval-service gating),
the runner claims one itself via `execute_owned_order()`/`bind_intent()`
before calling the executor, so "no canonical ownership claim -> broker call
0" holds regardless of entry point. `ExecutorAgent.execute_order()` now
threads the OrderIntent's own `intent_id` (assigned once, at
`TwoPhaseSupervisor.create_intent`) into the skill args so this check has an
identity to look up.

### Cross-path duplicate semantics and the run_id boundary (Fix1, 2026-09-11)

The automated path's intent_id is a deterministic hash of
`[execution_scope, run_id, symbol, action, orig_ord_no]` (see Boundary and
identity, above); the manual approval path's intent_id is an independent
`uuid4` assigned once at `TwoPhaseSupervisor.create_intent`. These two schemes
are **not** unified in this Fix -- doing so is explicitly out of scope
("large-scale identity redesign") for this closure pass. Consequently:

- The invariant this Fix guarantees is per-intent_id: whichever path first
  establishes a canonical claim for a given intent_id blocks every other path
  (or the same path, replayed) from claiming that *same* intent_id again,
  verified with real OS processes racing the identical intent_id from both a
  simulated automated-path shape and a simulated manual-path shape
  (`tests/test_step5c_fix1_shared_ownership.py::test_fix1_real_multiprocess_cross_path`).
- It does **not** guarantee that a human manually approving an order for
  symbol X via `scripts/approval_cli.py` while the automated loop
  independently decides to trade the same symbol X will be recognized as "the
  same real-world order" -- they will, by design, carry different intent_id
  values and each may independently claim and dispatch. This is the same
  boundary the automated path already accepts for its own `run_id` rotation
  (a new decision cycle after a restart intentionally gets a new intent_id);
  cross-path/cross-run deduplication for the *same* real order remains the
  job of the existing symbol+TTL guards
  (`recent_buy_order_guard`/`recent_sell_order_guard` in
  `graphs/nodes/execute_from_packet.py`), which this Fix does not extend to
  the manual approval path. A future Step5C fix or Step5D item should decide
  whether to extend those guards to the manual path or to unify intent_id
  generation; neither is implemented here.

### Shared DB operational assumption (updated)

"INTENT_STATE_DB_PATH must be identical for every participating process" is no
longer solely an operational assumption to document and hope operators honor
-- it is now also the *code default* every consumer falls back to when the
variable is unset, closing the specific way this assumption was previously,
silently violated. Explicitly setting INTENT_STATE_DB_PATH to divergent values
across processes remains possible (an explicit env override is still honored
verbatim, by design, e.g. for test isolation) and is still the operator's
responsibility to avoid in a real multi-host or multi-environment deployment.

BEGIN IMMEDIATE, expected-state UPDATE and journal/binding writes commit in one
transaction. New, already policy-approved submissions record pending/approved
and atomically claim executing. Existing pending rows are NOT auto-approved.
Existing executing/executed/failed/rejected rows never obtain another owner.

ACCEPTED -> executed means broker acceptance, NOT fill completion.
REJECTED / NOT_SENT after claiming -> failed (no implicit replay).
UNKNOWN / crash / normalization exception -> executing, reconciliation needed.
Terminal persistence failure preserves the broker outcome and executing lock.
CAS/backend failure -> NOT_SENT, physical broker calls zero.

Existing Step5B classification, mutation retry=0, UNKNOWN quarantine and
cancel-confirmation rules remain unchanged. Read queries do not acquire ownership.
Direct raw Executor calls without an OrderIntent remain Step5B transport APIs;
they are not an alternate approved OrderIntent execution entry point. New logical
order paths must use this adapter. Cross-tick newly-created intents are still
subject to existing symbol/TTL/risk guards; this layer does not infer that two
different IDs are the same trading decision.

## Validation and limitations

Focused coverage includes successful ownership, sequential and OS-process
duplicates, restart, terminal/failed/UNKNOWN no replay, backend failure, independent
IDs, same-symbol different IDs, CANCEL/MODIFY, identity conflicts and real
HttpClient+RealExecutor timeout composition with a fake network/token provider.
Automatic reconciliation and operator unlock controls are not implemented here.
No live restart, broker connection, historical data rewrite or policy tuning is
part of this change. Step5D requires its own scope approval; readiness does not
authorize an automatic live rollout.

## Recorded verification (2026-09-06)

- Cleanup full regression: 2998 passed, 1 skipped, exit 0 (c77f830).
- Step5C focused regression before final artifact assertions: 145 passed, exit 0.
- Final Step5C tree full regression, including artifact identity assertions and
  process-crash/persistence-failure regressions: 3012 passed, 1 skipped,
  exit 0, 206.82 seconds.
- Real spawned-process contention permits one executor call; a restarted process
  with the same identity performs zero additional calls. Crash leaves executing.
- Unavailable CAS database performs zero executor calls. RealExecutor/HttpClient
  fake-transport timeout performs one physical submission and no duplicate retry.
- No live restart or push was performed. These are isolated tests, not a claim
  of successful live broker reconciliation or multi-host deployment validation.

## Recorded verification -- Fix1 (2026-09-11)

- Reproduced first, pre-fix: the two default DB paths (`data/state/intent_state.db`
  vs `data/logs/intents.db`) were shown to diverge by direct interpreter
  inspection under the actual repository `.env` (INTENT_STATE_DB_PATH unset).
- New coverage in `tests/test_step5c_fix1_shared_ownership.py` (11 tests):
  canonical resolver shared by ApprovalService/intent_execution_owner/generic
  construction; explicit env override still honored by every consumer;
  cwd-independence of the production default via two real subprocesses
  launched from different working directories; automated-claims-first blocks
  manual replay and manual-claims-first blocks automated replay for the same
  intent_id; a real two-OS-process race between an automated-path shape and a
  manual-path shape for one shared intent_id (total physical dispatch == 1);
  manual path self-claims when reached with no prior ownership
  (APPROVAL_MODE=auto shape); manual path duplicate is blocked with zero
  additional broker calls; manual path CAS-backend-unavailable performs zero
  broker calls; manual path payload-mismatch-under-one-intent_id is blocked as
  an identity conflict; and an end-to-end APPROVAL_MODE=auto submission
  through the real ExecutorAgent, confirming the shortcut path that used to
  reach the broker with no CAS at all now records a canonical terminal state
  and blocks a naive replay of the same OrderIntent.
- Focused regression (Step5C/Fix1/ApprovalService/ExecutorAgent/runner/
  execute_from_packet/execute_order/M24 suites): all passed.
- Full regression: see the accompanying audit report for this pass's exact
  count; no strategy, Scanner, Monitor, Supervisor risk policy, Opening
  Alpha/Q10/Q12 policy, Step5B semantics, BrokerOutcome semantics, UNKNOWN
  quarantine, or broker retry policy file was touched by this Fix.
- No live restart, broker connection, commit, or production state/lock/halt
  marker modification was performed while producing this Fix.

## Fix2 (2026-09-11): ownership capability, canonical propagation, physical duplicate closure

Codex's independent Red-Team audit of Fix1 reproduced three HIGH findings
against the actual implementation. All three are closed by this pass.

### HIGH1 -- EXECUTING state alone was never ownership evidence

Fix1's `CompositeSkillRunner.run()` read `state == EXECUTING` and, if true,
called `executor.execute()` directly -- trusting that SOME earlier caller
(assumed to be `ApprovalService.approve()`'s own separate approved->executing
transition) had legitimately claimed it. Codex reproduced two independent
runner invocations for the same intent_id both observing EXECUTING and both
dispatching (broker calls == 2). The root cause was having **two** independent
claiming mechanisms -- `ApprovalService`'s own `transition()` call and
`execute_owned_order()`'s `claim_execution()` -- with no ownership check tying
them together.

Fixed by deleting the "trust the state value" branch entirely.
`CompositeSkillRunner.run()` now calls `execute_owned_order()`
unconditionally for every real mutation, with no alternate path.
`ApprovalService.approve()` no longer performs its own approved->executing
transition; it leaves the intent in `approved` state and calls `execute_fn`
directly, which (via `ToolFacade.order_execute`/`ExecutorAgent.execute_order`
-> `CompositeSkillRunner.run()`) is what reaches the one, canonical
`claim_execution()` CAS. A concurrent second `approve()` call for the same
intent_id now loses at that single CAS point instead of at a separate,
independently-guarded transition.

`claim_execution()`/`finish_execution()` additionally expose the owner token
durably bound in `intent_execution_binding`
(`SQLiteIntentStateStore.get_owner()`/`verify_ownership()`) for observability
and for any future caller that needs to verify a specific claim rather than
attempt one -- but the safety invariant itself comes from there being exactly
one call site (`execute_owned_order`) that ever performs the claim, not from
callers passing tokens to each other.

### HIGH2 -- the real production CLI path lost the original intent_id

Codex traced the actual path `scripts/approval_cli.py` uses:
`ToolFacade.approve_intent` (`libs/tools/tool_facade.py`) ->
`ApprovalService` -> `ToolFacade.order_execute` -> `CompositeSkillRunner`.
This never goes through `libs/agent/executor/executor_agent.py::ExecutorAgent`
at all -- Fix1 only patched `ExecutorAgent`'s copy of this plumbing, so the
real CLI path still silently minted a brand-new content-hash identity at the
runner boundary (observed: original `b0279a...` became execution intent
`intent-v1-1ebbea...`).

Fixed by threading `intent.get("intent_id")` through
`ToolFacade.order_execute()` the same way `ExecutorAgent.execute_order()`
already did (and, for consistency/defense-in-depth, the otherwise-unused
`libs/tools/tool_schema.py::ToolFacade.order_execute()`, which has no
importers anywhere in this codebase today but shares the same runner
contract). The approved OrderIntent's own identity, assigned once at
`TwoPhaseSupervisor.create_intent`, now survives unchanged through approval,
execution, and the terminal canonical state.

### HIGH3 -- different intent_id, same physical order

Intent-level ownership guarantees at most one owner per intent_id, but two
different intent_id values (the automated path's content-hash scheme and the
manual path's uuid4 scheme) can describe the same real-world physical order.
Fixed by adding a second, independent guard:
`libs.execution.intent_identity.physical_order_fingerprint()` (account/broker
scope + symbol + action + order_type + qty + price + orig_ord_no; price is
canonicalized to null for market orders since it carries no real identity
there) keys a new `physical_order_claim` table
(`SQLiteIntentStateStore.claim_physical_order`/`release_physical_order`) in
the same canonical database. `execute_owned_order()` claims the physical
lease *before* the intent-level CAS; either guard alone denying blocks the
dispatch.

The lease is released only when its owning intent reaches a genuine terminal
state (EXECUTED/FAILED) -- never automatically on an ambiguous outcome
(UNKNOWN, crash, persistence failure), matching this module's existing
Option A philosophy. This means the guard blocks truly concurrent duplicate
attempts (two ingress points racing the same physical order while one is
still active) without permanently blocking a later, genuinely new decision
cycle from placing what looks like "the same" order once the earlier attempt
has fully resolved -- the explicit "no permanent dedup" requirement. A CANCEL
child intent's own action+orig_ord_no keep its physical key from ever
colliding with the original BUY/SELL it targets.

Cross-path duplicate prevention for the same real-world order is therefore
guaranteed at the physical-order level regardless of intent_id scheme; it is
**not** guaranteed at the intent-identity level (the two schemes remain
unmerged, by design, per the explicit "avoid large-scale identity redesign"
scope for this Fix).

### MEDIUM1 -- UNKNOWN lifecycle truth

A structural consequence of the HIGH1 fix: since `ApprovalService` no longer
force-writes a status, it reads the canonical `intent_state` row (written
solely by `execute_owned_order`) after `execute_fn` returns. An UNKNOWN
broker outcome leaves the row in `executing` (non-terminal,
`reconciliation_required: True` in the returned dict) and is never recorded
as `executed`. A pre-claim exception (raised before any canonical claim was
ever attempted, e.g. a bug in request-building code) is recorded as `failed`
directly -- newly allowed in the state machine (`approved -> failed`,
additive to the existing `approved -> executing` and `executing ->
{executed, failed}` transitions) since there is no dispatch ambiguity when no
claim was ever taken.

### MEDIUM2 -- relative INTENT_STATE_DB_PATH was cwd-dependent

`resolve_intent_state_db_path()` now anchors any *relative* explicit path or
`INTENT_STATE_DB_PATH` env value to the repository root before handing it to
`resolve_runtime_write_path` (which remains a no-op outside pytest); an
absolute value, explicit or from the env, is still used as-is. Two processes
started from different working directories with the same relative override
now resolve to the same physical file.

### Verification

- `tests/test_step5c_fix2_ownership_capability.py` (18 tests): same-intent
  claim/deny/real-multiprocess; the actual `ToolFacade` chain preserving the
  original intent_id end-to-end (including a real UNKNOWN-outcome run
  confirming the canonical row never reads `executed`); different-intent
  same-physical-order denial under genuine overlap (single-process via
  `on_submit`, and real two-OS-process via a synchronization `Event`);
  independence of different qty/side/order_type physical keys; the "later
  legitimate cycle may reuse the physical key" boundary and its inverse
  ("an ambiguous outcome never releases the lease"); child CANCEL ownership
  and non-collision with its original order; cwd-independence of a relative
  `INTENT_STATE_DB_PATH` across two real subprocesses; and the runner
  refusing a mutation with no canonical intent_id rather than inventing one.
- Fixed three pre-existing M24 tests (`test_m24_2_approval_state_store_
  integration.py`, `test_m24_3_duplicate_execution_claim_guard.py`) and one
  operational script (`scripts/run_m24_guard_precedence_check.py`) whose fake
  `execute_fn` stand-ins never reached a real claim under the old contract
  (ApprovalService trusted execute_fn's return value unconditionally, which
  is the exact class of bug MEDIUM1 closes) -- they now call the same
  canonical `claim_execution`/`finish_execution` primitives a real dispatch
  would, exercising the corrected contract instead of the old one.
- Full regression: 3088 passed, 1 skipped, 0 failed. `git diff --check`
  clean. No strategy, Scanner, Monitor, Supervisor risk policy, Opening
  Alpha/Q10/Q12 policy, Step5B semantics, BrokerOutcome semantics, UNKNOWN
  quarantine, or broker retry policy file was touched.
- No live restart, broker connection, commit, push, or production
  state/lock/halt marker modification was performed while producing this Fix.

## Fix3 (2026-09-11): canonical physical order normalization, authoritative intent validation

Codex's independent Red-Team audit of Fix2 reproduced two more HIGH findings
against the actual implementation.

### HIGH1 -- physical_order_fingerprint hashed raw values, not canonical ones

Fix2's `physical_order_fingerprint()` hashed `order.get(...)` values
directly. Equivalent representations of the same real order --
`qty=10`/`qty="10"`, `order_type="market"`/`"mkt"`/`""`, a market order
carrying a stray cached/reference price -- produced different keys, so the
guard could be defeated by trivial representation differences (Codex:
broker calls == 2, not <= 1). Worse, `"mkt"` was never a real alias
anywhere in this codebase (confirmed by grep, not assumed away), and an
empty `order_type` actually defaults to **LIMIT** in
`graphs/nodes/execute_from_packet.py::_build_order_from_intent` (`order_type
= intent.get("order_type") or intent.get("type") or "limit"`) -- Fix2 had
this backwards, treating `""` as market-equivalent.

Fixed by canonicalizing every field before hashing
(`_canonical_action`/`_canonical_order_type`/`_canonical_qty`/
`_canonical_positive_number` in `libs/execution/intent_identity.py`), each
grounded in this codebase's own existing contract (grepped and verified,
per field, before writing the canonicalizer -- not guessed):
`_canonical_action` accepts only `BUY`/`SELL`/`CANCEL`/`MODIFY`
(case-insensitive); `_canonical_order_type` matches
`_build_order_from_intent`'s exact default (only the literal string
`"market"` means MARKET, everything else -- including `""` -- means LIMIT);
`_canonical_qty` accepts int/str/whole-float positive quantities only
(`"10.5"`, `-1`, `0`, `"abc"`, `None` all invalid); `_canonical_positive_number`
is the same for LIMIT price, hashed as a whole KRW-won integer (never a
float, which is not deterministically hashable/comparable across equal
values). `physical_order_fingerprint` now returns `None` -- not a
fingerprint of best-effort defaults -- for anything that fails to
canonicalize (unrecognized action, invalid symbol, invalid qty, a LIMIT
with no valid price); `execute_owned_order` treats `None` as
`invalid_physical_order`, broker calls zero, fail closed. A market order's
price is still always canonicalized to `None` regardless of what raw value
the caller carried (unchanged from Fix2, now proven under real
representation variance rather than only the one literal form Fix2's own
tests happened to use). CANCEL/MODIFY's physical identity remains
action+`orig_ord_no` (plus `cncl_qty`/`mdfy_qty`/`mdfy_uv` where
applicable) -- unaffected by this normalization, still never collides with
the BUY/SELL it targets.

### HIGH2 -- a caller-supplied intent_id did not need to exist to be admitted

> Historical Fix3 description. The self-minted authorization mechanism below
> is superseded by the Fix4 authority correction at the end of this document.

`claim_execution()` self-admitted (pending->approved->executing) *any*
never-before-seen `intent_id`, including one supplied by an external
caller with no persisted OrderIntent behind it at all. Codex's
reproduction: format checks blocked `None`/`""`/`"   "` but not `"bad id"`/
`"@@@"`, and -- more importantly -- a well-formed but entirely fictitious
identity (never created, never approved anywhere) was admitted and
dispatched to the broker exactly as if it had gone through real approval.
A caller-supplied identity does not, by itself, carry execution authority.

Fixed by having `claim_execution()` require its caller to prove
self-mintedness before self-admission is allowed:
`intent_identity.is_self_minted_intent_id(state, order, intent_id, child=...)`
recomputes `bind_intent`'s own deterministic content-hash for the order's
current material and compares it to the supplied `intent_id` -- true only
when `execute_owned_order`'s *own* `bind_intent` call, in *this* call,
generated the identity (i.e. this call is the authorized creator, reached
only after existing policy guards already passed for the automated path).
`claim_execution(..., allow_auto_admit=self_minted)`: when `False` (any
externally-asserted id -- a `TwoPhaseSupervisor.create_intent` uuid4, or
arbitrary caller input), a missing row is refused as `INTENT_NOT_FOUND`
(never created), a `pending_approval` row as `NOT_APPROVED`, and a
malformed id (`_INTENT_ID_FORMAT_RE`, rejecting whitespace/control/symbol
characters like `"bad id"`/`"@@@"` up front) as `INVALID_INTENT_ID` -- all
broker calls zero.

This tightening required separating creation authority from execution
authority for the two "auto" shortcuts that never went through
`ApprovalService.approve()`'s own PENDING->APPROVED transition:
`ExecutorAgent.submit_order_intent` and `ToolFacade.order_place_intent`
(both `APPROVAL_MODE=auto`) now call the new
`ApprovalService.admit_pre_approved_intent(intent_id)` -- which persists
the already-risk-gated (`TwoPhaseSupervisor.create_intent`'s own
`self.risk.allow(...)`) intent as `approved` -- before reaching
`execute_order`/`order_execute`, exactly mirroring what `approve()` already
does for the manual path. The normal manual-approval flow
(`scripts/approval_cli.py`/`ToolFacade.approve_intent`/
`ExecutorAgent.approve`) needed no change: `ApprovalService.approve()`'s
existing PENDING->APPROVED transition already persists the row before
`execute_fn` ever reaches `execute_owned_order`.

### MEDIUM1 -- physical claim orphan observability

If a process crashes (or `claim_execution` itself raises) between
`claim_physical_order` succeeding and `finish_execution` ever running, the
physical lease is left orphaned -- safe (fail-closed, no duplicate
dispatch possible) but, until now, invisible. Fix3 does **not** implement
automatic release or recovery (explicitly out of scope, deferred to
Step5D) but adds read-only introspection:
`SQLiteIntentStateStore.get_physical_claim(key)` and
`list_active_physical_claims()`. A claim immediately followed by a
*deterministic, pre-dispatch* `claim_execution` denial (ordinary control
flow, no crash -- e.g. `INTENT_NOT_FOUND`) is still safely released by
`execute_owned_order` itself, same as Fix2 -- there is no ambiguity about a
dispatch in that case. Only a genuine crash (verified with a real
`os._exit(0)` in a separate OS process, not a simulated exception) leaves
the row orphaned, observable via the new methods, blocking any retry at
that physical order until an operator or a future Step5D reconciliation
process acts on it.

### MEDIUM2 -- approval read-model could contradict canonical SQLite truth

`ApprovalService.approve()`'s exception handler unconditionally wrote a
`"failed"` marker into its own JSON read-model (`IntentStore`), even when
canonical SQLite already said `"executing"` (a claim was taken, then an
ambiguous exception occurred) -- two different "truths" visible to
different consumers. Fixed: the handler now checks canonical state first.
If it is still `"approved"` (no claim was ever taken -- no ambiguity about
a dispatch), both canonical SQLite and the JSON marker are set to
`"failed"`. If canonical state is already `"executing"` (a claim was
taken; `execute_owned_order`'s own crash-boundary contract already governs
it), the JSON marker instead records `"executing"` +
`reconciliation_required` -- never `"failed"`. `SQLiteIntentStateStore` is
the execution-lifecycle authority; `IntentStore`'s JSON rows are an
approval/audit read-model that must not contradict it.

### LOW -- `verify_ownership()` documented as observability, not authorization

No code path in this repository calls `verify_ownership()` before
dispatching to a broker (confirmed by search). Rather than imply it is a
production authorization gate, its docstring now states plainly that it is
an observability/debug helper -- the actual safety invariant (`EXECUTING`
state alone is never permission to execute) comes from
`execute_owned_order()` being the only call site that ever performs the
`claim_execution()` CAS in the same call that dispatches, not from a
second, separate verification step.

### Verification

- `tests/test_step5c_fix3_authoritative_intent.py` (31 tests): physical
  fingerprint normalization (market-alias/empty-order_type, cached-price
  exclusion, qty int/str/zero-padded, limit price int/str/string-float,
  action case aliases, symbol `A`-prefix alias, invalid-qty fail-closed,
  CANCEL requires `orig_ord_no` and never collides with its original
  order) with both same-key (false-negative) and different-key
  (false-positive) coverage; a real two-OS-process alias attack forcing
  genuine overlap (qty int vs str, a stray market price) with total broker
  calls == 1; authoritative-intent validation across the full state matrix
  (`None`/`""`/whitespace/`"bad id"`/`"@@@"` -> broker 0; well-formed but
  nonexistent -> `INTENT_NOT_FOUND`; pending -> `NOT_APPROVED`; approved ->
  claims; executing/executed/failed -> broker 0) plus confirmation the
  automated path's self-minted ids still auto-admit; both `APPROVAL_MODE=
  auto` shortcuts (real `ToolFacade` and real `ExecutorAgent`) still
  dispatch after the `admit_pre_approved_intent` fix; a safely-released
  orphan (deterministic pre-dispatch denial) versus a real-crash orphan
  (genuine `os._exit(0)` in a separate process) that stays held and is
  observable via `get_physical_claim`/`list_active_physical_claims`; and
  the approval read-model truth tests for both the UNKNOWN-after-claim
  case (JSON marker must not say "failed") and the pre-claim-exception case
  (both canonical and JSON correctly say "failed").
- Updated three test files whose fixtures assumed the now-closed HIGH2 gap
  (explicit, non-self-minted intent_id strings used as convenience labels
  without a corresponding persisted/approved OrderIntent):
  `tests/test_step5c_execution_owner.py`, `tests/test_step5c_fix1_shared_
  ownership.py`, `tests/test_step5c_fix2_ownership_capability.py`,
  `tests/test_step5b_fix3.py`, `tests/test_step5b_fix4.py` -- each now
  authorizes its explicit test id first (mirroring
  `admit_pre_approved_intent`) or switches to letting `bind_intent`
  self-mint when the specific id value doesn't matter to what the test
  verifies. Also fixed `tests/test_decision_trace_ledger.py`'s executor
  fixture, whose intent had neither `order_type` nor `price` and so
  defaulted to an unfingerprintable LIMIT-with-no-price order once physical
  validation became strict (a latent fixture gap this exposed, not a new
  restriction beyond what a real such order already could never legitimately
  be).
- Additive-only change to the intent state machine:
  `approved -> failed` (direct, no `executing` hop) is now allowed,
  covering exactly the "exception before any claim was taken" case above;
  `approved -> executing` remains the only path into `executing`, and only
  `claim_execution`'s CAS performs it.
- Full regression: see the accompanying audit report for this pass's exact
  count. No strategy, Scanner, Monitor, Supervisor risk policy, Opening
  Alpha/Q10/Q12 policy, Step5B semantics, BrokerOutcome semantics, UNKNOWN
  quarantine, or broker retry policy file was touched.
- No live restart, broker connection, commit, push, or production
  state/lock/halt marker modification was performed while producing this Fix.
# Step5C Fix4 Authority Correction

Fix4 supersedes the Fix3 self-minted auto-admission design described in the
historical sections below. A deterministic `intent-v1-*` value identifies a
payload; it does not authorize broker execution.

The active contract is:

1. A trusted upstream policy or manual approval boundary creates/binds the
   canonical intent.
2. That boundary persists `intent_admission` with the broker-semantic physical
   fingerprint and an `admission_source`.
3. `claim_execution()` requires an existing `approved` intent and performs
   only the atomic `approved -> executing` transition.
4. Missing, pending, rejected, executing, terminal, or fingerprint-conflicting
   identities fail closed. The runner cannot create or approve them.

Broker order type identity uses `trde_tp` when present and reconciles it with
logical aliases. `market` and `mkt` both normalize to `MARKET`; reference or
cached prices do not participate in a market-order physical key. Conflicting
logical and broker-native types fail closed.

**Superseded by Fix5 (2026-09-12):** the paragraph above described Fix4's own
behavior -- an approved row with no admission row was, until Fix5, executable
anyway, because `claim_execution()` itself inserted a one-time compatibility
admission (`source="legacy_approved_state"`) bound to whatever fingerprint the
*current caller* submitted. Codex's independent audit of Fix4 reproduced this
as a real attack (see the Fix5 section below): persist intent X as approved
with payload "BUY 005930 qty=1 MARKET", never admit it, then submit "BUY
000660 qty=99 MARKET" under the same intent_id -- claim_execution manufactured
admission from the attacker's own submitted payload and dispatched it. That
branch is deleted outright. An approved row with no admission is now refused
as `ADMISSION_NOT_FOUND`, full stop; there is no compatibility path left
inside the claim boundary itself.

The production admission sources currently include manual approval,
ToolFacade/ExecutorAgent automatic policy, the canonical packet execution
boundary, legacy execute-order compatibility, and automatic child-cancel
boundaries. Admission provenance is queryable through
`SQLiteIntentStateStore.get_admission()`.

## Fix5 (2026-09-12): mutation symbol fail-closed, claim_execution consumer-only authority

Codex's independent Red-Team audit of Fix4 reproduced two more HIGH findings
and one MEDIUM against the actual implementation.

### HIGH1 -- a mutation whose symbol failed to canonicalize bypassed the protected path entirely

`CompositeSkillRunner.run()` gated its entire protected mutation path
(quarantine check + `intent_execution_owner` claim) behind
`if is_mutation and mutation_symbol:`. Codex's exact reproduction: `BUY
0082N0 qty=10 MARKET` -- `is_mutation_api_id()` was `True`, but
`normalize_symbol("0082N0")` returns `""` (a 6-character mixed
alphanumeric code with both letters and digits is explicitly rejected by
`libs/core/symbols.py`'s own contract, verified by direct call, not assumed),
so `mutation_symbol` was falsy and the *entire* protected branch was skipped
-- falling through to the plain `self.executor.execute(prep.request)` branch
with zero ownership/quarantine/physical-claim protection at all (broker calls
== 1, expected 0, with the intent_id neither persisted, admitted, nor
approved).

Fixed by restructuring the boundary so mutation detection alone decides
which branch runs, per the invariant this Fix formalizes: every mutation is
either (A) a valid canonical mutation that goes through the
ownership/admission/physical-claim path, or (B) an invalid/un-normalizable
one that fails closed with broker calls 0 -- `mutation + normalization
failure -> generic executor` is never a legal third outcome.
`if is_mutation:` now unconditionally enters the protected branch; a symbol
that fails to canonicalize inside that branch returns `INVALID_SYMBOL`
(broker calls 0) immediately, before the quarantine check or the ownership
claim ever run, and there is no remaining code path (for any recognized
mutation api_id: BUY/SELL live today, CANCEL/MODIFY remain unwired to any
skill, confirmed by search) that reaches the plain `else: res =
self.executor.execute(...)` branch.

### HIGH2 -- claim_execution manufactured admission from the submitted payload

Described above (see the superseded paragraph). `SQLiteIntentStateStore.
claim_execution()` is now strictly a CONSUMER of authority some other,
explicit upstream boundary already established -- it never creates,
approves, or repairs anything. Its full contract, in order:

1. validate intent_id format -> malformed -> `INVALID_INTENT_ID`
2. load the persisted intent -> absent -> `INTENT_NOT_FOUND`
3. load the persisted admission -> absent -> `ADMISSION_NOT_FOUND`
4. compare the submitted fingerprint to the admitted one -> mismatch ->
   `PAYLOAD_MISMATCH`
5. verify state == approved -> pending -> `NOT_APPROVED`; any other
   non-approved state -> `intent_already_owned_or_not_approved`
6. check the execution-binding fingerprint (a second, later comparison
   covering an already-claimed intent replayed with a different payload)
   -> mismatch -> `intent_identity_conflict`
7. perform the atomic `approved -> executing` CAS
8. record the (now confirmed, never invented) owner binding

Note step 4 runs *before* step 5: a payload substitution attack against an
intent that has already reached a terminal state (executed/failed) is still
caught as `PAYLOAD_MISMATCH`, not masked by a "not approved anymore" message.

`ApprovalService.approve()`'s own admission creation was narrowed to match:
it only calls `admit_pre_approved_intent()` for a genuinely fresh intent
(`effective_status in ("", "pending_approval")`), never for a row that is
already `"approved"` with no admission -- that legacy shape now falls
through unchanged and fails closed downstream at `claim_execution()`
(`ADMISSION_NOT_FOUND`), exactly like any other unadmitted approved row.
Closing that gap for real requires an explicit, separately authorized
migration step (not implemented here -- out of scope for Fix5), never an
implicit repair inside the execution claim path or the approval service.

### MEDIUM -- admission schema readiness

The real operational DB had `intent_state`/`intent_journal` but no
`intent_admission` table yet; `get_admission()`/`claim_execution()` issuing a
bare `SELECT` against a missing table could raise `sqlite3.OperationalError`
instead of a clean `None`/denial. Fixed: `SQLiteIntentStateStore._init_db()`
now creates every table this store owns (`intent_admission`,
`intent_execution_binding`, `physical_order_claim`, in addition to
`intent_state`/`intent_journal`) at construction time -- for both a
brand-new DB and an existing one created before these tables existed, with
existing rows left untouched.

### Verification

- `tests/test_step5c_fix5_mutation_failclosed_and_consumer_only.py` (23
  tests): Codex's exact `BUY 0082N0` literal reproduced and closed (fails
  `INVALID_SYMBOL`, intent_id never created); an exhaustive invalid-symbol
  sweep (`""`, `" "`, `"0082N0"`, `"A0082N0"`, `"ABCDEFG12345"`, `None`) all
  broker-zero, with a control test confirming a *valid* admitted symbol
  still dispatches through the same code path; a legacy approved-without-
  admission row refused as `ADMISSION_NOT_FOUND` with the admission row
  confirmed absent both before and after the denial; Codex's exact HIGH2
  payload-substitution literal (authoritative "BUY 005930 qty=1 MARKET" vs
  submitted "BUY 000660 qty=99 MARKET") reproduced and closed, with the
  admission row asserted unchanged after the attack; the matching-payload
  happy path; an AST-based regression guard asserting the deleted
  auto-admission SQL statement is absent from `claim_execution`'s
  executable body (docstring prose describing the removal is deliberately
  exempted from the scan); an existing DB missing the `intent_admission`
  table opening cleanly with existing rows intact; `get_admission`/
  `get_physical_claim`/`list_active_physical_claims` returning empty/None
  rather than raising on a missing table; and the automatic, manual
  (`ToolFacade`), and child-cancel paths all still dispatching exactly once.
- Updated every pre-existing Step5C test file whose helpers admitted an
  intent via the old `ensure_intent`+`transition(approved)` pattern with no
  admission row (`tests/test_step5c_execution_owner.py`,
  `tests/test_step5c_fix1_shared_ownership.py`,
  `tests/test_step5c_fix2_ownership_capability.py`,
  `tests/test_step5c_fix3_authoritative_intent.py`,
  `tests/test_step5b_fix3.py`, `tests/test_step5b_fix4.py`) to call
  `admit_intent`/`admit_order_intent` with the correct canonical physical
  fingerprint instead -- exercising the corrected consumer-only contract
  rather than the now-removed auto-admission fallback. Two tests' expected
  denial reason changed from `intent_identity_conflict` to
  `PAYLOAD_MISMATCH` where a payload mismatch is now caught earlier (step 4
  above) than the binding-level check that used to be the only one.
- Full regression: see the accompanying audit report for this pass's exact
  count. No strategy, Scanner, Monitor, Supervisor risk policy, Opening
  Alpha/Q10/Q12 policy, Step5B semantics, BrokerOutcome semantics, UNKNOWN
  quarantine, or broker retry policy file was touched.
- No live restart, broker connection, commit, push, or production
  state/lock/halt marker modification was performed while producing this Fix.

---

## Step5C Final Closure (2026-09-12)

```
STEP5C STATUS: CLOSED
FORMAL FREEZE: YES
OPERATIONAL FREEZE: YES
CRITICAL: 0
HIGH: 0
READY_FOR_STEP5D: YES
```

Confirmed by Codex's independent Red-Team audit of Fix5 (final stability
validation pass): CRITICAL 0, HIGH 0, MEDIUM 0, LOW 0.

### Final invariants

1. Every broker mutation requires canonical intent authority -- no mutation
   dispatches on identity or state alone.
2. An executable intent follows exactly one lifecycle: **persist ->
   admission -> approved -> claim**. There is no shortcut into "approved
   and executable" that skips admission.
3. `claim_execution()` is consumer-only: it loads, validates, compares, and
   performs the atomic CAS. It never creates an intent, never creates or
   repairs an admission, and never approves anything.
4. Malformed, invalid, or non-canonicalizable mutation input fails closed
   (broker calls == 0) -- including a mutation whose symbol cannot be
   normalized; mutation detection alone decides the authority boundary,
   never symbol-normalization success.
5. Different representations of the same real physical order (numeric vs
   string quantity, market/mkt/trde_tp=3 aliasing, a stray cached price on
   a market order) canonicalize to the same identity before any duplicate
   check runs.
6. A physical-order duplicate claim blocks a second dispatch of the same
   real-world order across processes and across a restart -- a crash
   leaves the lease held (fail closed, observable), never silently
   released.
7. An UNKNOWN broker outcome is never implicitly replayed: the intent
   stays non-terminal, the physical claim stays held, and both the
   canonical SQLite lifecycle and the JSON read-model agree it requires
   reconciliation.
8. Step5B's own broker-mutation-at-most-once semantics (BrokerOutcome
   4-state, UNKNOWN quarantine, physical HTTP at-most-once,
   token-invalid-no-replay) are unmodified by any Step5C fix.

### Fix-by-fix summary (architecture contract, not an incident log)

- **Fix1** -- shared canonical DB authority: one resolver
  (`resolve_intent_state_db_path`) for every consumer, anchored to the
  repository root (cwd-independent in production).
- **Fix2** -- ownership path unification: every real mutation dispatch
  goes through the single `execute_owned_order()` claim-dispatch-finish
  sequence; canonical intent_id propagates unchanged through every entry
  point; a physical-order duplicate claim closes the cross-path/cross-
  scheme gap intent-level ownership alone cannot catch.
- **Fix3** -- physical order canonicalization (first pass) grounded in
  this codebase's own order-building contract; authoritative intent
  validation (format + existence + approval, never self-admission from an
  external caller); physical-claim orphan observability
  (`get_physical_claim`/`list_active_physical_claims`, read-only, no
  auto-recovery); approval read-model truth kept consistent with
  canonical SQLite.
- **Fix4** -- broker-semantic order normalization (`market`/`mkt`/
  `trde_tp=3` equivalence, conflicting logical/broker-native types fail
  closed); deterministic identity generation is explicitly documented as
  never equivalent to execution authority; an explicit `intent_admission`
  boundary (`libs/execution/intent_admission.py`) introduced for
  authorized creators (automatic policy, child cancel).
- **Fix5** -- mutation symbol normalization failure fails closed instead
  of falling through to the generic executor; `claim_execution()` made
  strictly consumer-only (the "legacy_approved_state" auto-admission
  branch, which let a submitted payload manufacture its own authority,
  deleted outright); admission schema (`intent_admission`,
  `intent_execution_binding`, `physical_order_claim`) guaranteed ready at
  store construction for both new and pre-existing databases.

### Final execution model

```
OrderIntent
  -> Persist              (intent_state: pending_approval)
  -> Admission            (intent_admission: fingerprint + source, bound
                            to the authoritative payload -- never the
                            submitted-at-claim-time one)
  -> Approved             (intent_state: approved; admission and approval
                            happen together for a fresh intent)
  -> claim_execution CAS  (consumer-only: validate format, load intent,
                            load admission, compare fingerprint, verify
                            approved, atomic approved -> executing)
  -> Physical Order Claim (claim_physical_order: at most one active lease
                            per canonicalized real-world order shape)
  -> Step5B Broker Mutation Safety (BrokerOutcome classification,
                            physical HTTP at-most-once -- unmodified)
  -> Broker
```

UNKNOWN outcome:

```
Broker UNKNOWN
  -> intent stays non-terminal (state: executing)
  -> physical order claim stays held (no auto-release)
  -> reconciliation_required: True (both canonical SQLite and the JSON
     read-model agree -- neither claims "executed" nor "failed")
  -> no implicit replay, ever
```

Resolving what actually happened at the broker for an UNKNOWN/orphaned
claim -- broker truth reconciliation, fill reconciliation, operator
release/recovery of a held lease -- is explicitly **not** Step5C's job.

### Step5C / Step5D boundary

- **Step5C answers**: who is allowed to execute this, and is this
  execution already owned or duplicated?
- **Step5D answers**: what actually happened at the broker?

Step5C deliberately does not implement: broker reconciliation, fill
reconciliation, UNKNOWN resolution, or operator release/recovery of a held
intent or physical-order lease. These remain Step5D (broker truth
reconciliation) / Step5E (operator workflow) scope, unstarted by this
closure.

### Operational note

Step5C code freeze is complete as of this closure. The currently running
production process has not yet been restarted with the final Fix5 code --
the frozen implementation becomes active at the next planned runtime
restart. No emergency restart is required solely for freeze bookkeeping;
Codex's independent audit already approved both formal and operational
freeze against the frozen source, in advance of that restart.

### Final regression evidence

```
Focused regression:      297 passed
Fix5 exact regression:   23 passed
Full regression:         3150 passed, 1 skipped
Assertion failures:      0
Step5C-caused failures:  0
git diff --check:        PASS
```

The full-regression process exit code observed during this work was
non-zero on at least one run; that was this repository's own conftest.py
"production path write detected" session guard reacting to the
concurrently-running live production process's own normal state/heartbeat
writes during the test window -- not a test assertion failure (confirmed
by grep-ing the run's output for `^FAILED` lines: zero, every time this
was checked).
