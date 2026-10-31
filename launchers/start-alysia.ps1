param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$url = 'http://127.0.0.1:8765/'
$healthUrl = 'http://127.0.0.1:8765/api/health'

function Test-AlysiaReady {
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
        return $health.status -eq 'healthy' -and [bool]$health.local_only
    } catch {
        return $false
    }
}

try {
    if (-not (Test-AlysiaReady)) {
        if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
            throw '8765 端口已被其他程序占用，未启动或结束任何进程。'
        }
        if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
            throw "Alysia Python 环境不存在：$python"
        }
        $logDir = Join-Path $repoRoot 'workspace\launcher_logs'
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        $stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
        $stdout = Join-Path $logDir "alysia_$stamp.stdout.log"
        $stderr = Join-Path $logDir "alysia_$stamp.stderr.log"
        $server = Start-Process -FilePath $python -ArgumentList @('-m', 'alysia', 'control', 'start') `
            -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr -PassThru
        $ready = $false
        for ($attempt = 0; $attempt -lt 90; $attempt++) {
            if (Test-AlysiaReady) { $ready = $true; break }
            if ($server.HasExited) { break }
            Start-Sleep -Milliseconds 500
        }
        if (-not $ready) { throw "Alysia 启动失败；查看日志：$stdout 和 $stderr" }
    }
    Write-Host "Alysia 控制中心已就绪：$url"
    if (-not $NoBrowser) { Start-Process -FilePath $url }
} catch {
    Write-Error $_
    exit 1
}
