param(
    [string]$ComfyRoot = 'D:\ComfyUI',
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $ComfyRoot '.venv\Scripts\python.exe'
$url = 'http://127.0.0.1:8188/'
$healthUrl = 'http://127.0.0.1:8188/system_stats'

function Test-ComfyUIReady {
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
        return $null -ne $health.system -and $null -ne $health.devices
    } catch {
        return $false
    }
}

try {
    if (-not (Test-ComfyUIReady)) {
        if (Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue) {
            throw '8188 端口已被其他程序占用，未启动或结束任何进程。'
        }
        if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
            throw "ComfyUI Python 环境不存在：$python"
        }
        if (-not (Test-Path -LiteralPath (Join-Path $ComfyRoot 'main.py') -PathType Leaf)) {
            throw "ComfyUI main.py 不存在：$ComfyRoot"
        }
        $logDir = Join-Path $repoRoot 'workspace\launcher_logs'
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        $stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
        $stdout = Join-Path $logDir "comfyui_$stamp.stdout.log"
        $stderr = Join-Path $logDir "comfyui_$stamp.stderr.log"
        $server = Start-Process -FilePath $python -ArgumentList @('main.py', '--listen', '127.0.0.1', '--port', '8188', '--lowvram', '--disable-auto-launch') `
            -WorkingDirectory $ComfyRoot -WindowStyle Hidden -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr -PassThru
        $ready = $false
        for ($attempt = 0; $attempt -lt 120; $attempt++) {
            if (Test-ComfyUIReady) { $ready = $true; break }
            if ($server.HasExited) { break }
            Start-Sleep -Milliseconds 500
        }
        if (-not $ready) { throw "ComfyUI 启动失败；查看日志：$stdout 和 $stderr" }
    }
    Write-Host "ComfyUI 已就绪：$url"
    if (-not $NoBrowser) { Start-Process -FilePath $url }
} catch {
    Write-Error $_
    exit 1
}
