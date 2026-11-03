"""Editores compatibles con el espacio temporal y la navegación por línea."""
from pathlib import Path
import shutil
import sys


EDITORES = {
    'vsCode': {'nombre': 'Visual Studio Code', 'mac': 'Visual Studio Code',
               'bundle': 'com.microsoft.VSCode', 'binario': 'code', 'proceso': 'Code.exe'},
    'cursor': {'nombre': 'Cursor', 'mac': 'Cursor',
               'bundle': 'com.todesktop.230313mzl4w4u92', 'binario': 'cursor', 'proceso': 'Cursor.exe'},
    'windsurf': {'nombre': 'Windsurf', 'mac': 'Windsurf',
                 'bundle': 'com.exafunction.windsurf', 'binario': 'windsurf', 'proceso': 'Windsurf.exe'},
    'vsCodeInsiders': {'nombre': 'Visual Studio Code Insiders', 'mac': 'Visual Studio Code - Insiders',
                       'bundle': 'com.microsoft.VSCodeInsiders', 'binario': 'code-insiders', 'proceso': 'Code - Insiders.exe'},
}


def binario_editor(editor):
    info = EDITORES[editor]
    if sys.platform == 'darwin':
        from AppKit import NSWorkspace
        aplicacion = NSWorkspace.sharedWorkspace().URLForApplicationWithBundleIdentifier_(info['bundle'])
        if aplicacion is None:
            return None
        ruta = Path(str(aplicacion.path())) / 'Contents/Resources/app/bin' / info['binario']
        return str(ruta) if ruta.is_file() else None
    return shutil.which(info['binario'])


def editores_instalados():
    # El orden prioriza VS Code cuando no hay una elección guardada disponible.
    return {clave: info['nombre'] for clave, info in EDITORES.items() if binario_editor(clave)}
