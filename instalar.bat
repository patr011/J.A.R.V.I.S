@echo off
chcp 65001 >nul
title J.A.R.V.I.S. - Instalacion
cd /d "%~dp0"

echo.
echo  ================================================================
echo    J.A.R.V.I.S.  -  Instalacion automatica
echo  ================================================================
echo.

REM ---------- 1. Comprobar que Python esta instalado ----------
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] No se encuentra Python.
    echo.
    echo  Descargalo desde https://www.python.org/downloads/
    echo  IMPORTANTE: marca la casilla "Add Python to PATH" al instalarlo.
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version') do echo  [OK] %%v

REM ---------- 2. Crear el entorno virtual ----------
if not exist ".venv" (
    echo.
    echo  Creando el entorno virtual .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo  [ERROR] No se ha podido crear el entorno virtual.
        pause
        exit /b 1
    )
)
call .venv\Scripts\activate.bat

REM ---------- 3. Instalar las librerias ----------
echo.
echo  Actualizando pip ...
python -m pip install --upgrade pip --quiet

echo  Instalando las librerias obligatorias ...
python -m pip install PyQt6 requests psutil --quiet
if errorlevel 1 (
    echo  [ERROR] Fallo instalando las librerias obligatorias.
    pause
    exit /b 1
)
echo  [OK] PyQt6, requests y psutil instalados.

echo.
echo  Instalando las librerias opcionales (voz, volumen, brillo) ...
python -m pip install pyttsx3 --quiet          && echo  [OK] pyttsx3 ^(voz del asistente^)
python -m pip install SpeechRecognition --quiet && echo  [OK] SpeechRecognition ^(reconocimiento de voz^)
python -m pip install pyaudio --quiet           && echo  [OK] PyAudio ^(microfono^)
python -m pip install pycaw comtypes --quiet    && echo  [OK] pycaw ^(control de volumen^)
python -m pip install screen-brightness-control --quiet && echo  [OK] control de brillo

echo.
echo  Si PyAudio ha fallado, no pasa nada: el asistente funciona por texto.
echo  Para arreglarlo mas tarde:  pip install pipwin ^&^& pipwin install pyaudio
echo.

REM ---------- 4. Diagnostico ----------
echo  ================================================================
echo    Comprobando el sistema...
echo  ================================================================
python main.py --check

echo.
echo  ================================================================
echo    Instalacion terminada.
echo.
echo    Siguiente paso: instala Ollama desde https://ollama.com/download
echo    y descarga el modelo que te ha recomendado el diagnostico.
echo.
echo    Para arrancar el asistente, haz doble clic en  ejecutar.bat
echo  ================================================================
echo.
pause
