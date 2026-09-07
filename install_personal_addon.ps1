$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Source = Join-Path $ProjectRoot "anki_addon\anki_voice_field"
$DestinationRoot = Join-Path $env:APPDATA "Anki2\addons21"
$Destination = Join-Path $DestinationRoot "anki_voice_field"
$HelperDestination = Join-Path $Destination "helper"
$ExistingHelperVenv = Join-Path $HelperDestination ".venv"
$PreservedHelperVenv = $null
$PreservedFiles = @{}

if (-not (Test-Path $Source)) {
    throw "Add-on source folder not found: $Source"
}

New-Item -ItemType Directory -Force -Path $DestinationRoot | Out-Null

if (Test-Path $ExistingHelperVenv) {
    $PreservedHelperVenv = Join-Path $env:TEMP ("anki_voice_field_venv_" + [guid]::NewGuid())
    Move-Item -LiteralPath $ExistingHelperVenv -Destination $PreservedHelperVenv
}

foreach ($RelativePath in @("config.json", "helper\voice_notes_log.txt", "helper\anki_voice_field.log")) {
    $ExistingPath = Join-Path $Destination $RelativePath
    if (Test-Path $ExistingPath) {
        $PreservedPath = Join-Path $env:TEMP ("anki_voice_field_" + [guid]::NewGuid())
        Copy-Item -Force -LiteralPath $ExistingPath -Destination $PreservedPath
        $PreservedFiles[$RelativePath] = $PreservedPath
    }
}

if (Test-Path $Destination) {
    Remove-Item -Recurse -Force -LiteralPath $Destination
}

Copy-Item -Recurse -Force -LiteralPath $Source -Destination $Destination

New-Item -ItemType Directory -Force -Path $HelperDestination | Out-Null

if ($PreservedHelperVenv -and (Test-Path $PreservedHelperVenv)) {
    Move-Item -LiteralPath $PreservedHelperVenv -Destination $ExistingHelperVenv
}

$HelperFiles = @(
    "anki_client.py",
    "config.py",
    "control_server.py",
    "headless.pyw",
    "legacy_client.pyw",
    "launcher.pyw",
    "recorder.py",
    "requirements.txt",
    "session_log.py",
    "setup_helper_env.ps1",
    "single_instance.py",
    "transcriber.py",
    "voice_service.py"
)

foreach ($HelperFile in $HelperFiles) {
    Copy-Item -Force -LiteralPath (Join-Path $ProjectRoot $HelperFile) -Destination $HelperDestination
}

foreach ($RelativePath in $PreservedFiles.Keys) {
    $PreservedPath = $PreservedFiles[$RelativePath]
    $RestorePath = Join-Path $Destination $RelativePath
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $RestorePath) | Out-Null

    if ($RelativePath -eq "config.json") {
        $DefaultConfig = Get-Content -Raw -LiteralPath $RestorePath | ConvertFrom-Json
        $OldConfig = Get-Content -Raw -LiteralPath $PreservedPath | ConvertFrom-Json
        $DeprecatedConfigProperties = @("show_advanced_menu_items")
        foreach ($Property in $OldConfig.PSObject.Properties) {
            if ($Property.Name -in $DeprecatedConfigProperties) {
                continue
            }
            $DefaultConfig | Add-Member -NotePropertyName $Property.Name -NotePropertyValue $Property.Value -Force
        }
        $DefaultConfig | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 -LiteralPath $RestorePath
    }
    else {
        Copy-Item -Force -LiteralPath $PreservedPath -Destination $RestorePath
    }

    Remove-Item -Force -LiteralPath $PreservedPath
}

Write-Host "Installed personal add-on to:"
Write-Host $Destination
Write-Host ""
Write-Host "Restart Anki, then use the reviewer strip or F8."
Write-Host "Settings: Tools > Add-ons > Anki Voice Field > Config."
