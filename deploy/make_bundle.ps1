# Creates TgBotReklama-vps.tar.gz for upload to a VPS.
# Run: powershell -ExecutionPolicy Bypass -File deploy\make_bundle.ps1

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$output = Join-Path $root "TgBotReklama-vps.tar.gz"

if (Test-Path $output) {
    Remove-Item -Force $output
}

Push-Location $root
try {
    tar -czf $output `
        --exclude=".venv" `
        --exclude="data" `
        --exclude=".env" `
        --exclude="__pycache__" `
        --exclude=".pytest_cache" `
        --exclude="*.pyc" `
        --exclude="TgBotReklama-vps.tar.gz" `
        .
}
finally {
    Pop-Location
}

Write-Host "Done: $output"
Write-Host "Upload: scp '$output' root@IP:/tmp/"
