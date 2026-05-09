$token = "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"
$version = "1.7.2"

Write-Host "Building EXE (onedir)..."
pyinstaller -y --onedir --windowed --name AgentHelper --hidden-import keyboard --icon images\icon.ico --add-data "images\icon.ico;images" main.py

Write-Host "Copying data & images..."
Copy-Item -Path "data" -Destination "dist\AgentHelper\data" -Recurse -Force
Copy-Item -Path "images" -Destination "dist\AgentHelper\images" -Recurse -Force

# Remove GitHub token from the distributed settings.json to be safe!
$distSettings = Get-Content "dist\AgentHelper\data\settings.json" -Raw | ConvertFrom-Json
$distSettings.PSObject.Properties.Remove("github_token")
$distSettings | ConvertTo-Json -Depth 5 | Set-Content "dist\AgentHelper\data\settings.json" -Encoding UTF8

Write-Host "Zipping..."
$zip = "$PSScriptRoot\dist\AgentHelper-v$version.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path "dist\AgentHelper\*" -DestinationPath $zip

Write-Host "Cloning Agent-Helper-Distribution..."
if (Test-Path "dist_repo") { Remove-Item "dist_repo" -Recurse -Force }
git clone "https://${token}@github.com/Mbuvi2003/Agent-Helper-Distribution.git" dist_repo

Write-Host "Committing to Distribution repo..."
Copy-Item $zip "dist_repo\"
# Also copy the raw exe just in case they want it in the repo
Copy-Item "dist\AgentHelper\AgentHelper.exe" "dist_repo\"

Set-Location dist_repo
git add .
git commit -m "Release v$version"
git push origin main
Set-Location ..

Write-Host "Creating GitHub Release on Agent-Helper-Distribution..."
$headers = @{ Authorization = "token $token"; Accept = "application/vnd.github.v3+json" }
$body = @{
    tag_name = "v$version"
    name = "Agent Helper v$version"
    body = "Microsoft Store Distribution Package v$version"
    draft = $false
    prerelease = $false
} | ConvertTo-Json

$release = Invoke-RestMethod -Uri "https://api.github.com/repos/Mbuvi2003/Agent-Helper-Distribution/releases" -Method Post -Headers $headers -Body $body -ContentType "application/json"

Write-Host "Uploading zip asset to release..."
Invoke-RestMethod -Uri "https://uploads.github.com/repos/Mbuvi2003/Agent-Helper-Distribution/releases/$($release.id)/assets?name=AgentHelper-v$version.zip" -Method Post -Headers @{ Authorization = "token $token"; "Content-Type" = "application/zip" } -InFile $zip

Write-Host "Uploading exe asset to release..."
Invoke-RestMethod -Uri "https://uploads.github.com/repos/Mbuvi2003/Agent-Helper-Distribution/releases/$($release.id)/assets?name=AgentHelper.exe" -Method Post -Headers @{ Authorization = "token $token"; "Content-Type" = "application/octet-stream" } -InFile "dist\AgentHelper\AgentHelper.exe"

Write-Host "Done!"
