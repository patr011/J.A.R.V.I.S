@echo off
chcp 65001 >nul
title J.A.R.V.I.S.
cd /d "%~dp0"

REM Usa el entorno virtual si existe; si no, el Python del sistema.
if exist ".venv\Scripts\activate.bat" call .venv\Scripts\activate.bat

REM Arranca Ollama en segundo plano si no esta ya en marcha.
tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /I "ollama.exe" >nul
if errorlevel 1 (
    where ollama >nul 2>&1
    if not errorlevel 1 (
        echo  Iniciando Ollama en segundo plano...
        start "" /min ollama serve
        timeout /t 3 /nobreak >nul
    )
)

REM pythonw.exe arranca la ventana sin dejar una consola negra detras.
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" main.py
) else (
    start "" pythonw main.py
)

exit
