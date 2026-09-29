from __future__ import annotations

import signal
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from libs.runtime.live_loop_lock import acquire_live_loop_lock, refresh_live_loop_lock, release_live_loop_lock
from libs.runtime.market_hours import MarketHours, now_kst
from libs.runtime.kiwoom_market_status import KiwoomMarketStatusListener
from libs.runtime.runtime_ownership import SQLiteRuntimeOwnershipStore, new_runtime_instance_id

_DEFAULT_OWNERSHIP_LEASE_SEC = 30.0


class ShutdownRequested:
    """P0-C (restart-safety hardening, 2026-09-17): mutable flag a SIGTERM/
    SIGINT handler sets, checked only at tick BOUNDARIES (top of the loop,
    and between sleep steps).

    This intentionally does nothing to interrupt an in-flight tick --
    Supervisor/guard/execution authority (Step5C's SQLite CAS ownership in
    libs/execution/intent_execution_owner.py, the guard chain in
    execute_from_packet.py) remain the only things that ever decide whether
    an order is admitted or dispatched. A signal must never be able to
    short-circuit that authority (INV-6) -- so this flag is deliberately
    "dumb": it can only stop a FUTURE tick from starting, never alter or
    bypass a tick already in progress. Primary execution safety continues
    to come from persistent idempotency + broker reconciliation + guards,
    exactly as before this change -- graceful shutdown is a latency/
    operability improvement on top of that, never a substitute for it.
    """

    def __init__(self) -> None:
        self.requested = False
        self.signal_name = ""

    def request(self, signal_name: str) -> None:
        self.requested = True
        self.signal_name = signal_name


def _resolve_shutdown_flag(shutdown_flag: Optional[Any]) -> ShutdownRequested:
    """None -> a fresh ShutdownRequested(). A real ShutdownRequested, or any
    object exposing the same interface (.requested, .signal_name,
    .request(signal_name)), is preserved as-is. Anything else fails loudly.

    A prior `shutdown_flag if isinstance(shutdown_flag, ShutdownRequested)
    else ShutdownRequested()` silently discarded any caller-supplied flag
    that didn't literally subclass ShutdownRequested (e.g. a duck-typed
    test double), substituting a fresh flag that only a real OS signal
    could ever set. Combined with `once=False`, that turned
    tests/test_paper_trading_execution_finalization.py::
    test_execution_disabled_survives_many_ticks_via_run_live_loop's own
    tick-count-based shutdown flag into a no-op -- the loop never stopped
    (confirmed directly: 785+ ticks with no sign of terminating before
    being killed externally). Failing loudly here, instead of silently
    substituting, is the fix: a caller relying on its own flag being
    honored now finds out immediately if it doesn't satisfy the interface,
    rather than getting an unbounded loop.
    """
    if shutdown_flag is None:
        return ShutdownRequested()
    if isinstance(shutdown_flag, ShutdownRequested):
        return shutdown_flag
    required_attrs = ("requested", "signal_name", "request")
    missing = [name for name in required_attrs if not hasattr(shutdown_flag, name)]
    if not missing and not callable(getattr(shutdown_flag, "request", None)):
        missing = ["request (not callable)"]
    if missing:
        raise TypeError(
            "run_live_loop(shutdown_flag=...) must be None, a ShutdownRequested "
            "instance, or an object providing the same interface "
            "(.requested: bool, .signal_name: str, .request(signal_name) -> None); "
            f"got {type(shutdown_flag)!r} missing/incompatible: {missing}"
        )
    return shutdown_flag


def install_shutdown_handler(flag: ShutdownRequested) -> Dict[str, bool]:
    """Best-effort SIGTERM/SIGINT registration; never raises.

    Returns which signals were actually hooked, for observability/tests.
    `signal.signal()` only works in the main thread of the main interpreter
    -- if this is ever called from anywhere else, registration is skipped
    and the loop still exits cleanly via its existing normal exit paths
    (--once, session-window close), just without early SIGTERM drain.
    """

    installed: Dict[str, bool] = {}
    for name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            def _handler(signum, frame, _flag=flag, _name=name):  # noqa: ANN001
                _flag.request(_name)

            signal.signal(sig, _handler)
            installed[name] = True
        except Exception:
            installed[name] = False
    return installed


