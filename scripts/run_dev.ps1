[CmdletBinding()]
param(
    [switch]$ValidateShutdownAfterReady
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"

function Add-OwnedProcess {
    param(
        [Parameter(Mandatory = $true)][hashtable]$OwnedProcesses,
        [Parameter(Mandatory = $true)][int]$TargetProcessId
    )

    $ProcessInfo = Get-CimInstance Win32_Process `
        -Filter "ProcessId = $TargetProcessId" -ErrorAction SilentlyContinue
    if ($null -ne $ProcessInfo) {
        $OwnedProcesses[$TargetProcessId] = [string]$ProcessInfo.CreationDate
    }
}

function Update-OwnedProcessSnapshot {
    param([Parameter(Mandatory = $true)][hashtable]$OwnedProcesses)

    $ProcessSnapshot = @(Get-CimInstance Win32_Process -ErrorAction Stop)
    $DiscoveredProcess = $true
    while ($DiscoveredProcess) {
        $DiscoveredProcess = $false
        foreach ($ProcessInfo in $ProcessSnapshot) {
            $TargetProcessId = [int]$ProcessInfo.ProcessId
            $ParentProcessId = [int]$ProcessInfo.ParentProcessId
            if (
                $OwnedProcesses.ContainsKey($ParentProcessId) -and
                -not $OwnedProcesses.ContainsKey($TargetProcessId)
            ) {
                $OwnedProcesses[$TargetProcessId] = [string]$ProcessInfo.CreationDate
                $DiscoveredProcess = $true
            }
        }
    }
}

function Test-OwnedProcessIsRunning {
    param(
        [Parameter(Mandatory = $true)][int]$TargetProcessId,
        [Parameter(Mandatory = $true)][string]$CreationDate
    )

    $ProcessInfo = Get-CimInstance Win32_Process `
        -Filter "ProcessId = $TargetProcessId" -ErrorAction SilentlyContinue
    return (
        $null -ne $ProcessInfo -and
        [string]$ProcessInfo.CreationDate -eq $CreationDate
    )
}

function Stop-OwnedProcessTrees {
    param(
        [Parameter(Mandatory = $true)][object[]]$RootProcesses,
        [Parameter(Mandatory = $true)][hashtable]$OwnedProcesses
    )

    foreach ($RootProcess in $RootProcesses) {
        if ($null -ne $RootProcess) {
            Add-OwnedProcess -OwnedProcesses $OwnedProcesses -TargetProcessId $RootProcess.Id
        }
    }
    Update-OwnedProcessSnapshot -OwnedProcesses $OwnedProcesses

    foreach ($RootProcess in $RootProcesses) {
        if ($null -ne $RootProcess -and -not $RootProcess.HasExited) {
            & taskkill.exe /PID $RootProcess.Id /T /F 2>$null | Out-Null
        }
    }

    $Deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        $RemainingProcessIds = @()
        foreach ($Entry in $OwnedProcesses.GetEnumerator()) {
            $TargetProcessId = [int]$Entry.Key
            if (
                Test-OwnedProcessIsRunning `
                    -TargetProcessId $TargetProcessId `
                    -CreationDate ([string]$Entry.Value)
            ) {
                $RemainingProcessIds += $TargetProcessId
            }
        }

        if ($RemainingProcessIds.Count -eq 0) {
            return
        }

        foreach ($TargetProcessId in $RemainingProcessIds) {
            Stop-Process -Id $TargetProcessId -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $Deadline)

    $StillRunning = @()
    foreach ($Entry in $OwnedProcesses.GetEnumerator()) {
        if (
            Test-OwnedProcessIsRunning `
                -TargetProcessId ([int]$Entry.Key) `
                -CreationDate ([string]$Entry.Value)
        ) {
            $StillRunning += [int]$Entry.Key
        }
    }
    if ($StillRunning.Count -gt 0) {
        throw "Development cleanup could not stop owned process IDs: $($StillRunning -join ', ')."
    }
}

function Test-TcpEndpoint {
    param(
        [Parameter(Mandatory = $true)][string]$Address,
        [Parameter(Mandatory = $true)][int]$Port
    )

    $Client = New-Object Net.Sockets.TcpClient
    try {
        $Connection = $Client.BeginConnect($Address, $Port, $null, $null)
        if (-not $Connection.AsyncWaitHandle.WaitOne(250)) {
            return $false
        }
        $Client.EndConnect($Connection)
        return $true
    } catch {
        return $false
    } finally {
        $Client.Dispose()
    }
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment is missing. Run .\scripts\setup_windows.ps1 first."
}
if (-not (Test-Path -LiteralPath (Join-Path $RepositoryRoot "frontend\node_modules"))) {
    throw "Frontend dependencies are missing. Run .\scripts\setup_windows.ps1 first."
}

Push-Location $RepositoryRoot
$BackendProcess = $null
$FrontendProcess = $null
$OwnedProcesses = @{}
try {
    & $Python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "Database migration failed."
    }

    $Runtime = & $Python -c "import json; from backend.app.config import get_settings; s=get_settings(); print(json.dumps({'host': s.app_host, 'port': s.app_port}))" | ConvertFrom-Json

    Write-Host "Starting API at http://$($Runtime.host):$($Runtime.port)" -ForegroundColor Cyan
    Write-Host "Starting web UI at http://127.0.0.1:5173" -ForegroundColor Cyan
    Write-Host "Press Ctrl+C to stop both process trees.`n"

    $BackendProcess = Start-Process -FilePath $Python `
        -ArgumentList @("-m", "uvicorn", "backend.app.main:app", "--reload", "--host", $Runtime.host, "--port", $Runtime.port) `
        -WorkingDirectory $RepositoryRoot -PassThru -NoNewWindow
    Add-OwnedProcess -OwnedProcesses $OwnedProcesses -TargetProcessId $BackendProcess.Id

    $FrontendProcess = Start-Process -FilePath "npm.cmd" `
        -ArgumentList @("--prefix", "frontend", "run", "dev") `
        -WorkingDirectory $RepositoryRoot -PassThru -NoNewWindow
    Add-OwnedProcess -OwnedProcesses $OwnedProcesses -TargetProcessId $FrontendProcess.Id

    $ValidationDeadline = [DateTime]::UtcNow.AddSeconds(30)
    $ValidationReady = $false
    while (-not $BackendProcess.HasExited -and -not $FrontendProcess.HasExited) {
        Update-OwnedProcessSnapshot -OwnedProcesses $OwnedProcesses
        if (
            $ValidateShutdownAfterReady -and
            (Test-TcpEndpoint -Address ([string]$Runtime.host) -Port ([int]$Runtime.port)) -and
            (Test-TcpEndpoint -Address "127.0.0.1" -Port 5173)
        ) {
            $ValidationReady = $true
            Write-Host "Both development endpoints are reachable; validating cleanup." -ForegroundColor Green
            break
        }
        if ($ValidateShutdownAfterReady -and [DateTime]::UtcNow -ge $ValidationDeadline) {
            throw "Development endpoints did not become reachable within 30 seconds."
        }
        Start-Sleep -Milliseconds 250
    }

    if ($BackendProcess.HasExited) {
        throw "Backend exited unexpectedly with code $($BackendProcess.ExitCode)."
    }
    if ($FrontendProcess.HasExited) {
        throw "Frontend exited unexpectedly with code $($FrontendProcess.ExitCode)."
    }
    if ($ValidateShutdownAfterReady -and -not $ValidationReady) {
        throw "Development shutdown validation did not reach both endpoints."
    }
} finally {
    try {
        Stop-OwnedProcessTrees `
            -RootProcesses @($BackendProcess, $FrontendProcess) `
            -OwnedProcesses $OwnedProcesses
        if ($null -ne $BackendProcess -or $null -ne $FrontendProcess) {
            Write-Host "Development process trees stopped." -ForegroundColor Green
        }
    } finally {
        Pop-Location
    }
}
