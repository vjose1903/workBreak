import logging
import pyautogui
import subprocess
import time
import random
from base_automation import BaseAutomation
from statistics_tracker import StatisticsTracker

class WebInteractor(BaseAutomation):
    def __init__(self, stats_tracker: StatisticsTracker):
        super().__init__()
        
        self.stats_tracker = stats_tracker
        self.VALID_BROWSERS = ["chrome", "edge", "opera", "firefox"]
        self.paginas = []
        self.browser = None

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
        """Establece las páginas a las que navegar"""
        self.paginas = paginas

    def activar_navegador(self):
        """Intenta activar el navegador (macOS y Windows)"""
        if not self.browser:
            return

        config = self.browser_configs.get(self.browser)
        if not config:
            logging.error(f"Navegador no soportado: {self.browser}")
            return

        try:
            if self.is_windows:
                self.activar_navegador_windows(config['win'])
            elif self.is_mac:
                self.activar_navegador_mac(config['mac'], config['cmd'])

        except Exception as e:
            logging.error(f"Error activando navegador {self.browser}: {e}")

    def activar_navegador_windows(self, process_name: str):
        """Activa el navegador en Windows por su proceso"""
        try:
            subprocess.Popen(["taskkill", "/IM", process_name], shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            time.sleep(1)
            subprocess.Popen([process_name], shell=True)
            logging.info(f"Navegador {self.browser} activado (Windows, por proceso)")
            time.sleep(2)
        except Exception as e:
            logging.error(f"Error activando navegador (Windows): {e}")

    def activar_navegador_mac(self, browser_app: str, cmd: list):
        """Activa el navegador en macOS por aplicación"""
        try:
            subprocess.run(['osascript', '-e', f'tell application "{browser_app}" to activate'], check=True)
            logging.info(f"Navegador {self.browser} activado (macOS)")
            time.sleep(1)
        except subprocess.CalledProcessError as e:
            logging.error(f"Error activando navegador (macOS): {e}")

    def interactuar_web(self) -> None:
        """Navega por las páginas y las interactúa"""
        if not self.paginas:
            logging.warning("No hay páginas para interactuar")
            return

        try:
            for pagina in self.paginas:
                self.activar_navegador()  # Asegura que el navegador esté al frente
                self.move_cursor_to_center()  # Mover al centro de la pantalla

                pyautogui.hotkey(self.cmd_key, 't')
                time.sleep(1)
                
                pyautogui.write(pagina)
                pyautogui.press('return')
                logging.info(f"Navegando a {pagina}")
                time.sleep(3)
                
                self.interactuar_con_pagina(pagina)
                
                pyautogui.hotkey(self.cmd_key, 'w')
                logging.info(f"Cerrando pestaña de: {pagina}")
        except Exception as e:
            logging.error(f"Error durante la interacción web: {e}")

    def interactuar_con_pagina(self, pagina):
        """Interactúa con una página abierta en el navegador"""
        duracion = random.uniform(10, 20)
        tiempo_final = time.time() + duracion
        tiempo_inicio = time.time()
        logging.info(f"Interactuando con {pagina} por {duracion:.1f} segundos")

        try:
            center_x = self.screen_width // 2
            center_y = self.screen_height // 2
            pyautogui.moveTo(center_x, center_y, duration=0.3)
            pyautogui.click()

            while time.time() < tiempo_final:
                # Realizar clicks aleatorios dentro del radio
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
            self.registrar_tiempo_interaccion(pagina, tiempo_inicio)
        except Exception as e:
            logging.error(f"Error interactuando con página {pagina}: {e}")
            self.registrar_tiempo_interaccion(pagina, tiempo_inicio)

    def registrar_tiempo_interaccion(self, pagina, tiempo_inicio):
        """Registra el tiempo de interacción con una página"""
        tiempo_real = time.time() - tiempo_inicio
        self.stats_tracker.register_web_session(pagina, tiempo_real)
        logging.info(f"Interacción con {pagina} finalizada, duración real: {tiempo_real:.1f} segundos")
