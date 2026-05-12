Set-Location $PSScriptRoot

Write-Host "Anki Voice Field - REAL RUN" -ForegroundColor Cyan
Write-Host "This will append to the current reviewed card's Lecture Notes field." -ForegroundColor Yellow
Write-Host "Press F8 to start recording, then F8 again to stop." -ForegroundColor Yellow
Write-Host ""

& .\.venv\Scripts\python.exe main.py

Write-Host ""
Read-Host "Press Enter to close this window"
