from __future__ import annotations

import signal
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from libs.runtime.live_loop_lock import acquire_live_loop_lock, refresh_live_loop_lock, release_live_loop_lock
from libs.runtime.market_hours import MarketHours, now_kst
from libs.runtime.kiwoom_market_status import KiwoomMarketStatusListener
from libs.runtime.runtime_ownership import OwnershipResult, SQLiteRuntimeOwnershipStore, new_runtime_instance_id

_DEFAULT_OWNERSHIP_LEASE_SEC = 30.0
_DEFAULT_OWNERSHIP_WAIT_POLL_SEC = 1.0
_DEFAULT_OWNERSHIP_WAIT_MARGIN_SEC = 5.0
SHUTDOWN_REQUESTED_REASON = "shutdown_requested"


def _acquire_ownership_with_bounded_wait(
    store: SQLiteRuntimeOwnershipStore,
    *,
    instance_id: str,
    lease_seconds: float,
    allow_stale_takeover: bool,
    sleep_fn: Callable[[float], None],
    wait_poll_sec: float = _DEFAULT_OWNERSHIP_WAIT_POLL_SEC,
    wait_margin_sec: float = _DEFAULT_OWNERSHIP_WAIT_MARGIN_SEC,
    should_abort: Optional[Callable[[], bool]] = None,
):
    """2026-10-02 P1.3-R2 fix: a still-VALID other-instance lease is never
    stolen (acquire() itself already refuses this unconditionally -- this
    wrapper changes nothing about that). What changes is the CALLER's
    reaction: instead of giving up immediately (which, under Docker's
    on-failure restart policy, meant every restart attempt completing
    faster than the old lease's own natural expiry would exhaust the
    retry budget before the legitimate stale-takeover path ever became
    reachable -- a second restart-storm layer, found during the P1.3-R1
    controlled-restart validation, distinct from and on top of the
    already-fixed PID-1 file-lock defect), this waits -- bounded by the
    REJECTED attempt's own observed `lease_expires_at` (not a second,
    independently-hardcoded duration) plus a small fixed safety margin --
    then retries. Once the real lease has legitimately expired,
    store.acquire()'s own existing stale-takeover path (unchanged, not
    reimplemented here) takes over exactly as it already does outside
    Docker. A lease that is somehow still valid at the end of the bounded
    window (clock skew, a genuinely very-long-lived other owner) times out
    and fails closed -- this never loops forever and never dispatches
    before ownership is actually held.
    """
    deadline: Optional[float] = None
    waited = False
    while True:
        # P1.3-R5-B: a shutdown request (SIGTERM / `docker stop`) is checked
        # BEFORE every acquire attempt, so a contender told to stop never
        # takes ownership afterwards -- not even if the old lease happens to
        # expire right after the request. Legitimate stale takeover with no
        # shutdown request is unchanged.
        if should_abort is not None and should_abort():
            print(f"OWNERSHIP_WAIT_ABORTED_SHUTDOWN instance_id={instance_id} waited={waited}")
            return OwnershipResult(
                ok=False, reason=SHUTDOWN_REQUESTED_REASON, instance_id=instance_id, generation=0,
                acquired_at=0.0, lease_expires_at=0.0, recovery_required=False,
            )
        result = store.acquire(
            instance_id=instance_id, lease_seconds=lease_seconds,
            allow_stale_takeover=allow_stale_takeover,
        )
        if result.ok or result.reason != "owned_by_other_instance":
            if waited and result.ok:
                print(f"OWNERSHIP_ACQUIRED_AFTER_WAIT instance_id={instance_id} generation={result.generation}")
            return result

        now = time.time()
        remaining_ttl = max(0.0, result.lease_expires_at - now)
        if deadline is None:
            deadline = now + remaining_ttl + float(wait_margin_sec)
            print(
                f"OWNERSHIP_WAIT_STARTED current_owner={result.holder} "
                f"lease_expiry={result.lease_expires_at} remaining_ttl_sec={remaining_ttl:.1f}"
            )
        if now >= deadline:
            print(f"OWNERSHIP_WAIT_TIMEOUT current_owner={result.holder}")
            return result
        print(f"OWNERSHIP_RETRY remaining_wait_sec={deadline - now:.1f}")
        waited = True
        sleep_fn(max(0.01, min(float(wait_poll_sec), deadline - now)))


_HEARTBEAT_INTERVAL_DIVISOR = 3.0
_MIN_HEARTBEAT_INTERVAL_SEC = 0.02


def _resolve_heartbeat_interval_sec(lease_seconds: float, explicit: Optional[float]) -> float:
    """Derived from the EXISTING lease length (never a second, competing
    contract): a third of the lease, i.e. two full refreshes can be missed
    before the lease lapses. An explicit override must still sit strictly
    inside the lease, otherwise the lease could expire between refreshes."""
    lease = float(lease_seconds)
    interval = float(explicit) if explicit is not None else lease / _HEARTBEAT_INTERVAL_DIVISOR
    interval = max(_MIN_HEARTBEAT_INTERVAL_SEC, interval)
    if interval >= lease:
        raise ValueError(f"ownership heartbeat interval {interval}s must be < lease_seconds {lease}s")
    return interval


