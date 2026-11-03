#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "Detectando sistema operativo..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Sistema macOS detectado"
    echo "Instalando dependencias para macOS..."
    pip install -r requirements-mac.txt
else
    echo "Este script es solo para macOS"
    exit 1
fi

echo -e "\n\n ----- Instalación completada. Puedes ejecutar el bot con 'python src/main.py ...' ----- \n\n"
