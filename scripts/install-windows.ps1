<#
.SYNOPSIS
    Set up and operate the Synology RAG Retrieval REST API on Windows.

.DESCRIPTION
    Creates a virtual environment, installs locked dependencies, validates
    configuration, and runs / inspects the service. Does not require admin
    rights unless you later register a Windows service or firewall rule.

.PARAMETER Action
    install | validate | run | logs | uninstall

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1 -Action install
#>
param(
    [ValidateSet("install", "validate", "run", "logs", "uninstall")]
    [string]$Action = "install"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$LogDir = Join-Path $Root "logs"

function Invoke-Install {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv $Venv
    Write-Host "Installing dependencies..." -ForegroundColor Cyan
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -e "$Root[dev]"

    $envFile = Join-Path $Root ".env"
    if (-not (Test-Path $envFile)) {
        Copy-Item (Join-Path $Root ".env.example") $envFile
        Write-Host "Created .env from .env.example - edit it before running." -ForegroundColor Yellow
    }
    $mapFile = Join-Path $Root "config\schema_mapping.yaml"
    if (-not (Test-Path $mapFile)) {
        Copy-Item (Join-Path $Root "config\schema_mapping.example.yaml") $mapFile
        Write-Host "Created config\schema_mapping.yaml - edit it from your discovery report." -ForegroundColor Yellow
    }
    Write-Host "Install complete." -ForegroundColor Green
}

function Invoke-Validate {
    Write-Host "Validating configuration (fails closed on problems)..." -ForegroundColor Cyan
    & $Python -c "from synology_rag.container import build_container; build_container(); print('Configuration OK')"
    Write-Host "Verifying read-only enforcement..." -ForegroundColor Cyan
    & $Python (Join-Path $Root "scripts\verify_read_only.py")
}

function Invoke-Run {
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
    Write-Host "Starting REST API on http://127.0.0.1:8765 (Ctrl+C to stop)..." -ForegroundColor Cyan
    & $Python -m synology_rag.api
}

function Invoke-Logs {
    $log = Join-Path $LogDir "api.log"
    if (Test-Path $log) { Get-Content $log -Tail 100 -Wait }
    else { Write-Host "No log file at $log. Run with stderr redirected to it." -ForegroundColor Yellow }
}

function Invoke-Uninstall {
    if (Test-Path $Venv) {
        Remove-Item -Recurse -Force $Venv
        Write-Host "Removed virtual environment. .env and config were left in place." -ForegroundColor Green
    }
}

switch ($Action) {
    "install"   { Invoke-Install }
    "validate"  { Invoke-Validate }
    "run"       { Invoke-Run }
    "logs"      { Invoke-Logs }
    "uninstall" { Invoke-Uninstall }
}
