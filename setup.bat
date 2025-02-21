@echo off
echo Detectando sistema operativo...
ver | findstr /i "Windows" > nul
if %ERRORLEVEL% == 0 (
    echo Sistema Windows detectado
    echo Instalando dependencias para Windows...
    pip install -r requirements-windows.txt
) else (
    echo Este script es solo para Windows
    exit /b 1
)

echo.&echo.&echo ----- Instalacion completada. Puedes ejecutar el bot con 'python src/bot.py' -----&echo.&echo.

pause