FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN groupadd --system --gid 10002 trading \
    && useradd --system --uid 10002 --gid 10002 \
        --no-create-home --shell /usr/sbin/nologin trading

COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --requirement /tmp/requirements.txt \
    && rm /tmp/requirements.txt
# websockets (used by libs/runtime/kiwoom_market_status.py's background
# listener thread) is declared directly in the repo's root requirements.txt
# -- single dependency source of truth, no separate Dockerfile pin.

# Immutable-image policy (audit Section 4): application code and read-only
# reference config are baked in at build time -- never bind-mounted live.
# Everything under data/state/, data/logs/, reports/, data/evidence_ledger/,
# data/strategy_memory/, data/token_cache.json is EXECUTION-CRITICAL or
# operator-facing STATE and is deliberately NOT copied here -- it is
# supplied exclusively via the persistent volumes in compose.trading.yaml.
COPY --chown=10002:10002 graphs graphs
COPY --chown=10002:10002 libs libs
COPY --chown=10002:10002 scripts scripts
COPY --chown=10002:10002 config config
COPY --chown=10002:10002 data/specs data/specs

USER 10002:10002

# No shell wrapper (no cmd.exe/start/detached-launcher pattern -- P0-BUG
# CMD-popup avoidance applies here too, and on Linux containers there is
# no such concept anyway): python is PID 1, receives SIGTERM directly, and
# libs/runtime/live_loop_runner.py's P0-C handler (install_shutdown_handler)
# reacts to it.
ENTRYPOINT ["python", "scripts/run_session.py"]
CMD ["--mode", "live", "--phase", "intraday", \
     "--tick-pipeline", "integrated_chain", \
     "--sleep-sec", "10", \
     "--allow-offhours", \
     "--lock-path", "/app/data/state/m13_live_loop.lock", \
     "--lock-stale-sec", "300", \
     "--event-log-path", "/app/data/logs/events.jsonl", \
     "--state-path", "/app/data/state.json", \
     "--env-path", "/app/.env"]
