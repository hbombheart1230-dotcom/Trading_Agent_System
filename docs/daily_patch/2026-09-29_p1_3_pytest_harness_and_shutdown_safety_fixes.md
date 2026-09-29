# 2026-09-29 P1.3 Pytest Harness Speedup and Shutdown-Flag Safety Fix

## Scope

Test-harness/tooling performance work for the P1.3 Docker/runtime-safety acceptance track, plus four
correctness fixes surfaced while isolating the resulting bottlenecks. No Scanner/Strategist/Monitor
policy, decision logic, Reporter, UEF, or Alpha Board semantics touched. No Docker soak run, no P1.3
acceptance commit, no P1.5 refactor performed as part of this change.

## Test-harness performance

- `conftest.py`'s production-write detector (`reports/`+`data/`, ~578k files / ~90GB on this host) is now
  two-tier: a `fast` (default) mode that fully scans a handful of small, high-value state subtrees plus a
  depth-bounded presence/mtime scan of the full trees (~4.4s per session, from ~115s single-threaded / ~64-74s
  threaded), and an unweakened `full` mode (`PRODUCTION_WRITE_AUDIT_MODE=full`) that walks every file, for a
  deliberate pre-freeze audit. The fast tier's disclosed gap: an in-place overwrite of an existing file deeper
  than 3 levels below `reports/`/`data/` is not detected -- run `full` for an exhaustive check.
- Fixed a concurrent-pytest collision: `pytest.ini`'s fixed `--basetemp=.pytest-work` caused two pytest
  processes running at once to race on the same `tmp_path` directories (`[WinError 32]`, reproduced directly).
  `conftest.py` now rewrites `basetemp` to a PID-unique `.pytest-work-<pid>` per process, with best-effort
  cleanup of stale directories from dead processes.
- Registered `fast`/`p1_3`/`heavy`/`docker`/`benchmark` pytest markers and applied `@pytest.mark.heavy` to the
  9 test functions confirmed (by direct grep + inspection, not by name alone) to spawn a real OS subprocess or
  `multiprocessing.Process`: `test_step5c_fix1_shared_ownership.py::test_fix1_cwd_independent_default_path`
  and `::test_fix1_real_multiprocess_cross_path`;
  `test_step5c_fix2_ownership_capability.py::test_high1_t4_real_multiprocess_same_intent_total_calls_le_1`,
  `::test_high3_t8b_real_multiprocess_different_intents_same_physical_order`, and
  `::test_relative_env_override_is_repo_root_anchored_not_cwd`;
  `test_step5c_fix3_authoritative_intent.py::test_t12_real_multiprocess_normalization_alias_attack_total_calls_le_1`
  and `::test_orphan_from_real_process_crash_is_retained_and_observable`;
  `test_benchmark_operator_visibility_memory.py::test_measure_runs_isolated_child_and_returns_expected_shape`
  and `::test_measure_run_card_also_works`. `test_p0d_runtime_ownership.py`'s `test_own*` tests were checked
  and confirmed NOT heavy (in-process dual-instance simulation, no real subprocess) -- not moved.
