# 2026-09-30 P1.3 Final Closure Attempt: Paper Connectivity + Host/Docker Resource Benchmark

## Scope

Final P1.3 acceptance actions against the frozen revision `68573419f1df90e07f9e7f4497d897d9ffc795fe`,
explicitly authorized by the operator: gracefully stopping and restarting the Host trading runtime,
starting/stopping the frozen Docker trading runtime, real (non-order) Kiwoom Paper broker connectivity,
and a three-mode Host vs. Docker resource benchmark. No BUY/SELL order was placed. No source code, Docker
configuration, or UEF change was made. Real credentials were consumed by the runtime but never printed,
logged, or committed.

## Frozen-SHA Kiwoom Paper connectivity: 2 of 3 PASS, 1 structural FAIL

The Host runtime was cleanly stopped (its own graceful-stop mechanism; verified no remaining processes,
lock released, ownership lease allowed to expire naturally) and the frozen image was started against an
isolated state directory with real Paper credentials (`EXECUTION_MODE=real`, `KIWOOM_MODE=mock`,
`EXECUTION_ENABLED=false`, `ALLOW_REAL_EXECUTION=false`).

- **PAPER_AUTH = PASS.** A real token was obtained directly from Kiwoom's own mock/paper sandbox
  (`https://mockapi.kiwoom.com`) via the existing, executor-independent `KiwoomTokenClient`. Token value
  never printed.
- **PAPER_ACCOUNT_QUERY = PASS.** A real account balance was retrieved via the existing, also
  executor-independent `KiwoomPortfolioReader`/`KiwoomAccountClient` path. Balance/position detail not
  printed to logs.
- **PAPER_OPEN_ORDER_QUERY = FAIL -- structural, not a connectivity failure.** Every existing production
  code path for order/fill queries (`KiwoomOrderFillReader.get_open_orders_now`, and the equivalent
  `ka10075`/`kt00009` calls inside `KiwoomAccountSnapshotCollector`, and the generic
  `CompositeSkillRunner` skill path) routes through `KiwoomBrokerTruthClient` -> `get_executor()` ->
  `RealExecutor.preflight_check()`, which unconditionally requires `EXECUTION_ENABLED=true` -- for any
  call, read or mutating. With `EXECUTION_ENABLED=false` (the mandated safety configuration for this
  check), the call is rejected before any network request is attempted
  (`ExecutionDisabledError`). No un-gated production read path for order/fill data exists in this
  codebase today. This was verified by direct inspection of every code path that reaches these API IDs,
  not inferred from one failure.

`EXECUTION_DISPATCH_OCCURRED = NO`. `BROKER_ORDER_REQUEST_OCCURRED = NO` throughout.

Because not all three required checks passed, **`DOCKER_TECHNICAL_ACCEPTANCE` and `P1_3_CLOSED` remain
`NO`** -- this is reported honestly rather than closing on a partial result. The open item is narrow and
precisely diagnosed: a genuinely read-only open-order query needs its own code path that does not share
the order-dispatch executor's `EXECUTION_ENABLED` gate, or an explicit, deliberate decision that this
gate should stay unconditional for order-adjacent reads too. That decision is a source change and is
out of scope for this evidence-collection pass.

The Host runtime was restored immediately afterward (see below).

## Host vs. Docker resource benchmark

Three operational modes were measured on this machine, each sampled repeatedly (10-30s interval samples
per mode; the two later modes at a faster cadence per an explicit time-boxing request, reusing already-
collected valid samples rather than repeating work):

- **Mode A -- Host trading only, Docker fully stopped** (Docker Desktop itself exited via `docker desktop
  stop`, not just the containers): system memory averaged **~11.9 GiB used** (peak ~12.5 GiB), ~3.4 GiB
  free at minimum, ~48% average system CPU, Host Python process ~265 MiB RSS average (peak ~442 MiB).
  Zero Docker/WSL2 overhead (confirmed 0 MB for both `vmmemWSL` and Docker Desktop's own processes).
- **Mode B -- Host trading + Docker observability stack (web/api/cloudflared)**: system memory averaged
  **~13.5 GiB used** (peak ~14.6 GiB), free memory dropped as low as **~1.3 GiB**, ~44% average CPU, Host
  Python ~243 MiB RSS average. Docker's own footprint: `vmmemWSL` ~815 MiB average, Docker Desktop
  backend processes ~231 MiB average -- roughly **1.0 GiB of fixed overhead** just for observability to be
  available.
- **Mode C -- Frozen Docker trading runtime + Docker observability, Host stopped**: system memory averaged
  **~12.9 GiB used** (peak ~13.2 GiB), ~2.7 GiB free at minimum, ~36% average CPU. `vmmemWSL` ~820 MiB
  average, Docker Desktop backend ~231 MiB average -- essentially the same fixed Docker overhead as Mode
  B. The trading container itself measured a separately-captured **~59 MiB** average (well below the 1
  GiB container limit, consistent with every earlier measurement of this same image today), `OOMKilled`
  false, `RestartCount` 0.

Deltas (average system memory used): **B - A = +1.6 GiB**, **C - A = +1.0 GiB**, **C - B = -0.6 GiB**.
Docker Desktop/WSL2's own baseline overhead (~1.0 GiB) is essentially identical whether the trading
workload runs on it or not -- it is the cost of having observability available at all, not of the trading
container specifically. The trading container itself is lighter than the Host's native Python process
(~59 MiB vs. ~243-265 MiB), which is why Mode C measured slightly lower overall than Mode B in this
window; some of that gap is also ordinary background-process variance across the ~25-minute test window
(other applications were not perfectly held constant, per the benchmark's own fairness caveat).

**Assessment**: `HOST_RESOURCE_FIT = GOOD` (leanest, zero fixed tax). `HYBRID_RESOURCE_FIT = MARGINAL` on
this specific machine right now -- available memory fell to ~1.3 GiB during the observability-on window,
which is tight on a 15.9 GiB system already showing earlier-observed pressure. `FULL_DOCKER_RESOURCE_FIT
= ACCEPTABLE` -- comparable to Hybrid, not clearly worse, since the containerized trading process itself
is lighter than the Host's native one, but it still carries the same ~1 GiB Docker/WSL2 tax that Hybrid
does.

Advisory-only recommendation (not a decision -- `CANONICAL_RUNTIME_DECISION` stays `DEFERRED` per explicit
instruction): **Hybrid** (Host trading + Docker observability) is the safest default to keep -- it is the
configuration already proven stable over 9+ continuous hours today, and Full-Docker's own remaining gap
(no un-gated open-order read path) would need to be resolved before it could be operated with the same
confidence.

## Final state left running

Host trading runtime restored and healthy (fresh PID, fresh ownership lease, heartbeat current, no
`recovery_required`). Docker observability stack (web/api/cloudflared) restored to its pre-benchmark
state. No Docker trading runtime left running.

## Status

PAPER_AUTH = PASS, PAPER_ACCOUNT_QUERY = PASS, PAPER_OPEN_ORDER_QUERY = FAIL (structural)
DOCKER_TECHNICAL_ACCEPTANCE = FAIL
P1_3_CLOSED = NO
CANONICAL_RUNTIME_DECISION = DEFERRED (Hybrid recommended as the safe default to keep; not a final choice)
