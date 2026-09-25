# MyDevAgent Studio: installa quello che serve a Vio per lavorare, solo se manca.
#   1. Python 3.10 o più nuovo        2. Ollama (fa girare i modelli sul tuo PC)
#   3. MyDevAgent (con i suoi modelli, tramite scripts\install.ps1 del progetto)
# Uso: powershell -ExecutionPolicy Bypass -File installa-mydevagent.ps1 [-Cartella <dove installarlo>] [-Pausa]
param(
  [string]$Cartella = (Join-Path $env:LOCALAPPDATA "MyDevAgent"),
  [switch]$Pausa
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest è molto più veloce senza la barra
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Repo = "https://github.com/giovannisantorofrancesco2011-arch/MyDevAgent"

function Passo($testo) { Write-Host "`n==> $testo" -ForegroundColor Magenta }
function Ok($testo) { Write-Host "    $testo" -ForegroundColor Green }
function Aggiungi-Path($dir) {
  if ($dir -and (Test-Path $dir) -and (($env:Path -split ";") -notcontains $dir)) { $env:Path = "$dir;$env:Path" }
}
function Winget([string[]]$argomenti) {
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "Manca winget (App Installer di Microsoft Store): installalo, oppure installa a mano $($argomenti[0]), e riprova."
  }
  winget install -e --accept-package-agreements --accept-source-agreements --id @argomenti
  if ($LASTEXITCODE -ne 0) { throw "winget non è riuscito a installare $($argomenti[0]) (codice $LASTEXITCODE)" }
}

function Python-Buono($exe, [string[]]$prima) {
  try {
    $out = & $exe @prima -c "import sys; print(sys.executable if sys.version_info >= (3, 10) else '')" 2>$null
    if ($LASTEXITCODE -eq 0 -and $out) { return ($out | Select-Object -Last 1).Trim() }
  } catch { }
  return $null
}
function Trova-Python {
  if (Get-Command py -ErrorAction SilentlyContinue) { $p = Python-Buono "py" @("-3"); if ($p) { return $p } }
  if (Get-Command python -ErrorAction SilentlyContinue) { $p = Python-Buono "python" @(); if ($p) { return $p } }
  $cartelle = Get-ChildItem (Join-Path $env:LOCALAPPDATA "Programs\Python") -Directory -ErrorAction SilentlyContinue
  foreach ($dir in ($cartelle | Sort-Object Name -Descending)) {
    $p = Python-Buono (Join-Path $dir.FullName "python.exe") @(); if ($p) { return $p }
  }
  return $null
}
function Trova-Ollama {
  $cmd = Get-Command ollama -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $exe = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
  if (Test-Path $exe) { return $exe }
  return $null
}
function Ollama-Acceso {
  try { Invoke-RestMethod "http://127.0.0.1:11434/api/version" -TimeoutSec 2 | Out-Null; return $true } catch { return $false }
}
function Trova-MyDevAgent {  # gli stessi posti dove guarda l'estensione
  $candidati = @($env:MYDEVAGENT_HOME, $Cartella, (Join-Path $env:USERPROFILE "MyDevAgent"))
  foreach ($base in @("Desktop", "OneDrive\Desktop", "Documents", "OneDrive\Documents", "")) {
    $dir = Join-Path $env:USERPROFILE $base
    if (Test-Path $dir) { $candidati += @(Get-ChildItem $dir -Directory -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }) }
  }
  foreach ($c in $candidati) { if ($c -and (Test-Path (Join-Path $c "mydevagent\__init__.py"))) { return $c } }
  return $null
}

$codice = 0
try {
  Write-Host "MyDevAgent Studio: controllo cosa serve a Vio (serve Internet)." -ForegroundColor Magenta

  Passo "1/3 Python"
  $python = Trova-Python
  if (-not $python) {
    Write-Host "    Installo Python 3.12..."
    Winget @("Python.Python.3.12", "--scope", "user")
    $python = Trova-Python
    if (-not $python) { throw "Python installato, ma non lo trovo: riavvia il PC e riprova." }
  }
  Aggiungi-Path (Split-Path $python)
  Aggiungi-Path (Join-Path (Split-Path $python) "Scripts")
  Ok "Python: $python"

  Passo "2/3 Ollama"
  $ollama = Trova-Ollama
  if (-not $ollama) {
    Write-Host "    Installo Ollama..."
    Winget @("Ollama.Ollama")
    $ollama = Trova-Ollama
    if (-not $ollama) { throw "Ollama installato, ma non lo trovo: riavvia il PC e riprova." }
  }
  Aggiungi-Path (Split-Path $ollama)
  if (-not (Ollama-Acceso)) {
    $app = Join-Path (Split-Path $ollama) "ollama app.exe"
    if (Test-Path $app) { Start-Process $app } else { Start-Process $ollama -ArgumentList "serve" -WindowStyle Hidden }
    for ($i = 0; $i -lt 30 -and -not (Ollama-Acceso); $i++) { Start-Sleep -Seconds 1 }
    if (-not (Ollama-Acceso)) { throw "Ollama non si avvia: aprilo dal menu Start e riprova." }
  }
  Ok "Ollama: $ollama"

  Passo "3/3 MyDevAgent"
  $casa = Trova-MyDevAgent
  if ($casa -and (Test-Path (Join-Path $casa ".venv\Scripts\python.exe"))) {
    Ok "MyDevAgent è già installato in $casa"
  } else {
    if (-not $casa) {
      $casa = $Cartella
      if (Test-Path $casa) { throw "La cartella $casa esiste già ma non contiene MyDevAgent: spostala o scegline un'altra." }
      if (Get-Command git -ErrorAction SilentlyContinue) {
        Write-Host "    Scarico MyDevAgent con git in $casa..."
        git clone --depth 1 "$Repo.git" $casa
        if ($LASTEXITCODE -ne 0) { throw "git clone non è riuscito" }
      } else {
        Write-Host "    Scarico MyDevAgent in $casa..."
        $zip = Join-Path $env:TEMP "mydevagent.zip"
        $tmp = Join-Path $env:TEMP "mydevagent-zip"
        Invoke-WebRequest "$Repo/archive/HEAD.zip" -OutFile $zip -UseBasicParsing
        Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
        Expand-Archive $zip $tmp
        Move-Item (Get-ChildItem $tmp -Directory | Select-Object -First 1).FullName $casa
        Remove-Item $zip, $tmp -Recurse -Force -ErrorAction SilentlyContinue
      }
    }
    Write-Host "    Preparo MyDevAgent e scarico i modelli (la prima volta può volerci un po')..."
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $casa "scripts\install.ps1")
    if ($LASTEXITCODE -ne 0) { throw "l'installazione di MyDevAgent non è riuscita (codice $LASTEXITCODE)" }
    Ok "MyDevAgent installato in $casa"
  }
  Write-Host "`nTutto pronto! Apri MyDevAgent Studio: Vio ti aspetta nella barra a sinistra." -ForegroundColor Green
} catch {
  Write-Host "`nNon ce l'ho fatta: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host "Puoi riprovare da MyDevAgent Studio: Vio ti mostra il pulsante «Installa MyDevAgent»."
  $codice = 1
}
if ($Pausa) { Read-Host "`nPremi Invio per chiudere" | Out-Null }
exit $codice
