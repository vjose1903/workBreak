import logging
from timing_config import temporizacion_config
import json
import os
import platform
import random
import subprocess
import time
from typing import Optional

import pyautogui
import clipboard_state
from process_locale import locale_utf8_disponible

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class FailsafeActivo(Exception):
    """Excepción para detener el bot cuando pyautogui detecta failsafe"""


class TiempoAgotado(BaseException):
    """Finalización normal que no debe convertirse en un fallo de interacción."""


class PortapapelesNoDisponible(RuntimeError):
    """No se puede leer o atribuir con seguridad el contenido del portapapeles."""


def _es_emergente(ventana, contenedora):
    """True si `ventana` es más pequeña que `contenedora` y cabe por completo en ella."""
    a, b = ventana.get('kCGWindowBounds'), contenedora.get('kCGWindowBounds')
    if not a or not b:
        return False
    x, y, ancho, alto = (a.get(clave, 0) for clave in ('X', 'Y', 'Width', 'Height'))
    cx, cy, cancho, calto = (b.get(clave, 0) for clave in ('X', 'Y', 'Width', 'Height'))
    return (cx <= x and cy <= y and x + ancho <= cx + cancho and y + alto <= cy + calto
            and ancho * alto < cancho * calto)


class BaseAutomation:
    def __init__(self):
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05
        self.temporizacion = temporizacion_config()

        # Determinamos el sistema operativo de manera más eficiente
        self.is_windows = os.name == "nt"
        self.is_mac = platform.system() == 'Darwin'

        # Definimos el cmd_key según el sistema operativo
        self.cmd_key = "ctrl" if self.is_windows else "command"

        # Resolución de pantalla
        self.screen_width, self.screen_height = pyautogui.size()

        # Infraestructura de tiempo basada en time.monotonic()
        self._tiempo_limite_absoluto: Optional[float] = None

        # Estado del anti-reposo
        self._antidespierto_activo = False
        self._proceso_caffeinate = None
        self._mac_keyboard = None
        self.monitor_actividad = None
        self.portapapeles_bot = {"ultimo": None}
        self._limpiando = False
        self._area_mouse = None

    def _duracion_configurada(self, clave):
        return random.uniform(*self.temporizacion[clave])

    def _antes_accion(self):
        pyautogui.failSafeCheck()
        if not self._limpiando and self.tiempo_restante() == 0:
            raise TiempoAgotado()
        if self.monitor_actividad is not None:
            self.monitor_actividad.comprobar()

    def _esperar(self, segundos):
        restante = None if self._limpiando else self.tiempo_restante()
        agotara = restante is not None and segundos >= restante
        if restante is not None:
            segundos = min(segundos, restante)
        if self.monitor_actividad is None:
            time.sleep(segundos)
        else:
            self.monitor_actividad.esperar_intervalo(segundos)
        if agotara:
            raise TiempoAgotado()

    def _ejecutar_proceso(self, cmd, timeout=10, **opciones):
        """Cancela únicamente el proceso auxiliar del bot si interviene el usuario."""
        self._antes_accion()
        if self.is_mac:
            # Finder no proporciona LANG: pbpaste/pbcopy y osascript deben usar el
            # mismo UTF-8 que Python, también en la aplicación compilada.
            opciones['env'] = {**opciones.get('env', os.environ), 'LC_ALL': locale_utf8_disponible()}
            if opciones.get('text') or opciones.get('universal_newlines'):
                opciones.setdefault('encoding', 'utf-8')
        if self.monitor_actividad is None:
            return subprocess.run(cmd, timeout=timeout, **opciones)
        entrada = opciones.pop('input', None)
        if entrada is not None:
            opciones['stdin'] = subprocess.PIPE
        check = opciones.pop('check', False)
        if opciones.pop('capture_output', False):
            opciones['stdout'] = subprocess.PIPE
            opciones['stderr'] = subprocess.PIPE
        proceso = subprocess.Popen(cmd, **opciones)
        fin = time.monotonic() + timeout
        try:
            while True:
                self._antes_accion()
                restante = fin - time.monotonic()
                if restante <= 0:
                    raise subprocess.TimeoutExpired(cmd, timeout)
                try:
                    stdout, stderr = proceso.communicate(input=entrada, timeout=min(0.02, restante))
                    break
                except subprocess.TimeoutExpired:
                    entrada = None
                    continue
            self._antes_accion()
        except BaseException:
            if proceso.poll() is None:
                proceso.terminate()
                try:
                    proceso.communicate(timeout=0.2)
                except subprocess.TimeoutExpired:
                    proceso.kill()
                    proceso.communicate()
            raise
        if check and proceso.returncode:
            raise subprocess.CalledProcessError(proceso.returncode, cmd, stdout, stderr)
        return subprocess.CompletedProcess(cmd, proceso.returncode, stdout, stderr)

    def _teclado_mac(self):
        if self._mac_keyboard is None:
            from mac_keyboard import MacKeyboard
            self._mac_keyboard = MacKeyboard(antes_evento=self._antes_accion)
        return self._mac_keyboard

    def _hotkey(self, *teclas):
        self._antes_accion()
        if self.is_mac:
            self._teclado_mac().hotkey(*teclas)
        else:
            pyautogui.hotkey(*teclas)

    def _press(self, tecla):
        self._antes_accion()
        if self.is_mac:
            self._teclado_mac().press(tecla)
        else:
            pyautogui.press(tecla)

    def _write(self, texto, interval=0):
        self._antes_accion()
        if self.is_mac:
            self._teclado_mac().write(texto, interval=interval)
        elif self.monitor_actividad is not None:
            for caracter in texto:
                self._antes_accion()
                pyautogui.write(caracter, interval=0)
                if interval:
                    self._esperar(interval)
        else:
            pyautogui.write(texto, interval=interval)

    def _move_to(self, x, y, duration=0):
        self._antes_accion()
        if self._area_mouse is not None:
            izquierda, arriba, derecha, abajo = self._area_mouse
            x, y = max(izquierda, min(x, derecha)), max(arriba, min(y, abajo))
        if self.monitor_actividad is None and not self.is_mac:
            pyautogui.moveTo(x, y, duration=duration)
            return
        inicio_x, inicio_y = self._posicion_mouse()
        pasos = max(1, int(duration / 0.01))
        for paso in range(1, pasos + 1):
            self._antes_accion()
            fraccion = paso / pasos
            destino = (round(inicio_x + (x - inicio_x) * fraccion), round(inicio_y + (y - inicio_y) * fraccion))
            marcar = getattr(self.monitor_actividad, 'marcar_movimiento_bot', None)
            if marcar is not None:
                marcar(*destino)
            pyautogui.moveTo(*destino, _pause=False)
            if duration:
                self._esperar(duration / pasos)

    def _move_rel(self, x, y, duration=0):
        self._antes_accion()
        if self.monitor_actividad is None and self._area_mouse is None and not self.is_mac:
            pyautogui.moveRel(x, y, duration=duration)
        else:
            actual_x, actual_y = self._posicion_mouse()
            self._move_to(actual_x + x, actual_y + y, duration=duration)

    def _click(self):
        self._antes_accion()
        self._comprobar_area_mouse()
        if self.is_mac:
            pyautogui.click(*self._posicion_mouse())
        else:
            pyautogui.click()

    def _scroll(self, cantidad):
        self._antes_accion()
        self._comprobar_area_mouse()
        if self.is_mac:
            pyautogui.scroll(cantidad, *self._posicion_mouse())
        else:
            pyautogui.scroll(cantidad)

    def _posicion_mouse(self):
        if self.is_mac:
            import Quartz as q
            punto = q.CGEventGetLocation(q.CGEventCreate(None))
            return round(punto.x), round(punto.y)
        return pyautogui.position()

    def _monitores(self):
        """Rectángulos globales en puntos, incluidos orígenes negativos y Retina."""
        if self.is_mac:
            import Quartz as q
            error, pantallas, _ = q.CGGetActiveDisplayList(64, None, None)
            if error:
                raise RuntimeError('No se pudieron detectar los monitores')
            return [(r.origin.x, r.origin.y, r.size.width, r.size.height)
                    for r in (q.CGDisplayBounds(pantalla) for pantalla in pantallas)]
        if self.is_windows:
            import win32api
            return [(x, y, derecha - x, abajo - y)
                    for _, _, (x, y, derecha, abajo) in win32api.EnumDisplayMonitors()]
        return [(0, 0, self.screen_width, self.screen_height)]

    def _mouse_en_area_segura(self):
        if self._area_mouse is None:
            return False
        x, y = self._posicion_mouse()
        izquierda, arriba, derecha, abajo = self._area_mouse
        return izquierda <= x <= derecha and arriba <= y <= abajo

    def _comprobar_area_mouse(self):
        if self._area_mouse is None:
            raise RuntimeError("No hay un área segura confirmada para el mouse")
        x, y = self._posicion_mouse()
        izquierda, arriba, derecha, abajo = self._area_mouse
        if not (izquierda <= x <= derecha and arriba <= y <= abajo):
            raise RuntimeError("Mouse fuera del área segura; se cancela la interacción")

    def _configurar_area_mouse(self, rectangulo):
        self._area_mouse = None
        if rectangulo is None:
            raise RuntimeError("No se pudo confirmar la ventana para mover el mouse")
        x, y, ancho, alto = rectangulo
        areas = []
        for mx, my, mw, mh in self._monitores():
            izquierda, arriba = max(mx, x + ancho // 3), max(my, y + 160)
            derecha = min(mx + mw - 1, x + ancho - 30)
            abajo = min(my + mh - 1, y + alto - 60)
            if derecha > izquierda and abajo > arriba:
                areas.append((izquierda, arriba, derecha, abajo))
        if not areas:
            raise RuntimeError("La ventana no tiene un área visible suficiente para el mouse")
        izquierda, arriba, derecha, abajo = max(
            areas, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
        self._area_mouse = (izquierda, arriba, derecha, abajo)
        return ((izquierda + derecha) // 2, (arriba + abajo) // 2)

    def rectangulo_aplicacion(self, nombre_mac):
        self._antes_accion()
        if self.is_windows:
            import win32gui
            x, y, derecha, abajo = win32gui.GetWindowRect(win32gui.GetForegroundWindow())
            return x, y, derecha - x, abajo - y
        if self.is_mac:
            from mac_accessibility import rectangulo_aplicacion
            resultado = rectangulo_aplicacion(nombre_mac)
            self._antes_accion()
            return resultado
        return None

    def identidad_ventana_activa(self):
        """Identificador nativo de la ventana superior, sin cambiar el foco."""
        # Esta lectura también se usa dentro del guardián del editor: no reentrar en él.
        BaseAutomation._antes_accion(self)
        if self.is_windows:
            import win32gui
            return win32gui.GetForegroundWindow()
        if self.is_mac:
            import Quartz as q
            ventanas = [v for v in q.CGWindowListCopyWindowInfo(
                q.kCGWindowListOptionOnScreenOnly, q.kCGNullWindowID) or []
                if v.get('kCGWindowLayer') == 0]
            if ventanas:
                # Las ventanas superiores de la misma app que caben dentro de otra mayor son
                # emergentes (sugerencias de la barra de direcciones, tooltips): no cambian el foco.
                pid = ventanas[0].get('kCGWindowOwnerPID')
                propias = []
                for ventana in ventanas:
                    if ventana.get('kCGWindowOwnerPID') != pid:
                        break
                    propias.append(ventana)
                for indice, ventana in enumerate(propias):
                    if not any(_es_emergente(ventana, otra) for otra in propias[indice + 1:]):
                        return ventana.get('kCGWindowNumber')
        raise RuntimeError('No se pudo identificar la ventana activa')

    # ------------------------------------------------------------
    # Tiempo (time.monotonic)
    # ------------------------------------------------------------

    def set_limite_tiempo(self, segundos: Optional[float]) -> None:
        """Establece un límite absoluto de ejecución; None elimina el límite"""
        if segundos is None:
            self._tiempo_limite_absoluto = None
        else:
            self._tiempo_limite_absoluto = time.monotonic() + segundos

    def tiempo_restante(self) -> Optional[float]:
        """Segundos restantes hasta el límite; None si no hay límite, 0.0 si se agotó"""
        if self._tiempo_limite_absoluto is None:
            return None
        return max(0.0, self._tiempo_limite_absoluto - time.monotonic())

    # ------------------------------------------------------------
    # Activación de aplicaciones / ventanas
    # ------------------------------------------------------------

    def activar_aplicacion(self, nombre_proceso: str, nombre_mac: str) -> bool:
        """Trae al frente la aplicación (por proceso en Windows, por app en macOS)"""
        self._antes_accion()
        try:
            if self.is_windows:
                exito = self._activar_aplicacion_windows(nombre_proceso)
            elif self.is_mac:
                exito = self._activar_aplicacion_mac(nombre_mac)
            else:
                logging.warning("Sistema operativo no soportado para activar aplicaciones")
                return False
        except pyautogui.FailSafeException:
            raise
        except Exception as e:
            logging.error(f"Error activando la aplicación '{nombre_proceso or nombre_mac}': {e}")
            return False

        self._antes_accion()
        return exito

    def _activar_si_necesario(self, nombre_proceso: str, nombre_mac: str) -> bool:
        """Confirma la activación sin confiar en un foco guardado anteriormente."""
        return self.activar_aplicacion(nombre_proceso, nombre_mac)

    def _activar_aplicacion_mac(self, nombre_mac: str) -> bool:
        """Activa la aplicación desde el proceso autorizado de WorkBreak."""
        from mac_accessibility import activar_aplicacion, aplicacion, pid_aplicacion_al_frente
        self._antes_accion()
        try:
            pid = aplicacion(nombre_mac).processIdentifier()
            # El resultado de la solicitud no sustituye la comprobación del foco real.
            activar_aplicacion(nombre_mac)
            limite = time.monotonic() + 3
            while True:
                self._antes_accion()
                if pid_aplicacion_al_frente() == pid:
                    return True
                if time.monotonic() >= limite:
                    return False
                self._esperar(0.05)
        except ValueError as error:
            logging.error("Error activando aplicación: %s", json.dumps({
                "aplicacion": nombre_mac, "error": str(error)}, ensure_ascii=False))
            return False

    def _activar_aplicacion_windows(self, nombre_proceso: str) -> bool:
        """Activa una ventana perteneciente al ejecutable solicitado."""
        try:
            import psutil
            import win32gui
            import win32process
            ventanas = []

            def agregar_ventana(hwnd, _):
                if not win32gui.IsWindowVisible(hwnd) or not win32gui.GetWindowText(hwnd):
                    return
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if psutil.Process(pid).name().lower() == nombre_proceso.lower():
                        ventanas.append(hwnd)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            win32gui.EnumWindows(agregar_ventana, None)
            if not ventanas:
                logging.warning(f"No se encontraron ventanas para el proceso: {nombre_proceso}")
                return False
            hwnd = win32gui.GetForegroundWindow()
            if hwnd not in ventanas:
                hwnd = ventanas[0]
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
                win32gui.SetForegroundWindow(hwnd)
            logging.debug(f"Ventana activada en Windows: {nombre_proceso}")
            return win32gui.GetForegroundWindow() == hwnd
        except Exception as e:
            logging.error(f"Error activando la ventana en Windows ({nombre_proceso}): {e}")
            return False

    # ------------------------------------------------------------
    # Portapapeles centralizado
    # ------------------------------------------------------------

    def copiar_al_portapapeles(self, texto: str) -> bool:
        """Copia texto al portapapeles con fallback nativo; True si tuvo éxito"""
        self._antes_accion()
        self.portapapeles_bot['escritura_pendiente'] = texto
        exito = self._copiar_portapapeles_fallback(texto)
        if exito:
            self.portapapeles_bot["ultimo"] = texto
            self.portapapeles_bot['version'] = clipboard_state.version()
            self.portapapeles_bot.pop('copia_pendiente', None)
            self.portapapeles_bot.pop('escritura_pendiente', None)
        return exito

    def _copiar_portapapeles_fallback(self, texto: str) -> bool:
        """Copia al portapapeles usando utilidades nativas (pbcopy/clip)"""
        try:
            if self.is_windows:
                resultado = self._ejecutar_proceso(["clip"], input=texto.encode('utf-16-le'), shell=True, timeout=5)
            else:
                resultado = self._ejecutar_proceso(["pbcopy"], input=texto, text=True, timeout=5)
            return resultado.returncode == 0
        except pyautogui.FailSafeException:
            raise
        except Exception as e:
            logging.error(f"Error copiando al portapapeles (fallback): {e}")
            return False

    def leer_portapapeles(self) -> str:
        """Lee el portapapeles; un fallo nunca se representa como texto vacío."""
        self._antes_accion()
        try:
            if self.is_windows:
                resultado = self._ejecutar_proceso(
                    ["powershell", "-NoProfile", "-Command",
                     "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
                     "[Console]::Out.Write((Get-Clipboard -Raw))"],
                    capture_output=True, text=True, encoding='utf-8', timeout=5
                )
            else:
                resultado = self._ejecutar_proceso(["pbpaste"], capture_output=True, text=True, timeout=5)
            if resultado.returncode != 0:
                raise PortapapelesNoDisponible("El sistema rechazó la lectura del portapapeles: " + json.dumps({
                    "codigo": resultado.returncode, "stderr": resultado.stderr or ""}, ensure_ascii=False))
            return resultado.stdout
        except pyautogui.FailSafeException:
            raise
        except Exception as e:
            logging.error("Fallo leyendo el portapapeles: %s", json.dumps({
                "tipo": type(e).__name__, "error": str(e)}, ensure_ascii=False))
            raise PortapapelesNoDisponible("No se pudo leer el portapapeles; se conserva el estado anterior: " + str(e)) from e

    def copiar_seleccion(self):
        self._hotkey(self.cmd_key, 'c')
        self.portapapeles_bot['copia_pendiente'] = True
        self._esperar(0.15)
        contenido = self.leer_portapapeles()
        self.portapapeles_bot['ultimo'] = contenido
        self.portapapeles_bot['version'] = clipboard_state.version()
        self.portapapeles_bot.pop('copia_pendiente', None)
        return contenido

    def portapapeles_es_del_bot(self, contenido):
        revision = self.portapapeles_bot.get('version')
        if revision is not None and clipboard_state.version() != revision:
            if self.portapapeles_bot.get('copia_pendiente'):
                raise PortapapelesNoDisponible('Copia interrumpida sin confirmar: no se sobrescribirá el portapapeles actual')
            return False
        if contenido == self.portapapeles_bot['ultimo']:
            return True
        if contenido == self.portapapeles_bot.get('escritura_pendiente'):
            return True
        if self.portapapeles_bot.get('copia_pendiente'):
            raise PortapapelesNoDisponible(
                "Copia interrumpida sin confirmar: no se sobrescribirá el portapapeles actual")
        return False

    # ------------------------------------------------------------
    # Anti-reposo (caffeinate / SetThreadExecutionState)
    # ------------------------------------------------------------

    def mantener_despierto_iniciar(self) -> None:
        """Evita que el sistema entre en reposo; no-op si ya está activo"""
        if self._antidespierto_activo:
            return
        try:
            if self.is_windows:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(
                    0x80000000 | 0x00000001 | 0x00000002  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
                )
            else:
                self._proceso_caffeinate = subprocess.Popen(["caffeinate", "-i", "-d", "-w", str(os.getpid())])
            self._antidespierto_activo = True
            logging.info("Anti-reposo iniciado")
        except Exception as e:
            logging.error(f"Error iniciando anti-reposo: {e}")

    def mantener_despierto_detener(self) -> None:
        """Restaura el comportamiento normal de reposo; no-op si no estaba activo"""
        if not self._antidespierto_activo:
            return
        try:
            if self.is_windows:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)  # ES_CONTINUOUS
            else:
                if self._proceso_caffeinate is not None:
                    self._proceso_caffeinate.terminate()
                    try:
                        self._proceso_caffeinate.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        self._proceso_caffeinate.kill()
                        self._proceso_caffeinate.wait(timeout=1)
                    self._proceso_caffeinate = None
            logging.info("Anti-reposo detenido")
        except Exception as e:
            logging.error(f"Error deteniendo anti-reposo: {e}")
        finally:
            self._antidespierto_activo = False

    # ------------------------------------------------------------
    # Movimiento de cursor
    # ------------------------------------------------------------

    def move_cursor_to_center(self) -> bool:
        """Mueve el cursor al centro de la pantalla y hace clic"""
        x, y = self.screen_width // 2, self.screen_height // 2
        return self._move_cursor(x, y)

    def _move_cursor(self, x: int, y: int, duration: float = 0.5, click: bool = True) -> bool:
        """Mueve el cursor a (x, y) con la duración indicada y, opcionalmente, hace clic"""
        try:
            logging.debug(f"Moviendo el cursor a ({x}, {y})")
            self._move_to(x, y, duration=duration)
            if click:
                self._click()
            return True
        except pyautogui.FailSafeException:
            raise
        except Exception as e:
            logging.error(f"Error al mover el cursor a ({x}, {y}): {e}")
            return False

    def generar_texto_aleatorio(self, longitud: int = 10) -> str:
        """Genera un texto aleatorio de longitud 'longitud'"""
        return "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=longitud))