def run_live_loop(
    state: Dict[str, Any],
    *,
    once: bool,
    sleep_sec: int,
    session_hard_gate: bool,
    lock_path: Path,
    lock_stale_sec: int,
    now_fn: Callable[[], datetime] = now_kst,
    run_once_fn: Callable[..., Dict[str, Any]],
    sleep_fn: Callable[[float], None] = time.sleep,
    market_hours: MarketHours | None = None,
    shutdown_flag: Optional[Any] = None,
    install_signal_handler: bool = True,
    ownership_store: Optional[SQLiteRuntimeOwnershipStore] = None,
    ownership_instance_id: Optional[str] = None,
    ownership_lease_sec: float = _DEFAULT_OWNERSHIP_LEASE_SEC,
    allow_stale_ownership_takeover: bool = True,
) -> int:
    if state.get("m13_tick_pipeline") == "legacy_m10" and not state.get("symbol"):
        raise SystemExit("symbol is required for legacy_m10: set --symbol or SYMBOL/UNIVERSE_SYMBOLS env")

    if session_hard_gate:
        hours = market_hours if isinstance(market_hours, MarketHours) else MarketHours()
        check_dt = now_fn()
        if not hours.is_open(check_dt):
            print(f"live_loop aborted: market_closed session_hard_gate=true now_kst={check_dt.isoformat()}")
            return 5

    acquired, reason = acquire_live_loop_lock(lock_path, lock_stale_sec=max(1, int(lock_stale_sec)))
    if not acquired:
        print(f"live_loop lock not acquired: {reason} lock_path={lock_path}")
        return 4

    # P0-D (real-readiness hardening, 2026-09-17): execution AUTHORITY, on
    # top of (never a replacement for) the coarse PID-heartbeat lock above.
    # The lock only ever answers "is some host-local process alive"; it is
    # not meaningful across Docker PID namespaces (empirically proven --
    # see runtime_ownership.py's own docstring) and was never designed to
    # answer "which of two runtimes sharing the same persistent state may
    # dispatch." This SQLite/CAS lease is that answer, and fails CLOSED
    # (never silently proceeds) whenever a still-live lease is held by a
    # different instance_id.
    store = ownership_store if ownership_store is not None else SQLiteRuntimeOwnershipStore()
    instance_id = str(ownership_instance_id or new_runtime_instance_id())
    ownership_result = store.acquire(
        instance_id=instance_id,
        lease_seconds=float(ownership_lease_sec),
        allow_stale_takeover=bool(allow_stale_ownership_takeover),
    )
    if not ownership_result.ok:
        print(
            f"live_loop ownership not acquired: {ownership_result.reason} "
            f"holder={ownership_result.holder}"
        )
        release_live_loop_lock(lock_path)
        return 6
    if ownership_result.recovery_required:
        # Lease expiry alone is NEVER execution readiness -- this instance
        # now holds dispatch authority (took over a stale/orphaned lease),
        # but must not treat that as "safe to trade" on its own. The
        # existing per-tick reconciliation this runtime already runs
        # unconditionally -- portfolio snapshot + preflight guard
        # (graphs/nodes/build_portfolio_snapshot.py,
        # commander_runtime.py's _apply_portfolio_preflight_guard),
        # Step5C orphan-claim visibility (scripts/docker_healthcheck.py),
        # and the P0-A open-order snapshot/guard added in this same phase
        # -- is what actually enforces the recovery chain before any BUY
        # dispatch; this flag is carried into state purely for
        # observability/health reporting of *why* recovery evidence
        # matters this run.
        print(
            f"live_loop acquired ownership via stale takeover "
            f"(generation={ownership_result.generation}, prior_holder={ownership_result.holder}); "
            "full recovery/readiness evidence required before this run may be trusted"
        )
    state["runtime_ownership"] = {
        "instance_id": instance_id,
        "generation": ownership_result.generation,
        "recovery_required": bool(ownership_result.recovery_required),
        "acquired_at": ownership_result.acquired_at,
    }

    flag = _resolve_shutdown_flag(shutdown_flag)
    if install_signal_handler:
        install_shutdown_handler(flag)

    exit_code = 0
    market_status_listener = KiwoomMarketStatusListener()
    market_status_listener.start()
    try:
        while True:
            if flag.requested:
                print(f"live_loop draining: shutdown requested via {flag.signal_name}, no new tick will start")
                break
            refresh_live_loop_lock(lock_path)
            ownership_refresh = store.refresh(instance_id=instance_id, lease_seconds=float(ownership_lease_sec))
            if not ownership_refresh.ok:
                # We have LOST execution authority (our lease expired and a
                # different instance took over while we kept running, or
                # our own ownership row is simply gone). No new tick may
                # start under a stolen/absent claim -- stop immediately,
                # before run_once_fn, exactly like the pre-loop ACQUIRE
                # gate above.
                print(
                    f"live_loop ownership lost: {ownership_refresh.reason} "
                    f"holder={ownership_refresh.holder} -- stopping before next tick"
                )
                exit_code = 7
                break
            state = run_once_fn(state, dt=now_fn())
            refresh_live_loop_lock(lock_path)
            store.refresh(instance_id=instance_id, lease_seconds=float(ownership_lease_sec))

            if once:
                break
            if flag.requested:
                print(f"live_loop draining: shutdown requested via {flag.signal_name} after tick, stopping before next sleep")
                break
            # Sleep in short, flag-checked steps (rather than one long
            # sleep_fn(sleep_sec) call) so a SIGTERM/SIGINT arriving during
            # the idle window is honored within ~1s, not up to sleep_sec
            # (default 60s) later -- meaningful under Docker's default
            # stop_grace_period (10s) before SIGKILL.
            remaining = max(1, int(sleep_sec))
            while remaining > 0 and not flag.requested:
                step = min(1.0, float(remaining))
                sleep_fn(step)
                remaining -= step
            if flag.requested:
                print(f"live_loop draining: shutdown requested via {flag.signal_name} during idle sleep, stopping")
                break
    finally:
        market_status_listener.stop()
        release_live_loop_lock(lock_path)
        # Only ever releases OUR OWN lease (release() is a strict no-op
        # otherwise) -- if ownership was already lost to a takeover above,
        # this does not disturb the new owner's claim.
        store.release(instance_id=instance_id)

    return exit_code
