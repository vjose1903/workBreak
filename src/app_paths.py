"""Recursos del bundle y datos que deben sobrevivir a una actualización."""
import json
import os
import stat
from pathlib import Path
import sys
import tempfile


MAX_JSON_BYTES = 2 * 1024 * 1024


def leer_json(ruta):
    descriptor = os.open(ruta, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(descriptor, 'rb') as entrada:
        info = os.fstat(entrada.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_JSON_BYTES:
            raise ValueError('La configuración no es un archivo regular de hasta 2 MiB')
        contenido = entrada.read(MAX_JSON_BYTES + 1)
    if len(contenido) > MAX_JSON_BYTES:
        raise ValueError('La configuración supera 2 MiB')
    try:
        return json.loads(contenido)
    except RecursionError as error:
        raise ValueError('La configuración contiene demasiados niveles de anidamiento') from error


def recurso(nombre):
    raiz = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
    return raiz / nombre


def directorio_datos():
    return Path.home() / 'Library' / 'Application Support' / 'WorkBreak'


def ruta_historial():
    if getattr(sys, 'frozen', False):
        return directorio_datos() / 'config_history.json'
    return recurso('config_history.json')


def migrar_historial(origen, destino=None):
    """Copia una configuración local existente; nunca reemplaza la instalada."""
    destino = Path(destino) if destino else directorio_datos() / 'config_history.json'
    origen = Path(origen)
    if destino.exists() or not origen.is_file():
        return False
    registros = leer_json(origen)
    if not isinstance(registros, list):
        raise ValueError('El historial anterior no es una lista válida')
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destino.parent, delete=False) as archivo:
            temporal = Path(archivo.name)
            json.dump(registros, archivo, ensure_ascii=False, indent=2)
            archivo.flush()
            os.fsync(archivo.fileno())
        try:
            os.link(temporal, destino)
        except FileExistsError:
            return False
        return True
    finally:
        if temporal:
            temporal.unlink(missing_ok=True)
