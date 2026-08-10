# Build the backend executable for the Electron desktop app.
#
# IMPORTANT: This build MUST use CPU-only PyTorch (torch==2.11.0+cpu).
# The release venv should be created from requirements-release.txt, NOT
# from requirements.txt (which would install CUDA torch and cause
# shm.dll load failures on end-user machines without NVIDIA drivers).
#
# To set up the release venv:
#   python -m venv venv310
#   .\venv310\Scripts\pip install -r requirements-release.txt
#
param(
    [string]$Python = ".\venv310\Scripts\python.exe",
    [string]$SampleSourceData = "",
    [string]$SampleBookName = "优化设计",
    [switch]$SkipSampleDataPrepare,
    [switch]$RequireSampleData,
    [string]$SampleDataDir = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$frontendDist = Join-Path $projectRoot "frontend\dist"
$sampleData = if ($SampleDataDir) { [System.IO.Path]::GetFullPath((Join-Path $projectRoot $SampleDataDir)) } else { Join-Path $projectRoot "desktop\sample_data" }
Set-Location $projectRoot

function Invoke-CheckedCommand {
    param(
        [string]$Label,
        [scriptblock]$Command
    )

    Write-Host $Label
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

if (-not $SkipSampleDataPrepare) {
    if (-not $SampleSourceData) { $SampleSourceData = Join-Path $projectRoot "data" }
    if (Test-Path -LiteralPath $SampleSourceData) {
        & (Join-Path $projectRoot "scripts\prepare-desktop-sample-data.ps1") -SourceData $SampleSourceData -TargetData $sampleData -BookName $SampleBookName
    } elseif ($RequireSampleData) {
        throw "Sample source data not found: $SampleSourceData"
    } else {
        Write-Warning "Sample source data not found: $SampleSourceData. The desktop package will not include bundled demo data/models."
    }
}

if (-not (Test-Path -LiteralPath $sampleData)) {
    throw "Sample data directory not found: $sampleData"
}
$sampleFiles = Get-ChildItem -LiteralPath $sampleData -Recurse -File
$sampleSize = ($sampleFiles | Measure-Object Length -Sum).Sum
if ($RequireSampleData -and $sampleFiles.Count -eq 0) {
    throw "Sample data directory is empty: $sampleData"
}
Write-Host "Sample data: $sampleData"
Write-Host "  Files: $($sampleFiles.Count)"
Write-Host "  Size:  $([math]::Round($sampleSize / 1MB, 1)) MiB"

Invoke-CheckedCommand "[Content gate] Verifying bundled sample licenses and hashes..." {
    & $Python scripts\check_release_content.py --sample-dir $sampleData
}

Invoke-CheckedCommand "[1/3] Building frontend assets..." {
    Push-Location (Join-Path $projectRoot "frontend")
    try {
        npm.cmd run build
    } finally {
        Pop-Location
    }
}

Invoke-CheckedCommand "[2/3] Checking PyInstaller..." {
    & $Python -m PyInstaller --version
}

Write-Host "[2.5/3] Verifying CPU-only PyTorch..."
$torchCheck = & $Python -c "import json, torch; print(json.dumps({'version': torch.__version__, 'compiled_cuda': torch.version.cuda, 'cuda_available': torch.cuda.is_available()}))" 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Failed to import torch: $torchCheck"
}
try {
    $torchInfo = ($torchCheck | Select-Object -Last 1) | ConvertFrom-Json
} catch {
    throw "Could not parse PyTorch build information: $torchCheck"
}
Write-Host "  PyTorch version:      $($torchInfo.version)"
Write-Host "  Compiled CUDA runtime: $($torchInfo.compiled_cuda)"
Write-Host "  CUDA available:       $($torchInfo.cuda_available)"
if (
    $torchInfo.version -notmatch '\+cpu$' -or
    $null -ne $torchInfo.compiled_cuda -or
    [bool]$torchInfo.cuda_available
) {
    throw @"
Non-CPU PyTorch detected: version=$($torchInfo.version), compiled_cuda=$($torchInfo.compiled_cuda), cuda_available=$($torchInfo.cuda_available)
The release build requires an explicit +cpu wheel. Reinstall from requirements-release.txt.
"@
}
Write-Host "  Explicit CPU-only PyTorch confirmed - OK"

Invoke-CheckedCommand "[3/3] Building backend executable..." {
    & $Python -m PyInstaller `
      --noconfirm `
      --clean `
      --name backend_server `
      --distpath build\backend `
      --workpath build\pyinstaller `
      --specpath build\pyinstaller `
      --paths $projectRoot `
      --hidden-import backend.main `
      --hidden-import langchain_chroma `
      --hidden-import chromadb `
      --hidden-import sentence_transformers `
      --hidden-import huggingface_hub `
      --collect-submodules backend `
      --collect-submodules graph `
      --collect-submodules ingestion `
      --collect-submodules knowledge `
      --collect-submodules memory `
      --collect-submodules utils `
      --collect-data chromadb `
      --collect-data sentence_transformers `
      --collect-data transformers `
      --exclude-module agents `
      --exclude-module paddle `
      --exclude-module paddleocr `
      --exclude-module paddlex `
      --exclude-module cv2 `
      --exclude-module mineru `
      --exclude-module mineru_vl_utils `
      --exclude-module marker_pdf `
      --exclude-module marker `
      --exclude-module surya `
      --exclude-module nougat `
      --exclude-module doclayout_yolo `
      --exclude-module modelscope `
      --exclude-module albumentations `
      --exclude-module skimage `
      --exclude-module gradio `
      --exclude-module gradio_client `
      --exclude-module plotly `
      --exclude-module coverage `
      --exclude-module hypothesis `
      --exclude-module pytest_cov `
      --exclude-module notebook `
      --exclude-module jupyter `
      --exclude-module jupyterlab `
      --exclude-module sphinx `
      --exclude-module mkdocs `
      --exclude-module ultralytics `
      --exclude-module torchvision `
      --exclude-module datasets `
      --exclude-module timm `
      --exclude-module av `
      --exclude-module boto3 `
      --exclude-module botocore `
      --exclude-module s3transfer `
      --exclude-module pandas `
      --exclude-module polars `
      --exclude-module pyarrow `
      --exclude-module matplotlib `
      --exclude-module IPython `
      --exclude-module jedi `
      --exclude-module pytest `
      --exclude-module nltk `
      --exclude-module sklearn `
      --exclude-module lightning `
      --exclude-module onnxruntime `
      --exclude-module tkinter `
      --exclude-module _tkinter `
      --add-data "${frontendDist};frontend\dist" `
      --add-data "${projectRoot}\VERSION;." `
      --add-data "${projectRoot}\THIRD_PARTY_NOTICES;THIRD_PARTY_NOTICES" `
      --add-data "${sampleData};sample_data" `
      desktop\backend_server.py
}

Write-Host "[Post-build] Verifying CPU-only PE imports..."
& $Python -B scripts\verify_cpu_only_build.py --root build\backend\backend_server
if ($LASTEXITCODE -ne 0) {
    throw "CPU-only PE verification failed. The backend build was not accepted."
}
Write-Host "Backend executable ready: build\backend\backend_server\backend_server.exe"
Write-Host "Next: cd desktop; npm install; npm run dist"
