"""P1.3-R4 (2026-10-02): explicit canonical-runtime-mode authority.

Why this exists: the weekday Windows tasks TradingAgent-MockExamDay-Session
(09:00) and TradingAgent-MockExamDay-SessionWatchdog (09:05..15:25, every 5
minutes) run scripts/start_trading_day.py, which launches the Host's
mutation-capable M13 live loop (via scripts/restart_live_session.py) AND the
Q10/Q11/Q12, opportunity-engine and macro collectors that feed the Daily UEF
freshness contracts. Once Docker is the canonical trading runtime the Host
must stop launching the live loop, but disabling those whole tasks would also
stop the collectors. This is the single, explicit configuration switch that
suppresses ONLY the Host live-loop launch.

  TRADING_RUNTIME_MODE=host    (default) current behavior, unchanged.
  TRADING_RUNTIME_MODE=docker  Host live-loop launch is skipped
                               (HOST_LIVE_START_SKIPPED_CANONICAL_RUNTIME_DOCKER);
                               collectors/shadow loops continue untouched.
  anything else                fail closed for the Host live launch only
                               (HOST_LIVE_START_SKIPPED_RUNTIME_MODE_INVALID):
                               a typo must never silently re-enable a second
                               mutation-capable runtime.

Resolution order: process environment, then the repository `.env` file (the
scheduled tasks run with the user's environment, so `.env` is the practical
authority), then the default. This deliberately NEVER infers anything from
Docker container state or from Host PID liveness: a container's PID lives in
its own namespace and is meaningless to a Host process (see
runtime_ownership.py's docstring) -- the mode is configuration, not
inference. Only this one key is read from `.env`; nothing else in that file
is parsed or retained.

The mode gates Host LAUNCH only. It is not an ownership authority: the SQLite
runtime-ownership lease remains the sole authority over which runtime may
dispatch, so a misconfiguration can at worst produce a Host process that
loses the ownership race and exits, never a second dispatching runtime.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Optional, Tuple

RUNTIME_MODE_ENV = "TRADING_RUNTIME_MODE"
MODE_HOST = "host"
MODE_DOCKER = "docker"
DEFAULT_MODE = MODE_HOST

SKIP_REASON_DOCKER = "HOST_LIVE_START_SKIPPED_CANONICAL_RUNTIME_DOCKER"
SKIP_REASON_INVALID = "HOST_LIVE_START_SKIPPED_RUNTIME_MODE_INVALID"


def _read_key_from_env_file(env_file: Optional[Path], key: str) -> str:
    if env_file is None:
        return ""
    try:
        for raw in Path(env_file).read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip() != key:
                continue
            value = value.strip()
            if value[:1] in ("'", '"') and value[-1:] == value[:1] and len(value) >= 2:
                value = value[1:-1]
            else:
                value = value.split(" #", 1)[0].strip()
            return value
    except OSError:
        return ""
    return ""


def resolve_trading_runtime_mode(
    *, env: Optional[Mapping[str, str]] = None, env_file: Optional[Path] = None
) -> str:
    """Returns "host", "docker", or "invalid:<raw value>"."""
    environ = os.environ if env is None else env
    raw = str(environ.get(RUNTIME_MODE_ENV, "") or "").strip()
    if not raw:
        raw = _read_key_from_env_file(env_file, RUNTIME_MODE_ENV).strip()
    if not raw:
        return DEFAULT_MODE
    normalized = raw.lower()
    if normalized in (MODE_HOST, MODE_DOCKER):
        return normalized
    return f"invalid:{raw}"


def host_live_start_decision(
    *, env: Optional[Mapping[str, str]] = None, env_file: Optional[Path] = None
) -> Tuple[bool, str, str]:
    """(host_live_start_allowed, runtime_mode, skip_reason). skip_reason is
    "" when the Host live start is allowed."""
    mode = resolve_trading_runtime_mode(env=env, env_file=env_file)
    if mode == MODE_HOST:
        return True, mode, ""
    if mode == MODE_DOCKER:
        return False, mode, SKIP_REASON_DOCKER
    return False, mode, SKIP_REASON_INVALID


__all__ = [
    "DEFAULT_MODE",
    "MODE_DOCKER",
    "MODE_HOST",
    "RUNTIME_MODE_ENV",
    "SKIP_REASON_DOCKER",
    "SKIP_REASON_INVALID",
    "host_live_start_decision",
    "resolve_trading_runtime_mode",
]
