# 2026-09-30 P1.3 Docker Operational Acceptance (IN PROGRESS)

## Scope

Validation only -- no Docker architecture, runtime ownership, Step5C/Step5D, SIGTERM, reporting, UEF,
strategy, Q10/Q12, Scanner, Strategist, or Alpha Board changes in this pass. All evidence below
corresponds to the frozen P1.3 acceptance revision `68573419f1df90e07f9e7f4497d897d9ffc795fe`, built
from a clean detached git worktree (not the working tree's in-progress changes).

## What this validates

The currently-running Host trading runtime (live during this validation, real market hours) was never
touched, killed, restarted, or signaled. All Docker validation used an isolated `test-state/` data and
reports volume, `EXECUTION_ENABLED=false`, and `EXECUTION_MODE=mock` -- no broker order dispatch
anywhere in this pass.

## Results so far

- **Image/source parity**: the built image's baked-in `graphs/`, `libs/`, `scripts/`, `config/`,
  `data/specs/` are byte-identical (1070/1070 file hashes) to the frozen commit's tree, and confirmed
  DIFFERENT from the current (newer) working tree for files known to have changed since -- proving the
  image was not accidentally built from modified/dirty source. No `.env.real` or credential file is
  baked into the image.
- **Isolated smoke**: container starts, `python scripts/run_session.py` runs as the entrypoint's direct
  child under Docker's own PID-1 init (compose `init: true`, by design -- SIGTERM is forwarded correctly),
  health reports `healthy` within seconds, runtime ownership lease acquired, heartbeat fresh, both the
  isolated data and reports volumes are writable (state files and canonical report artifacts were
  written and persisted).
- **Double-runtime protection**: a second container instance attached to the same isolated lock file was
  correctly rejected (`lock_active`, exit code 4) while the first instance kept running undisturbed.
- **State/volume persistence**: `runtime_ownership.db`, the Step5C intent-state DB, `state.json`, the
  event log, and canonical reports all survived a full container recreate (new container ID) without
  loss; the intent-state DB was byte-identical before and after.
- **Execution-readiness fail-closed**: the isolated environment correctly reports execution as
  `NOT_READY` (missing portfolio-reconciliation baseline, and after a simulated crash, an additional
  Step5D recovery-required condition) rather than defaulting to ready.
- **Crash/restart**: a hard `SIGKILL` left an unreleased (correctly non-strict, age-based) lock behind,
  which blocked immediate reclaim for the configured 300s staleness window (observed: the container's
  own `restart: on-failure:5` policy exhausted its retries and stopped cleanly rather than crash-looping
  forever) and reclaimed correctly once that window passed, logging the prior holder's full lease detail
  before continuing ("stale takeover" is explicit and durable, not silent).
- **SIGTERM drain**: `docker compose stop` completed in ~1.3s, exit code 0, `OOMKilled=false`, and the
  container's own log shows the drain handler engaging cleanly ("shutdown requested via SIGTERM during
  idle sleep, stopping") with the lock file removed (ownership released) before exit.
- **Resource cost**: container-only memory stayed flat at roughly 65 MiB idle/active in this isolated
  mock smoke (well under the 1 GiB limit); `RestartCount=0` and `OOMKilled=false` at every steady state.
  The current Host process (still running, undisturbed) measured roughly 180 MiB working set / 443 MiB
  private bytes. Docker's own total Windows-side footprint (Docker Desktop's backend processes plus the
  WSL2 VM) measured roughly 3+ GiB at the time of this check -- most of that is the WSL2 VM's own
  memory ceiling/build-layer cache, not this one container's requirement, and is not a cost this specific
  container incurs on its own. Both figures are recorded as measured trade-offs; no runtime choice is
  made from them.

## Deliberately not run in this pass

- **Paper broker connectivity** (Kiwoom sandbox auth/account/open-order query): skipped, not failed.
  Running it requires `compose.trading.real.yaml`, which by design shares the exact same canonical
  `data/`/`reports/` directories as the Host runtime (that is the whole point of that file -- one
  ownership authority, one shared state). With the real Host runtime actively trading during today's
  real market session, starting a second process against that same shared state right now was judged
  unsafe and out of proportion to this validation's purpose. Deferred to a deliberate, explicitly
  scheduled window.
- **Full-session soak**: started (fresh isolated container, healthy, generation 1 lease) during today's
  live market window, but a full session (through EOD cascade and post-EOD survival) cannot be completed
  synchronously within this pass. Recorded as PENDING, not fabricated as complete.

## Status

DOCKER_OPERATIONAL_ACCEPTANCE = IN_PROGRESS (smoke-level acceptance passed; soak evidence pending)
FULL_SESSION_SOAK = PENDING
P1_3_CLOSED = NO
CANONICAL_RUNTIME_DECISION = DEFERRED (out of scope for this pass by explicit instruction)
