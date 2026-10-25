# Phase 1 verification. Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
$root = Split-Path -Parent $PSScriptRoot
$py   = Join-Path $root 'backend\.venv\Scripts\python.exe'
$results = [ordered]@{}
$procs = @()

function Record($name, $ok) { $script:results[$name] = if ($ok) { 'PASS' } else { 'FAIL' } }
function Wait-Url($url, $seconds) {
  $end = (Get-Date).AddSeconds($seconds)
  while ((Get-Date) -lt $end) {
    try { return Invoke-RestMethod -Uri $url -TimeoutSec 2 } catch { Start-Sleep -Milliseconds 500 }
  }
  return $null
}

if (-not (Test-Path $py)) { Write-Error 'Backend venv missing. Run backend setup first.'; exit 1 }
if (-not (Test-Path (Join-Path $root 'frontend\node_modules'))) { Write-Error 'Run npm install in frontend first.'; exit 1 }

Write-Host "`n== Backend tests (pytest) =="
Push-Location (Join-Path $root 'backend'); & $py -m pytest -q; Record 'backend pytest' ($LASTEXITCODE -eq 0); Pop-Location

Write-Host "`n== Frontend type check =="
Push-Location (Join-Path $root 'frontend'); npm run typecheck; Record 'frontend typecheck (incl. unused imports)' ($LASTEXITCODE -eq 0)

Write-Host "`n== Frontend production build =="
npm run build; Record 'frontend build' ($LASTEXITCODE -eq 0); Pop-Location

try {
  Write-Host "`n== Start backend =="
  $be = Start-Process $py -ArgumentList '-m','uvicorn','app.main:app','--port','8000' -WorkingDirectory (Join-Path $root 'backend') -PassThru -WindowStyle Hidden
  $procs += $be
  $h = Wait-Url 'http://127.0.0.1:8000/api/health' 20
  Record 'backend starts + /api/health direct' ($h -and $h.status -eq 'ok')
  if ($h) { $h | ConvertTo-Json }

  $m = Wait-Url 'http://127.0.0.1:8000/api/model/status' 5
  Record '/api/model/status responds' ($null -ne $m -and $null -ne $m.state)
  if ($m) { Write-Host ("Model state: " + $m.state + " - " + $m.reason) }

  Write-Host "`n== Start frontend dev server =="
  $fe = Start-Process cmd.exe -ArgumentList '/c','npm run dev' -WorkingDirectory (Join-Path $root 'frontend') -PassThru -WindowStyle Hidden
  $procs += $fe
  $page = Wait-Url 'http://localhost:5173/' 40
  Record 'frontend dev server serves page' ($null -ne $page)
  $p = Wait-Url 'http://localhost:5173/api/health' 10
  Record 'frontend -> backend via Vite proxy' ($p -and $p.status -eq 'ok')
}
finally {
  foreach ($pr in $procs) { if ($pr -and -not $pr.HasExited) { taskkill /PID $pr.Id /T /F | Out-Null } }
}

Write-Host "`n===== RESULTS ====="
$results.GetEnumerator() | ForEach-Object { '{0,-45} {1}' -f $_.Key, $_.Value }
Write-Host "`nBrowser tests (microphone, recording, playback, quality checks) are NOT covered here. Use the checklist in README.md."
