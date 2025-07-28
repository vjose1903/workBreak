import logging
import os
import platform
import pyautogui
import time
import random

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class BaseAutomation:
    def __init__(self):
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.5

        # Determinamos el sistema operativo de manera más eficiente
        self.is_windows = os.name == "nt"
        self.is_mac = platform.system() == 'Darwin'
        
        # Definimos el cmd_key según el sistema operativo
        self.cmd_key = "ctrl" if self.is_windows else "command"

        # Resolución de pantalla
        self.screen_width, self.screen_height = pyautogui.size()

        # Intervalo de tipeo (se puede configurar por defecto)
        self.TYPING_INTERVAL = 0.1

    def move_cursor_to_center(self) -> bool:
        """Mueve el cursor al centro de la pantalla y hace clic"""
        x, y = self.screen_width // 2, self.screen_height // 2
        return self._move_cursor(x, y)

    def _move_cursor(self, x: int, y: int, duration: float = 0.5) -> bool:
        """Mueve el cursor a las coordenadas (x, y) con la duración especificada"""
        try:
            logging.info(f"Moviendo el cursor a ({x}, {y})")
            pyautogui.moveTo(x, y, duration=duration)
            time.sleep(duration)  # Mejor control de tiempo
            pyautogui.click()
            return True
        except Exception as e:
            logging.error(f"Error al mover el cursor a ({x}, {y}): {e}")
            return False

    def generar_texto_aleatorio(self, longitud: int = 10) -> str:
        """Genera un texto aleatorio de longitud 'longitud'"""
        return "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=longitud))

    def obtener_codigo_boilerplate_aleatorio(self) -> str:
        """Obtiene el contenido completo de un archivo de boilerplate de manera aleatoria"""
        try:
            boilerplate_dir = os.path.join(os.path.dirname(__file__), "boilerplate")
            archivos = [f for f in os.listdir(boilerplate_dir) if f.endswith(('.ts', '.tsx', '.js', '.jsx'))]
            
            if not archivos:
                logging.warning("No se encontraron archivos de boilerplate")
                return self.generar_texto_aleatorio()
            
            archivo_seleccionado = random.choice(archivos)
            ruta_archivo = os.path.join(boilerplate_dir, archivo_seleccionado)
            
            logging.info(f"Leyendo archivo de boilerplate: {archivo_seleccionado}")
            
            with open(ruta_archivo, 'r', encoding='utf-8') as f:
                contenido = f.read()
            
            return contenido
            
        except Exception as e:
            logging.error(f"Error al leer archivo de boilerplate: {e}")
            return self.generar_texto_aleatorio()

