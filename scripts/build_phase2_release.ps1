param(
    [ValidateSet("baseline", "candidate")]
    [string]$Variant,
    [string]$Python
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$phase = Join-Path $root "benchmark_results\embedding_onnx_phase2"
$frontend = Join-Path $root "frontend\dist"
$variantRoot = Join-Path $phase $Variant
$dist = Join-Path $variantRoot "backend"
$work = Join-Path $variantRoot "pyinstaller"
$sample = if ($Variant -eq "baseline") {
    Join-Path $root "desktop\sample_data"
} else {
    Join-Path $phase "candidate_sample_data"
}
$entry = if ($Variant -eq "baseline") {
    Join-Path $root "desktop\backend_server.py"
} else {
    Join-Path $root "scripts\phase2_candidate_backend_server.py"
}

if (-not $Python) {
    $Python = if ($Variant -eq "baseline") {
        Join-Path $root "venv310\Scripts\python.exe"
    } else {
        Join-Path $phase "venv\Scripts\python.exe"
    }
}

$args = @(
    "--noconfirm", "--clean", "--name", "backend_server",
    "--distpath", $dist, "--workpath", $work, "--specpath", $work,
    "--paths", $root,
    "--hidden-import", "backend.main",
    "--hidden-import", "langchain_chroma",
    "--hidden-import", "chromadb",
    "--hidden-import", "huggingface_hub",
    "--collect-submodules", "backend",
    "--collect-submodules", "graph",
    "--collect-submodules", "ingestion",
    "--collect-submodules", "knowledge",
    "--collect-submodules", "memory",
    "--collect-submodules", "utils",
    "--collect-submodules", "chromadb",
    "--collect-data", "chromadb"
)

if ($Variant -eq "baseline") {
    $args += @(
        "--hidden-import", "sentence_transformers",
        "--collect-data", "sentence_transformers",
        "--collect-data", "transformers",
        "--exclude-module", "onnxruntime"
    )
} else {
    $args += @(
        "--hidden-import", "evaluation.embedding_backend.phase2_runtime",
        "--hidden-import", "onnxruntime",
        "--hidden-import", "tokenizers",
        "--exclude-module", "torch",
        "--exclude-module", "sentence_transformers",
        "--exclude-module", "transformers",
        "--exclude-module", "safetensors"
    )
}

$excludes = @(
    "agents", "paddle", "paddleocr", "paddlex", "cv2", "mineru",
    "mineru_vl_utils", "marker_pdf", "marker", "surya", "nougat",
    "doclayout_yolo", "modelscope", "albumentations", "skimage", "plotly",
    "coverage", "hypothesis", "pytest_cov",
    "notebook", "jupyter", "jupyterlab", "sphinx", "mkdocs", "ultralytics",
    "torchvision", "datasets", "timm", "av", "boto3", "botocore",
    "s3transfer", "pandas", "polars", "pyarrow", "matplotlib", "IPython",
    "jedi", "pytest", "nltk", "lightning", "tkinter", "_tkinter"
)
foreach ($name in $excludes) {
    $args += @("--exclude-module", $name)
}

$args += @(
    "--add-data", "${frontend};frontend\dist",
    "--add-data", "${root}\VERSION;.",
    "--add-data", "${root}\THIRD_PARTY_NOTICES;THIRD_PARTY_NOTICES",
    "--add-data", "${sample};sample_data",
    $entry
)

New-Item -ItemType Directory -Force -Path $variantRoot | Out-Null
& $Python -m PyInstaller @args
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller $Variant failed with exit code $LASTEXITCODE"
}

$backendSource = Join-Path $dist "backend_server"
$releaseOutput = Join-Path $variantRoot "release"
$configPath = Join-Path $variantRoot "electron-builder.json"
$config = [ordered]@{
    appId = "local.kaoyan.assistant.phase2.$Variant"
    productName = "Texa Phase2 $Variant"
    artifactName = ('texa-phase2-' + $Variant + '-${version}-${arch}.${ext}')
    directories = @{ output = $releaseOutput }
    files = @("main.cjs", "preload.cjs", "runtime.cjs", "loading.html", "update-config.json", "package.json")
    extraResources = @(@{ from = $dist; to = "backend"; filter = @("**/*") })
    win = @{ target = @("nsis", "zip") }
    nsis = @{
        oneClick = $false
        allowToChangeInstallationDirectory = $true
        createDesktopShortcut = $false
        createStartMenuShortcut = $false
        deleteAppDataOnUninstall = $false
    }
}
$config | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $configPath -Encoding UTF8

Push-Location (Join-Path $root "desktop")
try {
    & ".\node_modules\.bin\electron-builder.cmd" --win nsis zip --config $configPath
    if ($LASTEXITCODE -ne 0) {
        throw "electron-builder $Variant failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

Write-Host "Phase 2 $Variant release complete: $releaseOutput"
