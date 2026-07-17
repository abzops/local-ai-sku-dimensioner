[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment is missing. Run .\scripts\setup_windows.ps1 first."
}

Push-Location $RepositoryRoot
try {
    npm --prefix frontend run build
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend production build failed."
    }

    & $Python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "Database migration failed."
    }

    $Runtime = & $Python -c "import json; from backend.app.config import get_settings; s=get_settings(); print(json.dumps({'host': s.app_host, 'port': s.app_port}))" | ConvertFrom-Json
    Write-Host "Starting Local AI SKU Dimensioner at http://$($Runtime.host):$($Runtime.port)" -ForegroundColor Green
    & $Python -m uvicorn backend.app.main:app --host $Runtime.host --port $Runtime.port
    if ($LASTEXITCODE -ne 0) {
        throw "Production server exited with code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}

