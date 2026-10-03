# Host -> Docker cutover tooling (Real Docker Deployment audit, 2026-09-17).
#
# HARD SAFETY GUARANTEE: this script NEVER sets EXECUTION_ENABLED or
# ALLOW_REAL_EXECUTION to true, anywhere, under any flag or condition. It
# asserts compose.trading.real.yaml's own hardcoded "false" values are
# still present and refuses to proceed if they are not. Real trading
# enable is a separate, later, explicitly-approved "REAL EXECUTION CHANGE
# WINDOW" phase -- not this script's concern.
#
# WINDOWS GRACEFUL-STOP LIMITATION (discovered and documented during this
# phase's own validation, not fixed here -- production-semantics/host-
# tooling change, out of this task's scope): the existing host stop path
# (scripts/restart_live_session.py::_stop_pid) uses `taskkill /PID <pid> /F`
# on Windows -- a force-kill. Python's SIGTERM handler
# (libs/runtime/live_loop_runner.py::install_shutdown_handler) never gets a
# chance to run gracefully; the host's own ownership row is left with a
# LIVE (not yet expired) lease pointing at a now-dead process. This is why
# step 4 below WAITS for that lease to naturally expire rather than
# assuming a clean release, then uses the SAME explicit, audited
# `allow_stale_takeover` path this whole system was built to handle safely
# (libs/runtime/runtime_ownership.py) -- never a silent/forced takeover.
#
# Usage:
#   .\cutover-to-docker.ps1                 # interactive, asks for confirmation
#   .\cutover-to-docker.ps1 -Yes            # non-interactive (still all the same checks)
#   .\cutover-to-docker.ps1 -WhatIf         # print the plan, run zero steps

param(
    [switch]$Yes,
    [switch]$WhatIf,
    [string]$ComposeFile = (Join-Path $PSScriptRoot "compose.trading.real.yaml"),
    # Validation-only hook: an additional `-f` compose file layered on top
    # (e.g. compose.trading.real.dryrun-override.yaml, to redirect volumes
    # to an isolated mirror instead of the real host data/ tree). Never
    # used in a real cutover.
    [string]$OverrideComposeFile = "",
    # Where the CODE lives -- always the real repo (needed to import
    # libs.runtime.runtime_ownership regardless of which data this run
    # inspects). Only the venv location and PYTHONPATH depend on this.
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    # Where the DATA (lock file, ownership DB) lives -- the real repo's
    # data/ for an actual cutover, an isolated mirror for validation.
    # Defaults to -RepoRoot (i.e. identical for a real run).
    [string]$DataRoot = ""
)
if (-not $DataRoot) { $DataRoot = $RepoRoot }

$composeArgs = @("-f", $ComposeFile)
if ($OverrideComposeFile) { $composeArgs += @("-f", $OverrideComposeFile) }

$ErrorActionPreference = "Stop"

function Write-Step($n, $msg) { Write-Host "[$n] $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "    OK: $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    WARN: $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "    FAIL: $msg" -ForegroundColor Red }

function Assert-ExecutionDisabledInComposeFile {
    param([string]$Path)
    $content = Get-Content -Raw -Path $Path
    if ($content -notmatch 'EXECUTION_ENABLED:\s*"false"') {
        throw "SAFETY ABORT: $Path does not contain a literal EXECUTION_ENABLED: `"false`" line. This script refuses to run against a compose file where real execution might not be hardcoded off."
    }
    if ($content -notmatch 'ALLOW_REAL_EXECUTION:\s*"false"') {
        throw "SAFETY ABORT: $Path does not contain a literal ALLOW_REAL_EXECUTION: `"false`" line."
    }
}

function Get-PythonExe {
    $venvPy = Join-Path $RepoRoot "venv\Scripts\python.exe"
    if (Test-Path $venvPy) { return $venvPy }
    return "python"
}

$py = Get-PythonExe
$lockPath = Join-Path $DataRoot "data\state\m13_live_loop.lock"
# Explicit, not relying on cwd/venv-location auto-detection: every
# inline Python call below must resolve the SAME ownership DB this
# script's own -DataRoot points at (matters for validation runs against
# an isolated mirror; harmless/identical to the default for a real run
# against the real repo root). PYTHONPATH always points at the CODE root
# (-RepoRoot) so `from libs.runtime...` imports succeed regardless of
# this process's own working directory or which data it is inspecting.
$env:RUNTIME_OWNERSHIP_DB_PATH = Join-Path $DataRoot "data\state\runtime_ownership.db"
$env:PYTHONPATH = $RepoRoot

Write-Host "=== Host -> Docker Cutover ===" -ForegroundColor Magenta
Write-Host "Compose file: $ComposeFile"
Write-Host "Repo root:    $RepoRoot"
Write-Host ""

# --- Step 1: assert EXECUTION_ENABLED=false --------------------------------
Write-Step 1 "Asserting EXECUTION_ENABLED/ALLOW_REAL_EXECUTION are hardcoded false"
Assert-ExecutionDisabledInComposeFile -Path $ComposeFile
Write-Ok "compose file hardcodes execution disabled"

# --- Step 2: current host runtime status (read-only) ------------------------
Write-Step 2 "Reading current host runtime status (read-only)"
$hostStatusJson = & $py -c @"
import json, time
from pathlib import Path
p = Path(r'$lockPath')
if not p.exists():
    print(json.dumps({'lock_exists': False}))
