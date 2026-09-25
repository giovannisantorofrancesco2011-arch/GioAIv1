@echo off
rem Crea il modello "mycode" in Ollama. Aggiungi --subito per provarlo prima dell'addestramento.
cd /d "%~dp0\..\.."
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" finetune\mycode\crea_mycode.py %*
) else (
  python finetune\mycode\crea_mycode.py %*
)
pause
