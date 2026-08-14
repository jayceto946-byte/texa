param(
    [string]$Owner = "jayceto946-byte",
    [string]$Repository = "kaoyan-assistant",
    [string]$Tag = "embedding-runtime-onnx-fp32-v1",
    [string]$TargetCommitish = "5ea4fb0a3c71fe0b9cbd6ca3034b45e7b6cb3605",
    [string]$AssetDirectory = "assets\embedding-runtime\bge-small-zh-v1.5\onnx-fp32-v1"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$assetRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $AssetDirectory))
$manifestPath = Join-Path $assetRoot "embedding-runtime.json"
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Embedding runtime manifest not found: $manifestPath"
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$required = @($manifest.expected_files)
if ($required.Count -ne 6) {
    throw "Expected exactly six runtime assets, found $($required.Count)"
}
foreach ($item in $required) {
    $path = Join-Path $assetRoot ([string]$item.path)
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required asset is missing: $path"
    }
    $file = Get-Item -LiteralPath $path
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($file.Length -ne [long]$item.size -or $hash -ne ([string]$item.sha256).ToLowerInvariant()) {
        throw "Manifest verification failed before upload: $($item.path)"
    }
}

# Reuse Windows Git Credential Manager without printing or persisting its token.
$credentialLines = @("protocol=https", "host=github.com", "") | & git credential fill
if ($LASTEXITCODE -ne 0) {
    throw "Git Credential Manager did not return GitHub credentials"
}
$credential = @{}
foreach ($line in $credentialLines) {
    if ($line -match "^([^=]+)=(.*)$") {
        $credential[$matches[1]] = $matches[2]
    }
}
$token = [string]$credential["password"]
if (-not $token) {
    throw "No GitHub token is available from Git Credential Manager"
}
$headers = @{
    Authorization = "Bearer $token"
    Accept = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
    "User-Agent" = "Texa-embedding-runtime-publisher"
}

$apiRoot = "https://api.github.com/repos/$Owner/$Repository"
$release = $null
try {
    $release = Invoke-RestMethod -Uri "$apiRoot/releases/tags/$Tag" -Headers $headers -Method Get
} catch {
    $status = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
    if ($status -ne 404) { throw }
}

if (-not $release) {
    $notes = @"
Texa Standard frozen embedding runtime assets.

- Model: $($manifest.model_name)
- Model revision: $($manifest.model_version)
- ONNX graph: $($manifest.onnx_graph_version)
- Dtype: $($manifest.dtype)
- Pooling: $($manifest.pooling)
- Normalization: $($manifest.normalization)
- Max length: $($manifest.max_length)
- Embedding dimension: $($manifest.embedding_dimension)

The six attached files are verified against the repository embedding-runtime.json manifest before upload. This is an asset-only release; existing Chroma indexes do not require rebuild or re-embedding.
"@
    $body = @{
        tag_name = $Tag
        target_commitish = $TargetCommitish
        name = "Texa BGE-small ONNX FP32 runtime v1"
        body = $notes
        draft = $false
        prerelease = $false
    } | ConvertTo-Json
    $release = Invoke-RestMethod -Uri "$apiRoot/releases" -Headers $headers -Method Post -ContentType "application/json" -Body $body
    Write-Host "Created GitHub Release $Tag (id=$($release.id))"
} else {
    Write-Host "Using existing GitHub Release $Tag (id=$($release.id))"
}

$uploadBase = ([string]$release.upload_url).Split("{")[0]
$existing = @{}
foreach ($asset in @($release.assets)) {
    $existing[[string]$asset.name] = $asset
}
$uploaded = @()
foreach ($item in $required) {
    $name = [string]$item.path
    $path = Join-Path $assetRoot $name
    if ($existing.ContainsKey($name)) {
        $asset = $existing[$name]
        if ([long]$asset.size -ne [long]$item.size) {
            throw "Existing release asset has an unexpected size; refusing replacement: $name"
        }
        Write-Host "Asset already exists with expected size: $name"
        $uploaded += $asset
        continue
    }
    $encoded = [System.Uri]::EscapeDataString($name)
    Write-Host "Uploading $name ($((Get-Item -LiteralPath $path).Length) bytes)..."
    $asset = Invoke-RestMethod -Uri "$uploadBase`?name=$encoded" -Headers $headers -Method Post -ContentType "application/octet-stream" -InFile $path
    if ([long]$asset.size -ne [long]$item.size -or [string]$asset.state -ne "uploaded") {
        throw "GitHub did not confirm a complete upload for $name"
    }
    $uploaded += $asset
}

[pscustomobject]@{
    release_id = $release.id
    tag = $Tag
    target_commitish = $TargetCommitish
    html_url = $release.html_url
    assets = @($uploaded | ForEach-Object {
        [pscustomobject]@{
            name = $_.name
            size = $_.size
            state = $_.state
            browser_download_url = $_.browser_download_url
        }
    })
} | ConvertTo-Json -Depth 5

$token = $null
$credential = $null
