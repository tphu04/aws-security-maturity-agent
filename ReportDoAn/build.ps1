#!/usr/bin/env pwsh
# Build script for ReportDoAn LaTeX project (MiKTeX + latexmk + biber).
# Usage:
#   .\build.ps1            # full build (pdflatex + biber)
#   .\build.ps1 -Clean     # clean intermediate files
#   .\build.ps1 -Watch     # rebuild on file change

param(
    [switch]$Clean,
    [switch]$Watch,
    [switch]$Open
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$miktex = 'C:\Users\trung\AppData\Local\Programs\MiKTeX\miktex\bin\x64'
if (Test-Path $miktex) { $env:PATH = "$miktex;$env:PATH" }

if ($Clean) {
    Write-Host "[clean] removing build/ ..." -ForegroundColor Yellow
    latexmk -C
    if (Test-Path 'build') { Remove-Item -Recurse -Force 'build' }
    Write-Host "[clean] done." -ForegroundColor Green
    return
}

if ($Watch) {
    Write-Host "[watch] latexmk -pvc main.tex" -ForegroundColor Cyan
    latexmk -pvc main.tex
    return
}

if (-not (Test-Path 'build')) { New-Item -ItemType Directory -Path 'build' | Out-Null }

# Use latexmk: it auto-determines the right number of pdflatex passes and re-runs
# biber when needed. Required for forward references with biblatex+hyperref+TikZ to
# fully stabilize (a fixed 3-4 pass sequence does not always converge).
Write-Host "[build] latexmk -pdf main.tex" -ForegroundColor Cyan
& latexmk -pdf -synctex=1 -interaction=nonstopmode -file-line-error -output-directory=build main.tex | Out-Null

$pdf = Join-Path $PSScriptRoot 'build\main.pdf'
if (-not (Test-Path $pdf)) {
    Write-Error "Build failed: $pdf was not produced. See build/main.log"
    exit 1
}
$size = '{0:N0}' -f (Get-Item $pdf).Length
Write-Host "[build] OK -> $pdf ($size bytes)" -ForegroundColor Green
if ($Open) { Start-Process $pdf }
