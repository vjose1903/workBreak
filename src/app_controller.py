"""Control del proceso del bot; no depende de AppKit ni envía entradas de usuario."""
import copy
import logging
import json
from logging.handlers import RotatingFileHandler
import multiprocessing
import os
from pathlib import Path
import queue
import signal
import time
from collections import deque

from menu import _dict_a_config, _registro_valido, guardar_configuracion
from user_activity import DetencionSolicitada


def _publicar(eventos, evento):
    try:
        eventos.put_nowait(evento)
    except (queue.Full, ValueError, OSError):
        pass  # Los registros están también en disco; la interfaz no bloquea la automatización.


def _estadisticas(bot):
    tracker = bot.stats_tracker
    return {
        'total': tracker.get_total_runtime(),
        'editor': tracker.get_total_editor_time(),
        'navegador': tracker.get_total_web_time(),
        'sesiones_editor': tracker.get_editor_sessions(),
    }


class RegistroInterfaz(logging.Handler):
    def __init__(self, eventos):
        super().__init__()
        self.eventos = eventos
        self.setFormatter(logging.Formatter('%(asctime)s — %(levelname)s — %(message)s'))

    def emit(self, registro):
        _publicar(self.eventos, {
            'tipo': 'registro', 'mensaje': self.format(registro),
            'error': registro.levelno >= logging.ERROR,
        })


def ejecutar_proceso_bot(registro, detener, eventos, ruta_log, pid_interfaz):
    """Entrada independiente para multiprocessing con spawn (sin heredar AppKit)."""
    # Ctrl+C lo gestiona la interfaz, que solicita la limpieza mediante el evento.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    raiz = logging.getLogger()
    archivo = RotatingFileHandler(ruta_log, maxBytes=2_000_000, backupCount=2, encoding='utf-8')
    archivo.setFormatter(logging.Formatter('%(asctime)s — %(levelname)s — %(message)s'))
    consola = logging.StreamHandler()
    consola.setFormatter(archivo.formatter)
    puente = RegistroInterfaz(eventos)
    raiz.addHandler(archivo)
    raiz.addHandler(puente)
    raiz.addHandler(consola)
    raiz.setLevel(logging.INFO)
    bot = None
    codigo = 1

    def cancelado():
        return detener.is_set() or os.getppid() != pid_interfaz

    def informar(estado, **datos):
        evento = {'tipo': 'estado', 'estado': estado, **datos}
        if bot is not None:
            evento['estadisticas'] = _estadisticas(bot)
        _publicar(eventos, evento)

    def comprobar_cancelacion():
        if cancelado():
            raise DetencionSolicitada()

    try:
        if cancelado():
            codigo = 0
            return
        informar('iniciando')
        config = _dict_a_config(registro, comprobar_cancelacion=comprobar_cancelacion)
        if registro.get('fuente_tipo') == 'directorio' and not hasattr(config.fuente, 'directorio'):
            raise ValueError('No se pudo cargar el directorio elegido. Selecciona otro directorio.')
        if cancelado():
            codigo = 0
            return
        from automation_bot import AutomationBot
        guardar_configuracion(config)
        bot = AutomationBot(solicitar_detencion=cancelado, informar_estado=informar)
        codigo = bot.gestionar_ejecucion(config)
    except DetencionSolicitada:
        codigo = 0
    except Exception as error:
        logging.error('Fallo en la sesión del bot: %s', json.dumps({
            'tipo': type(error).__name__, 'error': str(error)}, ensure_ascii=False), exc_info=True)
    finally:
        _publicar(eventos, {
            'tipo': 'finalizado', 'codigo': codigo,
            'estadisticas': _estadisticas(bot) if bot is not None else {},
        })
        raiz.removeHandler(puente)
        raiz.removeHandler(archivo)
        raiz.removeHandler(consola)
        archivo.close()
        consola.close()
        if os.getppid() != pid_interfaz:
            eventos.cancel_join_thread()
        if codigo:
            raise SystemExit(codigo)


