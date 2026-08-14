param(
    [string]$Python = "benchmark_results\embedding_onnx_phase2\venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$phase = Join-Path $root "benchmark_results\embedding_onnx_phase3"
$dist = Join-Path $phase "benchmark_companion"
$work = Join-Path $phase "benchmark_companion_work"

& $Python -m PyInstaller `
  --noconfirm `
  --clean `
  --name phase3_embedding_benchmark `
  --distpath $dist `
  --workpath $work `
  --specpath $work `
  --paths $root `
  --hidden-import onnxruntime `
  --hidden-import tokenizers `
  --hidden-import evaluation.embedding_backend.phase1_worker `
  --exclude-module torch `
  --exclude-module sentence_transformers `
  --exclude-module transformers `
  --exclude-module safetensors `
  --add-data "${root}\evaluation\datasets;evaluation\datasets" `
  (Join-Path $root "scripts\benchmark_phase3_embedding.py")
if ($LASTEXITCODE -ne 0) {
    throw "Phase 3 benchmark companion failed with exit code $LASTEXITCODE"
}

Write-Host "Phase 3 benchmark companion ready: $dist\phase3_embedding_benchmark"
