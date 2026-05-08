# PDCA Prowler Agent — start all services for demo
#
# Launches 4 services as VSCode tasks. Each task opens its own dedicated tab
# inside the VSCode integrated terminal panel (no external PowerShell windows).
# Tasks are defined in .vscode/tasks.json.
#
# Usage (from repo root, inside VSCode):
#   powershell -ExecutionPolicy Bypass -File scripts\start-all.ps1
#
# Or from VSCode Command Palette:
#   Ctrl+Shift+P  ->  Tasks: Run Task  ->  start-all
#
# Requirements (one-time):
#   - venv/ at repo root (Python 3.13) with requirements installed
#   - Frontend/node_modules (run `npm install` in Frontend/)
#   - Ollama running with the model in OLLAMA_MODEL pulled
#   - .env at repo root with AWS + Langfuse + RAG_API_URL filled
#
# Stop everything: run scripts\stop-all.ps1, or kill each terminal tab.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "[start-all] repo root: $RepoRoot" -ForegroundColor Cyan

# --------------------------------------------------------------------------
# Pre-flight checks - fail fast if env is broken
# --------------------------------------------------------------------------
if (-not (Test-Path "venv\Scripts\python.exe")) {
    throw "venv not found at $RepoRoot\venv. Run: python -m venv venv && venv\Scripts\pip install -r requirements.txt"
}
if (-not (Test-Path "Frontend\node_modules")) {
    throw "Frontend\node_modules missing. Run: cd Frontend && npm install"
}
if (-not (Test-Path ".env")) {
    Write-Warning ".env not found at repo root - services will use defaults from settings.py"
}
if (-not (Test-Path ".vscode\tasks.json")) {
    throw ".vscode\tasks.json missing - cannot launch services as VSCode tasks"
}

# --------------------------------------------------------------------------
# Launch the compound 'start-all' task in VSCode
# --------------------------------------------------------------------------
# `code` CLI re-uses the current window when given a folder path, then we
# fire the runTask command via the URI handler. If code CLI is unavailable,
# fall back to printing manual instructions.
$codeCmd = Get-Command code -ErrorAction SilentlyContinue
if (-not $codeCmd) {
    Write-Warning "VSCode CLI 'code' not on PATH."
    Write-Host ""
    Write-Host "Open this folder in VSCode, then run the task manually:" -ForegroundColor Yellow
    Write-Host "  Ctrl+Shift+P  ->  Tasks: Run Task  ->  start-all" -ForegroundColor Yellow
    exit 1
}

Write-Host "[start-all] opening repo in VSCode and running 'start-all' task..." -ForegroundColor Cyan
& code $RepoRoot --reuse-window
Start-Sleep -Milliseconds 800

# Trigger the task via VSCode URI handler. Each sub-task uses panel=dedicated
# so it gets its own tab in the integrated terminal panel.
$uri = "vscode://fabiospampinato.vscode-commands/run?command=workbench.action.tasks.runTask&args=start-all"
# Plain VSCode does not expose runTask via URI without an extension; instead
# we instruct the user. The reliable cross-setup path is the Command Palette.

Write-Host ""
Write-Host "VSCode is open. Now run the task:" -ForegroundColor Green
Write-Host "  Ctrl+Shift+P  ->  Tasks: Run Task  ->  start-all" -ForegroundColor Green
Write-Host ""
Write-Host "Each service will appear as a dedicated tab in the integrated terminal panel." -ForegroundColor Gray
Write-Host ""
Write-Host "Health checks (after ~30s):" -ForegroundColor Yellow
Write-Host "  curl http://127.0.0.1:9001/v1/jobs?limit=1"
Write-Host "  curl http://127.0.0.1:9002/v1/environment"
Write-Host "  curl http://localhost:9005/"
Write-Host "  open  http://localhost:5173"
