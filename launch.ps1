#Requires -Version 5.1
<#
.SYNOPSIS
    Texa — 完整启动脚本
.DESCRIPTION
    自动检测虚拟环境、检查配置、清理残留进程、启动服务。
    支持 FastAPI 后端和 CLI 两种模式。
.EXAMPLE
    .\launch.ps1 web        # 启动 Web UI（默认端口 8080）
    .\launch.ps1 web 9000   # 启动 Web UI（自定义端口）
    .\launch.ps1 cli        # 启动命令行界面
    .\launch.ps1 --kill     # 仅清理残留进程
#>

param(
    [Parameter(Position=0)]
    [ValidateSet("web", "cli", "--kill", "")]
    [string]$Mode = "web",

    [Parameter(Position=1)]
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# ── 颜色输出辅助 ──────────────────────────────────────────
function Write-Info    ($msg) { Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Write-Ok      ($msg) { Write-Host "[OK]    $msg" -ForegroundColor Green }
function Write-Warn    ($msg) { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Write-Err     ($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red }
function Write-Section ($msg) { Write-Host "`n>>> $msg" -ForegroundColor Magenta }

# ── 1. 清理残留进程 ───────────────────────────────────────
function Kill-Residual {
    Write-Section "清理残留进程"
    $procs = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -match "main\.py" -or $_.CommandLine -match "uvicorn" -or $_.CommandLine -match "backend\.main"
    }
    if ($procs) {
        foreach ($p in $procs) {
            Write-Warn "终止残留进程: PID=$($p.Id)"
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 1
        Write-Ok "残留进程已清理"
    } else {
        Write-Ok "无残留进程"
    }

    # 检查端口占用
    $portProc = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($portProc) {
        $proc = Get-Process -Id $portProc.OwningProcess -ErrorAction SilentlyContinue
        Write-Warn "端口 $Port 被占用: PID=$($portProc.OwningProcess) ($($proc.ProcessName))"
        Write-Warn "尝试释放端口..."
        Stop-Process -Id $portProc.OwningProcess -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
        Write-Ok "端口 $Port 已释放"
    }
}

if ($Mode -eq "--kill") {
    Kill-Residual
    Write-Ok "仅执行清理，退出"
    exit 0
}

# ── 2. 激活虚拟环境 ───────────────────────────────────────
Write-Section "检查虚拟环境"
$VenvPaths = @(
    "$ScriptDir\venv310\Scripts\Activate.ps1",
    "$ScriptDir\venv\Scripts\Activate.ps1"
)
$VenvFound = $false
foreach ($vp in $VenvPaths) {
    if (Test-Path $vp) {
        Write-Info "激活虚拟环境: $vp"
        & $vp
        $VenvFound = $true
        break
    }
}
if (-not $VenvFound) {
    Write-Err "未找到虚拟环境 (venv310 或 venv)"
    Write-Err "请运行: python -m venv venv310"
    exit 1
}
Write-Ok "虚拟环境已激活: $(python --version)"

# ── 3. 检查 .env 配置 ─────────────────────────────────────
Write-Section "检查配置文件"
$EnvFile = "$ScriptDir\.env"
if (-not (Test-Path $EnvFile)) {
    Write-Warn ".env 文件不存在，从 .env.example 复制"
    if (Test-Path "$ScriptDir\.env.example") {
        Copy-Item "$ScriptDir\.env.example" $EnvFile
        Write-Ok "已创建 .env，请编辑配置你的 API Key"
    } else {
        Write-Warn ".env.example 也不存在，继续启动..."
    }
}

# 检查关键配置
$envContent = if (Test-Path $EnvFile) { Get-Content $EnvFile -Raw } else { "" }
$hasMoonshot = $envContent -match "MOONSHOT_API_KEY\s*=\s*sk-"
$hasOpenAI   = $envContent -match "OPENAI_API_KEY\s*=\s*sk-"
$hasOllama   = $envContent -match "OLLAMA_BASE_URL"

if ($hasMoonshot) {
    Write-Ok "检测到 MOONSHOT_API_KEY (Kimi K2.6)"
} elseif ($hasOpenAI) {
    Write-Ok "检测到 OPENAI_API_KEY"
} elseif ($hasOllama) {
    Write-Ok "检测到 Ollama 本地配置"
} else {
    Write-Warn "未检测到任何 LLM API Key"
    Write-Warn "编辑 .env 文件配置 MOONSHOT_API_KEY 或其他后端"
}

# ── 4. 检查关键依赖 ───────────────────────────────────────
Write-Section "检查依赖"
$RequiredPkgs = @("fastapi", "uvicorn", "langchain", "chromadb")
$Missing = @()
foreach ($pkg in $RequiredPkgs) {
    $found = python -c "import $pkg" 2>$null
    if ($LASTEXITCODE -ne 0) {
        $Missing += $pkg
    }
}
if ($Missing.Count -gt 0) {
    Write-Warn "缺少依赖: $($Missing -join ', ')"
    Write-Info "正在安装..."
    pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Err "依赖安装失败"
        exit 1
    }
    Write-Ok "依赖安装完成"
} else {
    Write-Ok "所有关键依赖已安装"
}

# ── 5. 清理残留并启动 ─────────────────────────────────────
Kill-Residual

Write-Section "启动 Texa"
if ($Mode -eq "web" -or $Mode -eq "") {
    Write-Info "模式: FastAPI 后端 | 端口: $Port"
    Write-Info "访问地址: http://127.0.0.1:$Port"
    Write-Host "────────────────────────────────────────" -ForegroundColor DarkGray
    python main.py web --host 127.0.0.1 --port $Port
} elseif ($Mode -eq "cli") {
    Write-Info "模式: CLI"
    Write-Host "────────────────────────────────────────" -ForegroundColor DarkGray
    python main.py cli
}

# ── 6. 退出处理 ───────────────────────────────────────────
Write-Host "`n────────────────────────────────────────" -ForegroundColor DarkGray
if ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq $null) {
    Write-Ok "服务已正常退出"
} else {
    Write-Err "服务异常退出 (ExitCode=$LASTEXITCODE)"
}
Write-Host "按 Enter 键关闭窗口..." -NoNewline
[void][System.Console]::ReadLine()
