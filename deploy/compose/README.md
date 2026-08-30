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

## Private Internet Access Through Cloudflare

The optional Cloudflare overlay publishes the existing Web gateway at
`https://agentra.win`. It does not publish the API or Trading Runtime and does
not change the localhost binding at `127.0.0.1:3000`.

Before starting the connector, complete these dashboard steps in this order:

1. Create a remotely managed Cloudflare Tunnel named
   `trading-agent-observability`.
2. Add a published application route for `agentra.win` with service URL
   `http://web:8080`.
3. Create a Cloudflare Access self-hosted application for `agentra.win/*`.
4. Add one Allow policy containing only the operator's email address and enable
   email one-time PIN authentication.
5. Copy only the `eyJ...` tunnel token into
   `CLOUDFLARE_TUNNEL_TOKEN` in `deploy/compose/.env`. Never commit or paste the
   token into documentation, commands, chat, or logs.

If Cloudflare reports that the root hostname already has an A, AAAA, or CNAME
record, replace the old parking record through the Tunnel route workflow. Do
not start the connector until the Access policy is present.

Validate the merged configuration without printing or sharing its output:

```powershell
docker compose -f deploy/compose/compose.yaml -f deploy/compose/compose.cloudflare.yaml --env-file deploy/compose/.env config --quiet
```

Start the Web/API/Tunnel stack:

```powershell
docker compose -f deploy/compose/compose.yaml -f deploy/compose/compose.cloudflare.yaml --env-file deploy/compose/.env up -d --build
docker compose -f deploy/compose/compose.yaml -f deploy/compose/compose.cloudflare.yaml --env-file deploy/compose/.env ps
```

Verify local health first, then open `https://agentra.win` in a private browser
window. The Cloudflare Access login page must appear before the Trading Agent
UI. If the UI appears without authentication, stop `cloudflared` immediately
and correct the Access policy.

```powershell
Invoke-RestMethod http://127.0.0.1:3000/web-health
docker compose -f deploy/compose/compose.yaml -f deploy/compose/compose.cloudflare.yaml --env-file deploy/compose/.env logs --tail 100 cloudflared
```

Stop only the Tunnel while keeping the local UI running:

```powershell
docker compose -f deploy/compose/compose.yaml -f deploy/compose/compose.cloudflare.yaml --env-file deploy/compose/.env stop cloudflared
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
