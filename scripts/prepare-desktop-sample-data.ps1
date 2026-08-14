param(
    [string]$SourceData = "",
    [string]$TargetData = "",
    [string]$BookName = "优化设计",
    [bool]$IncludeOriginalPdf = $false
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $SourceData) { $SourceData = Join-Path $projectRoot "data" }
if (-not $TargetData) { $TargetData = Join-Path $projectRoot "desktop\sample_data" }

$source = Resolve-Path -LiteralPath $SourceData -ErrorAction Stop
$sourcePath = $source.Path
$targetPath = [System.IO.Path]::GetFullPath($TargetData)

function Reset-ChildPath {
    param([string]$RelativePath)
    $target = Join-Path $targetPath $RelativePath
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

function Copy-IfExists {
    param([string]$From, [string]$To)
    if (-not (Test-Path -LiteralPath $From)) { return }
    $parent = Split-Path -Parent $To
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Copy-Item -LiteralPath $From -Destination $To -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $targetPath | Out-Null
@("books", "chapters", "images", "progress", "vector_db", "models", "desktop_assets.json") | ForEach-Object { Reset-ChildPath $_ }

if ($IncludeOriginalPdf) {
    Copy-IfExists (Join-Path $sourcePath "books\$BookName.pdf") (Join-Path $targetPath "books\$BookName.pdf")
}
Copy-IfExists (Join-Path $sourcePath "chapters\$BookName") (Join-Path $targetPath "chapters\$BookName")
Copy-IfExists (Join-Path $sourcePath "images\$BookName") (Join-Path $targetPath "images\$BookName")
Copy-IfExists (Join-Path $sourcePath "progress\$BookName") (Join-Path $targetPath "progress\$BookName")

$progressSource = Join-Path $sourcePath "progress"
if (Test-Path -LiteralPath $progressSource) {
    Get-ChildItem -LiteralPath $progressSource -File | Where-Object {
        $_.Name -like "*_$BookName.db" -or $_.Name -like "*_$BookName.db-*"
    } | ForEach-Object {
        Copy-IfExists $_.FullName (Join-Path $targetPath "progress\$($_.Name)")
    }
}

Copy-IfExists (Join-Path $sourcePath "vector_db") (Join-Path $targetPath "vector_db")
$manifest = [ordered]@{
    schema_version = 1
    assets = [ordered]@{
        vector_bundle = [ordered]@{
            version = "demo-v1"
            url = "bundled://desktop/sample_data/vector_db"
            sha256 = ""
            path = "vector_db"
            installed_at = (Get-Date).ToString("s")
        }
    }
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $targetPath "desktop_assets.json") -Encoding UTF8

$fileCount = (Get-ChildItem -LiteralPath $targetPath -Recurse -File | Measure-Object).Count
$totalBytes = (Get-ChildItem -LiteralPath $targetPath -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host "Prepared desktop sample data: $fileCount files, $([Math]::Round($totalBytes / 1MB, 2)) MB"
Write-Host "Target: $targetPath"
