import logging
import os
import platform
import random
import subprocess
import time
from typing import Optional

import pyautogui

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class FailsafeActivo(Exception):
    """Excepción para detener el bot cuando pyautogui detecta failsafe"""


class BaseAutomation:
    def __init__(self):
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05

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
        try:
            if self.is_windows:
                return self._activar_aplicacion_windows(nombre_proceso)
            if self.is_mac:
                return self._activar_aplicacion_mac(nombre_mac)
            logging.warning("Sistema operativo no soportado para activar aplicaciones")
            return False
        except Exception as e:
            logging.error(f"Error activando la aplicación '{nombre_proceso or nombre_mac}': {e}")
            return False

    def _activar_aplicacion_mac(self, nombre_mac: str) -> bool:
        """Activa la app en macOS vía System Events, con fallback a 'activate'"""
        try:
            subprocess.run(
                ['osascript', '-e',
                 f'tell application "System Events" to set frontmost of process "{nombre_mac}" to true'],
                check=True,
                capture_output=True
            )
            logging.debug(f"Aplicación activada en macOS (frontmost): {nombre_mac}")
            return True
        except subprocess.CalledProcessError:
            try:
                subprocess.run(
                    ['osascript', '-e', f'tell application "{nombre_mac}" to activate'],
                    check=True,
                    capture_output=True
                )
                logging.debug(f"Aplicación activada en macOS (activate): {nombre_mac}")
                return True
            except subprocess.CalledProcessError as e:
                logging.error(f"Error activando la aplicación en macOS ({nombre_mac}): {e}")
                return False

    def _activar_aplicacion_windows(self, nombre_proceso: str) -> bool:
        """Activa la primera ventana del proceso en Windows vía pygetwindow"""
        try:
            import pygetwindow as gw
            ventanas = gw.getWindowsWithTitle(nombre_proceso)
            if not ventanas:
                logging.warning(f"No se encontraron ventanas para el proceso: {nombre_proceso}")
                return False
            ventanas[0].activate()
            logging.debug(f"Ventana activada en Windows: {nombre_proceso}")
            return True
        except Exception as e:
            logging.error(f"Error activando la ventana en Windows ({nombre_proceso}): {e}")
            return False

    # ------------------------------------------------------------
    # Portapapeles centralizado
    # ------------------------------------------------------------

    def copiar_al_portapapeles(self, texto: str) -> bool:
        """Copia texto al portapapeles con fallback nativo; True si tuvo éxito"""
        try:
            import pyperclip
            pyperclip.copy(texto)
            return True
        except Exception as e:
            logging.warning(f"pyperclip no disponible ({e}); usando fallback del sistema")
            return self._copiar_portapapeles_fallback(texto)

    def _copiar_portapapeles_fallback(self, texto: str) -> bool:
        """Copia al portapapeles usando utilidades nativas (pbcopy/clip)"""
        try:
            if self.is_windows:
                resultado = subprocess.run(["clip"], input=texto, text=True, shell=True)
            else:
                resultado = subprocess.run(["pbcopy"], input=texto, text=True)
            return resultado.returncode == 0
        except Exception as e:
            logging.error(f"Error copiando al portapapeles (fallback): {e}")
            return False

    def leer_portapapeles(self) -> str:
        """Lee el portapapeles con fallback nativo; devuelve '' si no se puede"""
        try:
            import pyperclip
            return pyperclip.paste()
        except Exception as e:
            logging.warning(f"pyperclip no disponible ({e}); usando fallback del sistema")
        try:
            if self.is_windows:
                resultado = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                    capture_output=True, text=True, timeout=5
                )
            else:
                resultado = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
            return resultado.stdout if resultado.returncode == 0 else ""
        except Exception as e:
            logging.error(f"Error leyendo el portapapeles (fallback): {e}")
            return ""

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
                self._proceso_caffeinate = subprocess.Popen(["caffeinate", "-i", "-d"])
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
            pyautogui.moveTo(x, y, duration=duration)
            if click:
                pyautogui.click()
            return True
        except pyautogui.FailSafeException:
            raise
        except Exception as e:
            logging.error(f"Error al mover el cursor a ({x}, {y}): {e}")
            return False

    def generar_texto_aleatorio(self, longitud: int = 10) -> str:
        """Genera un texto aleatorio de longitud 'longitud'"""
        return "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=longitud))
