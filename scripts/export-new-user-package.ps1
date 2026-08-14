param(
    [string]$OutputRoot = "exports",
    [switch]$IncludeOutsideNotes
)

$ErrorActionPreference = "Stop"

function Get-RelativePathCompat {
    param(
        [string]$From,
        [string]$To
    )
    $fromFull = [System.IO.Path]::GetFullPath($From).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    $toFull = [System.IO.Path]::GetFullPath($To)
    $fromUri = New-Object System.Uri($fromFull)
    $toUri = New-Object System.Uri($toFull)
    $relative = $fromUri.MakeRelativeUri($toUri).ToString()
    return [System.Uri]::UnescapeDataString($relative).Replace('/', [System.IO.Path]::DirectorySeparatorChar)
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$repoRoot = (& git -C $projectRoot rev-parse --show-toplevel).Trim()
$projectRel = (Get-RelativePathCompat -From $repoRoot -To $projectRoot).Replace("\", "/")

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outputBase = Join-Path $projectRoot $OutputRoot
$packageRoot = Join-Path $outputBase "texa-new-user-$timestamp"
$targetRoot = Join-Path $packageRoot "texa"

New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null

$tracked = & git -C $repoRoot -c core.quotePath=false ls-files -- $projectRel
$untracked = & git -C $repoRoot -c core.quotePath=false ls-files --others --exclude-standard -- $projectRel
$files = @($tracked + $untracked) | Where-Object { $_ -and $_.Trim() } | Sort-Object -Unique

$copied = New-Object System.Collections.Generic.List[string]
foreach ($repoRelative in $files) {
    $source = Join-Path $repoRoot ($repoRelative -replace '/', '\')
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { continue }

    $relativeToProject = Get-RelativePathCompat -From $projectRoot -To (Resolve-Path -LiteralPath $source).Path
    $dest = Join-Path $targetRoot $relativeToProject
    $destDir = Split-Path -Parent $dest
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    Copy-Item -LiteralPath $source -Destination $dest -Force
    $copied.Add($relativeToProject.Replace("\", "/")) | Out-Null
}

if ($IncludeOutsideNotes) {
    foreach ($outside in @("KG_Agent.md", "chunk_middle.py")) {
        $source = Join-Path (Split-Path -Parent $projectRoot) $outside
        if (Test-Path -LiteralPath $source -PathType Leaf) {
            $destDir = Join-Path $packageRoot "outside-notes"
            New-Item -ItemType Directory -Force -Path $destDir | Out-Null
            Copy-Item -LiteralPath $source -Destination (Join-Path $destDir $outside) -Force
        }
    }
}

$manifest = @()
$manifest += "Texa new-user source package"
$manifest += "Generated: $(Get-Date -Format o)"
$manifest += "Project root: $projectRoot"
$manifest += "Repository root: $repoRoot"
$manifest += "Files copied: $($copied.Count)"
$manifest += ""
$manifest += "Excluded by design:"
$manifest += "- .env and API key files"
$manifest += "- data/ local learning data"
$manifest += "- virtualenvs"
$manifest += "- frontend/node_modules and frontend/dist"
$manifest += "- caches, logs, diagnostics, backups, exports"
$manifest += ""
$manifest += "Next steps on the new machine:"
$manifest += "1. Copy .env.example to .env and fill API keys."
$manifest += "2. Run: docker compose up -d --build"
$manifest += "3. Open: http://127.0.0.1:8000"
$manifest += "4. Import textbooks and generate local indexes."
$manifest += ""
$manifest += "Copied files:"
$manifest += $copied

$manifestPath = Join-Path $packageRoot "PACKAGE_MANIFEST.txt"
$manifest | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Write-Host "New-user package created: $packageRoot"
Write-Host "Manifest: $manifestPath"