class ControladorBot:
    def __init__(self, contexto=None, ruta_log=None):
        self.contexto = contexto or multiprocessing.get_context('spawn')
        self.ruta_log = Path(ruta_log or Path.home() / 'Library/Logs/WorkBreak/workbreak.log')
        self.ruta_log.parent.mkdir(parents=True, exist_ok=True)
        self.proceso = None
        self.detencion = None
        self.eventos = None
        self.estado = {'estado': 'detenido'}
        self.estadisticas = {}
        self.registros = deque(maxlen=300)
        self.ultimo_error = ''
        self.inicio = None
        self.deteniendo = False
        self._resultado_recibido = False

    @property
    def activo(self):
        return self.proceso is not None and self.proceso.is_alive()

    def iniciar(self, registro):
        self.actualizar()
        if self.activo:
            raise ValueError('Ya hay una sesión del bot en ejecución.')
        if not _registro_valido(registro):
            raise ValueError('La configuración no es válida.')
        if registro.get('modo') == 'web' and (not registro.get('browser') or not any(p.strip() for p in registro.get('paginas', []))):
            raise ValueError('Para usar solo navegador selecciona un navegador y al menos una web.')
        if registro.get('modo') != 'editor' and registro.get('paginas') and not registro.get('browser'):
            raise ValueError('Selecciona un navegador para utilizar las webs configuradas.')
        if self.proceso is not None:
            self.proceso.close()
            self.proceso = None
        if self.eventos is not None:
            self.eventos.close()
            self.eventos.join_thread()
        self.eventos = self.contexto.Queue(maxsize=256)
        self.detencion = self.contexto.Event()
        self.proceso = self.contexto.Process(
            target=ejecutar_proceso_bot,
            args=(copy.deepcopy(registro), self.detencion, self.eventos, str(self.ruta_log), os.getpid()),
            name='WorkBreak-bot', daemon=True,
        )
        self.estado = {'estado': 'iniciando'}
        self.estadisticas = {}
        self.ultimo_error = ''
        self.deteniendo = False
        self._resultado_recibido = False
        try:
            self.proceso.start()
        except Exception:
            self.proceso = None
            self.estado = {'estado': 'error'}
            raise
        self.inicio = time.monotonic()

    def detener(self):
        if self.activo:
            self.deteniendo = True
            self.estado = {'estado': 'deteniendo'}
            self.detencion.set()

    def actualizar(self):
        if self.eventos is not None:
            while True:
                try:
                    evento = self.eventos.get_nowait()
                except queue.Empty:
                    break
                tipo = evento.get('tipo')
                if tipo == 'registro':
                    self.registros.append(evento['mensaje'])
                    if evento.get('error'):
                        self.ultimo_error = evento['mensaje']
                elif tipo == 'estado' and not self.deteniendo:
                    self.estado = evento
                elif tipo == 'finalizado':
                    self._resultado_recibido = True
                    self.estado = {'estado': 'finalizado' if evento['codigo'] == 0 else 'error'}
                if 'estadisticas' in evento:
                    self.estadisticas = evento['estadisticas']
        if self.proceso is not None and not self.proceso.is_alive():
            self.proceso.join(timeout=0)
            if not self._resultado_recibido:
                self.estado = {'estado': 'finalizado' if self.proceso.exitcode == 0 else 'error'}
                if self.proceso.exitcode and not self.ultimo_error:
                    self.ultimo_error = f'El proceso terminó con código {self.proceso.exitcode}.'
            self.deteniendo = False

    def cerrar(self):
        if self.activo:
            raise RuntimeError('La sesión debe finalizar antes de cerrar la interfaz.')
        if self.proceso is not None:
            self.proceso.join(timeout=0)
            self.proceso.close()
            self.proceso = None
        if self.eventos is not None:
            self.eventos.close()
            self.eventos.join_thread()
            self.eventos = None
        self.detencion = None
