$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Source = Join-Path $ProjectRoot "anki_addon\anki_voice_field"
$Dist = Join-Path $ProjectRoot "dist"
$ZipPath = Join-Path $Dist "anki_voice_field.zip"
$AddonPath = Join-Path $Dist "anki_voice_field.ankiaddon"

if (-not (Test-Path $Source)) {
    throw "Add-on source folder not found: $Source"
}

Get-ChildItem -Path $Source -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force

New-Item -ItemType Directory -Force -Path $Dist | Out-Null
Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $ZipPath
Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $AddonPath

Compress-Archive -Path (Join-Path $Source "*") -DestinationPath $ZipPath
Move-Item -LiteralPath $ZipPath -Destination $AddonPath

Write-Host "Packaged add-on:"
Write-Host $AddonPath
