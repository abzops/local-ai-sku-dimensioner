[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"

function Test-PortIsAvailable {
    param([Parameter(Mandatory = $true)][int]$Port)

    $Listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $Port)
    $Listener.Server.ExclusiveAddressUse = $true
    try {
        $Listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        $Listener.Stop()
    }
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment is missing. Run .\scripts\setup_windows.ps1 first."
}

Push-Location $RepositoryRoot
try {
    $Runtime = & $Python -c "import json; from backend.app.config import get_settings; s=get_settings(); print(json.dumps({'port': s.app_port}))" | ConvertFrom-Json
    $Ports = @([int]$Runtime.port, 5173)
    foreach ($Port in $Ports) {
        if (-not (Test-PortIsAvailable -Port $Port)) {
            throw "Port $Port is already in use; shutdown validation will not disturb that process."
        }
    }

    & (Join-Path $PSScriptRoot "run_dev.ps1") -ValidateShutdownAfterReady

    $Deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        $BlockedPorts = @($Ports | Where-Object { -not (Test-PortIsAvailable -Port $_) })
        if ($BlockedPorts.Count -eq 0) {
            break
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $Deadline)
    if ($BlockedPorts.Count -gt 0) {
        throw "Development cleanup did not release ports: $($BlockedPorts -join ', ')."
    }

    $RepositoryMarker = $RepositoryRoot.ToLowerInvariant()
    $RemainingProcesses = @(
        Get-CimInstance Win32_Process | Where-Object {
            $CommandLine = ([string]$_.CommandLine).ToLowerInvariant()
            $CommandLine.Contains($RepositoryMarker) -and (
                $CommandLine.Contains("backend.app.main:app") -or
                $CommandLine.Contains("frontend\node_modules\vite")
            )
        }
    )
    if ($RemainingProcesses.Count -gt 0) {
        $ProcessSummary = $RemainingProcesses | ForEach-Object {
            "$($_.Name):$($_.ProcessId)"
        }
        throw "Development descendants remain: $($ProcessSummary -join ', ')."
    }

    Write-Host "Development shutdown validation passed; process trees ended and ports $($Ports -join ' and ') are released." -ForegroundColor Green
} finally {
    Pop-Location
}
