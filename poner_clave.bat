@echo off
chcp 65001 >nul
title J.A.R.V.I.S. - Clave de la API
cd /d "%~dp0"

REM Toda la logica esta en poner_clave.py: asi se puede probar de verdad,
REM cosa que un script de consola de Windows no permite.
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe poner_clave.py
) else (
    python poner_clave.py
)

if errorlevel 1 (
    echo.
    pause
    exit /b 1
)

echo  ----------------------------------------------------------------
echo    Comprobando que la API responde...
echo  ----------------------------------------------------------------
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe main.py --check
) else (
    python main.py --check
)

echo.
echo  ================================================================
echo    Si arriba pone  [OK] La API responde correctamente,
echo    ya puedes arrancar el asistente con  ejecutar.bat
echo  ================================================================
echo.
pause
