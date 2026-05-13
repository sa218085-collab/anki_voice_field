$ErrorActionPreference = "Stop"

$HelperRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $HelperRoot

Write-Host "Setting up Anki Voice Field helper..."
Write-Host "Helper folder: $HelperRoot"
Write-Host ""

if (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 -m venv .venv
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    python -m venv .venv
}
else {
    Write-Host "Could not find Python on this computer."
    Write-Host "Install Python 3.12+ from https://www.python.org/downloads/"
    Write-Host "Then run this setup again."
    Read-Host "Press Enter to close"
    exit 1
}

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host ""
Write-Host "Setup complete."
Write-Host "Restart Anki, then use Tools > Anki Voice Field: Record / Stop."
Read-Host "Press Enter to close"
