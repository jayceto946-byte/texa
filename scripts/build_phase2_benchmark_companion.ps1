param(
    [ValidateSet("baseline", "candidate")]
    [string]$Variant
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$phase = Join-Path $root "benchmark_results\embedding_onnx_phase2"
$variantRoot = Join-Path $phase $Variant
$dist = Join-Path $variantRoot "benchmark_companion"
$work = Join-Path $variantRoot "benchmark_companion_work"
$python = if ($Variant -eq "baseline") {
    Join-Path $root "venv310\Scripts\python.exe"
} else {
    Join-Path $phase "venv\Scripts\python.exe"
}
$modelData = if ($Variant -eq "baseline") {
    Join-Path $root "data\models"
} else {
    Join-Path $phase "candidate_sample_data\models"
}

$args = @(
    "--noconfirm", "--clean", "--name", "phase2_benchmark",
    "--distpath", $dist, "--workpath", $work, "--specpath", $work,
    "--paths", $root,
    "--hidden-import", "evaluation.embedding_backend.providers",
    "--add-data", "${root}\evaluation\datasets;evaluation\datasets",
    "--add-data", "${modelData};data\models"
)

if ($Variant -eq "baseline") {
    $args += @(
        "--hidden-import", "sentence_transformers",
        "--collect-data", "sentence_transformers",
        "--collect-data", "transformers",
        "--exclude-module", "onnxruntime",
        "--exclude-module", "torchvision"
    )
} else {
    $args += @(
        "--hidden-import", "onnxruntime",
        "--hidden-import", "tokenizers",
        "--exclude-module", "torch",
        "--exclude-module", "sentence_transformers",
        "--exclude-module", "transformers",
        "--exclude-module", "safetensors"
    )
}

$args += Join-Path $root "evaluation\embedding_backend\phase1_worker.py"
& $python -m PyInstaller @args
if ($LASTEXITCODE -ne 0) {
    throw "Phase 2 benchmark companion $Variant failed with exit code $LASTEXITCODE"
}
$bundleRoot = $dist
New-Item -ItemType Directory -Force -Path (Join-Path $bundleRoot "evaluation\datasets") | Out-Null
Copy-Item -LiteralPath (Join-Path $root "evaluation\datasets\embedding_parity.json") -Destination (Join-Path $bundleRoot "evaluation\datasets") -Force
Copy-Item -LiteralPath (Join-Path $root "evaluation\datasets\embedding_retrieval.json") -Destination (Join-Path $bundleRoot "evaluation\datasets") -Force
New-Item -ItemType Directory -Force -Path (Join-Path $bundleRoot "data\models") | Out-Null
Copy-Item -LiteralPath (Join-Path $modelData "models--BAAI--bge-small-zh-v1.5") -Destination (Join-Path $bundleRoot "data\models") -Recurse -Force
Write-Host "Built $Variant benchmark companion at $dist"
