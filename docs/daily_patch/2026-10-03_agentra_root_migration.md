# Agentra root migration

## Summary

The repository root was moved from `C:\Trading_Agent_System` to `C:\Agentra` during weekend maintenance. A temporary compatibility junction remains at the old path.

## Boundary updates

- Docker `TRADING_REPO_ROOT` now points to `C:/Agentra`.
- Compose identity remains `trading-agent-observability`.
- Scheduler paths were migrated while all TradingAgent tasks remain disabled.
- All thirteen disabled Scheduler tasks were migrated, including the S4U Daily UEF task.
- The canonical Windows and Linux scheduler templates use `C:\Agentra`.

## Runtime and validation

- The stale live-loop lock and expired ownership record were preserved unchanged.
- The venv was recreated at `C:\Agentra\venv` from `requirements.txt`.
- Docker compose configuration validation passed.
- Runtime ownership, lock, UEF, replay, authority, and leakage regression tests passed where run.
- No live runtime or Docker workload was restarted.

## Status

Migration finalization passed. The old path remains only in historical/generated material and the temporary compatibility junction.
