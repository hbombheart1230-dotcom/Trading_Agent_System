# M7 Engine Gate - 2026-08-26

## Result

M7 is complete. The post-restart Linux Engine, Compose, private/public profile,
browser, read-only filesystem, and shutdown-isolation gates all passed.

## Installed

| Component | Version |
| --- | --- |
| Docker Desktop | 4.88.1 |
| Docker CLI | 29.7.2 |
| Docker Compose | v5.4.0 |
| kubectl | v1.36.1 |

## Verified Before Restart

| Check | Result |
| --- | --- |
| M7 deployment contracts | 8 passed |
| API suite | 57 passed, 1 skipped |
| Web unit tests | 3 passed |
| Web production build | passed |
| Compose config parse | passed |
| Host Web `127.0.0.1:5173` | HTTP 200 |
| Host API `127.0.0.1:8000/health/ready` | HTTP 200 |

The first parallel pytest attempt caused a shared `.pytest-work` cleanup race.
Sequential reruns passed; this was not an application defect.

## Restart Boundary

Windows reports `PendingReboot=True`. Before restart, `wsl --status` still
reports that WSL is unavailable and Docker Engine cannot create its named pipe.
Docker Desktop startup was stopped after that result so no retrying backend
process remains active.

## Post-Restart Gate

Run in this order:

```powershell
wsl --update
wsl --status
wsl -l -v
docker version
docker compose version
docker info --format '{{.OSType}}'
docker run --rm hello-world
docker compose -f deploy/compose/compose.yaml --env-file deploy/compose/.env config
docker compose -f deploy/compose/compose.yaml --env-file deploy/compose/.env build
docker compose -f deploy/compose/compose.yaml --env-file deploy/compose/.env up -d
docker compose -f deploy/compose/compose.yaml --env-file deploy/compose/.env ps
```

Pass conditions:

* Docker reports `linux`;
* API and Web containers become healthy;
* `http://127.0.0.1:3000` and proxied health endpoints return 200;
* writing to `/data/reports` fails;
* host Trading Runtime is not started, stopped, or modified by Compose;
* `compose down` stops only M7 services.

All checks passed on 2026-08-26. M8 is unblocked.

## Engine-Discovered Corrections

The first real image build found two gaps that static contracts did not expose:

1. Web build context re-included local `node_modules` and `dist`; explicit
   exclusions reduced the context from more than 80 MB to about 254 KB.
2. Docker Desktop does not publish a port for a container attached only to an
   `internal` network. Web now joins a separate `edge` network while API remains
   exclusively on the internal `observability` network.

Both corrections are deployment-only and do not import or modify Trading
Runtime behavior.

## Final Engine Evidence

| Check | Result |
| --- | --- |
| WSL default version | 2 |
| Docker Engine OSType | `linux` |
| `hello-world` | passed |
| API container | healthy, non-root `10001:10001`, internal network only |
| Web container | healthy, non-root `101:101`, localhost `127.0.0.1:3000` only |
| Web routes | 10 routes passed at desktop and mobile viewports |
| Private profile | passed; report access enabled and execution disabled |
| Public profile | passed; private navigation hidden and host paths redacted |
| API tests | 57 passed, 1 skipped |
| Web unit tests | 3 passed |
| M7 deployment contracts | 7 passed |
| Web production build | passed |
| Read-only mounts/root filesystem | write attempts rejected |
| `compose down` isolation | only M7 containers removed; host process set unchanged |

## Engine-Discovered Performance Corrections

Docker Desktop bind-mount traversal is slower than native host filesystem
access. Initial 90-120 day trade scans exceeded the proxy limit, and the LLM
surface scanned a large bounded tail from the multi-gigabyte event log.

The read-only UI now:

* starts trade, report, strategy, and data-quality catalog views at 45 days;
* retains explicit date controls for wider user-requested ranges;
* bounds the Compose LLM event tail to 8 MiB;
* allows 30 seconds for bounded API reads before proxy timeout;
* wraps long authority identifiers on narrow screens.

These changes affect observability reads only. They do not change Trading
Runtime, strategy, evaluation, order, broker, or LLM execution behavior.

## Final Runtime State

The private profile is running at `http://127.0.0.1:3000`. The API has no host
port. Trading Runtime was not started, stopped, imported, or modified by M7.
