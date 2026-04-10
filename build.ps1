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

# ── Build exe ─────────────────────────────────────────────────────
Write-Host "`n=== Building exe ===" -ForegroundColor Cyan
pyinstaller --onefile --windowed --name AgentHelper --hidden-import keyboard --icon images\icon.ico --add-data "images\icon.ico;images" main.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "BUILD FAILED." -ForegroundColor Red
    exit 1
}

# ── Copy data folder ──────────────────────────────────────────────
Write-Host "`n=== Copying data folder ===" -ForegroundColor Cyan
Copy-Item -Path "data" -Destination "dist\data" -Recurse -Force

# ── Create zip ────────────────────────────────────────────────────
Write-Host "`n=== Creating zip ===" -ForegroundColor Cyan
$zip = "$PSScriptRoot\dist\AgentHelper.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path "dist\AgentHelper.exe", "dist\data" -DestinationPath $zip
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
    $release = Invoke-RestMethod `
        -Uri "https://api.github.com/repos/Mbuvi2003/Agent-helper/releases" `
        -Method Post -Headers $headers -Body $releaseBody -ContentType "application/json"

    Invoke-RestMethod `
        -Uri "https://uploads.github.com/repos/Mbuvi2003/Agent-helper/releases/$($release.id)/assets?name=AgentHelper.exe" `
        -Method Post `
        -Headers @{ Authorization = "token $token"; "Content-Type" = "application/octet-stream" } `
        -InFile "dist\AgentHelper.exe" | Out-Null

    Write-Host "GitHub release v$version published." -ForegroundColor Green
} catch {
    Write-Host "GitHub release failed: $_" -ForegroundColor Red
    Write-Host "The zip was still built — you can release manually on github.com" -ForegroundColor Yellow
}

Write-Host "`n=== All done! ===" -ForegroundColor Green
Write-Host "Google Drive zip : $zip" -ForegroundColor Yellow
Write-Host "GitHub release   : https://github.com/Mbuvi2003/Agent-helper/releases/tag/v$version" -ForegroundColor Yellow
