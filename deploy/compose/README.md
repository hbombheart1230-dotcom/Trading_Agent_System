# Observability Compose

This deployment starts only the read-only API and Web UI. It does not start,
stop, inspect, or health-gate the Trading Runtime.

## Prerequisites

Docker Desktop must be running with the WSL2 Linux-container backend.

Copy `.env.example` to `.env` inside this directory and adjust
`TRADING_REPO_ROOT` when the repository is stored elsewhere. The file contains
no credentials.

## Private Local Profile

```powershell
docker compose -f deploy/compose/compose.yaml --env-file deploy/compose/.env config
docker compose -f deploy/compose/compose.yaml --env-file deploy/compose/.env build
docker compose -f deploy/compose/compose.yaml --env-file deploy/compose/.env up -d
docker compose -f deploy/compose/compose.yaml --env-file deploy/compose/.env ps
```

Open `http://127.0.0.1:3000`. The API has no host port and is reachable only
through the Web reverse proxy. The API is attached only to the internal
`observability` network. Web also uses an `edge` network because Docker Desktop
does not publish host ports from a container attached only to an internal
network.

## Public Sanitization Profile

This profile enables API redaction only. It does not expose the service to the
internet and does not add authentication or HTTPS.

```powershell
docker compose -f deploy/compose/compose.yaml -f deploy/compose/compose.public.yaml --env-file deploy/compose/.env up -d --build
```

## Verification

```powershell
Invoke-RestMethod http://127.0.0.1:3000/web-health
Invoke-RestMethod http://127.0.0.1:3000/health/live
Invoke-RestMethod http://127.0.0.1:3000/health/ready
docker compose -f deploy/compose/compose.yaml exec api sh -c 'touch /data/reports/m7-write-check'
```

The final command must fail with a read-only filesystem error. Confirm that no
`m7-write-check` file exists on the host.

Stop only the observability containers:

```powershell
docker compose -f deploy/compose/compose.yaml --env-file deploy/compose/.env down
```
