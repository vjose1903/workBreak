"""Consulta Releases generadas desde los tags de GitHub, sin bloquear AppKit."""
import json
import platform
import queue
import threading
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app_version import GITHUB_REPO, VERSION, version_numerica


def interpretar_release(release, version_actual=VERSION, arquitectura=None):
    if not isinstance(release, dict):
        raise ValueError('GitHub devolvió una respuesta inválida')
    if release.get('draft') or release.get('prerelease'):
        return None
    version = release.get('tag_name', '')
    nueva = version_numerica(version)
    if nueva <= version_numerica(version_actual):
        return None
    arquitectura = arquitectura or platform.machine()
    if arquitectura not in ('arm64', 'x86_64'):
        raise ValueError('Arquitectura de Mac no compatible')
    numero = version.removeprefix('v')
    nombre = f'WorkBreak-{numero}-macos-{arquitectura}.dmg'
    esperado = f'https://github.com/{GITHUB_REPO}/releases/download/{version}/{nombre}'
    for asset in release.get('assets', []):
        if asset.get('name') == nombre and asset.get('browser_download_url') == esperado:
            return {'version': numero, 'url': esperado}
    raise ValueError('La nueva versión todavía no tiene un instalador para este Mac. Inténtalo más tarde.')


def consultar_github():
    import certifi
    peticion = Request(f'https://api.github.com/repos/{GITHUB_REPO}/releases/latest', headers={
        'Accept': 'application/vnd.github+json', 'User-Agent': f'WorkBreak/{VERSION}',
        'X-GitHub-Api-Version': '2022-11-28',
    })
    try:
        contexto = ssl.create_default_context(cafile=certifi.where())
        with urlopen(peticion, timeout=15, context=contexto) as respuesta:
            contenido = respuesta.read(2_000_001)
        if len(contenido) > 2_000_000:
            raise ValueError('La respuesta de GitHub supera el tamaño permitido')
        return interpretar_release(json.loads(contenido))
    except HTTPError as error:
        if error.code == 404:
            raise ValueError('Todavía no hay una Release pública disponible en GitHub.') from error
        raise ValueError(f'No se pudo consultar GitHub (HTTP {error.code}). Inténtalo más tarde.') from error
    except URLError as error:
        raise ValueError('No se pudo conectar con GitHub. Comprueba tu conexión.') from error


class Actualizador:
    def __init__(self):
        self.consultando = False
        self.resultados = queue.Queue()

    def buscar(self):
        if self.consultando:
            return
        self.consultando = True
        threading.Thread(target=self._consultar, daemon=True, name='actualizaciones').start()

    def _consultar(self):
        try:
            self.resultados.put({'actualizacion': consultar_github()})
        except Exception as error:
            self.resultados.put({'error': str(error)})

    def obtener_resultado(self):
        try:
            resultado = self.resultados.get_nowait()
        except queue.Empty:
            return None
        self.consultando = False
        return resultado
