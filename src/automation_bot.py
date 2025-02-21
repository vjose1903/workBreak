import argparse
import time
import logging
import sys
from typing import Optional

from editor_interactor import EditorInteractor
from web_interactor import WebInteractor
from statistics_tracker import StatisticsTracker

class AutomationBot:
    def __init__(self):
        self.stats_tracker = StatisticsTracker()
        self.editor_interactor = EditorInteractor(self.stats_tracker)
        self.web_interactor = WebInteractor(self.stats_tracker)

    def validar_tiempo(self, value: str) -> Optional[int]:
        """Valida el tiempo proporcionado por el usuario"""
        if value.lower() == 'indefinido':
            return None
        try:
            tiempo = int(value)
            if tiempo <= 0:
                raise argparse.ArgumentTypeError("El tiempo debe ser 'indefinido' o un número positivo")
            return tiempo
        except ValueError:
            raise argparse.ArgumentTypeError("El tiempo debe ser 'indefinido' o un número positivo")

    def configurar_parser(self):
        """Configura el parser de argumentos para la ejecución del bot"""
        parser = argparse.ArgumentParser(description="Bot para descansos en el trabajo")
        parser.add_argument("-editor", type=self.editor_interactor.validar_editor, required=True,
                            help=f"Editor a usar: {', '.join(self.editor_interactor.VALID_EDITORS)}")
        parser.add_argument("-browser", type=self.web_interactor.validar_browser, required=False,
                            help=f"Navegador a usar: {', '.join(self.web_interactor.VALID_BROWSERS)}")
        parser.add_argument("-web", type=str, required=False,
                            help="Lista de webs separadas por coma")
        parser.add_argument("-tiempo", type=self.validar_tiempo, default=None,
                            help="Tiempo total de ejecución en minutos (default: indefinido)")
        return parser

    def gestionar_ejecucion(self, args):
        """Gestiona la ejecución del bot según los parámetros proporcionados"""
        paginas = args.web.split(",") if args.web else []
        self.web_interactor.set_paginas(paginas)
        
        if args.browser:
            self.web_interactor.set_browser(args.browser)
        
        tiempo_inicio = time.time()

        try:
            while True:
                if self.comprobar_tiempo_ejecucion(args.tiempo, tiempo_inicio):
                    break
                
                self.ejecutar_tareas(args.editor, paginas)
                
                time.sleep(1)

        except KeyboardInterrupt:
            logging.info("Programa terminado por el usuario")
        except Exception as e:
            logging.error(f"Error inesperado: {e}")
        finally:
            self.finalizar_ejecucion()

    def comprobar_tiempo_ejecucion(self, tiempo_limite: Optional[int], tiempo_inicio: float) -> bool:
        """Verifica si el tiempo límite de ejecución ha sido alcanzado"""
        if tiempo_limite is None:
            return False
        
        tiempo_transcurrido = (time.time() - tiempo_inicio) / 60
        logging.info(f"Tiempo transcurrido: {tiempo_transcurrido:.1f} minutos")
                    
        if tiempo_transcurrido >= tiempo_limite:
            logging.info(f"Tiempo total de ejecución ({tiempo_limite} minutos) alcanzado")
            return True
        return False

    def ejecutar_tareas(self, editor: str, paginas: list):
        """Ejecuta las tareas principales: abrir el editor, interactuar con él y navegar por la web"""
        self.editor_interactor.abrir_editor(editor)
        self.editor_interactor.interactuar_editor()
        
        if paginas:
            self.web_interactor.interactuar_web()

    def finalizar_ejecucion(self):
        """Muestra las estadísticas y finaliza la ejecución"""
        logging.info("Finalizando ejecución...")
        self.stats_tracker.print_statistics()
        sys.exit(0)

    def ejecutar(self):
        """Configura los argumentos y ejecuta el bot"""
        parser = self.configurar_parser()
        args = parser.parse_args()
        
        self.gestionar_ejecucion(args)


if __name__ == "__main__":
    bot = AutomationBot()
    bot.ejecutar()
