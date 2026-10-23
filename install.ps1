# Versline installer for Windows (PowerShell). Installs the latest GitHub release; no git or Python needed.
# Usage:  irm https://raw.githubusercontent.com/miroverse-solutions/versline/main/install.ps1 | iex
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$repo = "miroverse-solutions/versline"

Write-Host "Finding the latest Versline release..."
$release = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest" -Headers @{ "User-Agent" = "versline-installer" }
$zip = $release.assets | Where-Object { $_.name -eq "versline-windows-x64.zip" } | Select-Object -First 1
if (-not $zip) {
    throw "No versline-windows-x64.zip was found in the latest release at https://github.com/$repo/releases"
}

# Self-contained build: no Python, uv or PyPI access needed.
$dir = Join-Path $env:LOCALAPPDATA "Versline"
$tmp = Join-Path $env:TEMP "versline-windows-x64.zip"
Write-Host "Downloading Versline $($release.tag_name)..."
# curl.exe ships with Windows 10+ and shows a real progress bar; Invoke-WebRequest's own is slow and unreadable.
$curl = Get-Command curl.exe -ErrorAction SilentlyContinue
if ($curl) {
    & $curl.Source -L --fail --progress-bar -o $tmp $zip.browser_download_url
    if ($LASTEXITCODE -ne 0) { throw "Download failed (curl exit code $LASTEXITCODE)." }
} else {
    $ProgressPreference = "SilentlyContinue"
    Invoke-WebRequest $zip.browser_download_url -OutFile $tmp -UseBasicParsing
}
if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
Expand-Archive $tmp -DestinationPath $dir -Force
Remove-Item $tmp -Force

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (($userPath -split ";") -notcontains $dir) {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$dir".TrimStart(";"), "User")
}

Write-Host ""
Write-Host "Done. Close this window, open a NEW terminal, then run:  versline init"
