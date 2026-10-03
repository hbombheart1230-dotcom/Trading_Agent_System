# Mock Trading Runtime -- thin Docker CLI wrapper. Intentionally minimal:
# every subcommand is a single `docker compose` invocation run directly in
# the caller's own interactive shell -- no cmd.exe, no Start-Process, no
# hidden/detached child process, no new background launcher. This avoids
# reintroducing the class of problem tracked separately as
# "P0-BUG Windows CMD Popup" (Task-Scheduler .bat chains spawning visible
# console windows); a plain PowerShell function has nothing to spawn.
#
# Usage (from this directory, or `-ComposeFile` with a path):
#   .\trading-docker.ps1 build
#   .\trading-docker.ps1 start
#   .\trading-docker.ps1 stop
#   .\trading-docker.ps1 status
#   .\trading-docker.ps1 logs
#   .\trading-docker.ps1 redeploy   # build --build then up -d (patch workflow)
#   .\trading-docker.ps1 recreate   # down (keeps volumes) then up -d --build

# Works for either compose.trading.yaml (mock, default) or
# compose.trading.real.yaml (real, -ComposeFile) -- `status` additionally
# runs the SAME canonical scripts/docker_healthcheck.py the container's own
# HEALTHCHECK uses (single source of truth, nothing reimplemented here) so
# an operator sees instance_id/generation/EXECUTION_READY/EXECUTION_ENABLED/
# Step5D orphan count in one command instead of composing `docker exec`
# manually every time.

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("build", "start", "stop", "status", "logs", "redeploy", "recreate")]
    [string]$Command,

    [string]$ComposeFile = (Join-Path $PSScriptRoot "compose.trading.yaml")
)

switch ($Command) {
    "build"    { docker compose -f $ComposeFile build trading-runtime }
    "start"    { docker compose -f $ComposeFile up -d trading-runtime }
    "stop"     { docker compose -f $ComposeFile stop trading-runtime }
    "status"   {
        docker compose -f $ComposeFile ps
        $containerNameMatch = [regex]::Match((Get-Content -Raw -Path $ComposeFile), 'container_name:\s*(\S+)')
        if ($containerNameMatch.Success) {
            $name = $containerNameMatch.Groups[1].Value
            $state = ""
            try { $state = docker inspect -f '{{.State.Status}}' $name } catch { $state = "" }
            if ($state -eq "running") {
                Write-Host ""
                Write-Host "--- canonical readiness/ownership (scripts/docker_healthcheck.py) ---" -ForegroundColor Cyan
                docker exec $name python scripts/docker_healthcheck.py
            }
        }
    }
    "logs"     { docker compose -f $ComposeFile logs -f trading-runtime }
    "redeploy" { docker compose -f $ComposeFile up -d --build trading-runtime }
    "recreate" {
        # Removes the CONTAINER only -- volumes (bind-mounted host
        # directories under ./test-state/) are untouched, so persistent
        # state survives exactly as compose.trading.yaml's mounts intend.
        docker compose -f $ComposeFile down
        docker compose -f $ComposeFile up -d --build trading-runtime
    }
}
