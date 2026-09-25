# MyDevAgent — installazione rapida (Windows PowerShell)
# Uso:  powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -HwProfile gpu8
param([ValidateSet("cpu","gpu8","gpu16","gpu24")][string]$HwProfile = "gpu8")
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$main = @{ cpu = "qwen2.5-coder:3b"; gpu8 = "qwen2.5-coder:7b"; gpu16 = "qwen2.5-coder:14b"; gpu24 = "qwen3-coder:30b" }[$HwProfile]

Write-Host "==> 1/4 Ollama"
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
  Write-Host "Installo Ollama con winget..."
  winget install -e --id Ollama.Ollama
  $env:Path += ";$env:LOCALAPPDATA\Programs\Ollama"
}
[Environment]::SetEnvironmentVariable("OLLAMA_FLASH_ATTENTION", "1", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_KV_CACHE_TYPE", "q8_0", "User")

Write-Host "==> 2/4 Modelli ($HwProfile)"
$models = @($main, "qwen2.5-coder:1.5b", "nomic-embed-text")
if ($HwProfile -eq "cpu") { $models += "qwen2.5-coder:7b" }
foreach ($m in $models) { ollama pull $m }
ollama create mydevagent -f "modelfiles/Modelfile.$HwProfile"

Write-Host "==> 3/4 Ambiente Python"
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install -q --upgrade pip
pip install -q -e ".[server,search]"

Write-Host "==> 4/4 Configurazione"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
(Get-Content .env) -replace '^MYDEVAGENT_PROFILE=.*', "MYDEVAGENT_PROFILE=$HwProfile" | Set-Content .env

mydevagent doctor
Write-Host "`nFatto!  .\.venv\Scripts\Activate.ps1 ; mydevagent"
