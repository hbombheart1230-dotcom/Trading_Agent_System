$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$targets = @(
    ".pytest-work-entry-*",
    ".pytest-work-execution-*",
    ".pytest-work-lifecycle-*",
    ".pytest-work-reporter-*",
    ".pytest-work-scanner-*",
    ".pytest-work-story-*",
    ".pytest-work-*",
    "data\.pytest-work-*",
    "data\pytest-cache-files-*"
)

Push-Location $repoRoot
try {
    $items = @()
    foreach ($pattern in $targets) {
        $items += Get-ChildItem -Force -Path $pattern -ErrorAction SilentlyContinue
    }
    $items =
        $items |
        Where-Object { $_.FullName -notmatch [regex]::Escape((Join-Path $repoRoot ".pytest-work")) } |
        Sort-Object -Property FullName -Unique

    foreach ($item in $items) {
        Remove-Item -LiteralPath $item.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
}
finally {
    Pop-Location
}
