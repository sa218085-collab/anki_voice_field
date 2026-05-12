$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Source = Join-Path $ProjectRoot "anki_addon\anki_voice_field"
$DestinationRoot = Join-Path $env:APPDATA "Anki2\addons21"
$Destination = Join-Path $DestinationRoot "anki_voice_field"

if (-not (Test-Path $Source)) {
    throw "Add-on source folder not found: $Source"
}

New-Item -ItemType Directory -Force -Path $DestinationRoot | Out-Null

if (Test-Path $Destination) {
    Remove-Item -Recurse -Force -LiteralPath $Destination
}

Copy-Item -Recurse -Force -LiteralPath $Source -Destination $Destination

Write-Host "Installed personal add-on to:"
Write-Host $Destination
Write-Host ""
Write-Host "Restart Anki, then use Tools > Anki Voice Field: Toggle Recording."
