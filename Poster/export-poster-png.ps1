param(
    [ValidateSet("a4", "a0-150", "a0-300", "custom")]
    [string]$Preset = "a0-150",
    [string]$OutputPath = "",
    [int]$Width = 0,
    [int]$Height = 0,
    [int]$WaitMs = 8000
)

$ErrorActionPreference = "Stop"

$posterPath = Join-Path $PSScriptRoot "Poster.html"
if (-not (Test-Path -LiteralPath $posterPath)) {
    throw "Poster.html not found next to this script."
}

$browserCandidates = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
)

$browser = $browserCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $browser) {
    throw "Chrome or Edge was not found. Install one of them or update browserCandidates in this script."
}

switch ($Preset) {
    "a4" {
        if ($Width -le 0) { $Width = 2065 }
        if ($Height -le 0) { $Height = 2920 }
        if ([string]::IsNullOrWhiteSpace($OutputPath)) { $OutputPath = "poster-a4.png" }
    }
    "a0-150" {
        # A0 portrait at 150 DPI: 33.11 x 46.81 in.
        if ($Width -le 0) { $Width = 4967 }
        if ($Height -le 0) { $Height = 7022 }
        if ([string]::IsNullOrWhiteSpace($OutputPath)) { $OutputPath = "poster-a0-150dpi.png" }
    }
    "a0-300" {
        # A0 portrait at 300 DPI. Large file, best for final raster export.
        if ($Width -le 0) { $Width = 9933 }
        if ($Height -le 0) { $Height = 14043 }
        if ([string]::IsNullOrWhiteSpace($OutputPath)) { $OutputPath = "poster-a0-300dpi.png" }
        if ($WaitMs -lt 12000) { $WaitMs = 12000 }
    }
    "custom" {
        if ($Width -le 0 -or $Height -le 0) {
            throw "Preset custom requires positive -Width and -Height."
        }
        if ([string]::IsNullOrWhiteSpace($OutputPath)) { $OutputPath = "poster-custom.png" }
    }
}

if (-not [System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath = Join-Path $PSScriptRoot $OutputPath
}

if (Test-Path -LiteralPath $OutputPath) {
    Remove-Item -LiteralPath $OutputPath -Force
}

$posterUri = [System.Uri]::new((Resolve-Path -LiteralPath $posterPath).Path).AbsoluteUri + "?export=png&w=$Width&h=$Height"
$profileDir = Join-Path $PSScriptRoot ".chrome-export-profile"
New-Item -ItemType Directory -Force -Path $profileDir | Out-Null

$args = @(
    "--headless=new",
    "--disable-gpu",
    "--disable-crash-reporter",
    "--disable-crashpad",
    "--hide-scrollbars",
    "--allow-file-access-from-files",
    "--no-first-run",
    "--no-default-browser-check",
    "--user-data-dir=$profileDir",
    "--run-all-compositor-stages-before-draw",
    "--virtual-time-budget=$WaitMs",
    "--window-size=$Width,$Height",
    "--screenshot=$OutputPath",
    $posterUri
)

& $browser @args
$browserExitCode = $LASTEXITCODE

$fileReady = $false
for ($i = 0; $i -lt 30; $i++) {
    if (Test-Path -LiteralPath $OutputPath) {
        $fileReady = $true
        break
    }
    Start-Sleep -Milliseconds 250
}

if (-not $fileReady) {
    throw "Export finished but output PNG was not created."
}

if ($null -ne $browserExitCode -and $browserExitCode -ne 0) {
    Write-Warning "Browser returned exit code $browserExitCode, but the PNG file was created."
}

Remove-Item -LiteralPath $profileDir -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Exported poster PNG: $OutputPath"
