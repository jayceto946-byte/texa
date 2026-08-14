param(
    [string]$OutputRoot = "exports",
    [string]$BookName = "优化设计",
    [switch]$IncludeSourcePdf,
    [switch]$Zip
)

$ErrorActionPreference = "Stop"

function Copy-IfExists {
    param(
        [string]$Source,
        [string]$Destination
    )
    if (Test-Path -LiteralPath $Source) {
        $destParent = Split-Path -Parent $Destination
        New-Item -ItemType Directory -Force -Path $destParent | Out-Null
        Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
        return $true
    }
    return $false
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$packageName = "texa-demo-$BookName-$timestamp"
$packageRoot = Join-Path (Join-Path $projectRoot $OutputRoot) $packageName
$dataRoot = Join-Path $packageRoot "data"
$copied = New-Object System.Collections.Generic.List[string]

New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null

$progressSource = Join-Path $projectRoot "data\progress\$BookName"
$progressDest = Join-Path $dataRoot "progress\$BookName"
if (Copy-IfExists $progressSource $progressDest) {
    $copied.Add("data/progress/$BookName/") | Out-Null
}

foreach ($dbName in @("exercise_bank_$BookName.db", "mistake_book_$BookName.db")) {
    $source = Join-Path $projectRoot "data\progress\$dbName"
    $dest = Join-Path $dataRoot "progress\$dbName"
    if (Copy-IfExists $source $dest) {
        $copied.Add("data/progress/$dbName") | Out-Null
    }
}

$vectorSource = Join-Path $projectRoot "data\vector_db"
$vectorDest = Join-Path $dataRoot "vector_db"
if (Copy-IfExists $vectorSource $vectorDest) {
    $copied.Add("data/vector_db/") | Out-Null
}

if ($IncludeSourcePdf) {
    $pdfSource = Join-Path $projectRoot "data\books\$BookName.pdf"
    $pdfDest = Join-Path $dataRoot "books\$BookName.pdf"
    if (Copy-IfExists $pdfSource $pdfDest) {
        $copied.Add("data/books/$BookName.pdf") | Out-Null
    }
}

$readme = @"
# $BookName 示例数据包

这是 Texa 的示例数据包，用于向新用户演示教材问答、知识图谱、错题本和习题库能力。

## 包含内容

- data/progress/$BookName：章节、知识图谱、关键词索引、概念记忆等学习数据
- data/progress/exercise_bank_$BookName.db：示例习题库
- data/progress/mistake_book_$BookName.db：示例错题本
- data/vector_db：本地 Chroma 向量库

## 不包含内容

- .env、API Key、账号信息
- Python 虚拟环境
- frontend/node_modules
- OCR 临时目录和调试日志
- 原始 PDF，除非导出时显式传入 -IncludeSourcePdf

## 导入方式

把本包内的 data 目录合并到软件根目录的 data 目录。若目标机器已有同名数据，请先备份。

注意：data/vector_db 当前按整库导出，适合演示包使用。若未来同时维护多本教材，建议再做 collection 级别的纯净导出。

## 版权提醒

如果导出时包含原始 PDF，请确认你拥有向用户分发该文件的权利。默认导出不会包含原始 PDF。
"@
$readme | Set-Content -LiteralPath (Join-Path $packageRoot "README.md") -Encoding UTF8

$manifest = [ordered]@{
    name = "$BookName 示例数据包"
    package = $packageName
    created_at = (Get-Date -Format o)
    book_name = $BookName
    include_source_pdf = [bool]$IncludeSourcePdf
    copied = $copied
    excluded = @(".env", "API keys", "virtualenvs", "node_modules", "logs", "temporary OCR outputs")
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $packageRoot "manifest.json") -Encoding UTF8

if ($Zip) {
    $zipPath = "$packageRoot.zip"
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    Compress-Archive -LiteralPath $packageRoot -DestinationPath $zipPath -Force
    Write-Host "Demo package created: $packageRoot"
    Write-Host "Zip created: $zipPath"
} else {
    Write-Host "Demo package created: $packageRoot"
}
