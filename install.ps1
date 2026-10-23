# Versline installer for Windows (PowerShell). Installs the latest GitHub release; no git or Python needed.
# Usage:  irm https://raw.githubusercontent.com/miroverse-solutions/versline/main/install.ps1 | iex
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$repo = "miroverse-solutions/versline"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv (Python tool manager)..."
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Write-Host "Finding the latest Versline release..."
$release = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest" -Headers @{ "User-Agent" = "versline-installer" }
$asset = $release.assets | Where-Object { $_.name -like "*.whl" } | Select-Object -First 1
if (-not $asset) {
    throw "No published release with a .whl file was found at https://github.com/$repo/releases"
}

Write-Host "Installing Versline $($release.tag_name)..."
uv tool install --force --python 3.12 $asset.browser_download_url
if ($LASTEXITCODE -ne 0) { throw "Installation failed (uv exit code $LASTEXITCODE)." }
uv tool update-shell | Out-Null

Write-Host ""
Write-Host "Done. Close this window, open a NEW terminal, then run:  versline init"