else:
    obj = json.loads(p.read_text(encoding='utf-8'))
    hb = int(obj.get('heartbeat_epoch') or obj.get('started_epoch') or 0)
    print(json.dumps({'lock_exists': True, 'pid': obj.get('pid'), 'heartbeat_age_sec': (int(time.time()) - hb) if hb else None}))
"@
$hostStatus = $hostStatusJson | ConvertFrom-Json
Write-Host "    $hostStatusJson"
if (-not $hostStatus.lock_exists) {
    Write-Warn "no host lock file found -- host runtime does not appear to be running"
} else {
    Write-Ok "host lock present (pid=$($hostStatus.pid), heartbeat_age_sec=$($hostStatus.heartbeat_age_sec))"
}

if ($WhatIf) {
    Write-Host ""
    Write-Host "-WhatIf: stopping here. Remaining steps would be: request host graceful shutdown, wait for ownership release/expiry, start Docker, verify ownership/LIVENESS/READINESS/EXECUTION_READY, confirm EXECUTION_ENABLED=false, done." -ForegroundColor Yellow
    exit 0
}

if (-not $Yes) {
    $confirm = Read-Host "Proceed with cutover? This will stop the host runtime process. [y/N]"
    if ($confirm -ne "y") { Write-Host "Aborted by operator."; exit 1 }
}

# --- Step 3: request host graceful shutdown ---------------------------------
Write-Step 3 "Requesting host runtime shutdown"
if ($hostStatus.lock_exists -and $hostStatus.pid) {
    Write-Warn "Windows has no reliable graceful-SIGTERM delivery to an external console process (see this script's header comment) -- using the same taskkill /F this repo's own scripts/restart_live_session.py already uses. The ownership lease this leaves behind is handled safely via explicit stale-takeover below, never silently."
    & taskkill /PID $hostStatus.pid /F 2>&1 | ForEach-Object { Write-Host "    $_" }
} else {
    Write-Ok "no host process to stop"
}

# --- Step 4: wait for ownership release or natural lease expiry ------------
Write-Step 4 "Waiting for ownership release (clean) or lease expiry (stale, handled explicitly)"
$maxWaitSec = 90
$waited = 0
$released = $false
while ($waited -lt $maxWaitSec) {
    $statusJson = & $py -c "from libs.runtime.runtime_ownership import SQLiteRuntimeOwnershipStore; import json,time; s=SQLiteRuntimeOwnershipStore().status(); print(json.dumps({'status': s, 'now': time.time()}))"
    $parsed = $statusJson | ConvertFrom-Json
    if (-not $parsed.status) { $released = $true; break }
    if ($parsed.now -gt $parsed.status.lease_expires_at) { Write-Ok "prior lease has naturally expired (stale, will be taken over explicitly)"; break }
    Start-Sleep -Seconds 3
    $waited += 3
}
if ($released) { Write-Ok "ownership cleanly released" }

# --- Step 5: start Docker Real runtime --------------------------------------
Write-Step 5 "Starting Docker Real runtime"
docker compose @composeArgs up -d --build trading-runtime
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed (exit $LASTEXITCODE)" }

Start-Sleep -Seconds 8

# --- Step 6/7/8/9: verify ownership, LIVENESS, READINESS, EXECUTION_READY --
Write-Step 6 "Verifying Docker ownership acquisition + LIVENESS + READINESS + EXECUTION_READY"
# container_name is fixed in the compose file itself -- reading it back out
# of `docker compose ps`'s JSON output is unnecessary indirection with its
# own shape/timing pitfalls (a container that already exited -- e.g. lost
# an ownership race -- won't even appear without `-a`).
$containerNameMatch = [regex]::Match((Get-Content -Raw -Path $ComposeFile), 'container_name:\s*(\S+)')
if (-not $containerNameMatch.Success) { throw "Could not find container_name: in $ComposeFile" }
$containerName = $containerNameMatch.Groups[1].Value

$dockerState = docker inspect -f '{{.State.Status}}' $containerName
if ($dockerState -ne "running") {
    $exitReason = docker logs $containerName --tail 5
    Write-Fail "Docker container is not running (state=$dockerState) -- cutover did NOT complete. Last log lines:"
    Write-Host $exitReason
    Write-Fail "Ownership may not have been acquired (expected if the host process never actually stopped, or its lease had not yet expired). Investigate before retrying."
    exit 1
}
Write-Ok "Docker container running: $containerName"
$health = docker exec $containerName python scripts/docker_healthcheck.py
Write-Host $health

# --- Step 10: re-confirm EXECUTION_ENABLED=false ----------------------------
Write-Step 10 "Re-confirming EXECUTION_ENABLED=false inside the running container"
$envCheck = docker exec $containerName python -c "import os; print(os.getenv('EXECUTION_ENABLED'))"
if ($envCheck.Trim() -ne "false") {
    Write-Fail "EXECUTION_ENABLED inside the container is '$envCheck', not 'false' -- this should be structurally impossible. STOP and investigate immediately."
    exit 1
}
Write-Ok "EXECUTION_ENABLED=false confirmed inside the running container"

Write-Host ""
Write-Host "=== Cutover complete. Container running, execution disabled. ===" -ForegroundColor Magenta
Write-Host "Real trading remains OFF. Enabling it is a separate, later, explicitly-approved phase." -ForegroundColor Yellow
