@echo off
cd /d "%~dp0"
echo Detectando sistema operativo...
ver | findstr /i "Windows" > nul
if %ERRORLEVEL% == 0 (
    echo Sistema Windows detectado
    echo Instalando dependencias para Windows...
    pip install -r requirements-windows.txt
    if errorlevel 1 exit /b 1
) else (
    echo Este script es solo para Windows
    exit /b 1
)

echo.&echo.&echo ----- Instalacion completada. Puedes ejecutar el bot con 'python src/main.py ...' -----&echo.&echo.

pause
