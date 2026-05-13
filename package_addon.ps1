$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Source = Join-Path $ProjectRoot "anki_addon\anki_voice_field"
$BuildRoot = Join-Path $ProjectRoot "build"
$BuildAddon = Join-Path $BuildRoot "anki_voice_field"
$HelperDestination = Join-Path $BuildAddon "helper"
$Dist = Join-Path $ProjectRoot "dist"
$ZipPath = Join-Path $Dist "anki_voice_field.zip"
$AddonPath = Join-Path $Dist "anki_voice_field.ankiaddon"

if (-not (Test-Path $Source)) {
    throw "Add-on source folder not found: $Source"
}

Remove-Item -Recurse -Force -ErrorAction SilentlyContinue -LiteralPath $BuildAddon
New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
Copy-Item -Recurse -Force -LiteralPath $Source -Destination $BuildAddon

New-Item -ItemType Directory -Force -Path $HelperDestination | Out-Null

$HelperFiles = @(
    "anki_client.py",
    "config.py",
    "control_server.py",
    "launcher.pyw",
    "recorder.py",
    "requirements.txt",
    "session_log.py",
    "setup_helper_env.ps1",
    "single_instance.py",
    "transcriber.py"
)

foreach ($HelperFile in $HelperFiles) {
    Copy-Item -Force -LiteralPath (Join-Path $ProjectRoot $HelperFile) -Destination $HelperDestination
}

Get-ChildItem -Path $BuildAddon -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force

New-Item -ItemType Directory -Force -Path $Dist | Out-Null
Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $ZipPath
Remove-Item -Force -ErrorAction SilentlyContinue -LiteralPath $AddonPath

Compress-Archive -Path (Join-Path $BuildAddon "*") -DestinationPath $ZipPath
Move-Item -LiteralPath $ZipPath -Destination $AddonPath

Write-Host "Packaged add-on:"
Write-Host $AddonPath
