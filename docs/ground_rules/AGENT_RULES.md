# AGENT_RULES.md
> Trading_Agent_System — Agent Rules / Non‑Negotiables (M20 Prep)

This file is the **hard guardrail** for any human or AI (Codex) changes.
If a proposed change violates any item below, **STOP** and redesign.

---

## 1) Core Non‑Negotiables (Must Hold Always)

1. **Monitor must never place orders** (structurally prohibited).
2. **Execution Layer must never execute without approval**.
3. **Guards override approvals** (approved but guarded == blocked).
4. **DTO/IO contracts must not introduce breaking changes** (use versioning).
5. **Logging/observability is observational only** (must not alter control flow).
6. **Default stance is “do not execute”** (safe defaults).

---

## 2) Role Boundaries (Who Does What)

### Commander (지휘관) — Orchestrator
- Owns the **run-cycle orchestration** (who to call next, when to pause/stop).
- Routes outputs between agents (plan → scan → monitor → approve → execute).
- Handles abnormal events (API failure, guard blocks, retries/cancel).
- Triggers approval → execution chain via Supervisor + AgentExecutor.
- **Does NOT**:
  - select symbols directly
  - compute indicators/features
  - place orders

### Strategist (전략가)
- Chooses candidates (typically 3–5) and scenarios (entry/add/stop/take-profit).
- Decides what signals/news/features to consult (but does not execute).

### Scanner (스캐너)
- Fetches data via skills with accuracy.
- Computes features and returns ranked results + gaps/uncertainty.

### Monitor (모니터)
- Watches the chosen primary symbol(s) (initially 1).
- Emits **ActionProposal / OrderIntent** only.
- **Never executes** or calls broker APIs.

### Supervisor (감독관)
- Owns risk limits and policy.
- Validates OrderIntent and **approves / rejects / modifies**.
- Can pause/stop the system.

### AgentExecutor (에이전트 수행자) — Bridge
- Translates SupervisorDecision + OrderIntent into an execution request.
- Must obey all guards and idempotency rules.

### Execution Layer (실행 계층)
- Guard evaluation (EXECUTION_ENABLED, real-mode allow, allowlist, limits, idempotency).
- Broker routing (mock/real).
- Side-effect boundary (only place/cancel/status).

### Reporter (리포터)
- Reads EventLog and produces reports / improvement suggestions.
- No control authority; does not change runtime decisions.

---

## 3) Guard Precedence (Must Preserve Order)

1) EXECUTION_ENABLED == false → always block  
2) KIWOOM_MODE == real AND ALLOW_REAL_EXECUTION != true → block  
3) SYMBOL_ALLOWLIST is configured and mismatch → block  
4) MAX_QTY exceeded → block  
5) MAX_NOTIONAL exceeded → block  
6) Idempotency (intent_id already executed) → block  

**Rule:** the same `intent_id` must not execute twice.

---

## 4) Contract Stability (DTO/IO)

- Required fields must never be removed.
- Additive changes only (optional/defaults).
- Semantic changes prohibited → add new field instead.
- Versioning policy: keep `dto_version="v1"`, introduce `v2` in parallel for breaking changes.

---

## 5) Change Discipline (How We Work)

- Prefer **small PR-sized changes** (one goal, bounded files).
- Update documentation in `docs/` for every meaningful behavior/config/contract change in the same task.
- Every completed update must include at least one traceable `.md` update (plan/runtime/report) so progress remains visible without code diff inspection.
- Run tests locally before “done”.
- Never print secrets; never commit `.env`.
- If you must touch frozen areas (Execution/Guards/Contracts), explain why and add regression tests.

## 6) Test Artifact Hygiene

- Pytest/test temporary artifacts must use pytest `tmp_path`/`tmp_path_factory` or OS-level session-isolated
  temporary storage (see `conftest.py`'s own basetemp handling for the canonical pattern in this repo).
- Do not create persistent repo-local `.pytest-*` or test scratch directories.
- Successful temporary artifacts must be cleaned automatically. Failure evidence must use bounded retention
  (kept only until the next session confirms the owning process has exited — never indefinitely).
- Never solve test-artifact accumulation merely by adding broad `.gitignore` rules; the primary fix is not
  generating the artifact inside the repository in the first place.

## 7) Storage and Temporary-Artifact Hygiene

This rule applies to every human and engineering agent, including Claude and Codex. Temporary engineering
artifacts are session-scoped resources. Their default lifecycle is **create -> use -> verify the result is
preserved -> clean up**. A successful task is not an exception to cleanup.

### 7.1 Git worktrees

- Do not create a Git worktree unless isolation is required. Prefer, in order: the current worktree, an
  existing compatible temporary worktree, then one new temporary worktree.
- Before creating one, run `git worktree list --porcelain` and determine whether an existing worktree can be
  reused. A dirty primary worktree alone does not justify multiple temporary worktrees.
- A task may have at most one temporary worktree. Do not create arbitrary sibling directories such as
  `C:\Trading_Agent_System_fix`, `_final`, `_test`, or `_<task>` without explicit approval.
- If unavoidable, use one controlled project-managed temp/worktree location following the repository's existing
  convention; do not scatter permanent-looking worktrees around `C:\`.
- Once commits are safely preserved, remove completed worktrees with `git worktree remove <path>` and
  `git worktree prune`. Keep provenance branches when useful, but not completed working directories.

### 7.2 Tests, debugging, and generated data

- Test artifacts must use `tmp_path`, `tmp_path_factory`, or OS-level session-isolated storage. Successful runs
  leave zero repo-local pytest temporary directories. Failure evidence has bounded run-count or time retention;
  it is never indefinite.
- Scratch JSON/CSV, debug logs, one-off reports, temporary database copies, reproduction fixtures, and other
  investigation artifacts must not accumulate in the repository or project root. Preserve only canonical audit
  evidence and retain failed evidence only under bounded retention.
- Never delete canonical market or trading evidence, runtime state, broker evidence, event histories, UEF
  evidence, observation registries, accepted reports, or audit trails. Distinguish canonical data from
  regenerable cache and temporary engineering artifacts.
- Before copying a large production artifact for a test, prefer read-only access, bounded readers, streaming,
  day-scoped slices, or existing fixtures. Remove any temporary full copy after successful use.

### 7.3 Docker storage

- After major build or test work, inspect `docker system df`. Remove only items proven unused: stale test
  containers, dangling/intermediate images, temporary volumes, and completed-test build cache.
- Never remove a running image, production-state volume, runtime-evidence volume, required rollback image, or
  explicitly frozen acceptance image. Do not run `docker system prune -a` without explicit approval.
- Retain operationally useful development images only: the current accepted runtime image, its immediate rollback
  image, and explicitly required frozen acceptance images. Temporary test/build images are cleanup candidates
  after acceptance.

### 7.4 Completion and safety

- Any task that creates temporary resources must end with: zero temporary worktrees unless explicitly required,
  zero successful-run pytest leftovers, zero temporary containers, cleaned unneeded temporary images and large
  files, and zero unbounded failure-evidence stores.
- For anything intentionally retained, record what it is, why it is needed, its retention authority, and when it
  may be removed.
- Hygiene never authorizes destructive cleanup. Never use `git reset --hard`, `git clean -fd`, delete dirty user
  work, unknown directories, canonical runtime state, production evidence, or active Docker volumes. Preserve and
  report anything whose ownership or purpose is unclear.
