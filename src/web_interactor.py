import logging
import pyautogui
import subprocess
import time
import random
from typing import Optional
from base_automation import BaseAutomation, FailsafeActivo
from statistics_tracker import StatisticsTracker


class WebInteractor(BaseAutomation):
    def __init__(self, stats_tracker: StatisticsTracker):
        super().__init__()

        self.stats_tracker = stats_tracker
        self.VALID_BROWSERS = ["chrome", "edge", "opera", "firefox"]
        self.paginas = []
        self.browser = None
        self.browser_abierto = False

        # Configuración de navegadores y comandos
        self.browser_configs = {
            'chrome': {'win': 'chrome.exe', 'mac': 'Google Chrome', 'cmd': ['open', '-a', 'Google Chrome']},
            'firefox': {'win': 'firefox.exe', 'mac': 'Firefox', 'cmd': ['open', '-a', 'Firefox']},
            'edge': {'win': 'msedge.exe', 'mac': 'Microsoft Edge', 'cmd': ['open', '-a', 'Microsoft Edge']},
            'opera': {'win': 'opera.exe', 'mac': 'Opera', 'cmd': ['open', '-a', 'Opera']}
        }

    def validar_browser(self, value: str) -> str:
        """Valida que el navegador esté en la lista de navegadores permitidos"""
        if value not in self.VALID_BROWSERS:
            raise ValueError(f"El navegador debe ser uno de {self.VALID_BROWSERS}")
        return value

    def set_browser(self, browser: str) -> None:
        """Establece el navegador para interactuar"""
        self.browser = self.validar_browser(browser)

    def set_paginas(self, paginas: list) -> None:
        """Establece las páginas a las que navegar (descartando entradas vacías)"""
        self.paginas = [p.strip() for p in paginas if p and p.strip()]

    def activar_navegador(self) -> bool:
        """Activa el navegador de forma NO destructiva.

        Activa la ventana existente con `activar_aplicacion`; si el navegador
        no está abierto, lo lanza UNA sola vez. Nunca mata procesos existentes.
        """
        if not self.browser:
            logging.warning("No hay navegador configurado")
            return False

        config = self.browser_configs.get(self.browser)
        if not config:
            logging.error(f"Navegador no soportado: {self.browser}")
            return False

        try:
            if self.activar_aplicacion(config['win'], config['mac']):
                return True

            if not self.browser_abierto:
                self._lanzar_navegador(config)
                self.browser_abierto = True
                return True

            logging.warning(f"Navegador {self.browser} no disponible y ya se intentó lanzar antes")
            return False
        except Exception as e:
            logging.error(f"Error activando navegador {self.browser}: {e}", exc_info=True)
            return False

    def _lanzar_navegador(self, config) -> None:
        """Lanza el navegador la primera vez que no está abierto (sin matar nada)"""
        if self.is_mac:
            subprocess.run(config['cmd'], check=True)
            logging.info(f"Navegador {self.browser} lanzado (macOS)")
        elif self.is_windows:
            subprocess.Popen(config['win'], shell=True)
            logging.info(f"Navegador {self.browser} lanzado (Windows)")
        time.sleep(1)

    def interactuar_web(self, duracion_maxima: Optional[float] = None) -> None:
        """Navega por las páginas y las interactúa.

        `duracion_maxima` limita el turno actual (usado al alternar con el editor).
        """
        if not self.paginas:
            logging.warning("No hay páginas para interactuar")
            return

        if not self.browser:
            logging.warning("No hay navegador configurado")
            return

        inicio = time.monotonic()
        for pagina in self.paginas:
            if duracion_maxima is not None and time.monotonic() - inicio >= duracion_maxima:
                break
            self._procesar_pagina(pagina)

    def _procesar_pagina(self, pagina) -> None:
        """Abre, interactúa y cierra una página con try/except/finally por página.

        Una página que falle no deja pestañas basura y no detiene el bot.
        """
        pagina_abierta = False
        try:
            if not self.activar_navegador():
                logging.error(f"No se pudo activar el navegador para {pagina}")
                return

            self.move_cursor_to_center()  # Asegura foco

            pyautogui.hotkey(self.cmd_key, 't')  # Pestaña nueva
            time.sleep(0.4)

            if not self.copiar_al_portapapeles(pagina):
                logging.error(f"No se pudo copiar la URL de {pagina}, se omite")
                return

            pyautogui.hotkey(self.cmd_key, 'v')
            pyautogui.press('return')
            pagina_abierta = True
            logging.info(f"Navegando a {pagina}")
            time.sleep(2)  # Deja cargar la página

            self.interactuar_con_pagina(pagina)
        except FailsafeActivo:
            raise
        except Exception as e:
            logging.error(f"Error procesando página {pagina}: {e}", exc_info=True)
        finally:
            if pagina_abierta:
                try:
                    pyautogui.hotkey(self.cmd_key, 'w')
                    logging.info(f"Cerrando pestaña de: {pagina}")
                except Exception:
                    logging.debug(f"No se pudo cerrar la pestaña de {pagina}", exc_info=True)

    def interactuar_con_pagina(self, pagina):
        """Interactúa con una página abierta en el navegador"""
        duracion = random.uniform(10, 20)
        restante = self.tiempo_restante()
        if restante is not None:
            duracion = min(duracion, restante)
        tiempo_final = time.monotonic() + duracion
        tiempo_inicio = time.monotonic()
        logging.info(f"Interactuando con {pagina} por {duracion:.1f} segundos")

        try:
            center_x = self.screen_width // 2
            center_y = self.screen_height // 2
            pyautogui.moveTo(center_x, center_y, duration=0.3)
            pyautogui.click()

            while self._queda_tiempo(tiempo_final):
                # Clicks aleatorios dentro del radio
                x_offset = random.randint(-30, 30)
                y_offset = random.randint(-30, 30)
                target_x = center_x + x_offset
                target_y = center_y + y_offset

                pyautogui.moveTo(target_x, target_y, duration=0.5)
                pyautogui.click()

                # Scroll aleatorio
                pyautogui.scroll(random.randint(-300, 300))
                time.sleep(random.uniform(1, 3))

            self.registrar_tiempo_interaccion(pagina, tiempo_inicio)
        except pyautogui.FailSafeException:
            logging.warning("Failsafe activado durante la navegación")
            raise FailsafeActivo("Failsafe activado durante la interacción web")
        except Exception as e:
            logging.error(f"Error interactuando con página {pagina}: {e}", exc_info=True)
            self.registrar_tiempo_interaccion(pagina, tiempo_inicio)

    def _queda_tiempo(self, tiempo_final) -> bool:
        """Indica si queda tiempo (duración de la página y límite global)"""
        if time.monotonic() >= tiempo_final:
            return False
        restante = self.tiempo_restante()
        if restante is not None and restante <= 0:
            return False
        return True

    def registrar_tiempo_interaccion(self, pagina, tiempo_inicio):
        """Registra el tiempo de interacción con una página (con time.monotonic)"""
        tiempo_real = time.monotonic() - tiempo_inicio
        self.stats_tracker.register_web_session(pagina, tiempo_real)
        logging.info(f"Interacción con {pagina} finalizada, duración real: {tiempo_real:.1f} segundos")
