# Starts backend and frontend in two new PowerShell windows.
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { Write-Error 'Backend venv missing. Follow README step 3 first.'; exit 1 }
Start-Process powershell -ArgumentList '-NoExit','-Command',"Set-Location '$root\backend'; & '$py' -m uvicorn app.main:app --reload --port 8000"
Start-Process powershell -ArgumentList '-NoExit','-Command',"Set-Location '$root\frontend'; npm run dev"
Write-Host 'Frontend: http://localhost:5173   Backend: http://127.0.0.1:8000/docs'
