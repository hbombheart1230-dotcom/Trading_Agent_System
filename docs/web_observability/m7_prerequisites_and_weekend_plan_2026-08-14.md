# M7 Docker Compose Prerequisites and Weekend Plan - 2026-08-14

## Decision

M7 containerizes only the independent Web and read-only API. The active
Trading Runtime stays on the Windows host through the current M7-M9
observability roadmap.

This is a sequencing decision, not a permanent prohibition. The runtime uses
Kiwoom REST over HTTPS and has no confirmed ActiveX/COM dependency, so a future
Linux-container migration is technically plausible. It requires a separate
shadow and mock validation track because duplicate process or token ownership
errors can create duplicate orders.

## Host Audit

Audit performed on 2026-08-14 without changing host configuration:

| Requirement | Observed state |
| --- | --- |
| Operating system | Windows 11 Home, 64-bit, build 26200 |
| Memory | 15.5 GB |
| Free C: storage | 220.2 GB |
| Hypervisor | Detected; virtualization-based security running |
| WSL | Not installed |
| Docker CLI/Desktop | Not installed |
| Docker Compose | Not installed |
| Windows file-server service | Running, automatic |

The hardware and operating-system baseline are sufficient for Linux
containers. WSL2 and Docker Desktop are the missing prerequisites.

## Installation Gate

Installation must happen after the market session because WSL installation
requires an administrator shell and normally a Windows restart.

Administrator PowerShell:

```powershell
wsl --install
```

After restart:

```powershell
wsl --update
wsl --status
wsl -l -v
```

Then install Docker Desktop with the WSL2 Linux-container backend and verify:

```powershell
docker version
docker compose version
docker run --rm hello-world
docker info --format '{{.OSType}}'
```

M7 image build and container smoke verification start only after all four
commands pass and the last command reports `linux`. Deployment source files
and static isolation tests may be prepared earlier because they do not change
the host or start containers.

## Weekend Work Slices

### M7.1 Images

* minimal non-root FastAPI image;
* multi-stage Web production build;
* no `.env`, credentials, reports, logs, or state copied into either image;
* image-level health checks.

### M7.2 Compose Network and Storage

* Web is the only host-facing service;
* API is reachable only on the private Compose network;
* `reports`, `data/logs`, and `data/state` are bind-mounted read-only;
* container root filesystems are read-only with explicit temporary filesystems;
* CPU and memory limits protect the host Trading Runtime.

### M7.3 Profiles

* private profile remains the localhost default;
* public profile uses `OBSERVABILITY_EXPOSURE_PROFILE=public`;
* public mode retains simulation/mock identification and the M6 redaction
  contract;
* internet exposure is not enabled by Compose alone.

### M7.4 Verification

```text
docker compose config
docker compose build
docker compose up -d
docker compose ps
API/Web health smoke
read-only mount write-failure proof
private/public profile regression
desktop/mobile browser smoke
docker compose down
```

The verification records Trading Runtime PID, event-log cadence, working set,
and Q evidence cadence before and after. M7 fails if those operating signals
change materially.

## External Access Boundary

M7 first proves local Compose operation on `127.0.0.1`. External access is a
separate controlled step using HTTPS and authentication through a tunnel or
reverse proxy. Ports 5173 and 8000 must not be forwarded directly from the
router, and the API must remain private behind the Web gateway.

## Future Runtime Container Track

After M9, runtime migration can be evaluated in this order:

1. build a runtime image without enabling OrderIntent;
2. compare Windows and container shadow artifacts;
3. run one mock runtime container with persistent state;
4. prove single token writer and duplicate-order exclusion;
5. validate KST scheduling, restart reconciliation, and kill switch;
6. migrate only after the host and container outputs remain equivalent.

For a single trading workstation, Docker Compose is the preferred final
orchestrator. Kubernetes remains useful for infrastructure demonstration and
multi-host services, but a trading runtime would additionally require a
singleton lease and idempotent broker execution.
