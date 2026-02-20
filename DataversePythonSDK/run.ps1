param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
    Write-Host "No .env file found in repo root. Continuing with existing process/user environment variables." -ForegroundColor Yellow
    if ((-not $env:DATAVERSE_URL) -and (Test-Path ".env.example")) {
        Write-Host "Tip: copy .env.example to .env and set DATAVERSE_URL + auth values." -ForegroundColor Yellow
    }
}

if (-not $SkipInstall) {
    python -m pip install -e .
}

if (-not $env:DATAVERSE_URL -and -not (Test-Path ".env")) {
    Write-Host "DATAVERSE_URL is not set and no .env file was found. Server may fail when first Dataverse tool is called." -ForegroundColor Yellow
}

python -m dataverse_mcp_server.server
