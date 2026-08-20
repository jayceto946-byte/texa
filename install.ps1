# Texa - Windows 安装脚本
Write-Host "📚 Texa - 安装脚本" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# 1. 检查Python
Write-Host "🔍 检查Python环境..." -ForegroundColor Yellow
try {
    $pyVersion = python --version
    Write-Host "  ✓ $pyVersion" -ForegroundColor Green
} catch {
    Write-Host "  ❌ 未找到Python，请先安装 Python 3.10+" -ForegroundColor Red
    Write-Host "  下载地址: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

# 2. 创建虚拟环境
Write-Host "`n🔧 创建虚拟环境..." -ForegroundColor Yellow
$venvPath = Join-Path $PSScriptRoot "venv"
if (-not (Test-Path $venvPath)) {
    python -m venv $venvPath
    Write-Host "  ✓ 虚拟环境已创建" -ForegroundColor Green
} else {
    Write-Host "  ✓ 虚拟环境已存在" -ForegroundColor Green
}

# 3. 激活虚拟环境并安装依赖
Write-Host "`n📦 安装依赖包..." -ForegroundColor Yellow
$pip = Join-Path $venvPath "Scripts\pip.exe"
& $pip install --upgrade pip -q
& $pip install -r "$PSScriptRoot\requirements.txt"

if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ 依赖安装完成" -ForegroundColor Green
} else {
    Write-Host "  ❌ 依赖安装失败" -ForegroundColor Red
    exit 1
}

# 4. 配置.env
Write-Host "`n🔑 配置环境变量..." -ForegroundColor Yellow
$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item "$PSScriptRoot\.env.example" $envFile
    Write-Host "  ✓ 已创建 .env 文件，请编辑配置你的 API Key" -ForegroundColor Green
} else {
    Write-Host "  ✓ .env 文件已存在" -ForegroundColor Green
}

# 5. 创建启动脚本
Write-Host "`n🚀 创建启动脚本..." -ForegroundColor Yellow

# 启动CLI的脚本
$cliScript = @"
@echo off
call "$PSScriptRoot\venv\Scripts\activate"
python "$PSScriptRoot\main.py" cli
pause
"@
$cliScript | Out-File -FilePath "$PSScriptRoot\启动CLI.bat" -Encoding default

# 启动Web的脚本
$webScript = @"
@echo off
call "$PSScriptRoot\venv\Scripts\activate"
python "$PSScriptRoot\main.py" web --host 127.0.0.1 --port 8000
pause
"@
$webScript | Out-File -FilePath "$PSScriptRoot\启动Web.bat" -Encoding default

Write-Host "  ✓ 启动脚本已创建" -ForegroundColor Green

# 6. 完成
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "✅ 安装完成！" -ForegroundColor Green
Write-Host "使用方法：" -ForegroundColor White
Write-Host "  1. 将PDF教材放入 data/books/ 目录" -ForegroundColor White
Write-Host "  2. 编辑 .env 文件配置 API Key" -ForegroundColor White
Write-Host "  3. 运行 启动Web.bat 启动 FastAPI 后端，浏览器访问 http://127.0.0.1:8000" -ForegroundColor White
Write-Host "  或手动运行: python main.py web --port 8000" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
