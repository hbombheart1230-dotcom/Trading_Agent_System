# 2026-08-29 Cloudflare Private Ingress

## Scope

- Added an optional Cloudflare Tunnel Compose overlay for `agentra.win`.
- Kept the Web host binding at `127.0.0.1:3000`.
- Kept the API private with no host port.
- Added Cloudflare Access email allowlist and OTP setup requirements.
- Added a pinned, non-root `cloudflared` container and `/ready` healthcheck.

## Behavior Impact

None. The Trading Runtime, agents, evaluation, reporting, LLM calls and order
execution are unchanged. The Tunnel overlay is inactive until an operator adds
the secret token and explicitly starts the overlay.

## Operator Action

1. Create the Tunnel and `agentra.win -> http://web:8080` route.
2. Protect `agentra.win/*` with Cloudflare Access before starting the connector.
3. Allow only the operator email and enable email OTP.
4. Paste the Tunnel token into ignored `deploy/compose/.env`.
5. Start with both `compose.yaml` and `compose.cloudflare.yaml`.
