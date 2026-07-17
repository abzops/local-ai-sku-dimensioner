[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
$FrontendIndex = Join-Path $RepositoryRoot "frontend\dist\index.html"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment is missing. Run .\scripts\setup_windows.ps1 first."
}
if (-not (Test-Path -LiteralPath $FrontendIndex)) {
    throw "Frontend build is missing. Run npm --prefix frontend run build first."
}

$TempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$SmokeRoot = [IO.Path]::Combine(
    $TempBase,
    "local-ai-sku-dimensioner-smoke-$([guid]::NewGuid().ToString('N'))"
)
New-Item -ItemType Directory -Path $SmokeRoot -Force | Out-Null

$Listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, 0)
$Listener.Start()
$Port = ([Net.IPEndPoint]$Listener.LocalEndpoint).Port
$Listener.Stop()

$StdOut = Join-Path $SmokeRoot "server.stdout.log"
$StdErr = Join-Path $SmokeRoot "server.stderr.log"
$Server = $null
$PreviousEnvironment = @{
    APP_ENV = $env:APP_ENV
    APP_HOST = $env:APP_HOST
    APP_PORT = $env:APP_PORT
    DATA_ROOT = $env:DATA_ROOT
    DATABASE_URL = $env:DATABASE_URL
}

try {
    $env:APP_ENV = "production"
    $env:APP_HOST = "127.0.0.1"
    $env:APP_PORT = [string]$Port
    $env:DATA_ROOT = $SmokeRoot
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue

    Push-Location $RepositoryRoot
    try {
        & $Python -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) {
            throw "Smoke-test database migration failed."
        }

        $Server = Start-Process -FilePath $Python `
            -ArgumentList @("-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", $Port) `
            -WorkingDirectory $RepositoryRoot -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $StdOut -RedirectStandardError $StdErr

        $Health = $null
        $Deadline = [DateTime]::UtcNow.AddSeconds(20)
        while ([DateTime]::UtcNow -lt $Deadline) {
            if ($Server.HasExited) {
                throw "Smoke-test server exited before becoming ready."
            }
            try {
                $Health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" `
                    -Method Get -TimeoutSec 2
                break
            } catch {
                Start-Sleep -Milliseconds 250
            }
        }

        if ($null -eq $Health -or $Health.status -ne "ok") {
            throw "Health endpoint did not become ready within 20 seconds."
        }
        if ($Health.database.revision -ne "0001_phase0") {
            throw "Unexpected database revision: $($Health.database.revision)"
        }

        $Page = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 5
        if ($Page.StatusCode -ne 200 -or $Page.Content -notmatch '<div id="root"></div>') {
            throw "Production frontend shell was not served correctly."
        }

        $JavaScriptMatch = [regex]::Match(
            $Page.Content,
            '<script[^>]+src="(?<path>/[^"?]+\.js(?:\?[^\"]*)?)"'
        )
        if (-not $JavaScriptMatch.Success) {
            throw "Production frontend did not reference a compiled JavaScript asset."
        }
        $JavaScriptAsset = Invoke-WebRequest `
            -Uri "http://127.0.0.1:$Port$($JavaScriptMatch.Groups['path'].Value)" `
            -UseBasicParsing -TimeoutSec 5
        if ($JavaScriptAsset.StatusCode -ne 200 -or -not $JavaScriptAsset.Content) {
            throw "Compiled JavaScript asset was not served correctly."
        }

        $CssMatch = [regex]::Match(
            $Page.Content,
            '<link[^>]+href="(?<path>/[^"?]+\.css(?:\?[^\"]*)?)"'
        )
        if (-not $CssMatch.Success) {
            throw "Production frontend did not reference a compiled CSS asset."
        }
        $CssAsset = Invoke-WebRequest `
            -Uri "http://127.0.0.1:$Port$($CssMatch.Groups['path'].Value)" `
            -UseBasicParsing -TimeoutSec 5
        if ($CssAsset.StatusCode -ne 200 -or -not $CssAsset.Content) {
            throw "Compiled CSS asset was not served correctly."
        }

        Write-Host "Smoke test passed at http://127.0.0.1:$Port" -ForegroundColor Green
    } finally {
        Pop-Location
    }
} catch {
    if (Test-Path -LiteralPath $StdOut) {
        Write-Host "`nServer standard output:"
        Get-Content -LiteralPath $StdOut
    }
    if (Test-Path -LiteralPath $StdErr) {
        Write-Host "`nServer error output:"
        Get-Content -LiteralPath $StdErr
    }
    throw
} finally {
    if ($null -ne $Server -and -not $Server.HasExited) {
        Stop-Process -Id $Server.Id -Force -ErrorAction SilentlyContinue
        Wait-Process -Id $Server.Id -Timeout 5 -ErrorAction SilentlyContinue
    }

    foreach ($Name in $PreviousEnvironment.Keys) {
        $Value = $PreviousEnvironment[$Name]
        if ($null -eq $Value) {
            Remove-Item "Env:$Name" -ErrorAction SilentlyContinue
        } else {
            Set-Item "Env:$Name" $Value
        }
    }

    $ResolvedSmokeRoot = [IO.Path]::GetFullPath($SmokeRoot)
    if ($ResolvedSmokeRoot.StartsWith($TempBase, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $ResolvedSmokeRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
