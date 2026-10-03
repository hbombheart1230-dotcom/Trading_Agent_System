# M7.4 Cloudflare Private Ingress

## Purpose

Expose the read-only Trading Agent UI at `https://agentra.win` for one operator
without opening a router port or publishing the API and Trading Runtime.

## Fixed Architecture

```text
Operator browser
  -> Cloudflare Access (email allowlist + one-time PIN)
  -> Cloudflare Tunnel
  -> cloudflared container
  -> web:8080 (existing Nginx)
  -> api:8000 (internal observability network only)
  -> read-only report/log/state mounts
```

The Windows Trading Runtime remains outside Docker. The Tunnel cannot submit an
order, invoke an LLM, restart Trading Main, or write to an evidence mount.

## Isolation Rules

- `compose.cloudflare.yaml` is optional and never loaded by the local Compose
  command.
- The host Web port remains bound to `127.0.0.1`.
- The API has no host port and is not attached to the `edge` network.
- `cloudflared` joins only `edge` and can reach only the Web gateway.
- The Tunnel token exists only in ignored `deploy/compose/.env`.
- Cloudflare Access authentication is mandatory before the connector starts.
- Only `GET` and `HEAD` reach the Web/API gateway because the existing Nginx
  method gate remains authoritative.

## Cloudflare Dashboard Contract

| Setting | Value |
| --- | --- |
| Tunnel name | `trading-agent-observability` |
| Public hostname | `agentra.win` |
| Origin service | `http://web:8080` |
| Access type | Self-hosted application |
| Access domain | `agentra.win/*` |
| Allow policy | Operator email only |
| Login method | Email one-time PIN |

## Failure Policy

- No token: the Cloudflare overlay must fail configuration.
- Tunnel unhealthy: local UI remains available at `127.0.0.1:3000`.
- Access login absent: stop `cloudflared`; do not accept unauthenticated public
  operation.
- Cloudflare unavailable: Trading Runtime and local observability continue
  independently.

## Verification

1. Base Compose still binds only `127.0.0.1:3000`.
2. The merged Cloudflare Compose adds no API host port.
3. `cloudflared` exposes no host port.
4. Local `/web-health`, `/health/live`, and `/health/ready` remain healthy.
5. An incognito request to `https://agentra.win` shows Cloudflare Access before
   the UI.
6. A non-allowlisted email cannot enter the application.

## Activated State (2026-08-30)

- Tunnel `trading-agent-observability` is healthy with the pinned connector.
- `agentra.win` resolves through Cloudflare and routes to `http://web:8080`.
- An unauthenticated HTTPS request returns the Cloudflare Access login redirect.
- Local Web, internal API and the Tunnel connector remain independently healthy.
- The local token is present only in ignored `deploy/compose/.env` and is not
  included in repository files or documentation.

This milestone changes deployment observability only. Trading, evaluation,
Strategist, Scanner, Monitor, Commander, Executor, and Reporter behavior are
unchanged.
