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
    MIN_IMAGE_LONG_EDGE = $env:MIN_IMAGE_LONG_EDGE
    MIN_IMAGE_SHORT_EDGE = $env:MIN_IMAGE_SHORT_EDGE
    CAPTURE_SETUP_ID = $env:CAPTURE_SETUP_ID
    CAPTURE_SETUP_VERSION = $env:CAPTURE_SETUP_VERSION
    CAPTURE_SETUP_QUALIFIED = $env:CAPTURE_SETUP_QUALIFIED
    CAPTURE_SETUP_TYPE = $env:CAPTURE_SETUP_TYPE
    CAPTURE_SETUP_MIN_OBJECT_MM = $env:CAPTURE_SETUP_MIN_OBJECT_MM
    CAPTURE_SETUP_MAX_OBJECT_MM = $env:CAPTURE_SETUP_MAX_OBJECT_MM
    CAPTURE_SETUP_MARKER_SIZE_UNCERTAINTY_MM = $env:CAPTURE_SETUP_MARKER_SIZE_UNCERTAINTY_MM
    CAPTURE_SETUP_PLANE_UNCERTAINTY_MM = $env:CAPTURE_SETUP_PLANE_UNCERTAINTY_MM
    CAPTURE_SETUP_ORTHOGONALITY_UNCERTAINTY_DEG = $env:CAPTURE_SETUP_ORTHOGONALITY_UNCERTAINTY_DEG
    CAPTURE_SETUP_STANDOFF_UNCERTAINTY_MM = $env:CAPTURE_SETUP_STANDOFF_UNCERTAINTY_MM
    CAPTURE_SETUP_MAX_OFF_PLANE_MM = $env:CAPTURE_SETUP_MAX_OFF_PLANE_MM
    MEASUREMENT_PROCESSING_DEADLINE_SECONDS = $env:MEASUREMENT_PROCESSING_DEADLINE_SECONDS
    SMOKE_IMAGE_PATH = $env:SMOKE_IMAGE_PATH
    SMOKE_IMAGE_ROOT = $env:SMOKE_IMAGE_ROOT
    SMOKE_CALIBRATION_IMAGE_PATH = $env:SMOKE_CALIBRATION_IMAGE_PATH
}

