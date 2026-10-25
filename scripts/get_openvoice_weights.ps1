# Downloads the OpenVoice V2 tone-colour converter from the official Hugging Face repo
# (huggingface.co/myshell-ai/OpenVoiceV2, MIT licence) into models\openvoice_v2\converter.
# The older S3 zip link in OpenVoice's USAGE.md returned 404 (checked by the project owner, Oct 2026).
# Resumable: re-run it if the download is interrupted.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dest = Join-Path $root 'models\openvoice_v2\converter'
$base = 'https://huggingface.co/myshell-ai/OpenVoiceV2/resolve/main/converter'
New-Item -ItemType Directory -Force -Path $dest | Out-Null

$files = @(
  @{ Name = 'config.json';     MinBytes = 500 },
  @{ Name = 'checkpoint.pth';  MinBytes = 100MB }   # the model page lists it as about 131 MB
)
foreach ($f in $files) {
  $out = Join-Path $dest $f.Name
  if ((Test-Path $out) -and ((Get-Item $out).Length -ge $f.MinBytes)) { Write-Host "$($f.Name) already present, skipping."; continue }
  Write-Host "Downloading $($f.Name) ... (checkpoint.pth is about 131 MB; this can take several minutes)"
  & curl.exe -L --fail --retry 3 -C - -o $out "$base/$($f.Name)"
  if ($LASTEXITCODE -ne 0) { throw "Download of $($f.Name) failed (curl exit code $LASTEXITCODE). Copy this message and the exit code to me." }
}

foreach ($f in $files) {
  $out = Join-Path $dest $f.Name
  $len = (Get-Item $out).Length
  if ($len -lt $f.MinBytes) { throw "$($f.Name) is only $len bytes; the download is incomplete or wrong. Delete it and re-run." }
  Write-Host ("{0,-16} {1,12:N0} bytes  SHA256 {2}" -f $f.Name, $len, (Get-FileHash $out -Algorithm SHA256).Hash)
}
Write-Host "`nOK: weights are in models\openvoice_v2\converter. If the backend is already running, the page picks them up within a few seconds."
