@echo off
rem MyDevAgent - avvio con un comando (Windows), senza attivare l'ambiente virtuale.
rem Uso, dalla cartella del tuo progetto:   C:\percorso\di\mydevagent\run.bat   [opzioni di mydevagent]
setlocal
set "HERE=%~dp0"
set "BIN=%HERE%.venv\Scripts\mydevagent.exe"
if not exist "%BIN%" (
  echo MyDevAgent non e' ancora installato: avvio l'installazione ^(una volta sola^).
  powershell -ExecutionPolicy Bypass -File "%HERE%scripts\install.ps1"
  if errorlevel 1 exit /b 1
)
"%BIN%" %*
