@echo off
chcp 65001 >nul
title J.A.R.V.I.S.
cd /d "%~dp0"

REM Usa el entorno virtual si existe; si no, el Python del sistema.
set "PY=python"
set "PYW=pythonw"
if exist ".venv\Scripts\python.exe" (
    call .venv\Scripts\activate.bat
    set "PY=.venv\Scripts\python.exe"
    set "PYW=.venv\Scripts\pythonw.exe"
)

REM Ollama solo se arranca si de verdad es el cerebro elegido. Con Claude no
REM pinta nada: ocuparia varios GB de memoria y de tarjeta grafica sin que
REM nadie le pregunte nada, y añadiria tres segundos a cada arranque.
set "CEREBRO=claude"
for /f "usebackq tokens=*" %%p in (`%PY% main.py --cerebro 2^>nul`) do set "CEREBRO=%%p"

if /I "%CEREBRO%"=="ollama" (
    tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /I "ollama.exe" >nul
    if errorlevel 1 (
        where ollama >nul 2>&1
        if not errorlevel 1 (
            echo  Iniciando Ollama en segundo plano...
            start "" /min ollama serve
            timeout /t 3 /nobreak >nul
        )
    )
)

REM pythonw.exe arranca la ventana sin dejar una consola negra detras.
start "" "%PYW%" main.py

exit
