# Docker -> Host rollback tooling (Real Docker Deployment audit, 2026-09-17).
# The reverse of cutover-to-docker.ps1 -- same hard safety guarantee: never
# sets EXECUTION_ENABLED/ALLOW_REAL_EXECUTION true, anywhere.
#
# Usage:
#   .\rollback-to-host.ps1                 # interactive
#   .\rollback-to-host.ps1 -Yes            # non-interactive
#   .\rollback-to-host.ps1 -WhatIf         # print the plan, run zero steps
#
# NOTE: this script stops the Docker container and reports the host is
# clear to restart -- it does NOT itself launch the host process (that
# remains scripts/restart_live_session.py / the operator's own launch
# procedure, unmodified by this phase), since inventing a new host-launch
# path here would be exactly the kind of scope creep this task's Non-goals
# section excludes.

param(
    [switch]$Yes,
    [switch]$WhatIf,
    [string]$ComposeFile = (Join-Path $PSScriptRoot "compose.trading.real.yaml"),
    # Validation-only hook -- see cutover-to-docker.ps1's own comment.
    [string]$OverrideComposeFile = "",
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
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

function Get-PythonExe {
    $venvPy = Join-Path $RepoRoot "venv\Scripts\python.exe"
    if (Test-Path $venvPy) { return $venvPy }
    return "python"
}

$py = Get-PythonExe
$env:RUNTIME_OWNERSHIP_DB_PATH = Join-Path $DataRoot "data\state\runtime_ownership.db"
$env:PYTHONPATH = $RepoRoot

Write-Host "=== Docker -> Host Rollback ===" -ForegroundColor Magenta

# --- Step 1: confirm Docker execution disabled ------------------------------
Write-Step 1 "Confirming EXECUTION_ENABLED=false in the running Docker container"
$containerNameMatch = [regex]::Match((Get-Content -Raw -Path $ComposeFile), 'container_name:\s*(\S+)')
if (-not $containerNameMatch.Success) { throw "Could not find container_name: in $ComposeFile" }
$containerName = $containerNameMatch.Groups[1].Value
$dockerState = ""
try { $dockerState = docker inspect -f '{{.State.Status}}' $containerName } catch { $dockerState = "" }
if ($LASTEXITCODE -ne 0 -or $dockerState -ne "running") {
    Write-Warn "no running Docker container '$containerName' found -- nothing to roll back"
    exit 0
}
$envCheck = docker exec $containerName python -c "import os; print(os.getenv('EXECUTION_ENABLED'))"
if ($envCheck.Trim() -ne "false") {
    throw "SAFETY ABORT: EXECUTION_ENABLED inside $containerName is '$envCheck', not 'false'. This script refuses to touch a container that might be live-trading without independently verifying that state first."
}
Write-Ok "EXECUTION_ENABLED=false confirmed"

if ($WhatIf) {
    Write-Host "-WhatIf: stopping here. Remaining steps would be: SIGTERM the container, verify ownership release, report host is clear to restart." -ForegroundColor Yellow
    exit 0
}
if (-not $Yes) {
    $confirm = Read-Host "Proceed with rollback? This will stop the Docker runtime. [y/N]"
    if ($confirm -ne "y") { Write-Host "Aborted by operator."; exit 1 }
}

# --- Step 2: graceful SIGTERM stop ------------------------------------------
Write-Step 2 "Sending graceful SIGTERM stop to Docker container"
docker compose @composeArgs stop -t 20 trading-runtime
if ($LASTEXITCODE -ne 0) { throw "docker compose stop failed (exit $LASTEXITCODE)" }
Write-Ok "container stopped"

# --- Step 3: verify ownership release ---------------------------------------
Write-Step 3 "Verifying ownership was released"
$statusJson = & $py -c "from libs.runtime.runtime_ownership import SQLiteRuntimeOwnershipStore; import json; print(json.dumps(SQLiteRuntimeOwnershipStore().status()))"
$status = $statusJson | ConvertFrom-Json
if ($status) {
    Write-Warn "ownership row still present after graceful stop: $statusJson -- host restart will need to go through the explicit stale-takeover path once this lease naturally expires. This should not normally happen after a clean SIGTERM; investigate if it does."
} else {
    Write-Ok "ownership cleanly released -- no owner recorded"
}

# --- Step 4-7: host restart is the operator's own procedure -----------------
Write-Step 4 "Host is clear to restart"
Write-Host "    Run the existing host launch procedure now, e.g.:" -ForegroundColor Yellow
Write-Host "      python scripts/restart_live_session.py   (or this repo's own documented host-start command)" -ForegroundColor Yellow
Write-Host "    That process will itself acquire ownership fresh (step 5), refresh LIVENESS (step 6), and run its own reconciliation/readiness evaluation every tick (step 7) -- unchanged, existing behavior." -ForegroundColor Yellow

Write-Host ""
Write-Host "=== Rollback complete. Docker stopped, execution was disabled throughout. ===" -ForegroundColor Magenta
