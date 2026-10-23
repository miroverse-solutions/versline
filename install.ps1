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

# Extract entry by entry so we can draw a curl-style bar; Expand-Archive's own progress is unreadable.
Write-Host "Extracting Versline..."
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead($tmp)
try {
    $root = [IO.Path]::GetFullPath($dir).TrimEnd("\") + "\"
    $entries = @($archive.Entries)
    $total = [Math]::Max($entries.Count, 1)
    $width = 60
    $lastFilled = -1
    for ($i = 0; $i -lt $entries.Count; $i++) {
        $entry = $entries[$i]
        $target = [IO.Path]::GetFullPath((Join-Path $dir $entry.FullName))
        if (-not $target.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Unsafe path in archive: $($entry.FullName)"
        }
        if ($entry.FullName.EndsWith("/") -or $entry.FullName.EndsWith("\")) {
            New-Item -ItemType Directory -Path $target -Force | Out-Null
        } else {
            New-Item -ItemType Directory -Path (Split-Path $target) -Force | Out-Null
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $true)
        }
        $percent = ($i + 1) * 100 / $total
        $filled = [int][Math]::Floor($percent * $width / 100)
        if ($filled -ne $lastFilled -or $i -eq $entries.Count - 1) {
            $lastFilled = $filled
            Write-Host ("`r" + ("#" * $filled) + (" " * ($width - $filled)) + (" {0,5:N1}%" -f $percent)) -NoNewline
        }
    }
    Write-Host ""
} finally {
    $archive.Dispose()
}
Remove-Item $tmp -Force

Write-Host "Adding Versline to PATH..."
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (($userPath -split ";") -notcontains $dir) {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$dir".TrimStart(";"), "User")
}

Write-Host ""
Write-Host "Done. Close this window, open a NEW terminal, then run:  versline init"
