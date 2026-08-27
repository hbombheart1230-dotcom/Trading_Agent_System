# M7 Docker Compose Implementation - 2026-08-18

## Status

M7 deployment source is complete. On 2026-08-26 Docker Desktop 4.88.1,
Docker CLI 29.7.2, Compose v5.4.0, and kubectl v1.36.1 were installed.
Docker Engine validation completed on 2026-08-26 after the required Windows
restart. Both services are healthy under Linux containers and M8 is unblocked.

No Trading Runtime, strategy, evaluation, broker, order, report-generation,
or live-session code was changed. The existing Web and API processes were not
restarted.

## Implemented Surface

```text
deploy/
  docker/
    Dockerfile.api
    Dockerfile.api.dockerignore
    Dockerfile.web
    Dockerfile.web.dockerignore
    nginx.conf
  compose/
    compose.yaml
    compose.public.yaml
    .env.example
    README.md

tests/deploy/
  test_m7_compose_contract.py
```

## Image Boundaries

### API

* Python 3.12 slim base;
* copies only `apps/api/**`;
* does not copy `.env`, Trading Core, graphs, libraries, scripts, reports,
  logs, state, or credentials;
* runs as UID/GID `10001`;
* runs one Uvicorn worker;
* exposes only the container network port `8000`;
* includes an image-level liveness check.

### Web

* Node 22 build stage with deterministic `npm ci`;
* Nginx static runtime stage;
* copies only the built Web assets and Nginx configuration;
* runs as UID/GID `101` on port `8080`;
* proxies `/api` and API health paths to the private `api` service;
* rejects methods other than GET and HEAD;
* includes an image-level Web health check.

Dockerfile-specific ignore files use an allowlist model. The repository is the
build context for path stability, but unrelated source and runtime artifacts
are excluded before the context is sent to the builder.

## Compose Isolation

The default Compose profile is private.

* only Web is published at `127.0.0.1:3000`;
* API has no host port;
* the API/Web service network is internal;
* Web alone also joins an `edge` network so Docker Desktop can publish the
  localhost-only port;
* reports, runtime logs, state, and evidence ledger are bind-mounted read-only;
* both root filesystems are read-only;
* only bounded `/tmp` tmpfs mounts are writable;
* Linux capabilities are dropped and privilege escalation is disabled;
* API is limited to 0.50 CPU, 512 MB, and 128 PIDs;
* Web is limited to 0.25 CPU, 128 MB, and 64 PIDs.

`compose.public.yaml` changes only
`OBSERVABILITY_EXPOSURE_PROFILE=public`. It enables the existing M6 server-side
sanitization contract but does not provide internet exposure, authentication,
or HTTPS.

## Verification Completed

```text
tests/apps/api + tests/deploy: 64 passed, 1 skipped
deployment contract tests: 7 passed
existing API /health/live: HTTP 200
existing API /health/ready: HTTP 200
existing Web root: HTTP 200
```

The tests enforce:

* source-copy allowlists;
* non-root users and image health checks;
* API network privacy and localhost-only Web publication;
* read-only evidence mounts;
* read-only roots and explicit resource limits;
* minimal public-profile override;
* GET-only private reverse proxy behavior.

## Engine Validation Gate

This gate was executed after market close on 2026-08-26 following the required
Windows restart.

```powershell
wsl --install
```

Executed post-restart commands:

```powershell
docker version
docker compose version
docker run --rm hello-world
docker info --format '{{.OSType}}'
docker compose -f deploy/compose/compose.yaml --env-file deploy/compose/.env config
docker compose -f deploy/compose/compose.yaml --env-file deploy/compose/.env build
docker compose -f deploy/compose/compose.yaml --env-file deploy/compose/.env up -d
docker compose -f deploy/compose/compose.yaml --env-file deploy/compose/.env ps
```

The engine gate passes only when:

* Docker reports Linux containers;
* API and Web containers are healthy;
* `http://127.0.0.1:3000` and proxied health endpoints respond;
* an attempted write under `/data/reports` fails;
* Trading Runtime PID, event cadence, working set, and evidence cadence remain
  materially unchanged;
* `docker compose down` stops only the observability services.

M8 Kubernetes work is unblocked because this gate passed on 2026-08-26.

## 2026-08-26 Host Gate Update

Pre-restart baseline:

* M7 Compose contract prepared;
* read-only API tests: 57 passed, 1 skipped;
* Web unit tests: 3 passed;
* Web production build: passed;
* `docker compose config --quiet`: passed;
* host Web and API healthy on ports 5173 and 8000 before container migration.

Completed after restart:

* `wsl --status` and WSL2 backend confirmation;
* Linux Docker Engine start and `hello-world`;
* image build and Compose up;
* container health, proxy, and read-only mount proof;
* private/public browser verification;
* Compose down isolation proof.
