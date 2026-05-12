Set-Location $PSScriptRoot

Write-Host "Anki Voice Field - DRY RUN" -ForegroundColor Cyan
Write-Host "This records/transcribes but does NOT write to Anki." -ForegroundColor Yellow
Write-Host "Press F8 to start recording, then F8 again to stop." -ForegroundColor Yellow
Write-Host ""

& .\.venv\Scripts\python.exe main.py --dry-run

Write-Host ""
Read-Host "Press Enter to close this window"
