"""Preferencias persistentes y apertura de la aplicación al iniciar sesión."""
import json
import os
from pathlib import Path
import sys
import tempfile

from app_paths import directorio_datos, leer_json, MAX_JSON_BYTES


def cargar_preferencias():
    from menu import _registro_valido
    try:
        datos = leer_json(directorio_datos() / 'preferences.json')
        return datos if _registro_valido(datos) else None
    except (OSError, ValueError, TypeError):
        return None


def guardar_preferencias(config):
    from menu import _registro_valido
    if not _registro_valido(config):
        raise ValueError('La configuración contiene valores inválidos')
    contenido = json.dumps(config, ensure_ascii=False, indent=2)
    if len(contenido.encode('utf-8')) > MAX_JSON_BYTES:
        raise ValueError('La configuración supera 2 MiB')
    destino = directorio_datos() / 'preferences.json'
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destino.parent, delete=False) as archivo:
            temporal = Path(archivo.name)
            archivo.write(contenido)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, destino)
    finally:
        if temporal:
            temporal.unlink(missing_ok=True)


def inicio_disponible():
    return (getattr(sys, 'frozen', False)
            and Path(sys.executable).resolve() == Path('/Applications/WB.app/Contents/MacOS/WB').resolve())


def estado_inicio():
    if not inicio_disponible():
        return False, 'Disponible al abrir la aplicación instalada en Aplicaciones.'
    from ServiceManagement import SMAppService
    estado = SMAppService.mainAppService().status()
    return estado in (1, 2), ('Pendiente de autorización en Ajustes del Sistema → General → Ítems de inicio.'
                         if estado == 2 else 'Abre la W al iniciar sesión. El bot no empieza automáticamente.')


def establecer_inicio(activar):
    if not inicio_disponible():
        raise ValueError('Abre WB desde Aplicaciones para configurar el inicio de sesión.')
    from ServiceManagement import SMAppService
    servicio = SMAppService.mainAppService()
    correcto, error = (servicio.registerAndReturnError_(None) if activar
                       else servicio.unregisterAndReturnError_(None))
    if not correcto:
        raise RuntimeError(str(error.localizedDescription()) if error else 'macOS no pudo cambiar el inicio de sesión')
    return estado_inicio()
