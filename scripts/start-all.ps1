# PDCA Prowler Agent -- start all services
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File scripts\start-all.ps1
# Stop: powershell -ExecutionPolicy Bypass -File scripts\stop-all.ps1

param([switch]$NoWait)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  PDCA Prowler Agent  --  start-all   " -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------
if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "[ERROR] venv not found. Run:" -ForegroundColor Red
    Write-Host "  python -m venv venv" -ForegroundColor Yellow
    Write-Host "  venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path "Frontend-v2\node_modules")) {
    Write-Host "[ERROR] Frontend-v2\node_modules missing. Run:" -ForegroundColor Red
    Write-Host "  cd Frontend-v2" -ForegroundColor Yellow
    Write-Host "  npm install" -ForegroundColor Yellow
    exit 1
}

$Python = Join-Path $RepoRoot "venv\Scripts\python.exe"

# ---------------------------------------------------------------------------
# Kill stale listeners
# ---------------------------------------------------------------------------
Write-Host "[preflight] clearing ports 9001 9002 9005 5173 5174..." -ForegroundColor Gray
foreach ($port in @(9001, 9002, 9005, 5173, 5174)) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "  killed PID $($c.OwningProcess) on :$port" -ForegroundColor Gray
    }
}
Start-Sleep -Milliseconds 600

# ---------------------------------------------------------------------------
# Launch helper: writes a tiny launcher script + opens a minimized window
# ---------------------------------------------------------------------------
function Start-Service {
    param(
        [string]$Name,
        [string]$Cwd,
        [string]$Command,
        [hashtable]$Env = @{}
    )
    # Write a temporary launcher so Start-Process doesn't hit quoting limits.
    $tmp = Join-Path $env:TEMP "pdca_start_$([System.IO.Path]::GetRandomFileName()).ps1"
    $lines = @()
    $lines += "Set-Location '$Cwd'"
    foreach ($kv in $Env.GetEnumerator()) {
        $lines += "`$env:$($kv.Key) = '$($kv.Value)'"
    }
    $lines += "Write-Host '[$Name] starting...' -ForegroundColor Cyan"
    $lines += $Command
    $lines += "Write-Host '[$Name] process exited' -ForegroundColor Yellow"
    $lines += "Read-Host 'Press Enter to close'"
    $lines -join "`n" | Set-Content $tmp -Encoding UTF8

    Start-Process powershell `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$tmp`"" `
        -WindowStyle Minimized
}

# ---------------------------------------------------------------------------
# Launch services
# ---------------------------------------------------------------------------
Write-Host "[start] Scanner API  :9001" -ForegroundColor Yellow
Start-Service `
    -Name    "Scanner :9001" `
    -Cwd     $RepoRoot `
    -Command "$Python -m uvicorn pdca.api_server:app --host 127.0.0.1 --port 9001"

Write-Host "[start] RAG API      :9005" -ForegroundColor Magenta
Start-Service `
    -Name    "RAG :9005" `
    -Cwd     $RepoRoot `
    -Command "$Python RAG\start.py --port 9005"

Write-Host "[start] Chatbot API  :9002" -ForegroundColor Cyan
Start-Service `
    -Name    "Chatbot :9002" `
    -Cwd     $RepoRoot `
    -Command "$Python -m uvicorn pdca.api.chatbot:app --host 127.0.0.1 --port 9002" `
    -Env     @{ SCANNER_API_URL = "http://127.0.0.1:9001" }

Write-Host "[start] Frontend-v2  :5174" -ForegroundColor Green
Start-Service `
    -Name    "Frontend-v2 :5174" `
    -Cwd     (Join-Path $RepoRoot "Frontend-v2") `
    -Command "npm run dev"

if ($NoWait) { exit 0 }

# ---------------------------------------------------------------------------
# Health check (max 90s)
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[wait] probing services (max 90s)..." -ForegroundColor Gray

$checks = @(
    @{ Name = "Scanner :9001"; Url = "http://127.0.0.1:9001/v1/jobs?limit=1" }
    @{ Name = "RAG     :9005"; Url = "http://127.0.0.1:9005/ready" }
    @{ Name = "Chatbot :9002"; Url = "http://127.0.0.1:9002/openapi.json" }
    @{ Name = "Frontend:5174"; Url = "http://localhost:5174/" }
)

$ready   = @{}
$maxWait = 90
$elapsed = 0

while ($elapsed -lt $maxWait) {
    foreach ($chk in $checks) {
        if ($ready.ContainsKey($chk.Name)) { continue }
        try {
            $r = Invoke-WebRequest -Uri $chk.Url -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
            if ($r.StatusCode -lt 400) {
                $ready[$chk.Name] = $true
                Write-Host "  [OK] $($chk.Name)" -ForegroundColor Green
            }
        } catch {}
    }
    if ($ready.Count -eq $checks.Count) { break }
    Start-Sleep -Seconds 2
    $elapsed += 2
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Write-Host ""
if ($ready.Count -eq $checks.Count) {
    Write-Host "======================================" -ForegroundColor Green
    Write-Host "  All 4 services ready!" -ForegroundColor Green
    Write-Host "======================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Frontend  ->  http://localhost:5174" -ForegroundColor White
    Write-Host "  Chatbot   ->  http://127.0.0.1:9002/docs" -ForegroundColor White
    Write-Host "  Scanner   ->  http://127.0.0.1:9001/docs" -ForegroundColor White
    Write-Host "  RAG       ->  http://127.0.0.1:9005/docs" -ForegroundColor White
    Write-Host ""
    Write-Host "  To stop:  scripts\stop-all.ps1" -ForegroundColor Gray
} else {
    Write-Host "[WARNING] some services did not respond in time:" -ForegroundColor Yellow
    foreach ($chk in $checks) {
        if ($ready.ContainsKey($chk.Name)) {
            Write-Host "  [OK]   $($chk.Name)" -ForegroundColor Green
        } else {
            Write-Host "  [FAIL] $($chk.Name)" -ForegroundColor Red
        }
    }
    Write-Host ""
    Write-Host "  Check the minimized terminal windows for errors." -ForegroundColor Yellow
}
