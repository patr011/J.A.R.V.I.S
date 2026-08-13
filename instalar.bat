@echo off
chcp 65001 >nul
title J.A.R.V.I.S. - Instalacion
cd /d "%~dp0"

echo.
echo  ================================================================
echo    J.A.R.V.I.S.  -  Instalacion automatica
echo  ================================================================
echo.

REM ---------- 1. Elegir la version de Python ----------
REM No vale cualquiera: las librerias de audio y de interfaz tardan meses en
REM publicar version precompilada para cada Python nuevo. Si usas la ultima
REM de todas, pip intenta compilarlas desde cero y falla. Por eso se busca
REM primero una version asentada y solo al final se recurre a la del PATH.
set "PYCMD="
for %%v in (3.12 3.11 3.13 3.10) do (
    if not defined PYCMD (
        py -%%v -c "pass" >nul 2>&1
        if not errorlevel 1 set "PYCMD=py -%%v"
    )
)
if not defined PYCMD (
    python --version >nul 2>&1
    if not errorlevel 1 set "PYCMD=python"
)

if not defined PYCMD (
    echo  [ERROR] No se encuentra Python.
    echo.
    echo  Descargalo desde https://www.python.org/downloads/
    echo  Version recomendada: Python 3.12
    echo  IMPORTANTE: marca la casilla "Add Python to PATH" al instalarlo.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('%PYCMD% --version') do echo  [OK] %%v  ^(%PYCMD%^)

REM Aviso si solo hay una version muy reciente: funcionara, pero es probable
REM que PyAudio no tenga paquete precompilado y el microfono se quede fuera.
%PYCMD% -c "import sys; sys.exit(0 if sys.version_info < (3,13) else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [AVISO] Esta version de Python es muy reciente y puede que PyAudio
    echo          no tenga paquete precompilado para ella. Si el microfono no
    echo          llega a funcionar, instala Python 3.12 y vuelve a ejecutar
    echo          este archivo: el asistente funciona igual por texto.
)

REM ---------- 2. Crear el entorno virtual ----------
REM Si ya existe un .venv creado con OTRA version de Python (por ejemplo,
REM porque instalaste la 3.12 despues de un primer intento fallido), hay que
REM rehacerlo: reutilizarlo dejaria el proyecto en la version antigua y los
REM mismos errores de instalacion de antes.
set "VENVVER="
set "WANTVER="
for /f %%a in ('%PYCMD% -c "import sys;print(sys.version_info.major*100+sys.version_info.minor)"') do set "WANTVER=%%a"
if exist ".venv\Scripts\python.exe" (
    for /f %%a in ('.venv\Scripts\python.exe -c "import sys;print(sys.version_info.major*100+sys.version_info.minor)"') do set "VENVVER=%%a"
)

if defined VENVVER if not "%VENVVER%"=="%WANTVER%" (
    echo.
    echo  El entorno .venv existente usa otra version de Python.
    echo  Se rehace para usar la correcta ...
    rmdir /s /q ".venv"
)

if not exist ".venv" (
    echo.
    echo  Creando el entorno virtual .venv ...
    %PYCMD% -m venv .venv
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
echo  Si PyAudio ha fallado, no pasa nada: el asistente funciona por texto,
echo  solo se queda sin el boton del microfono. La causa casi siempre es que
echo  tu version de Python es demasiado nueva; con Python 3.12 se instala solo.
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
