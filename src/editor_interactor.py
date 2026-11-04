import json
import clipboard_state
import logging
import os
from pathlib import Path
import pyautogui
import random
import re
import subprocess
import tempfile
import time
from typing import Optional

from base_automation import BaseAutomation, FailsafeActivo, PortapapelesNoDisponible
from code_generator import CodeGenerator
from code_source import RealProjectSource
from statistics_tracker import StatisticsTracker
from menu import acciones_config
from editor_catalog import EDITORES, binario_editor
from editor_shortcut import resolver_atajo
from mac_accessibility import documento_editor


class EditorNoDisponible(Exception):
    """Excepción para cuando no se puede abrir ningún editor instalado"""


def _misma_ruta(url: str, ruta: str) -> bool:
    """Compara una URL file:// con una ruta local (macOS resuelve /var como /private/var)."""
    from urllib.parse import unquote, urlparse
    partes = urlparse(url)
    return (partes.scheme == 'file' and bool(partes.path)
            and os.path.realpath(unquote(partes.path)) == os.path.realpath(ruta))


class LineaDesincronizada(Exception):
    """En una ventana del usuario, el editor cambió el código del bot (formateo, extensiones)."""


class EditorInteractor(BaseAutomation):
    def __init__(self, stats_tracker: StatisticsTracker, fuente_codigo=None):
        super().__init__()
        pyautogui.PAUSE = 0.05

        self.stats_tracker = stats_tracker
        self.fuente_codigo = fuente_codigo or CodeGenerator()
        self.VALID_EDITORS = list(EDITORES)
        self.EDITOR_STARTUP_TIME = 30
        self.EDITOR_WINDOW_OFFSET = 20
        self.EDITOR_ABIERTO = False
        self.editor_actual = None
        self._portapapeles_original = None
        self._formatos_portapapeles = None
        self.lineas_actuales = None
        self._lineas_observadas = {}
        self.fases = "ambas"
        self.acciones = None
        self.bloque_actual = None
        self.inicio_bloque = 0
        self.indice_linea = 0
        self.desplazamiento = 0
        self.necesita_reposicionar = True
        self.ruta_archivo = None
        self.directorio_trabajo = None
        self.informar_estado = None
        self._fases_con_archivo = 0
        # Con una carpeta como fuente, el archivo también rota por tiempo (no solo por fases).
        self._archivo_desde = None
        self._duracion_archivo = None
        self.EDITOR_INFO = EDITORES
        # True si al iniciar ya había una ventana del editor: el archivo se abre en ella.
        self.rango_duracion = (60, 240)
        self.reutilizar_ventana = False
        self._resincronizaciones = 0
        self._codigo_pendiente = None
        self.atajo_ir_linea = None

    def validar_editor(self, value: str) -> str:
        """Valida que el editor esté en la lista de editores válidos"""
        if value not in self.VALID_EDITORS:
            raise ValueError(f"El editor debe ser uno de {self.VALID_EDITORS}")
        return value

    def _comando_abrir_editor(self, editor: str, ruta_archivo: Optional[str]) -> Optional[list]:
        if editor not in self.VALID_EDITORS:
            return None
        if self.is_mac and self.directorio_trabajo:
            binario = binario_editor(editor)
            if binario is None:
                return None
            cmd = [binario]
        elif self.is_windows:
            cmd = [EDITORES[editor]['binario']]
        elif self.is_mac:
            cmd = ['open', '-g', '-a', self.EDITOR_INFO[editor]['mac']]
        else:
            return None
        if self.reutilizar_ventana:
            # Sin la carpeta temporal: no se reemplaza el espacio de trabajo de esa ventana.
            cmd.append('--reuse-window')
        elif self.directorio_trabajo and not self.EDITOR_ABIERTO:
            cmd.extend(['--new-window', self.directorio_trabajo])
        if ruta_archivo:
            cmd.append(ruta_archivo)
        return cmd

    def ejecutar_comando(self, cmd: list) -> bool:
        """Ejecuta el comando para abrir el editor; True si se lanzó correctamente"""
        self._antes_accion()
        logging.info(f"Ejecutando comando: {cmd}")
        try:
            if self.is_windows:
                subprocess.Popen(cmd, shell=True)
                return True
            resultado = self._ejecutar_proceso(cmd, capture_output=True, text=True, timeout=20)
            if resultado.returncode != 0:
                mensaje = (resultado.stderr or resultado.stdout or "").strip()
                logging.error(f"Error lanzando el editor ({cmd}): {mensaje}")
                return False
            return True
        except FileNotFoundError:
            logging.error(f"No se encontró el ejecutable para abrir el editor: {cmd}")
            return False
        except subprocess.TimeoutExpired:
            logging.error(f"Timeout lanzando el editor: {cmd}")
            return False
        except Exception as e:
            logging.error(f"Error lanzando el editor ({cmd}): {e}")
            return False

    def _crear_archivo_temporal(self, nombre: str = 'index.tsx') -> str:
        """Crea un archivo vacío con el nombre indicado en la carpeta temporal de la sesión.

        En macOS se confirma la ruta completa. En Windows el nombre incluye una
        identidad de sesión, porque la comprobación del título no proporciona la ruta.
        """
        if self.directorio_trabajo is None:
            self._crear_directorio_trabajo()
        carpeta = Path(self.directorio_trabajo)
        if self.is_windows:
            nombre = f'workbreak_{carpeta.name}_{nombre}'
        ruta, numero = carpeta / nombre, 2
        while ruta.exists():
            ruta = carpeta / str(numero) / nombre
            numero += 1
        ruta.parent.mkdir(exist_ok=True)
        ruta.touch()
        return str(ruta)

    def _crear_directorio_trabajo(self) -> None:
        # Sin prefijo propio: la ruta se ve en la barra de navegación del editor.
        carpeta = Path(tempfile.mkdtemp(prefix=""))
        self.directorio_trabajo = str(carpeta)
        ajustes_editor = {
            "editor.autoClosingBrackets": "never",
            "editor.autoClosingQuotes": "never",
            "editor.autoClosingComments": "never",
            "editor.autoSurround": "never",
            "editor.autoIndent": "none",
            "editor.formatOnType": False,
            "editor.formatOnPaste": False,
            "editor.formatOnSave": False,
            "editor.trimAutoWhitespace": False,
            "editor.quickSuggestions": False,
            "editor.suggestOnTriggerCharacters": False,
            "editor.acceptSuggestionOnEnter": "off",
            "editor.inlineSuggest.enabled": False,
            "editor.linkedEditing": False,
        }
        # Las preferencias del usuario por lenguaje prevalecen sobre ajustes genéricos.
        lenguajes = ("typescriptreact", "typescript", "javascriptreact", "javascript")
        ajustes = {**ajustes_editor, **{f"[{lenguaje}]": ajustes_editor for lenguaje in lenguajes},
                   "files.autoSave": "off", "files.trimTrailingWhitespace": False}
        (carpeta / '.vscode').mkdir()
        (carpeta / '.vscode/settings.json').write_text(json.dumps(ajustes, indent=2), encoding='utf-8')

    def _obtener_codigo(self) -> str:
        try:
            return self.fuente_codigo.obtener_codigo()
        except (OSError, ValueError) as error:
            raise EditorNoDisponible('No se pudo leer la fuente; se conserva el código actual') from error

    def _nombre_archivo_codigo(self) -> str:
        """Nombre del archivo de origen (fuente real) o del componente generado."""
        nombre = getattr(self.fuente_codigo, 'nombre_archivo', None)
        if isinstance(nombre, str) and os.path.basename(nombre):
            return os.path.basename(nombre)
        return 'index.tsx'

    def _cambiar_archivo(self, nombre: str) -> None:
        """Cierra la pestaña actual del bot y abre otra con el nombre del nuevo código."""
        anterior = self.ruta_archivo
        self._asegurar_destino()
        # Guardar antes de cerrar evita el diálogo de cambios sin guardar.
        self._hotkey(self.cmd_key, 's')
        self._esperar(0.5)
        self._asegurar_destino()
        self._hotkey(self.cmd_key, 'w')
        self._esperar(0.5)
        self.ruta_archivo = self._crear_archivo_temporal(nombre)
        cmd = self._comando_abrir_editor(self.editor_actual, self.ruta_archivo)
        if not cmd or not self.ejecutar_comando(cmd):
            raise EditorNoDisponible("No se pudo abrir el archivo del nuevo código")
        self._esperar(1)
        try:
            os.unlink(anterior)
        except OSError:
            pass

    def abrir_editor(self, editor: str) -> None:
        """Abre el editor seleccionado con el archivo temporal; falla si no está disponible."""
        if self.EDITOR_ABIERTO:
            return

        try:
            # El primer código se elige antes de abrir para que la pestaña lleve su nombre.
            acciones = acciones_config({'fases': self.fases, 'acciones_editor': self.acciones}, 'editor')
            if acciones['escribir']:
                self._codigo_pendiente = self._obtener_codigo()
            self.ruta_archivo = self._crear_archivo_temporal(self._nombre_archivo_codigo())
            self.reutilizar_ventana = self._editor_tiene_ventana(editor)
            if self.reutilizar_ventana:
                logging.info("Hay una ventana del editor abierta; el archivo del bot se abre en ella")

            efectivo = self._lanzar_editor(editor, self.ruta_archivo)
            if efectivo is None:
                raise EditorNoDisponible(
                    f"No se pudo abrir ningún editor instalado. "
                    "Instala un editor compatible para ejecutar el bot."
                )

            info = self.EDITOR_INFO[efectivo]
            if not self._esperar_ventana_editor(info):
                raise EditorNoDisponible("No se pudo confirmar la ventana del editor")
            self._esperar(1)

            self.editor_actual = efectivo
            self.EDITOR_ABIERTO = True  # Una pausa en la preparación debe recuperar esta misma ventana.
            self._comprobar_atajo_corrida()
            self._asegurar_destino()
            self._llevar_mouse_al_editor()
        except (EditorNoDisponible, pyautogui.FailSafeException):
            raise
        except Exception as e:
            self.manejar_error(f"Error al abrir el editor {editor}: {e}")

    def _lanzar_editor(self, editor: str, ruta_archivo: Optional[str]) -> Optional[str]:
        """Abre únicamente el editor elegido por el usuario."""
        cmd = self._comando_abrir_editor(editor, ruta_archivo)
        if cmd and self.ejecutar_comando(cmd):
            return editor
        return None

    def _esperar_ventana_editor(self, info: dict) -> bool:
        """Espera (reintentando) a que la ventana del editor esté disponible y la activa"""
        limite = time.monotonic() + self.EDITOR_STARTUP_TIME
        while time.monotonic() < limite:
            if self.activar_aplicacion(info["proceso"], info["mac"]):
                return True
            self._esperar(0.5)
        return False

    def asegurar_editor_abierto(self, editor: str) -> None:
        """Asegura que el editor esté abierto y enfocado sin relanzarlo cada ciclo.

        Una vez abierto, usa el editor efectivo (el que realmente se pudo lanzar).
        """
        if not self.EDITOR_ABIERTO:
            self.abrir_editor(editor)
            return

        self._comprobar_atajo_corrida()
        self._asegurar_destino()
        self._llevar_mouse_al_editor()

    def _comprobar_atajo_corrida(self):
        if self.atajo_ir_linea is not None:
            return
        if not self._esperar_editor_al_frente(self.EDITOR_INFO[self.editor_actual]):
            raise EditorNoDisponible("No se pudo consultar el atajo: el editor no está al frente")
        try:
            self.atajo_ir_linea = resolver_atajo(self.editor_actual, self._esperar)
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            detalle = getattr(error, 'stderr', None) or str(error)
            raise EditorNoDisponible("No se pudo determinar el atajo Ir a línea antes de interactuar: " + detalle.strip()) from error
        logging.info("Atajo Ir a línea de esta corrida: %s", json.dumps({
            "editor": self.editor_actual, "atajo": self.atajo_ir_linea}, ensure_ascii=False))

    def _editor_tiene_ventana(self, editor: str) -> bool:
        """True si el editor ya tiene alguna ventana (también minimizada o en otro escritorio)."""
        if not self.is_mac:
            return False
        try:
            from AppKit import NSRunningApplication
            import Quartz as q
            pids = {app.processIdentifier() for app in
                    NSRunningApplication.runningApplicationsWithBundleIdentifier_(EDITORES[editor]['bundle'])}
            if not pids:
                return False
            ventanas = q.CGWindowListCopyWindowInfo(
                q.kCGWindowListOptionAll | q.kCGWindowListExcludeDesktopElements, q.kCGNullWindowID)
            for ventana in ventanas or []:
                limites = ventana.get('kCGWindowBounds') or {}
                if (ventana.get('kCGWindowLayer') == 0 and ventana.get('kCGWindowOwnerPID') in pids
                        and limites.get('Width', 0) >= 200 and limites.get('Height', 0) >= 200):
                    return True
        except Exception as e:
            logging.warning(f"No se pudo comprobar si el editor tiene ventanas abiertas: {e}")
        return False

    def _llevar_mouse_al_editor(self) -> None:
        """Lleva el cursor a la pantalla del editor enfocado si está fuera de su ventana."""
        acciones = acciones_config({'fases': self.fases, 'acciones_editor': self.acciones}, 'editor')
        if not acciones['mover_mouse']:
            return
        try:
            centro = self._configurar_area_mouse(self._rectangulo_ventana_editor())
        except RuntimeError as e:
            logging.warning(f"No se pudo llevar el mouse al editor: {e}")
            return
        if not self._mouse_en_area_segura():
            # Un salto directo: un recorrido entre pantallas atraviesa huecos sin monitor.
            self._move_to(*centro)

    def _asegurar_destino(self) -> None:
        """Rechaza la entrada si no está activo el archivo temporal de esta sesión."""
        if not self.editor_actual or not self.ruta_archivo:
            raise EditorNoDisponible("No hay archivo temporal confirmado")
        info = self.EDITOR_INFO[self.editor_actual]
        if not self._activar_si_necesario(info["proceso"], info["mac"]):
            raise EditorNoDisponible("No se pudo enfocar el editor; se cancela la entrada")
        if not self._esperar_editor_al_frente(info):
            raise EditorNoDisponible("El editor no pasó a primer plano; se cancela la entrada")
        try:
            documento_previo = documento_editor(EDITORES[self.editor_actual]['bundle']) if self.is_mac else ''
            # Enfocar código también cuando el terminal integrado tenía el foco.
            self._hotkey(self.cmd_key, "1")
            self._esperar(0.15)
            if self.is_windows:
                import win32gui
                titulo = win32gui.GetWindowText(win32gui.GetForegroundWindow())
            elif self.is_mac:
                # La ruta del documento (AXDocument) distingue el archivo del bot de uno del
                # usuario con el mismo nombre.
                self._antes_accion()
                documento = documento_editor(EDITORES[self.editor_actual]['bundle'])
                self._antes_accion()
                if (self.reutilizar_ventana and _misma_ruta(documento_previo, self.ruta_archivo)
                        and not _misma_ruta(documento, self.ruta_archivo)):
                    # El archivo estaba en otro grupo: abrirlo en el grupo que acabamos de enfocar.
                    cmd = self._comando_abrir_editor(self.editor_actual, self.ruta_archivo)
                    if not cmd or not self.ejecutar_comando(cmd):
                        raise EditorNoDisponible('No se pudo enfocar el archivo temporal en el grupo de código')
                    limite = time.monotonic() + 5
                    while not _misma_ruta(documento, self.ruta_archivo) and time.monotonic() < limite:
                        self._esperar(0.1)
                        documento = documento_editor(EDITORES[self.editor_actual]['bundle'])
                        self._antes_accion()
                if not _misma_ruta(documento, self.ruta_archivo):
                    raise EditorNoDisponible("El archivo del bot no está activo; se cancela la entrada")
                return
            else:
                raise EditorNoDisponible("Sistema operativo no soportado")
            if os.path.basename(self.ruta_archivo) not in titulo:
                raise EditorNoDisponible("El archivo temporal no está activo; se cancela la entrada")
        except (EditorNoDisponible, pyautogui.FailSafeException):
            raise
        except Exception as e:
            stderr = getattr(e, "stderr", None)
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            detalle = {
                "editor": self.editor_actual,
                "archivo": self.ruta_archivo,
                "tipo": type(e).__name__,
                "error": str(e),
                "stderr": stderr,
            }
            logging.error("Fallo verificando el editor: %s", json.dumps(detalle, ensure_ascii=False))
            motivo = stderr or str(e)
            raise EditorNoDisponible(f"No se pudo verificar el archivo temporal: {motivo.strip()}") from e

    def _esperar_editor_al_frente(self, info: dict, limite: float = 3.0) -> bool:
        """Espera a que el editor esté de verdad en primer plano antes de enviarle teclas.

        Si su ventana está en otro escritorio o en pantalla completa, macOS tarda en
        cambiar de espacio: un atajo enviado antes llegaría a otra aplicación.
        """
        if not self.is_mac:
            return True
        from mac_accessibility import aplicacion, pid_aplicacion_al_frente
        pid = aplicacion(info['bundle']).processIdentifier()
        fin = time.monotonic() + limite
        reactivar = time.monotonic() + 1
        while True:
            if pid_aplicacion_al_frente() == pid:
                return True
            if time.monotonic() >= fin:
                return False
            if time.monotonic() >= reactivar:
                self._activar_si_necesario(info["proceso"], info["mac"])
                reactivar = time.monotonic() + 1
            self._esperar(0.1)

    def manejar_error(self, mensaje: str) -> None:
        """Registra el error y lo propaga para que el bot lo maneje (nunca sys.exit)"""
        logging.error(mensaje)
        raise RuntimeError(mensaje)

    def interactuar_editor(self, duracion_maxima: Optional[float] = None) -> None:
        """Inyecta código una vez y alterna fases de escritura y mouse con duraciones variables.

        `duracion_maxima` limita el turno actual (usado al alternar con el navegador).
        """
        acciones = acciones_config({'fases': self.fases, 'acciones_editor': self.acciones}, 'editor')
        if not any(acciones.values()):
            return
        tiempo_inicio = time.monotonic()
        tiempo_restante = self.tiempo_restante()

        if tiempo_restante is not None and tiempo_restante <= 0:
            logging.info("Tiempo restante agotado; se omite la interacción con el editor")
            return

        duracion = (random.uniform(*self.rango_duracion) if duracion_maxima is None
                    else duracion_maxima)
        if tiempo_restante is not None:
            duracion = min(duracion, tiempo_restante)

        tiempo_final = time.monotonic() + duracion

        logging.info(f"Iniciando interacción con editor por {duracion / 60:.1f} minutos")

        try:
            if acciones["escribir"] and self.lineas_actuales is None:
                self.inyectar_codigo()
                if self.lineas_actuales is None:
                    return

            while time.monotonic() < tiempo_final:
                if acciones["escribir"]:
                    self.fase_escritura(tiempo_final)
                if any(acciones[k] for k in ("click", "scroll", "mover_mouse")):
                    self.fase_mouse(tiempo_final)

        except pyautogui.FailSafeException:
            logging.warning("Failsafe activado - mouse en esquina superior izquierda")
            raise FailsafeActivo()
        except Exception:
            logging.exception("Error durante la interacción con el editor")
            raise
        finally:
            self.registrar_tiempo_interaccion(tiempo_inicio)

    def fase_escritura(self, tiempo_final: float) -> None:
        """Fase de escritura con duración variable: borra y reescribe bloques reales de código"""
        if not self._queda_tiempo_editor(tiempo_final):
            return
        linea_pendiente = (self.bloque_actual is not None
                           and self.indice_linea < len(self.bloque_actual)
                           and self.desplazamiento > 0)
        if (isinstance(self.fuente_codigo, RealProjectSource) and not linea_pendiente
                and (self._fases_con_archivo >= 3 or self._archivo_vencido())):
            self.inyectar_codigo()
        self._fases_con_archivo += 1
        if self.informar_estado:
            self.informar_estado('ejecutando', fase='escritura')
        duracion = self._duracion_fase_escritura()
        fin = min(time.monotonic() + duracion, tiempo_final)
        logging.info(f"Fase de escritura por {max(0.0, fin - time.monotonic()):.0f}s")

        self._asegurar_destino()

        while time.monotonic() < fin:
            if not self._queda_tiempo_editor(tiempo_final):
                break
            self._editar_bloque_real(fin)
            self._esperar(self._duracion_configurada('editor_bloque'))

    def _archivo_vencido(self) -> bool:
        return (self._archivo_desde is not None
                and time.monotonic() - self._archivo_desde >= self._duracion_archivo)

    def fase_mouse(self, tiempo_final: float) -> None:
        """Ejecuta las acciones de mouse habilitadas dentro de la ventana confirmada."""
        if self.informar_estado:
            self.informar_estado('ejecutando', fase='mouse')
        if not self._queda_tiempo_editor(tiempo_final):
            return
        duracion = self._duracion_fase_mouse()
        fin = min(time.monotonic() + duracion, tiempo_final)
        logging.info(f"Fase de mouse por {max(0.0, fin - time.monotonic()):.0f}s")

        self._asegurar_destino()

        self._ventana_mouse_editor = self.identidad_ventana_activa()
        if self._ventana_mouse_editor is None:
            raise EditorNoDisponible('No se pudo identificar la ventana del editor')
        try:
            self.necesita_reposicionar = True
            self._iniciar_fase_mouse()
            while time.monotonic() < fin:
                if not self._queda_tiempo_editor(tiempo_final):
                    break
                accion = self._movimiento_fase_mouse()
                clave = {'click': 'editor_pausa_click', 'scroll': 'editor_pausa_scroll',
                         'mover_mouse': 'editor_pausa_mover_mouse'}.get(accion, 'editor_pausa_mover_mouse')
                self._esperar(min(self._duracion_configurada(clave), max(0, fin - time.monotonic())))
        finally:
            self._ventana_mouse_editor = None

    def _antes_accion(self):
        super()._antes_accion()
        ventana = (getattr(self, '_ventana_escritura_editor', None)
                   or getattr(self, '_ventana_mouse_editor', None))
        if ventana is not None and self.identidad_ventana_activa() != ventana:
            raise EditorNoDisponible('Cambió la ventana del editor; se cancela la interacción')

    def _iniciar_fase_mouse(self) -> None:
        """Prepara el área segura y ejecuta solo las acciones habilitadas."""
        acciones = acciones_config({'fases': self.fases, 'acciones_editor': self.acciones}, 'editor')
        try:
            if acciones['scroll']:
                self._inicio_archivo()
            self._esperar(self._duracion_configurada('editor_preparacion'))
            centro = self._configurar_area_mouse(self._rectangulo_ventana_editor())
            if acciones['mover_mouse']:
                self._move_to(*centro, duration=self._duracion_configurada('editor_movimiento'))
            if acciones['click'] and self._mouse_en_area_segura():
                self._click()
            self._esperar(self._duracion_configurada('editor_preparacion'))
        except pyautogui.FailSafeException:
            raise
        except Exception as e:
            self._area_mouse = None
            logging.warning(f"No se pudo iniciar la fase de mouse: {e}")
            raise EditorNoDisponible("No se pudo confirmar un área segura para el mouse") from e

    def _movimiento_fase_mouse(self) -> None:
        """Elige una acción habilitada sin mover el cursor implícitamente."""
        acciones = acciones_config({'fases': self.fases, 'acciones_editor': self.acciones}, 'editor')
        centro = self._configurar_area_mouse(self._rectangulo_ventana_editor())
        if not self._mouse_en_area_segura():
            if acciones['mover_mouse']:
                self._move_to(*centro, duration=self._duracion_configurada('editor_centrado'))
            else:
                return
        opciones = [clave for clave in ('click', 'scroll', 'mover_mouse') if acciones[clave]]
        if not opciones:
            return
        accion = random.choice(opciones)
        if accion == 'click':
            self._click()
        elif accion == 'scroll':
            self._scroll(random.choice((-1, 1)) * random.randint(3, 12))
        else:
            x = random.randint(-self.EDITOR_WINDOW_OFFSET, self.EDITOR_WINDOW_OFFSET)
            y = random.randint(-self.EDITOR_WINDOW_OFFSET, self.EDITOR_WINDOW_OFFSET)
            self._move_rel(x, y, duration=self._duracion_configurada('editor_movimiento'))
        return accion

    def _rectangulo_ventana_editor(self):
        """Devuelve (x, y, ancho, alto) de la ventana del editor o None si no se puede obtener"""
        if not self.editor_actual:
            return None
        return self.rectangulo_aplicacion(self.EDITOR_INFO[self.editor_actual]['mac'])

    def _liberar_modificadores(self) -> None:
        """En macOS los modificadores pertenecen al evento, no se mantienen pulsados."""
        if self.is_mac:
            return
        for tecla in ("ctrl", "shift", "alt"):
            try:
                self._antes_accion()
                pyautogui.keyUp(tecla)
            except Exception:
                pass

    def _duracion_fase_escritura(self) -> float:
        """Duración aleatoria de la fase de escritura (corta, media, larga)"""
        if self.temporizacion['editor_escritura'] != [4, 115]:
            return self._duracion_configurada('editor_escritura')
        return random.choice([
            random.uniform(4, 8),
            random.uniform(10, 20),
            random.uniform(30, 55),
            random.uniform(70, 115),
        ])

    def _duracion_fase_mouse(self) -> float:
        """Duración aleatoria de la fase de mouse"""
        if self.temporizacion['editor_mouse'] != [2, 16]:
            return self._duracion_configurada('editor_mouse')
        return random.choice([
            random.uniform(2, 4),
            random.uniform(5, 9),
            random.uniform(10, 16),
        ])

    def _editar_bloque_real(self, tiempo_final: float) -> None:
        """Edita el bloque en curso o toma uno nuevo; continúa donde quedó la última iteración"""
        if not self.lineas_actuales:
            return

        try:
            self._asegurar_destino()
            if self.editor_actual:
                self._ventana_escritura_editor = self.identidad_ventana_activa()
                if self._ventana_escritura_editor is None:
                    raise EditorNoDisponible('No se pudo identificar la ventana de escritura')
            self._cerrar_paneles()

            if self.bloque_actual is None or self.indice_linea >= len(self.bloque_actual):
                inicio, bloque = self._elegir_bloque()
                if not bloque:
                    return
                self.bloque_actual = bloque
                self.inicio_bloque = inicio
                self.indice_linea = 0
                self.desplazamiento = 0
                n = len(bloque)
                logging.info(f"Nuevo bloque: líneas {inicio + 1} a {inicio + n} ({n} líneas)")
                self.necesita_reposicionar = True

            self._escribir_siguiente_linea(tiempo_final)
        except LineaDesincronizada:
            self._resincronizar_codigo()
        except (pyautogui.FailSafeException, EditorNoDisponible):
            raise
        except Exception as e:
            # No reiniciar la inyección completa si se pierde el estado de una edición.
            raise EditorNoDisponible("Se interrumpió la edición del fragmento; no se reemplazará el archivo completo") from e
        finally:
            self._ventana_escritura_editor = None

    def _escribir_siguiente_linea(self, tiempo_final: float) -> None:
        """Escribe la línea en curso; si quedó a medias, continúa desde donde se interrumpió"""
        linea = self.bloque_actual[self.indice_linea]
        if not linea.strip():
            # No seleccionar hasta el final en una línea vacía: incluye su salto.
            self.indice_linea += 1
            self.desplazamiento = 0
            self.necesita_reposicionar = True
            return

        if self.necesita_reposicionar:
            self._ir_a_linea(self.inicio_bloque + self.indice_linea + 1)
            self.necesita_reposicionar = False

        if self.desplazamiento == 0:
            self._limpiar_linea_actual()
            self._verificar_seleccion_linea(linea)
        else:
            self._fin_linea()
            self._esperar(self._duracion_configurada('editor_reanudar'))

        if self.desplazamiento:
            logging.info("Reanudando línea pendiente: %s", json.dumps({
                "linea": self.inicio_bloque + self.indice_linea + 1,
                "caracteres_escritos": self.desplazamiento,
                "caracteres_totales": len(linea),
            }))
        texto = linea[self.desplazamiento:]
        for c in texto:
            if not self._queda_tiempo_editor(tiempo_final):
                if self.desplazamiento:
                    self._guardar_linea_actual_mac()
                    self.necesita_reposicionar = True
                else:
                    self._press('left')
                    self.necesita_reposicionar = True
                return
            self._insertar_caracter(c)
            self.desplazamiento += 1
            self._lineas_observadas[self.inicio_bloque + self.indice_linea + 1] = linea[:self.desplazamiento]
            self._esperar(self._duracion_configurada('editor_caracter'))

        # Cada carácter ya se escribió; un segundo reemplazo puede
        # seleccionar el salto de línea y unir accidentalmente la línea siguiente.
        self._guardar_linea_actual_mac()
        self.indice_linea += 1
        self.desplazamiento = 0
        self.necesita_reposicionar = True
        self._resincronizaciones = 0

    def _insertar_caracter(self, caracter):
        self._write(caracter)

    def _max_bloque_segun_tamano(self) -> int:
        """Tamaño máximo del bloque según el tamaño del archivo para no borrarlo entero"""
        n = len(self.lineas_actuales)
        if n < 40:
            return random.randint(1, 2)
        if n < 80:
            return random.randint(1, 3)
        if n < 150:
            return random.randint(1, 4)
        return random.randint(1, 6)

    def _elegir_bloque(self) -> tuple:
        """Elige un bloque contiguo de líneas reales que se pueda reescribir con el teclado"""
        lineas = self.lineas_actuales

        if len(lineas) < 2:
            for idx, linea in enumerate(lineas):
                if self._linea_escribible(linea):
                    return idx, [linea]
            return 0, []

        for _ in range(25):
            inicio = random.randrange(len(lineas) - 1)
            if not self._linea_escribible(lineas[inicio]) or len(lineas[inicio]) > 160:
                continue
            max_bloque = self._max_bloque_segun_tamano()
            bloque = [lineas[inicio]]
            for idx in range(inicio + 1, len(lineas) - 1):
                if len(bloque) >= max_bloque:
                    break
                if not self._linea_escribible(lineas[idx]) or len(lineas[idx]) > 160:
                    break
                bloque.append(lineas[idx])
            if any(l.strip() for l in bloque):
                return inicio, bloque

        return 0, []

    def _linea_escribible(self, linea: str) -> bool:
        """Limita la reescritura a ASCII imprimible, sin tabulaciones."""
        return bool(linea.strip()) and all(0x20 <= ord(c) <= 0x7E for c in linea)

    def _limpiar_linea_actual(self) -> None:
        """Selecciona desde la columna 1 confirmada, sin borrar el salto de línea."""
        if self.is_windows:
            self._hotkey("shift", "end")
        else:
            self._hotkey("command", "shift", "right")
        self._liberar_modificadores()

    def _fin_linea(self) -> None:
        numero = self.inicio_bloque + self.indice_linea + 1
        self._confirmar_linea_mac(numero)
        # La lectura deja el cursor en columna 1; avanzar exactamente el prefijo
        # evita confundir el final visual de una línea ajustada con el lógico.
        for _ in range(self.desplazamiento):
            self._press('right')

    def _verificar_seleccion_linea(self, esperada):
        seleccion = self._leer_seleccion_mac()
        if seleccion != esperada:
            self._press('left')
            self.necesita_reposicionar = True
            raise EditorNoDisponible('La selección no coincide exactamente con la línea; no se reemplazará')

    def _inicio_archivo(self) -> None:
        if self.is_windows:
            self._hotkey("ctrl", "home")
        else:
            self._hotkey("command", "up")

    def _cerrar_paneles(self) -> None:
        """Cierra con Escape cualquier panel emergente (autocompletado, emojis, quick input)"""
        self._press("esc")
        self._esperar(0.1)

    def _ir_a_linea(self, numero: int) -> None:
        """Navega al archivo controlado y confirma la línea antes de editarla."""
        if self.atajo_ir_linea is None:
            raise EditorNoDisponible("El atajo Ir a línea no se comprobó al iniciar la corrida")
        self._hotkey(*self.atajo_ir_linea)
        self._esperar(0.2)
        if self.is_mac:
            # El quick input puede tomar el foco después de abrirse, especialmente al cargar.
            limite = time.monotonic() + 3.0
            intentos = 0
            while True:
                self._hotkey("command", "a")
                campo = self._leer_seleccion_mac()
                self._antes_accion()
                intentos += 1
                if campo is not None and re.fullmatch(r":\d*(?::\d*)?", campo) is not None:
                    break
                if time.monotonic() >= limite:
                    logging.error("No se confirmó Ir a línea: %s", json.dumps({
                        "editor": self.editor_actual, "atajo": self.atajo_ir_linea,
                        "intentos": intentos, "sin_seleccion": campo is None,
                        "longitud": len(campo) if campo is not None else None,
                        "prefijo_linea": bool(campo and campo.startswith(':')),
                    }, ensure_ascii=False))
                    self._press("esc")
                    raise EditorNoDisponible("No se confirmó el panel Ir a línea; no se enviaron coordenadas")
                self._esperar(0.1)
            destino = f":{numero}:1"
        else:
            destino = f"{numero}:1"
        self._write(destino, interval=0.03)
        self._esperar(0.1)
        self._press("enter")
        self._esperar(0.2)
        if self.is_mac or self.is_windows:
            self._confirmar_linea_mac(numero)
        self._liberar_modificadores()

    def _leer_seleccion_mac(self) -> Optional[str]:
        marcador = "workbreak:sin-seleccion"
        if not self.copiar_al_portapapeles(marcador):
            raise EditorNoDisponible("No se pudo preparar la comprobación del cursor")
        contenido = self.copiar_seleccion()
        # Un editor ocupado (p. ej. tras pegar muchos caracteres) puede copiar tarde.
        fin = time.monotonic() + 1.0
        while contenido == marcador and time.monotonic() < fin:
            self._esperar(0.1)
            contenido = self.leer_portapapeles()
        if contenido == marcador:
            return None
        self.portapapeles_bot['ultimo'] = contenido
        self.portapapeles_bot['version'] = clipboard_state.version()
        return contenido

    def _confirmar_linea_mac(self, numero: int) -> None:
        if not self.lineas_actuales or not 1 <= numero <= len(self.lineas_actuales):
            raise EditorNoDisponible("La línea solicitada no pertenece al código cargado")
        original = self.lineas_actuales[numero - 1]
        esperada = self._lineas_observadas.get(numero, original)
        actual = self._leer_linea_completa_mac()
        coincide = actual is not None and actual == esperada
        if not coincide:
            logging.error("Comprobación de línea fallida: %s", json.dumps({
                "linea": numero, "desplazamiento": self.desplazamiento,
                "longitud_esperada": len(esperada),
                "longitud_leida": len(actual) if actual is not None else None,
                "captura_previa": numero in self._lineas_observadas,
                "esperada": esperada[:80], "leida": actual[:80] if actual is not None else None,
            }, ensure_ascii=False))
            if self.reutilizar_ventana and actual is not None:
                raise LineaDesincronizada()
            raise EditorNoDisponible("El cursor no está en la línea esperada; se cancela la edición del fragmento")

    def _leer_linea_completa_mac(self) -> Optional[str]:
        # Cmd+L selecciona la línea lógica completa, incluso con ajuste visual de línea.
        self._hotkey(self.cmd_key, "l")
        actual = self._leer_seleccion_mac()
        self._press("left")
        if actual is not None:
            actual = actual.rstrip("\r\n")
            if "\n" in actual or "\r" in actual:
                raise EditorNoDisponible("La selección abarca más de una línea; se cancela la edición")
        return actual

    def _guardar_linea_actual_mac(self):
        if not (self.is_mac or self.is_windows) or not self.bloque_actual:
            return
        numero = self.inicio_bloque + self.indice_linea + 1
        actual = self._leer_linea_completa_mac()
        if actual is None:
            raise EditorNoDisponible("No se pudo guardar el estado de la línea reescrita")
        esperada = self.bloque_actual[self.indice_linea][:self.desplazamiento]
        if actual != esperada:
            logging.error("Contenido de línea inesperado: %s", json.dumps({
                "linea": numero, "desplazamiento": self.desplazamiento,
                "longitud_esperada": len(esperada), "longitud_leida": len(actual),
                "esperada": esperada[:80], "leida": actual[:80],
            }, ensure_ascii=False))
            if self.reutilizar_ventana:
                raise LineaDesincronizada()
            raise EditorNoDisponible("La línea cambió fuera de la escritura controlada; no se sobrescribirá")
        self._lineas_observadas[numero] = actual

    def _queda_tiempo_editor(self, tiempo_final: float) -> bool:
        """Indica si queda tiempo (duración de la fase y límite global)"""
        if time.monotonic() >= tiempo_final:
            return False
        restante = self.tiempo_restante()
        if restante is not None and restante <= 0:
            return False
        return True

    def guardar_portapapeles_original(self):
        if self._portapapeles_original is None:
            try:
                self._guardar_portapapeles_usuario()
                logging.info("Portapapeles del usuario guardado")
            except Exception as e:
                raise EditorNoDisponible("No se pudo guardar el portapapeles original; se cancela la inyección: " + str(e)) from e

    def _guardar_portapapeles_usuario(self):
        self._antes_accion()
        try:
            estado = clipboard_state.capturar()
        except Exception as error:
            raise PortapapelesNoDisponible('No se pudieron conservar todos los formatos del portapapeles') from error
        texto = self.leer_portapapeles()
        self._antes_accion()
        if clipboard_state.version() != estado['version']:
            raise PortapapelesNoDisponible('El portapapeles cambió mientras se guardaba; no se sobrescribirá')
        self._portapapeles_original = texto
        self._formatos_portapapeles = estado

    def inyectar_codigo(self) -> None:
        """Reemplaza el contenido del editor con un bloque grande de código realista"""
        self.guardar_portapapeles_original()
        if self._codigo_pendiente is not None:
            codigo, self._codigo_pendiente = self._codigo_pendiente, None
        else:
            codigo = self._obtener_codigo()
            nombre = self._nombre_archivo_codigo()
            actual = os.path.basename(self.ruta_archivo or '')
            if self.is_windows and self.directorio_trabajo:
                actual = actual.removeprefix(f'workbreak_{Path(self.directorio_trabajo).name}_')
            if self.EDITOR_ABIERTO and self.ruta_archivo and nombre != actual:
                self._cambiar_archivo(nombre)

        if not self.copiar_al_portapapeles(codigo):
            raise EditorNoDisponible('No se pudo copiar el código; se cancela la inyección')

        self._asegurar_destino()

        self._hotkey(self.cmd_key, 'a')
        self._esperar(0.15)
        self._hotkey(self.cmd_key, 'v')
        self.lineas_actuales = codigo.splitlines()
        self._fases_con_archivo = 0
        self._archivo_desde = time.monotonic()
        self._duracion_archivo = self._duracion_configurada('editor_archivo')
        self._lineas_observadas.clear()
        self.bloque_actual = None
        self.inicio_bloque = 0
        self.indice_linea = 0
        self.desplazamiento = 0
        self.necesita_reposicionar = True
        self._esperar(0.3)
        self._liberar_modificadores()
        if self.reutilizar_ventana:
            self._sincronizar_codigo_pegado()
        logging.info(f"Código inyectado: {len(self.lineas_actuales)} líneas, {len(codigo)} caracteres")

    def _sincronizar_codigo_pegado(self) -> None:
        """Toma como referencia el texto que muestra el editor tras pegar.

        Los ajustes del usuario (formatear o reindentar al pegar) pueden cambiar el código:
        las comprobaciones de línea deben compararse con lo que realmente quedó.
        """
        anterior = None
        # Los formateadores pueden tardar: se espera a dos lecturas iguales seguidas.
        for _ in range(6):
            self._esperar(0.5)
            self._hotkey(self.cmd_key, 'a')
            contenido = self._leer_seleccion_mac()
            self._press('left')
            if contenido is None:
                raise EditorNoDisponible("No se pudo leer el código pegado en el editor")
            if contenido == anterior:
                break
            anterior = contenido
        self.lineas_actuales = contenido.splitlines()

    def _resincronizar_codigo(self) -> None:
        """Adopta el código que muestra el editor y elige otro bloque, sin detener la sesión."""
        self._resincronizaciones += 1
        if self._resincronizaciones > 3:
            raise EditorNoDisponible("El editor sigue cambiando el código del bot; se cancela la edición")
        logging.warning("El editor cambió el código del bot; se toma lo que muestra como nueva referencia")
        # Confirmar que el archivo del bot sigue activo antes de copiar todo su contenido.
        self._asegurar_destino()
        self._sincronizar_codigo_pegado()
        self._lineas_observadas.clear()
        self.bloque_actual = None
        self.indice_linea = 0
        self.desplazamiento = 0
        self.necesita_reposicionar = True

    def restaurar_portapapeles(self) -> None:
        """Restaura el portapapeles del usuario al valor guardado en la primera inyección"""
        if self._portapapeles_original is None:
            return
        if self.portapapeles_es_del_bot(self.leer_portapapeles()):
            if self._formatos_portapapeles is not None:
                self._antes_accion()
                if not clipboard_state.restaurar(self._formatos_portapapeles,
                                                 esperada=self.portapapeles_bot.get('version')):
                    return  # Otra aplicación copió contenido después de la comprobación.
            elif not self.copiar_al_portapapeles(self._portapapeles_original):
                raise PortapapelesNoDisponible('No se pudo restaurar el portapapeles del usuario')
            logging.info("Portapapeles del usuario restaurado")

    def conservar_portapapeles_usuario(self):
        try:
            contenido = self.leer_portapapeles()
            try:
                propio = self.portapapeles_es_del_bot(contenido)
            except PortapapelesNoDisponible:
                if not self.portapapeles_bot.get('copia_pendiente'):
                    raise
                # Una copia interrumpida no permite atribuir el contenido: conservar el
                # actual completo como nueva referencia, sin escribir sobre él ni adivinar.
                propio = False
                logging.warning('Recuperación de copia interrumpida: %s', json.dumps({
                    'accion': 'conservar_portapapeles_actual', 'atribucion_al_bot': False}))
            if propio:
                self.portapapeles_bot['ultimo'] = contenido
            else:
                self._guardar_portapapeles_usuario()
        except PortapapelesNoDisponible as e:
            raise EditorNoDisponible(str(e)) from e
        self.portapapeles_bot.pop('copia_pendiente', None)
        self.portapapeles_bot.pop('escritura_pendiente', None)

    def registrar_tiempo_interaccion(self, tiempo_inicio: float) -> None:
        """Registra el tiempo de interacción con el editor"""
        tiempo_real = time.monotonic() - tiempo_inicio
        self.stats_tracker.register_editor_session(tiempo_real)
        logging.info(f"Interacción con editor finalizada, duración real: {tiempo_real / 60:.1f} minutos")
