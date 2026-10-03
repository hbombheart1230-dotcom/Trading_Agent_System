# 2026-10-02 -- P1.3 production cutover: Docker is now the canonical trading runtime

Operational change only: no code, strategy, UEF, Step5C or Step5D semantics changed, no
order was submitted, no worktree was created. Performed after the close (about 20:10-20:20 KST).

## Sequence

1. **Pre-cutover flat check (PASS).** Fresh read-only broker query: 0 positions, 0 open orders,
   cash positive; Host owner `BOOK-P23MBGEMI1:12244` generation 1; Step5C claims 0; Step5D
   orphans 0; `recovery_required` false; 2026-10-02 closeout SUCCESS.
2. **`TRADING_RUNTIME_MODE=docker`** appended to the repo `.env` (untracked, not committed).
   `Session` and `SessionWatchdog` Windows tasks were not disabled or modified. The real
   `run_start` / `run_watchdog` code was dry-run with the session window forced open and every
   subprocess launch recorded instead of executed: both returned
   `HOST_LIVE_START_SKIPPED_CANONICAL_RUNTIME_DOCKER`, 0 Host live launch attempts, and still
   (re)launch the baseline, opening-macro, opportunity-engine and Q10 collectors; the absence of the Host live
   loop is not a blocker. (No collector processes run after hours, so "preserved" is proven by the
   launch path, not by live processes.)
3. **Host stopped** via the documented path (`taskkill /F` on the M13 worker 12244 and its
   launcher 28380 only). Host trading python count 0. The hard kill left the Host lease valid
   until 20:15:48 KST; it was observed expired before Docker started.
4. **Docker started:** exactly one container `trading-agent-live` from image
   `trading-agent-20261002:61586ae` (`sha256:cafa93ed...f9e7f6`, label revision
   `61586aea3439ed26858fb070795747acfb39a1f5`). Current HEAD `efd46f9` differs from that
   revision only by four documentation files (`git diff --name-only` outside `docs/` is empty), so the
   running code is identical to HEAD. The previous exited container was renamed
   `trading-agent-live-incident-20261001` (forensic evidence kept). Config: `--restart
   unless-stopped`, read-only rootfs, tmpfs /tmp, user 10002, 1 GB / 1 CPU, binds data and reports, repo
   `.env` as env-file, no init (python is PID 1), healthcheck `python scripts/docker_healthcheck.py`
   (15s / 10s / 30s start / 3 retries).
5. **Production broker READ paths from inside the container (no orders):** auth PASS, account
   query PASS (0 positions, cash positive), open-order query PASS (0 rows today, 0 pending), market data
   PASS (005930 quote), market status = `MarketHours.is_open` False (after hours, as expected).
6. **Ownership at start:** stale takeover of the Host's expired lease, generation 2, owner
   `18f4ae4bbfd4:1`; lock identity `posix:12814478`; R3 heartbeat refreshing (heartbeat age
   ~5s, lease remaining ~24s); healthcheck LIVENESS PASS (`source=sqlite_ownership`). Step5D
   orphans 0, `physical_order_claim` 0 rows.
   `recovery_required` is TRUE after the takeover by design and can clear only through the readiness node
   on a market-hours tick with valid portfolio / open-order reconciliation. Fresh GREEN readiness is
   **NOT_AVAILABLE_AFTER_HOURS**: `MarketHours` is hard-coded 09:00-15:30 KST so every after-hours tick
   is a skipped no-op and no readiness file is produced. It was not faked; the stale Host file (15:29)
   is untouched. **Next-session validation item.**
7. **One controlled restart** (`docker kill` + immediate `docker start`, inside the unexpired
   lease): new PID-1 start identity (`posix:12814478` -> `posix:12826903`) reclaimed by R1 with no
   `lock_active`; R2 `OWNERSHIP_WAIT_STARTED` then ~23 s of `OWNERSHIP_RETRY` with the process alive;
   `OWNERSHIP_ACQUIRED_AFTER_WAIT generation=3` only after the old lease expired; healthcheck healthy
   throughout; Docker `RestartCount` 0; no restart storm; no repeated restarts.
8. **No Host resurrection:** the real `SessionWatchdog` task was triggered once
   (result 0); afterwards Host live python count 0 and Docker still healthy generation 3.
9. **Single startup authority:** Docker Engine restart policy `unless-stopped` on
   `trading-agent-live` plus the existing Docker Desktop logon autostart (HKCU Run). No Windows
   scheduled task, Startup-folder item or compose file creates or starts this container, and the
   Windows Session/Watchdog tasks no longer launch Host live in docker mode. Known constraint:
   Docker Desktop autostarts at user logon, not before logon.
10. **Boot simulation:** static / partial, no reboot and no Docker daemon restart (that would also
    cycle the observability containers). Verified state HOST=0, DOCKER=1, restart policy and autostart
    key in place, and the in-window Session/Watchdog gate. A true boot-time `unless-stopped` restart is a
    next-logon observation item.

## Rollback

Set `TRADING_RUNTIME_MODE=host` in `.env` (or remove the line), stop `trading-agent-live`, wait for
the lease to expire or release, then start the Host through the normal Session task or
`deploy/trading/rollback-to-host.ps1`.
