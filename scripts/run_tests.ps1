[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment is missing. Run .\scripts\setup_windows.ps1 first."
}

function Invoke-Validation {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][scriptblock]$Command
    )

    Write-Host "`n==> $Label" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

Push-Location $RepositoryRoot
try {
    Invoke-Validation "Backend tests" { & $Python -m pytest backend\tests }
    Invoke-Validation "Backend lint" { & $Python -m ruff check backend }
    Invoke-Validation "Backend type checks" { & $Python -m mypy backend\app }
    Invoke-Validation "Frontend lint" { npm --prefix frontend run lint }
    Invoke-Validation "Frontend type checks" { npm --prefix frontend run typecheck }
    Invoke-Validation "Frontend tests" { npm --prefix frontend run test }
    Invoke-Validation "Frontend production build" { npm --prefix frontend run build }
    Invoke-Validation "Production smoke test" { & (Join-Path $PSScriptRoot "smoke_test.ps1") }

    Write-Host "`nAll Phase 0 validation passed." -ForegroundColor Green
} finally {
    Pop-Location
}

