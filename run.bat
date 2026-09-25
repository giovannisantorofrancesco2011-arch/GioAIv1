@echo off
rem MyDevAgent - avvio con un comando (Windows), senza attivare l'ambiente virtuale.
rem Uso, dalla cartella del tuo progetto:   C:\percorso\di\mydevagent\run.bat   [opzioni di mydevagent]
setlocal
set "HERE=%~dp0"
set "PY=%HERE%.venv\Scripts\python.exe"
set "PYTHONUTF8=1"
rem python -m e non mydevagent.exe: l'exe smette di funzionare se la cartella viene spostata o rinominata
"%PY%" -c "import mydevagent.cli" >nul 2>&1 || call :ripara || goto errore
"%PY%" -m mydevagent.cli %*
if errorlevel 1 goto errore
exit /b 0

:ripara
if not exist "%PY%" goto installa
echo Sistemo l'installazione di MyDevAgent (cartella spostata o aggiornata)...
"%PY%" -m pip install -q -e "%HERE%.[server,search]" && "%PY%" -c "import mydevagent.cli" >nul 2>&1 && exit /b 0
:installa
echo MyDevAgent non e' ancora installato: avvio l'installazione (una volta sola).
powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%scripts\install.ps1"
exit /b %errorlevel%

:errore
echo.
echo MyDevAgent si e' chiuso con un errore: il messaggio e' qui sopra.
pause
exit /b 1
