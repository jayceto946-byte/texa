# Build the backend executable for the Electron desktop app.
#
# Texa Standard embeds with ONNX Runtime and MUST NOT package Torch,
# SentenceTransformers, Transformers, or safetensors.
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
$sampleData = if ($SampleDataDir) { [System.IO.Path]::GetFullPath((Join-Path $projectRoot $SampleDataDir)) } else { Join-Path $projectRoot "desktop\standard_seed" }
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

if (-not $SkipSampleDataPrepare -and $SampleSourceData) {
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

Write-Host "[2.5/3] Verifying ONNX Standard build environment..."
$runtimeCheck = & $Python -B -c "import json, onnxruntime, tokenizers; print(json.dumps({'onnxruntime': onnxruntime.__version__, 'tokenizers': tokenizers.__version__}))" 2>&1
if ($LASTEXITCODE -ne 0) { throw "Failed to import the ONNX Standard runtime: $runtimeCheck" }
Write-Host ($runtimeCheck | Select-Object -Last 1)

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
      --hidden-import huggingface_hub `
      --hidden-import onnxruntime `
      --hidden-import tokenizers `
      --collect-submodules backend `
      --collect-submodules graph `
      --collect-submodules ingestion `
      --collect-submodules knowledge `
      --collect-submodules memory `
      --collect-submodules utils `
      --collect-submodules chromadb `
      --collect-data chromadb `
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
      --exclude-module torch `
      --exclude-module sentence_transformers `
      --exclude-module transformers `
      --exclude-module safetensors `
      --exclude-module tkinter `
      --exclude-module _tkinter `
      --add-data "${frontendDist};frontend\dist" `
      --add-data "${projectRoot}\VERSION;." `
      --add-data "${projectRoot}\THIRD_PARTY_NOTICES;THIRD_PARTY_NOTICES" `
      --add-data "${sampleData};sample_data" `
      desktop\backend_server.py
}

Write-Host "[Post-build] Verifying Torch-free ONNX Standard runtime..."
& $Python -B scripts\validate_standard_release.py `
  --root build\backend\backend_server `
  --asset-dir assets\embedding-runtime\bge-small-zh-v1.5\onnx-fp32-v1 `
  --pyinstaller-xref build\pyinstaller\backend_server\xref-backend_server.html
if ($LASTEXITCODE -ne 0) {
    throw "Texa Standard validation failed. The backend build was not accepted."
}
Write-Host "Backend executable ready: build\backend\backend_server\backend_server.exe"
Write-Host "Next: cd desktop; npm install; npm run dist"
