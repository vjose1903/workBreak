"""Consulta Releases generadas desde los tags de GitHub, sin bloquear AppKit."""
import json
import logging
import multiprocessing
import platform
import queue
import threading
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app_version import GITHUB_REPO, VERSION, version_numerica
from app_update_install import (ActualizacionCancelada, preparar_descarga,
                                limpiar_descarga, instalar_y_reiniciar)


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
    assets = release.get('assets', [])
    if not isinstance(assets, list) or any(not isinstance(asset, dict) for asset in assets):
        raise ValueError('GitHub devolvió una lista de instaladores inválida')
    for asset in assets:
        if asset.get('name') == nombre and asset.get('browser_download_url') == esperado:
            return {'version': numero, 'url': esperado, 'bytes': asset.get('size'),
                    'sha256': str(asset.get('digest', '')).removeprefix('sha256:')}
    raise ValueError('La nueva versión todavía no tiene un instalador para este Mac. Inténtalo más tarde.')


def _consultar_github_http():
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


def _consulta_separada(resultados):
    try:
        resultados.put({'actualizacion': _consultar_github_http()})
    except Exception as error:
        resultados.put({'error': str(error)})


def consultar_github(cancelar=None):
    # Aislar también DNS y lecturas bloqueadas: un timeout de socket no limita el total.
    contexto = multiprocessing.get_context('spawn')
    resultados = contexto.Queue(maxsize=1)
    proceso = contexto.Process(target=_consulta_separada, args=(resultados,), daemon=True)
    iniciado = False
    limite = time.monotonic() + 30
    try:
        if cancelar is not None and cancelar.is_set():
            raise ActualizacionCancelada()
        proceso.start()
        iniciado = True
        while True:
            if cancelar is not None and cancelar.is_set():
                raise ActualizacionCancelada()
            restante = limite - time.monotonic()
            if restante <= 0:
                raise TimeoutError('La consulta de actualizaciones superó el límite de 30 segundos')
            try:
                resultado = resultados.get(timeout=min(0.1, restante))
            except queue.Empty:
                if not proceso.is_alive():
                    # El hijo espera a vaciar su cola antes de finalizar.
                    try:
                        resultado = resultados.get(timeout=0.1)
                    except queue.Empty as error:
                        raise RuntimeError('La consulta de actualizaciones terminó sin resultado') from error
                else:
                    continue
            if 'error' in resultado:
                raise ValueError(resultado['error'])
            return resultado['actualizacion']
    finally:
        if iniciado:
            proceso.join(timeout=0.2)
            if proceso.is_alive():
                proceso.terminate()
                proceso.join(timeout=1)
            if proceso.is_alive():
                proceso.kill()
                proceso.join(timeout=1)
        proceso.close()
        resultados.close()
        resultados.join_thread()


class Actualizador:
    def __init__(self):
        self.consultando = False
        self.resultados = queue.Queue()
        self.texto_menu = 'Buscar actualizaciones…'
        self.cancelacion = threading.Event()
        self.preparada = None
        self.entregada = False
        self._limpiezas = set()
        self._mutex_limpieza = threading.Lock()

    def buscar(self):
        if self.consultando:
            return
        self.consultando = True
        self.cancelacion.clear()
        self.texto_menu = 'Buscando actualizaciones…'
        threading.Thread(target=self._consultar, daemon=True, name='actualizaciones').start()

    def _consultar(self):
        try:
            self.resultados.put({'actualizacion': consultar_github(self.cancelacion)})
        except ActualizacionCancelada:
            self.resultados.put({'cancelada': True})
        except Exception as error:
            self.resultados.put({'error': str(error)})
        finally:
            self.consultando = False

    def descargar(self, nueva):
        if self.consultando:
            return
        self.descartar()
        self.cancelacion.clear()
        self.consultando = True
        self.texto_menu = 'Descargando actualización… 0%'
        threading.Thread(target=self._descargar, args=(nueva,), daemon=True,
                         name='descarga-actualizacion').start()

    def _descargar(self, nueva):
        try:
            self.preparada = preparar_descarga(nueva, self._progreso, self.cancelacion)
            self.resultados.put({'descargada': self.preparada})
        except ActualizacionCancelada:
            self.resultados.put({'cancelada': True})
        except Exception as error:
            self.resultados.put({'error': str(error)})
        finally:
            self.consultando = False

    def _progreso(self, texto):
        self.texto_menu = texto

    def cancelar(self):
        self.cancelacion.set()

    @property
    def limpiando(self):
        with self._mutex_limpieza:
            return bool(self._limpiezas)

    def descartar(self):
        if self.preparada is not None and not self.entregada:
            preparada = self.preparada
            self.preparada = None
            with self._mutex_limpieza:
                self._limpiezas.add(preparada['carpeta'])
            def limpiar():
                try:
                    limpiar_descarga(preparada)
                except Exception as error:
                    logging.warning('Descarga conservada para limpieza posterior: %s', json.dumps({
                        'carpeta': preparada['carpeta'], 'error': str(error)}))
                finally:
                    with self._mutex_limpieza:
                        self._limpiezas.discard(preparada['carpeta'])
            try:
                threading.Thread(target=limpiar, daemon=True, name='limpieza-actualizacion').start()
            except RuntimeError as error:
                with self._mutex_limpieza:
                    self._limpiezas.discard(preparada['carpeta'])
                logging.warning('No se pudo iniciar la limpieza: %s', json.dumps({
                    'carpeta': preparada['carpeta'], 'error': str(error)}))

    def instalar(self):
        if self.preparada is None:
            raise ValueError('No hay una actualización preparada')
        instalar_y_reiniciar(self.preparada)
        self.entregada = True

    def obtener_resultado(self):
        try:
            resultado = self.resultados.get_nowait()
        except queue.Empty:
            return None
        return resultado
