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
        self._mac_keyboard = None

    def _teclado_mac(self):
        if self._mac_keyboard is None:
            from mac_keyboard import MacKeyboard
            self._mac_keyboard = MacKeyboard()
        return self._mac_keyboard

    def _hotkey(self, *teclas):
        if self.is_mac:
            self._teclado_mac().hotkey(*teclas)
        else:
            pyautogui.hotkey(*teclas)

    def _press(self, tecla):
        if self.is_mac:
            self._teclado_mac().press(tecla)
        else:
            pyautogui.press(tecla)

    def _write(self, texto, interval=0):
        if self.is_mac:
            self._teclado_mac().write(texto, interval=interval)
        else:
            pyautogui.write(texto, interval=interval)

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
                exito = self._activar_aplicacion_windows(nombre_proceso)
            elif self.is_mac:
                exito = self._activar_aplicacion_mac(nombre_mac)
            else:
                logging.warning("Sistema operativo no soportado para activar aplicaciones")
                return False
        except Exception as e:
            logging.error(f"Error activando la aplicación '{nombre_proceso or nombre_mac}': {e}")
            return False

        return exito

    def _activar_si_necesario(self, nombre_proceso: str, nombre_mac: str) -> bool:
        """Confirma la activación sin confiar en un foco guardado anteriormente."""
        return self.activar_aplicacion(nombre_proceso, nombre_mac)

    def _activar_aplicacion_mac(self, nombre_mac: str) -> bool:
        """Activa la app en macOS vía System Events, con fallback a 'activate'"""
        try:
            subprocess.run(
                ['osascript', '-e',
                 f'set appBundleId to id of application "{nombre_mac}"\n'
                 'tell application "System Events"\n'
                 'set frontmost of (first application process whose bundle identifier is appBundleId) to true\n'
                 'end tell'],
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
