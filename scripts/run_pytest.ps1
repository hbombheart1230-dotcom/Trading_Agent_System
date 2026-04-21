$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot "venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

foreach ($arg in $args) {
    if ($arg -eq "--basetemp" -or $arg -like "--basetemp=*") {
        throw "Do not pass --basetemp. This repo standardizes pytest temp output in .pytest-work via pytest.ini."
    }
}

Push-Location $repoRoot
try {
    & $pythonExe -m pytest @args
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