class OwnershipHeartbeat:
    """P1.3-R3 (2026-10-02): keeps the SAME existing SQLite ownership lease
    fresh while a long tick runs, independent of tick boundaries.

    Before this, ownership was refreshed only at tick boundaries, but ticks
    were observed at median ~36s / p90 ~137s / max ~434s (and a ~55 minute
    closeout tick), against a 30s lease -- so a perfectly healthy, live owner
    routinely looked stale and a contender's stale-takeover would have
    succeeded mid-tick. This is NOT a second ownership authority: it only
    calls SQLiteRuntimeOwnershipStore.refresh() (unchanged), whose CAS is
    keyed on this process's own instance_id, so it can only ever extend a
    lease this exact instance still holds. After a takeover the row's
    instance_id differs, refresh() fails, and this heartbeat records the loss,
    stops, and never writes again -- a superseded owner is never resurrected.
    Generation is compared as well as instance_id as a belt-and-braces check.

    Fail closed: ownership loss, or no successful refresh for a full lease
    period (store unreachable), sets `lost`; run_live_loop checks it before
    starting any tick and exits 7, exactly like its existing ownership-loss
    path. This cannot interrupt a tick already in flight (same constraint as
    the shutdown flag -- Step5C/guards remain the only dispatch authority).

    A crash takes the daemon thread down with the process, so the lease then
    expires naturally and R2's bounded wait / the store's stale-takeover path
    apply unchanged.
    """

    def __init__(
        self,
        store: SQLiteRuntimeOwnershipStore,
        *,
        instance_id: str,
        generation: int,
        lease_seconds: float,
        interval_sec: Optional[float] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._store = store
        self.instance_id = str(instance_id)
        self.generation = int(generation)
        self.lease_seconds = float(lease_seconds)
        self.interval_sec = _resolve_heartbeat_interval_sec(self.lease_seconds, interval_sec)
        self._clock = clock
        self._stop = threading.Event()
        self._lost = threading.Event()
        self.lost_reason = ""
        self.refresh_count = 0
        self._thread: Optional[threading.Thread] = None
        self._last_ok = self._clock()

    @property
    def lost(self) -> bool:
        return self._lost.is_set()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> "OwnershipHeartbeat":
        if self._thread is not None:
            return self
        self._last_ok = self._clock()
        self._thread = threading.Thread(target=self._run, name="ownership-heartbeat", daemon=True)
        self._thread.start()
        return self

    def _mark_lost(self, reason: str) -> None:
        self.lost_reason = reason
        self._lost.set()
        print(
            f"OWNERSHIP_HEARTBEAT_LOST instance_id={self.instance_id} generation={self.generation} "
            f"reason={reason} -- no further tick will start"
        )

    def _run(self) -> None:
        while not self._stop.wait(self.interval_sec):
            try:
                result = self._store.refresh(instance_id=self.instance_id, lease_seconds=self.lease_seconds)
            except Exception as exc:  # noqa: BLE001 - a transient store error must not kill the heartbeat
                if self._clock() - self._last_ok >= self.lease_seconds:
                    self._mark_lost(f"refresh_errors_exceeded_lease:{type(exc).__name__}")
                    return
                continue
            if not result.ok or int(result.generation) != self.generation:
                self._mark_lost(result.reason if not result.ok else "generation_changed")
                return
            self._last_ok = self._clock()
            self.refresh_count += 1

    def stop(self, timeout: float = 5.0) -> None:
        """Stops the thread and waits for it, so no refresh can land after
        the caller releases the lease."""
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=timeout)


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
    strict_owner_identity: bool = True,
    ownership_wait_poll_sec: float = _DEFAULT_OWNERSHIP_WAIT_POLL_SEC,
    ownership_wait_margin_sec: float = _DEFAULT_OWNERSHIP_WAIT_MARGIN_SEC,
    ownership_heartbeat_interval_sec: Optional[float] = None,
) -> int:
    if state.get("m13_tick_pipeline") == "legacy_m10" and not state.get("symbol"):
        raise SystemExit("symbol is required for legacy_m10: set --symbol or SYMBOL/UNIVERSE_SYMBOLS env")

    if session_hard_gate:
        hours = market_hours if isinstance(market_hours, MarketHours) else MarketHours()
        check_dt = now_fn()
        if not hours.is_open(check_dt):
            print(f"live_loop aborted: market_closed session_hard_gate=true now_kst={check_dt.isoformat()}")
            return 5

    # 2026-10-02 Docker PID-1/M13 restart-storm fix: strict_owner_identity=True
    # by default (reusing the exact same strict-identity primitive already
    # proven for closeout's single-owner guard, not a second locking
    # subsystem). Root cause this replaces: every fresh container gets PID 1
    # in its own namespace, so the OLD non-strict lock's age-based reclaim
    # was the only thing standing between a genuinely dead prior container
    # and a live one -- but Docker's default sub-second restart backoff
    # means a crashed container's restart attempts can all complete well
    # inside lock_stale_sec, so none of them ever qualified as "stale" even
    # though PID 1 in each fresh container is trivially "alive" to
    # pid_exists(). Strict mode reclaims on conclusively dead pid or
    # confirmed pid reuse (the OS-provided process creation timestamp
    # differs even though the pid number is identical) -- never on age --
    # so a new container's PID 1 correctly reclaims a PID-1 lock left by a
    # prior, now-dead container on its very first attempt, regardless of
    # how little wall-clock time has elapsed. Unaffected outside Docker: a
    # genuinely live Host process is never stolen from merely for running
    # long (see live_loop_lock.py's own module docstring for the full
    # acquire/release/refresh decision table).
    owner_token = uuid.uuid4().hex
    acquired, reason = acquire_live_loop_lock(
        lock_path, lock_stale_sec=max(1, int(lock_stale_sec)),
        strict_owner_identity=strict_owner_identity, owner_token=owner_token,
    )
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
    # P1.3-R5-B: the shutdown flag/handler is installed BEFORE the (possibly
    # waiting) ownership acquisition, not after it. Previously a SIGTERM
    # during R2's bounded wait hit Python's default action -- instant
    # termination, the PID lock left behind -- and a flag-less loop would
    # still have taken ownership after the wait.
    flag = _resolve_shutdown_flag(shutdown_flag)
    if install_signal_handler:
        install_shutdown_handler(flag)
    store = ownership_store if ownership_store is not None else SQLiteRuntimeOwnershipStore()
    instance_id = str(ownership_instance_id or new_runtime_instance_id())
    ownership_result = _acquire_ownership_with_bounded_wait(
        store,
        instance_id=instance_id,
        lease_seconds=float(ownership_lease_sec),
        allow_stale_takeover=bool(allow_stale_ownership_takeover),
        sleep_fn=sleep_fn,
        wait_poll_sec=float(ownership_wait_poll_sec),
        wait_margin_sec=float(ownership_wait_margin_sec),
        should_abort=lambda: bool(flag.requested),
    )
    if not ownership_result.ok and ownership_result.reason == SHUTDOWN_REQUESTED_REASON:
        # Asked to stop before ownership was ever acquired: nothing was
        # dispatched, no lease/generation changed, no heartbeat was started.
        # Release only the coarse PID lock this process already holds.
        print(f"live_loop shutdown requested via {flag.signal_name or 'flag'} before ownership was acquired; exiting cleanly")
        release_live_loop_lock(lock_path, strict_owner_identity=strict_owner_identity, owner_token=owner_token)
        return 0
    if not ownership_result.ok:
        print(
            f"live_loop ownership not acquired: {ownership_result.reason} "
            f"holder={ownership_result.holder}"
        )
        release_live_loop_lock(lock_path, strict_owner_identity=strict_owner_identity, owner_token=owner_token)
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

    exit_code = 0
    market_status_listener = KiwoomMarketStatusListener()
    market_status_listener.start()
    heartbeat: Optional[OwnershipHeartbeat] = None
    try:
        # P1.3-R3: started only now that ownership is held; keeps the SAME
        # SQLite lease fresh during long ticks (see OwnershipHeartbeat).
        heartbeat = OwnershipHeartbeat(
            store,
            instance_id=instance_id,
            generation=int(ownership_result.generation),
            lease_seconds=float(ownership_lease_sec),
            interval_sec=ownership_heartbeat_interval_sec,
        ).start()
        while True:
            if flag.requested:
                print(f"live_loop draining: shutdown requested via {flag.signal_name}, no new tick will start")
                break
            if heartbeat.lost:
                print(
                    f"live_loop ownership lost (heartbeat): {heartbeat.lost_reason} -- stopping before next tick"
                )
                exit_code = 7
                break
            refresh_live_loop_lock(lock_path, strict_owner_identity=strict_owner_identity, owner_token=owner_token)
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
            refresh_live_loop_lock(lock_path, strict_owner_identity=strict_owner_identity, owner_token=owner_token)
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
            while remaining > 0 and not flag.requested and not heartbeat.lost:
                step = min(1.0, float(remaining))
                sleep_fn(step)
                remaining -= step
            if flag.requested:
                print(f"live_loop draining: shutdown requested via {flag.signal_name} during idle sleep, stopping")
                break
    finally:
        market_status_listener.stop()
        # Stop (and join) the heartbeat BEFORE releasing anything, so no
        # refresh can land after the lease is released.
        if heartbeat is not None:
            heartbeat.stop()
        release_live_loop_lock(lock_path, strict_owner_identity=strict_owner_identity, owner_token=owner_token)
        # Only ever releases OUR OWN lease (release() is a strict no-op
        # otherwise) -- if ownership was already lost to a takeover above,
        # this does not disturb the new owner's claim.
        store.release(instance_id=instance_id)

    return exit_code
