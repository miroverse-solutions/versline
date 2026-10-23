# Versline installer for Windows (PowerShell).
# Usage:  irm https://raw.githubusercontent.com/miroverse-solutions/versline/main/install.ps1 | iex
$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv (Python tool manager)..."
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Write-Host "Installing Versline..."
uv tool install --force --python 3.12 "git+https://github.com/miroverse-solutions/versline"
uv tool update-shell | Out-Null

Write-Host ""
Write-Host "Done. Close this window, open a NEW terminal, then run:  versline init"