- A reconstructed 20-file P1.3 targeted set now runs together in 45.58s (see "P1.3 targeted regression: final
  state" below for the final pass count), down from a run that exceeded 25 minutes before these fixes. Neither
  the targeted run nor the separate heavy subset created any net new file or directory under `reports/`/`data/`
  (measured before/after via the fast-tier manifest: no canonical-UUID artifact explosion).

## Correctness fixes found while isolating the bottleneck

- **Shutdown-flag silent discard** (`libs/runtime/live_loop_runner.py`): `run_live_loop` used
  `isinstance(shutdown_flag, ShutdownRequested)` to decide whether to honor a caller-supplied shutdown flag,
  silently substituting a fresh, never-triggered flag for anything that didn't literally subclass the concrete
  class. Combined with `once=False`, this turned a test's own tick-count-based shutdown flag into a no-op --
  the loop ran forever (reproduced directly: 785+ ticks with no sign of stopping). Replaced with a duck-typed
  resolution: `None` gets a fresh `ShutdownRequested()`, a compatible object (`.requested`, `.signal_name`,
  `.request()`) is preserved as-is, and an incompatible one now fails loudly (`TypeError`) instead of being
  silently dropped. SIGTERM/SIGINT semantics for the default (no `shutdown_flag=`) path are unchanged.
- **Pytest path-isolation regression** (`libs/core/path_isolation.py`): the basetemp-collision fix above
  renamed pytest's basetemp to `.pytest-work-<pid>`, which broke `resolve_runtime_write_path`'s existing,
  documented exception for pytest-owned paths (`_PYTEST_OWNED_REPO_SUBDIRS`, an exact-string match against the
  literal `.pytest-work`). Every explicit, already-isolated `tmp_path`-derived absolute path started getting
  redirected a second time, breaking the pre-existing, dedicated contract test
  `test_p0_pytest_isolation_fix2.py::test_resolve_runtime_write_path_passes_through_tmp_path` and, downstream,
  `test_p0b_step5d_crash_reconciliation.py`'s and two `test_step5c_fix*` tests' explicit-override assertions.
  Fixed by matching the bare name or a `<name>-` prefix instead of exact equality. This was a same-session
  regression introduced and fixed within this change, not a pre-existing defect.
- **Step5D durable audit trail**: was in fact already implemented correctly in
  `scripts/step5d_crash_reconciliation.py::resolve()` -- it was only failing to be *observed* because of the
  path-isolation regression above (the audit file was silently written to the isolated root instead of the
  caller's explicit `tmp_path`-based path). No change needed to the audit-write logic itself once the
  path-isolation fix landed; verified directly (`test_resolve_executed_transitions_state_and_releases_lease_and_audits`
  now passes).
- **`data/logs/events.jsonl`, `data/logs/controlled_mock_lanes/<day>/`, and
  `data/state/kiwoom_market_status_listener.json` production-write false positives**: this host runs a live
  trading process concurrently with test runs, and all three paths are confirmed (by direct evidence -- content
  inspection, timing correlation, and code-path tracing to the real, non-test writer) to be written by that
  live process, not by any test. Added a fast-tier-only (not shared with the `full`/heavy audit mode) known-
  external-host allowlist in `conftest.py` so the default dev-loop guard no longer flags them, while the `full`
  audit mode still sees every byte, unweakened.

## Stale executor-exception fixture correction

`test_paper_trading_execution_finalization.py::test_unexpected_exception_still_raises_not_swallowed` originally
omitted the BUY price and its fresh empty open-order snapshot, so normal admission guards stopped before the fake
executor could run -- a stale test fixture, not a production execution-safety regression. The fixture now supplies
both valid inputs and asserts that the fake executor was called exactly once before its deliberate `RuntimeError`
propagates out of `execute_from_packet`. Verified directly (traceback confirms the call path
`execute_from_packet -> execute_owned_order -> executor.execute -> raise`, and `executor.calls == 1` before the
exception surfaces) that the test genuinely reaches the executor rather than merely turning green. No production
execution code, guard semantics, Step5C, Step5D, or execution-readiness logic changed for this fix.

## P1.3 targeted regression: final state

With the fixture corrected, the same 20-file P1.3 targeted set (`-m "not heavy"`) runs **220 passed, 0 failed,
9 heavy deselected** in **45.58s**. The separate 9-test heavy subset passes cleanly as well (9 passed, 0 failed).
No known failures remain in this targeted set.

## P1.3 acceptance status (explicit)

This change covers test-harness/tooling correctness and speed, and the P1.3 implementation's own targeted/heavy
test coverage -- it is not, by itself, the P1.3 Docker operational acceptance.

- IMPLEMENTED = YES
- TARGETED VALIDATION = PASS (220 passed, 0 failed, 9 heavy deselected, 45.58s)
- HEAVY VALIDATION = PASS (9 passed, 0 failed)
- DOCKER OPERATIONAL ACCEPTANCE = PENDING
- FULL-SESSION SOAK = PENDING
- P1.3 CLOSED = NO
