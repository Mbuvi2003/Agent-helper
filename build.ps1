# Agent Helper - Build, Package & Release Script
# Run this whenever you want to deploy a new version.
# Steps: build exe → zip → git push → GitHub release (auto-update)

Set-Location $PSScriptRoot

# ── Read version from settings.json ──────────────────────────────
$settings = Get-Content "data\settings.json" -Raw | ConvertFrom-Json
$version  = $settings.version
$token    = $settings.github_token
Write-Host "`nBuilding version: v$version" -ForegroundColor White

# ── Prompt for release notes ──────────────────────────────────────
$notes = Read-Host "`nRelease notes (what changed?)"
if (-not $notes) { $notes = "Agent Helper v$version" }

# ── Stop running app ──────────────────────────────────────────────
Write-Host "`n=== Stopping any running AgentHelper ===" -ForegroundColor Cyan
Stop-Process -Name AgentHelper -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

# ── Build exe (--onedir: no runtime DLL extraction → no Defender issues) ──
Write-Host "`n=== Building exe (onedir mode) ===" -ForegroundColor Cyan
pyinstaller --onedir --windowed --name AgentHelper --hidden-import keyboard --icon images\icon.ico --add-data "images\icon.ico;images" main.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "BUILD FAILED." -ForegroundColor Red
    exit 1
}

# dist\AgentHelper\ now contains AgentHelper.exe + all DLLs

# ── Copy data & images into the onedir output ─────────────────────
Write-Host "`n=== Copying data & images into dist\AgentHelper ===" -ForegroundColor Cyan
Copy-Item -Path "data"   -Destination "dist\AgentHelper\data"   -Recurse -Force
Copy-Item -Path "images" -Destination "dist\AgentHelper\images" -Recurse -Force

# Ensure github_token is present in the dist copy
$distSettings = Get-Content "dist\AgentHelper\data\settings.json" -Raw | ConvertFrom-Json
$distSettings | Add-Member -NotePropertyName "github_token" -NotePropertyValue $token -Force
$distSettings | ConvertTo-Json -Depth 5 | Set-Content "dist\AgentHelper\data\settings.json" -Encoding UTF8

# ── Create zip of the entire folder ───────────────────────────────
Write-Host "`n=== Creating zip ===" -ForegroundColor Cyan
$zip = "$PSScriptRoot\dist\AgentHelper.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path "dist\AgentHelper\*" -DestinationPath $zip
Write-Host "Zip ready: $zip" -ForegroundColor Yellow

# ── Git commit & push ─────────────────────────────────────────────
Write-Host "`n=== Pushing code to GitHub ===" -ForegroundColor Cyan
git add -A
git commit -m "v$version - $notes"
git push origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "Git push failed. Check your connection." -ForegroundColor Red
    exit 1
}

# ── Create GitHub release & upload exe ───────────────────────────
Write-Host "`n=== Creating GitHub release v$version ===" -ForegroundColor Cyan
$headers = @{
    Authorization = "token $token"
    Accept        = "application/vnd.github+json"
}
$releaseBody = @{
    tag_name   = "v$version"
    name       = "v$version"
    body       = $notes
    draft      = $false
    prerelease = $false
} | ConvertTo-Json

try {
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/Mbuvi2003/Agent-helper/releases" -Method Post -Headers $headers -Body $releaseBody -ContentType "application/json"

    Invoke-RestMethod -Uri "https://uploads.github.com/repos/Mbuvi2003/Agent-helper/releases/$($release.id)/assets?name=AgentHelper.zip" -Method Post -Headers @{ Authorization = "token $token"; "Content-Type" = "application/zip" } -InFile "dist\AgentHelper.zip" | Out-Null

    Write-Host "GitHub release v$version published." -ForegroundColor Green
} catch {
    Write-Host "GitHub release failed: $_"
    Write-Host "The zip was still built - you can release manually on github.com"
}

## Removed problematic Write-Host lines at end of script (caused unterminated string error)
