$token = "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"

$headers = @{ Authorization = "token $token"; Accept = "application/vnd.github.v3+json" }
$releases = Invoke-RestMethod -Uri "https://api.github.com/repos/Mbuvi2003/Agent-Helper-Distribution/releases" -Method Get -Headers $headers
$release = $releases[0]

Write-Host "Uploading AgentHelper_Setup.exe to release $($release.id)..."
Invoke-RestMethod -Uri "https://uploads.github.com/repos/Mbuvi2003/Agent-Helper-Distribution/releases/$($release.id)/assets?name=AgentHelper_Setup.exe" -Method Post -Headers @{ Authorization = "token $token"; "Content-Type" = "application/octet-stream" } -InFile "dist\AgentHelper_Setup.exe"

Copy-Item "dist\AgentHelper_Setup.exe" "dist_repo\"
Set-Location dist_repo
git add AgentHelper_Setup.exe
git commit -m "Add MS Store Setup Installer"
git push origin main
