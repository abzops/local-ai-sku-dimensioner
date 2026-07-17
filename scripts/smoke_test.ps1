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
$ExpectedRevision = & $Python -c "from backend.app.database import expected_alembic_head; print(expected_alembic_head())"
if ($LASTEXITCODE -ne 0 -or -not $ExpectedRevision) {
    throw "Unable to resolve the expected Alembic head."
}

$TempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$SmokeRoot = [IO.Path]::Combine(
    $TempBase,
    "local-ai-sku-dimensioner-smoke-$([guid]::NewGuid().ToString('N'))"
)
New-Item -ItemType Directory -Path $SmokeRoot -Force | Out-Null
$FixtureRoot = [IO.Path]::Combine(
    $TempBase,
    "local-ai-sku-dimensioner-fixtures-$([guid]::NewGuid().ToString('N'))"
)
New-Item -ItemType Directory -Path $FixtureRoot -Force | Out-Null

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
    SMOKE_IMAGE_PATH = $env:SMOKE_IMAGE_PATH
    SMOKE_CALIBRATION_IMAGE_PATH = $env:SMOKE_CALIBRATION_IMAGE_PATH
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
        if ($Health.database.revision -ne $ExpectedRevision) {
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

        $CreateBody = @{ sku = "PHASE1-SMOKE"; product_name = "Smoke Test Item" } |
            ConvertTo-Json
        $CreatedScan = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/scans" `
            -Method Post -ContentType "application/json" -Body $CreateBody -TimeoutSec 5
        if (-not $CreatedScan.id -or $CreatedScan.status -ne "draft") {
            throw "Phase 1 scan creation smoke check failed."
        }

        $SmokeImage = Join-Path $SmokeRoot "smoke-source.png"
        $env:SMOKE_IMAGE_PATH = $SmokeImage
        & $Python -c "import os; from PIL import Image; Image.new('RGB', (1280, 720), (38, 118, 184)).save(os.environ['SMOKE_IMAGE_PATH'], 'PNG')"
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $SmokeImage)) {
            throw "Unable to create the isolated smoke-test image."
        }

        Add-Type -AssemblyName System.Net.Http
        $HttpClient = New-Object System.Net.Http.HttpClient
        $Multipart = New-Object System.Net.Http.MultipartFormDataContent
        try {
            foreach ($View in @("top", "front", "side")) {
                $ImageContent = New-Object System.Net.Http.ByteArrayContent -ArgumentList (, [IO.File]::ReadAllBytes($SmokeImage))
                $ImageContent.Headers.ContentType = New-Object System.Net.Http.Headers.MediaTypeHeaderValue("image/png")
                $Multipart.Add($ImageContent, $View, "client-name-$View.png")
            }
            $UploadResponse = $HttpClient.PostAsync(
                "http://127.0.0.1:$Port/api/scans/$($CreatedScan.id)/images",
                $Multipart
            ).GetAwaiter().GetResult()
            $UploadBody = $UploadResponse.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            if (-not $UploadResponse.IsSuccessStatusCode) {
                throw "Phase 1 image upload smoke check failed with HTTP $([int]$UploadResponse.StatusCode)."
            }
            $UploadPayload = $UploadBody | ConvertFrom-Json
            if ($UploadPayload.scan.status -ne "ready_for_processing" -or
                $UploadPayload.uploaded_images.Count -ne 3) {
                throw "Phase 1 upload response did not report three ready views."
            }
            if ($UploadBody -match "storage_key" -or $UploadBody.Contains($SmokeRoot)) {
                throw "Phase 1 upload response exposed private storage information."
            }
        } finally {
            $Multipart.Dispose()
            $HttpClient.Dispose()
        }

        $ReadScan = Invoke-RestMethod `
            -Uri "http://127.0.0.1:$Port/api/scans/$($CreatedScan.id)" `
            -Method Get -TimeoutSec 5
        $History = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/scans" `
            -Method Get -TimeoutSec 5
        if ($ReadScan.status -ne "ready_for_processing" -or
            $History.total -ne 1 -or $History.items[0].id -ne $CreatedScan.id) {
            throw "Phase 1 scan read or history smoke check failed."
        }

        $ProfileBody = @{
            name = "Phase 2 smoke marker"
            dictionary = "DICT_4X4_50"
            marker_id = 0
            marker_size_mm = 100.0
            minimum_marker_side_px = 64
            maximum_perspective_ratio = 3.0
            maximum_homography_condition_number = 1000000.0
            maximum_marker_edge_residual_px = 2.0
            rectified_pixels_per_mm = 4.0
        } | ConvertTo-Json
        $Profile = Invoke-RestMethod `
            -Uri "http://127.0.0.1:$Port/api/calibration/profiles" `
            -Method Post -ContentType "application/json" -Body $ProfileBody -TimeoutSec 5
        if (-not $Profile.id -or $Profile.is_active) {
            throw "Phase 2 calibration profile creation smoke check failed."
        }
        $Activated = Invoke-RestMethod `
            -Uri "http://127.0.0.1:$Port/api/calibration/profiles/$($Profile.id)/activate" `
            -Method Post -TimeoutSec 5
        if (-not $Activated.is_active) {
            throw "Phase 2 calibration profile activation smoke check failed."
        }

        $MarkerDocument = Invoke-WebRequest `
            -Uri "http://127.0.0.1:$Port/api/calibration/profiles/$($Profile.id)/marker.svg" `
            -UseBasicParsing -TimeoutSec 5
        if ($MarkerDocument.StatusCode -ne 200 -or
            $MarkerDocument.Headers["Content-Type"] -notmatch "^image/svg\+xml" -or
            $MarkerDocument.Content -notmatch 'width="100mm"' -or
            $MarkerDocument.Content -notmatch 'height="100mm"') {
            throw "Phase 2 exact-size marker SVG smoke check failed."
        }

        $CalibrationImage = Join-Path $FixtureRoot "calibration-marker.png"
        $env:SMOKE_CALIBRATION_IMAGE_PATH = $CalibrationImage
        & $Python -c "import os, cv2, numpy as np; canvas=np.full((720,1280),255,np.uint8); marker=cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),0,360); canvas[180:540,460:820]=marker; assert cv2.imwrite(os.environ['SMOKE_CALIBRATION_IMAGE_PATH'],canvas)"
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $CalibrationImage)) {
            throw "Unable to create the isolated Phase 2 calibration fixture."
        }
        $RuntimeFilesBeforeTest = @(
            Get-ChildItem -LiteralPath $SmokeRoot -Recurse -File |
                ForEach-Object FullName |
                Sort-Object
        )
        $CalibrationClient = New-Object System.Net.Http.HttpClient
        $CalibrationMultipart = New-Object System.Net.Http.MultipartFormDataContent
        try {
            $CalibrationBytes = [IO.File]::ReadAllBytes($CalibrationImage)
            $CalibrationContent = New-Object System.Net.Http.ByteArrayContent -ArgumentList (, $CalibrationBytes)
            $CalibrationContent.Headers.ContentType = New-Object System.Net.Http.Headers.MediaTypeHeaderValue("image/png")
            $CalibrationMultipart.Add($CalibrationContent, "image", "private-client-name.png")
            $CalibrationResponse = $CalibrationClient.PostAsync(
                "http://127.0.0.1:$Port/api/calibration/profiles/$($Profile.id)/test",
                $CalibrationMultipart
            ).GetAwaiter().GetResult()
            $CalibrationBody = $CalibrationResponse.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            if (-not $CalibrationResponse.IsSuccessStatusCode) {
                throw "Phase 2 calibration test failed with HTTP $([int]$CalibrationResponse.StatusCode)."
            }
            $CalibrationPayload = $CalibrationBody | ConvertFrom-Json
            if ($CalibrationPayload.marker_id -ne 0 -or
                $CalibrationPayload.ordered_corners.Count -ne 4 -or
                -not $CalibrationPayload.marker_edge_quality.valid -or
                -not $CalibrationPayload.annotated_preview.data_base64 -or
                -not $CalibrationPayload.rectified_preview.data_base64) {
                throw "Phase 2 calibration evidence response was incomplete."
            }
            if ($CalibrationBody -match "private-client-name" -or
                $CalibrationBody.Contains($SmokeRoot) -or
                $CalibrationBody.Contains($FixtureRoot)) {
                throw "Phase 2 calibration response exposed private input information."
            }
        } finally {
            $CalibrationMultipart.Dispose()
            $CalibrationClient.Dispose()
        }
        $RuntimeFilesAfterTest = @(
            Get-ChildItem -LiteralPath $SmokeRoot -Recurse -File |
                ForEach-Object FullName |
                Sort-Object
        )
        if (Compare-Object $RuntimeFilesBeforeTest $RuntimeFilesAfterTest) {
            throw "The Phase 2 calibration test persisted an unexpected runtime file."
        }

        $CalibrationPage = Invoke-WebRequest `
            -Uri "http://127.0.0.1:$Port/calibration" -UseBasicParsing -TimeoutSec 5
        if ($CalibrationPage.StatusCode -ne 200 -or
            $CalibrationPage.Content -notmatch '<div id="root"></div>') {
            throw "Direct production navigation to /calibration did not use the SPA fallback."
        }
        $UnknownClient = New-Object System.Net.Http.HttpClient
        try {
            $UnknownResponse = $UnknownClient.GetAsync(
                "http://127.0.0.1:$Port/api/unknown"
            ).GetAwaiter().GetResult()
            $UnknownBody = $UnknownResponse.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            if ([int]$UnknownResponse.StatusCode -ne 404 -or
                $UnknownResponse.Content.Headers.ContentType.MediaType -ne "application/json" -or
                $UnknownBody -notmatch '"detail"') {
                throw "Unknown API route did not retain its JSON 404 boundary."
            }
        } finally {
            $UnknownClient.Dispose()
        }

        Write-Host "Phase 2 smoke test passed at http://127.0.0.1:$Port" -ForegroundColor Green
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
    $ResolvedFixtureRoot = [IO.Path]::GetFullPath($FixtureRoot)
    if ($ResolvedFixtureRoot.StartsWith($TempBase, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $ResolvedFixtureRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
