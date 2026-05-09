$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

# ── Read version from settings.json ──────────────────────────────
$settings = Get-Content "data\settings.json" -Raw | ConvertFrom-Json
$version  = $settings.version

# AppxManifest version must be x.x.x.x
$versionParts = $version.Split('.')
while ($versionParts.Length -lt 4) { $versionParts += '0' }
$msixVersion = $versionParts -join '.'

Write-Host "`n=== Building Agent Helper v$version for MSIX ===" -ForegroundColor White

# ── Build exe (--onedir mode) ──────────────────────────────────────
Write-Host "`n=== Building exe (onedir mode) ===" -ForegroundColor Cyan
pyinstaller -y --onedir --windowed --name AgentHelper --hidden-import keyboard --icon images\icon.ico --add-data "images\icon.ico;images" main.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "BUILD FAILED." -ForegroundColor Red
    exit 1
}

# ── Prepare MSIX Layout Directory ──────────────────────────────────
$msixDir = "dist\msix_layout"
if (Test-Path $msixDir) { Remove-Item $msixDir -Recurse -Force }
New-Item -ItemType Directory -Path $msixDir | Out-Null

# Copy the built exe and dependencies
Write-Host "`n=== Copying files to MSIX layout ===" -ForegroundColor Cyan
Copy-Item -Path "dist\AgentHelper\*" -Destination $msixDir -Recurse

# Copy data & images
Copy-Item -Path "data"   -Destination "$msixDir\data"   -Recurse -Force
Copy-Item -Path "images" -Destination "$msixDir\images" -Recurse -Force

# Generate MSIX assets using python
Write-Host "`n=== Generating MSIX Assets ===" -ForegroundColor Cyan
python generate_msix_assets.py
# The python script outputs to msix_layout/Assets in the current dir, let's move it to dist/msix_layout/Assets
if (Test-Path "msix_layout\Assets") {
    Move-Item -Path "msix_layout\Assets" -Destination "$msixDir\Assets" -Force
    Remove-Item "msix_layout" -Force
}

# ── Generate AppxManifest.xml ──────────────────────────────────────
Write-Host "`n=== Generating AppxManifest.xml ===" -ForegroundColor Cyan
$manifestContent = @"
<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities">

  <!-- NOTE: Update Name and Publisher based on your Partner Center identity -->
  <Identity
    Name="YouGeni.AgentHelper"
    ProcessorArchitecture="x64"
    Publisher="CN=B451734E-9670-417F-808F-F56C3D51735A"
    Version="$msixVersion" />

  <Properties>
    <DisplayName>Agent Helper</DisplayName>
    <PublisherDisplayName>YouGeni</PublisherDisplayName>
    <Logo>Assets\StoreLogo.png</Logo>
    <Description>Agent Helper application.</Description>
  </Properties>

  <Resources>
    <Resource Language="en-us" />
  </Resources>

  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.19041.0" />
  </Dependencies>

  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>

  <Applications>
    <Application
      Id="AgentHelper"
      Executable="AgentHelper.exe"
      EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements
        DisplayName="Agent Helper"
        Description="Agent Helper Utility"
        BackgroundColor="#00A650"
        Square150x150Logo="Assets\Square150x150Logo.png"
        Square44x44Logo="Assets\Square44x44Logo.png">
      </uap:VisualElements>
    </Application>
  </Applications>
</Package>
"@

Set-Content -Path "$msixDir\AppxManifest.xml" -Value $manifestContent -Encoding UTF8

# ── Build the MSIX using makeappx.exe ──────────────────────────────
Write-Host "`n=== Packing MSIX ===" -ForegroundColor Cyan
$makeappx = "C:\Program Files (x86)\Windows Kits\10\bin\10.0.28000.0\x64\makeappx.exe"
if (-not (Test-Path $makeappx)) {
    # Fallback to finding any makeappx.exe in x64
    $makeappx = (Get-ChildItem -Path "C:\Program Files (x86)\Windows Kits\10\bin" -Filter "makeappx.exe" -Recurse | Where-Object { $_.FullName -like "*\x64\*" } | Select-Object -First 1).FullName
}

if (-not (Test-Path $makeappx)) {
    Write-Host "makeappx.exe not found! Please ensure Windows SDK is installed." -ForegroundColor Red
    exit 1
}

$msixOut = "dist\AgentHelper_$version.msix"
if (Test-Path $msixOut) { Remove-Item $msixOut -Force }

& $makeappx pack /d $msixDir /p $msixOut
if ($LASTEXITCODE -ne 0) {
    Write-Host "makeappx pack FAILED." -ForegroundColor Red
    exit 1
}

Write-Host "`n=== MSIX Packaging Complete ===" -ForegroundColor Green
Write-Host "Success: $msixOut" -ForegroundColor Yellow
Write-Host "You can now upload this file to the Microsoft Store Partner Center."