try {
    $env:APP_ENV = "production"
    $env:APP_HOST = "127.0.0.1"
    $env:APP_PORT = [string]$Port
    $env:DATA_ROOT = $SmokeRoot
    $env:MIN_IMAGE_LONG_EDGE = "800"
    $env:MIN_IMAGE_SHORT_EDGE = "600"
    $env:CAPTURE_SETUP_ID = "phase3-smoke-rig"
    $env:CAPTURE_SETUP_VERSION = "1"
    $env:CAPTURE_SETUP_QUALIFIED = "true"
    $env:CAPTURE_SETUP_TYPE = "orthogonal_rig"
    $env:CAPTURE_SETUP_MIN_OBJECT_MM = "75"
    $env:CAPTURE_SETUP_MAX_OBJECT_MM = "400"
    $env:CAPTURE_SETUP_MARKER_SIZE_UNCERTAINTY_MM = "0.2"
    $env:CAPTURE_SETUP_PLANE_UNCERTAINTY_MM = "0.5"
    $env:CAPTURE_SETUP_ORTHOGONALITY_UNCERTAINTY_DEG = "0.2"
    $env:CAPTURE_SETUP_STANDOFF_UNCERTAINTY_MM = "0.4"
    $env:CAPTURE_SETUP_MAX_OFF_PLANE_MM = "0.5"
    $env:MEASUREMENT_PROCESSING_DEADLINE_SECONDS = "60"
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

        $SmokeImages = @{}
        $env:SMOKE_IMAGE_ROOT = $FixtureRoot
        & $Python -c "import os, cv2; from pathlib import Path; from backend.app.contracts import ImageView; from backend.tests.fixtures.phase3_synthetic_factory import render_scene; root=Path(os.environ['SMOKE_IMAGE_ROOT']); [(cv2.imwrite(str(root / f'{view.value}.png'), render_scene(view).image_bgr) or (_ for _ in ()).throw(RuntimeError('encode failed'))) for view in (ImageView.TOP, ImageView.FRONT, ImageView.SIDE)]"
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to create isolated Phase 3 smoke images."
        }
        foreach ($View in @("top", "front", "side")) {
            $SmokeImages[$View] = Join-Path $FixtureRoot "$View.png"
            if (-not (Test-Path -LiteralPath $SmokeImages[$View])) {
                throw "A required isolated Phase 3 smoke image is missing."
            }
        }

        Add-Type -AssemblyName System.Net.Http
        $HttpClient = New-Object System.Net.Http.HttpClient
        $Multipart = New-Object System.Net.Http.MultipartFormDataContent
        try {
            foreach ($View in @("top", "front", "side")) {
                $ImageContent = New-Object System.Net.Http.ByteArrayContent -ArgumentList (, [IO.File]::ReadAllBytes($SmokeImages[$View]))
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
            rectified_pixels_per_mm = 2.0
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

        $MeasurementOptions = Invoke-RestMethod `
            -Uri "http://127.0.0.1:$Port/api/measurements/options" -Method Get -TimeoutSec 5
        if (-not $MeasurementOptions.capture_setup.processing_enabled -or
            $MeasurementOptions.capture_setup.id -ne "phase3-smoke-rig") {
            throw "Phase 3 qualified capture setup was not reported safely."
        }

        $StoredSourceFiles = @(
            Get-ChildItem -LiteralPath (Join-Path $SmokeRoot "scans") -Recurse -File |
                Where-Object FullName -NotMatch "[\\/]measurements[\\/]"
        )
        if ($StoredSourceFiles.Count -ne 3) {
            throw "Phase 3 smoke setup did not retain exactly three original scan images."
        }
        $SourceHashesBefore = @{}
        foreach ($SourceFile in $StoredSourceFiles) {
            $SourceHashesBefore[$SourceFile.FullName] = (Get-FileHash -LiteralPath $SourceFile.FullName -Algorithm SHA256).Hash
        }

        $MeasurementRequestId = [guid]::NewGuid().ToString()
        $MeasurementBody = @{
            request_id = $MeasurementRequestId
            expected_calibration_profile_id = $Profile.id
            expected_capture_setup_id = "phase3-smoke-rig"
            capture_contract_acknowledged = $true
            reprocess_of_measurement_id = $null
        } | ConvertTo-Json
        $MeasurementResponse = Invoke-WebRequest `
            -Uri "http://127.0.0.1:$Port/api/scans/$($CreatedScan.id)/measurements" `
            -Method Post -ContentType "application/json" -Body $MeasurementBody `
            -UseBasicParsing -TimeoutSec 90
        $Measurement = $MeasurementResponse.Content | ConvertFrom-Json
        if ($MeasurementResponse.StatusCode -ne 201 -or $Measurement.status -ne "succeeded" -or
            $Measurement.per_view_measurements.Count -ne 3 -or
            $Measurement.dimension_results.Count -ne 3 -or $Measurement.previews.Count -ne 3 -or
            $Measurement.final_dimensions.length_mm -lt 235 -or
            $Measurement.final_dimensions.length_mm -gt 245 -or
            $Measurement.final_dimensions.width_mm -lt 135 -or
            $Measurement.final_dimensions.width_mm -gt 145 -or
            $Measurement.final_dimensions.height_mm -lt 115 -or
            $Measurement.final_dimensions.height_mm -gt 125) {
            throw "Phase 3 deterministic measurement response was incomplete or out of bounds."
        }
        if ($MeasurementResponse.Content -match "storage_key|lease_token|request_signature" -or
            $MeasurementResponse.Content.Contains($SmokeRoot) -or
            $MeasurementResponse.Content.Contains($FixtureRoot)) {
            throw "Phase 3 measurement response exposed private information."
        }

        $ReplayResponse = Invoke-WebRequest `
            -Uri "http://127.0.0.1:$Port/api/scans/$($CreatedScan.id)/measurements" `
            -Method Post -ContentType "application/json" -Body $MeasurementBody `
            -UseBasicParsing -TimeoutSec 10
        $Replay = $ReplayResponse.Content | ConvertFrom-Json
        if ($ReplayResponse.StatusCode -ne 200 -or $Replay.id -ne $Measurement.id) {
            throw "Phase 3 request replay did not return the same immutable attempt."
        }

        foreach ($Preview in $Measurement.previews) {
            $PreviewResponse = Invoke-WebRequest `
                -Uri "http://127.0.0.1:$Port$($Preview.api_url)" `
                -UseBasicParsing -TimeoutSec 10
            if ($PreviewResponse.StatusCode -ne 200 -or
                $PreviewResponse.Headers["Content-Type"] -notmatch "^image/png" -or
                $PreviewResponse.Headers["Cache-Control"] -ne "no-store") {
                throw "A Phase 3 private annotated preview failed validation."
            }
        }

        $ReprocessBody = @{
            request_id = [guid]::NewGuid().ToString()
            expected_calibration_profile_id = $Profile.id
            expected_capture_setup_id = "phase3-smoke-rig"
            capture_contract_acknowledged = $true
            reprocess_of_measurement_id = $Measurement.id
        } | ConvertTo-Json
        $Reprocessed = Invoke-RestMethod `
            -Uri "http://127.0.0.1:$Port/api/scans/$($CreatedScan.id)/measurements" `
            -Method Post -ContentType "application/json" -Body $ReprocessBody -TimeoutSec 90
        if ($Reprocessed.status -ne "succeeded" -or $Reprocessed.id -eq $Measurement.id -or
            $Reprocessed.reprocess_of_measurement_id -ne $Measurement.id) {
            throw "Phase 3 explicit reprocessing did not create a linked immutable attempt."
        }
        $EarlierAttempt = Invoke-RestMethod `
            -Uri "http://127.0.0.1:$Port/api/scans/$($CreatedScan.id)/measurements/$($Measurement.id)" `
            -Method Get -TimeoutSec 10
        if ($EarlierAttempt.id -ne $Measurement.id -or
            $EarlierAttempt.final_dimensions.length_mm -ne $Measurement.final_dimensions.length_mm) {
            throw "Phase 3 reprocessing changed the earlier immutable attempt."
        }
        foreach ($SourceFile in $StoredSourceFiles) {
            $HashAfter = (Get-FileHash -LiteralPath $SourceFile.FullName -Algorithm SHA256).Hash
            if ($HashAfter -ne $SourceHashesBefore[$SourceFile.FullName]) {
                throw "Phase 3 processing modified an original scan image."
            }
        }

        $CalibrationPage = Invoke-WebRequest `
            -Uri "http://127.0.0.1:$Port/calibration" -UseBasicParsing -TimeoutSec 5
        if ($CalibrationPage.StatusCode -ne 200 -or
            $CalibrationPage.Content -notmatch '<div id="root"></div>') {
            throw "Direct production navigation to /calibration did not use the SPA fallback."
        }
        $MeasurementPage = Invoke-WebRequest `
            -Uri "http://127.0.0.1:$Port/scans/$($CreatedScan.id)/measurements/$($Measurement.id)" `
            -UseBasicParsing -TimeoutSec 5
        if ($MeasurementPage.StatusCode -ne 200 -or
            $MeasurementPage.Content -notmatch '<div id="root"></div>') {
            throw "Direct production measurement-result navigation did not use the SPA fallback."
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

        Write-Host "Phase 3 smoke test passed at http://127.0.0.1:$Port" -ForegroundColor Green
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
