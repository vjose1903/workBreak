import logging
import pyautogui
import subprocess
import sys
import time
import random
from base_automation import BaseAutomation
from statistics_tracker import StatisticsTracker

class EditorInteractor(BaseAutomation):
    def __init__(self, stats_tracker: StatisticsTracker):
        super().__init__()
        
        self.stats_tracker = stats_tracker
        self.VALID_EDITORS = ["cursor", "vsCode"]
        self.EDITOR_STARTUP_TIME = 5
        self.NUEVA_PAGINA_EDITOR_ABIERTA = False
        self.EDITOR_WINDOW_OFFSET = 20
        self.editor_commands = {
            "vsCode": ["code"],
            "cursor": ["cursor"] if self.is_windows else ["/Applications/Cursor.app/Contents/MacOS/Cursor"]
        }

    def validar_editor(self, value: str) -> str:
        """Valida que el editor esté en la lista de editores válidos"""
        if value not in self.VALID_EDITORS:
            raise ValueError(f"El editor debe ser uno de {self.VALID_EDITORS}")
        return value

    def ejecutar_comando(self, cmd: list) -> None:
        """Ejecuta el comando para abrir el editor"""
        logging.info(f"Ejecutando comando: {cmd}")
        subprocess.Popen(cmd, shell=self.is_windows)

    def abrir_editor(self, editor: str) -> None:
        """Abre el editor, asegurándose de que la ventana esté lista"""
        try:
            cmd = self.editor_commands[editor]
            self.ejecutar_comando(cmd)
            logging.info(f"Abriendo editor: {editor}")
            time.sleep(self.EDITOR_STARTUP_TIME)

            self.move_cursor_to_center()

            if not self.NUEVA_PAGINA_EDITOR_ABIERTA:
                pyautogui.hotkey(self.cmd_key, 'n')
                logging.info("Nueva página abierta en el editor")
            
            self.NUEVA_PAGINA_EDITOR_ABIERTA = True
            time.sleep(1)
                
        except Exception as e:
            self.manejar_error(f"Error al abrir el editor: {e}")

    def manejar_error(self, mensaje: str) -> None:
        """Manejo de errores comunes en el proceso de automatización"""
        logging.error(mensaje)
        sys.exit(1)

    def interactuar_editor(self) -> None:
        """Simula la interacción con el editor escribiendo texto y moviendo el mouse"""
        duracion = random.uniform(1*60, 4*60)  # ENTRE 1 Y 4 MINUTOS
        tiempo_final = time.time() + duracion
        tiempo_inicio = time.time()
        
        logging.info(f"Iniciando interacción con editor por {duracion / 60:.1f} minutos")
        
        try:
            while time.time() < tiempo_final:
                self.realizar_interacciones()
                time.sleep(random.uniform(0.5, 1.5))

            # Registrar tiempo total de interacción
            self.registrar_tiempo_interaccion(tiempo_inicio)
                
        except pyautogui.FailSafeException:
            logging.warning("Failsafe activado - mouse en esquina superior izquierda")
            self.registrar_tiempo_interaccion(tiempo_inicio)
        except Exception as e:
            logging.error(f"Error durante la interacción con el editor: {e}")
            self.registrar_tiempo_interaccion(tiempo_inicio)

    def realizar_interacciones(self) -> None:
        """Simula una interacción típica: escribir, seleccionar, borrar y mover el mouse"""
        texto = self.generar_texto_aleatorio()
        pyautogui.write(texto, interval=self.TYPING_INTERVAL)
        pyautogui.hotkey(self.cmd_key, 'a')
        pyautogui.press('backspace')

        x = random.randint(-self.EDITOR_WINDOW_OFFSET, self.EDITOR_WINDOW_OFFSET)
        y = random.randint(-self.EDITOR_WINDOW_OFFSET, self.EDITOR_WINDOW_OFFSET)
        pyautogui.moveRel(x, y, duration=0.3)
        pyautogui.click()

    def registrar_tiempo_interaccion(self, tiempo_inicio: float) -> None:
        """Registra el tiempo de interacción con el editor"""
        tiempo_real = time.time() - tiempo_inicio
        self.stats_tracker.register_editor_session(tiempo_real)
        logging.info(f"Interacción con editor finalizada, duración real: {tiempo_real / 60:.1f} minutos")
