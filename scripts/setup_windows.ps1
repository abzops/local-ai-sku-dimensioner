[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvRoot = Join-Path $RepositoryRoot ".venv"
$Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"

function Invoke-Checked {
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
    Write-Host "Checking the Windows development toolchain..." -ForegroundColor Cyan

    $PythonVersion = & py -3.11 -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $PythonVersion) {
        throw "Python 3.11 was not found. Install Python 3.11 with the Windows py launcher."
    }

    $NodeVersionText = & node -p "process.versions.node" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $NodeVersionText) {
        throw "Node.js was not found. Install Node.js 22.12+ or Node.js 24 LTS."
    }
    $NodeVersion = [version]$NodeVersionText
    $NodeSupported = ($NodeVersion.Major -eq 22 -and $NodeVersion.Minor -ge 12) -or `
        ($NodeVersion.Major -eq 24)
    if (-not $NodeSupported) {
        throw "Unsupported Node.js $NodeVersionText. Use Node.js 22.12+ or Node.js 24 LTS."
    }

    Write-Host "Python $PythonVersion"
    Write-Host "Node.js $NodeVersionText"

    if ((Test-Path -LiteralPath $VenvRoot) -and -not (Test-Path -LiteralPath $Python)) {
        throw "Existing .venv is incomplete. Rename or remove it only after explicit confirmation, then rerun setup."
    }
    if (-not (Test-Path -LiteralPath $VenvRoot)) {
        Invoke-Checked "Creating .venv" { py -3.11 -m venv .venv }
    }

    $VenvPythonVersion = & $Python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $VenvPythonVersion) {
        throw "Existing .venv Python could not be executed. Rename or remove it only after explicit confirmation, then rerun setup."
    }
    if (-not $VenvPythonVersion.StartsWith("3.11.")) {
        throw "Existing .venv uses Python $VenvPythonVersion; Python 3.11 is required. Rename or remove it only after explicit confirmation, then rerun setup."
    }
    Write-Host ".venv Python $VenvPythonVersion"

    Invoke-Checked "Installing locked Python development dependencies" {
        & $Python -m pip install --require-hashes -r requirements-dev.lock
    }
    Invoke-Checked "Checking NumPy and OpenCV marker support" {
        & $Python -c "import cv2, numpy; required=('DICT_4X4_50','DICT_5X5_50','DICT_6X6_50'); assert hasattr(cv2, 'aruco'); assert hasattr(cv2.aruco, 'ArucoDetector'); assert hasattr(cv2.aruco, 'generateImageMarker'); [cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, name)) for name in required]; print(f'NumPy {numpy.__version__}; OpenCV {cv2.__version__}; ArUco marker support ready')"
    }
    Invoke-Checked "Installing locked frontend dependencies" {
        npm --prefix frontend ci
    }

    if (-not (Test-Path -LiteralPath ".env")) {
        Copy-Item -LiteralPath ".env.example" -Destination ".env"
        Write-Host "Created .env from .env.example."
    } else {
        Write-Host "Preserved existing .env."
    }

    $DataRoot = & $Python -c "from backend.app.config import get_settings; print(get_settings().data_root)"
    if ($LASTEXITCODE -ne 0 -or -not $DataRoot) {
        throw "Unable to resolve DATA_ROOT."
    }
    foreach ($Folder in @("database", "scans", "calibration", "exports", "models", "logs")) {
        New-Item -ItemType Directory -Path (Join-Path $DataRoot $Folder) -Force | Out-Null
    }

    Invoke-Checked "Applying SQLite migrations" { & $Python -m alembic upgrade head }
    Invoke-Checked "Checking local database readiness" {
        & $Python -m backend.app.cli healthcheck
    }

    Write-Host "`nSetup complete." -ForegroundColor Green
    Write-Host "Development: .\scripts\run_dev.ps1"
    Write-Host "Production:  .\scripts\run_prod.ps1"
    Write-Host "Validation:  .\scripts\run_tests.ps1"
} finally {
    Pop-Location
}
