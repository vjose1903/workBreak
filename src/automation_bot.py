import argparse
import logging
import time
from typing import Optional

import pyautogui

from base_automation import FailsafeActivo
from editor_interactor import EditorInteractor
from menu import Configuracion, configuracion_desde_args, menu_interactivo
from web_interactor import WebInteractor
from statistics_tracker import StatisticsTracker

class AutomationBot:
    def __init__(self):
        self.stats_tracker = StatisticsTracker()
        self.editor_interactor = EditorInteractor(self.stats_tracker)
        self.web_interactor = WebInteractor(self.stats_tracker)

    def validar_tiempo(self, value: str) -> Optional[int]:
        """Valida el tiempo proporcionado por el usuario (minutos positivos o 'indefinido')"""
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
        parser.add_argument("-editor", type=self.editor_interactor.validar_editor, required=False,
                            help=f"Editor a usar: {', '.join(self.editor_interactor.VALID_EDITORS)} "
                                 f"(si no se pasa, se muestra el menú interactivo)")
        parser.add_argument("-browser", type=self.web_interactor.validar_browser, required=False,
                            help=f"Navegador a usar: {', '.join(self.web_interactor.VALID_BROWSERS)}")
        parser.add_argument("-web", type=str, required=False,
                            help="Lista de webs separadas por coma")
        parser.add_argument("-tiempo", type=self.validar_tiempo, default=None,
                            help="Tiempo total de ejecución en minutos (default: indefinido)")
        return parser

    def _tiempo_restante(self) -> float:
        """Segundos restantes de ejecución (infinito si no hay límite); usa time.monotonic()"""
        restante = self.editor_interactor.tiempo_restante()
        if restante is None:
            return float("inf")
        return restante

    def gestionar_ejecucion(self, config: Configuracion) -> int:
        """Gestiona la ejecución del bot con resiliencia; devuelve el código de salida"""
        if config.fuente:
            self.editor_interactor.fuente_codigo = config.fuente

        paginas = list(config.paginas)
        self.web_interactor.set_paginas(paginas)

        if config.browser:
            self.web_interactor.set_browser(config.browser)

        if config.tiempo:
            segundos_limite = config.tiempo * 60
            self.editor_interactor.set_limite_tiempo(segundos_limite)
            self.web_interactor.set_limite_tiempo(segundos_limite)

        self.editor_interactor.mantener_despierto_iniciar()

        codigo_salida = 0
        fallos_consecutivos = 0
        ultimo_log = time.monotonic()

        try:
            while self._tiempo_restante() > 0:
                try:
                    self.ejecutar_tareas(config.editor, paginas)
                    fallos_consecutivos = 0
                except (pyautogui.FailSafeException, FailsafeActivo):
                    logging.warning("Failsafe activado (mouse en esquina); deteniendo el bot")
                    codigo_salida = 2
                    break
                except KeyboardInterrupt:
                    logging.info("Programa terminado por el usuario (Ctrl+C)")
                    codigo_salida = 130
                    break
                except Exception:
                    fallos_consecutivos += 1
                    logging.error(
                        f"Error inesperado en iteración ({fallos_consecutivos} fallos consecutivos)",
                        exc_info=True,
                    )
                    if fallos_consecutivos >= 5:
                        logging.error("Demasiados fallos consecutivos (5); abortando ejecución")
                        codigo_salida = 1
                        break
                    time.sleep(min(60, 2 ** fallos_consecutivos))

                if time.monotonic() - ultimo_log >= 300:
                    restante = self._tiempo_restante()
                    resto_str = f"{restante / 60:.1f} minutos" if restante != float("inf") else "indefinido"
                    logging.info(f"Bot activo; tiempo restante: {resto_str}")
                    ultimo_log = time.monotonic()
        except KeyboardInterrupt:
            logging.info("Programa terminado por el usuario (Ctrl+C)")
            codigo_salida = 130
        finally:
            try:
                self.editor_interactor.mantener_despierto_detener()
            except Exception as e:
                logging.error(f"Error deteniendo anti-reposo: {e}")
            try:
                self.editor_interactor.restaurar_portapapeles()
            except Exception as e:
                logging.error(f"Error restaurando el portapapeles: {e}")
            codigo_salida = self._imprimir_y_cerrar(codigo_salida)

        return codigo_salida

    def _imprimir_y_cerrar(self, codigo_salida: int) -> int:
        """Imprime las estadísticas finales y devuelve el código de salida"""
        logging.info("Finalizando ejecución...")
        self.stats_tracker.print_statistics()
        return codigo_salida

    def ejecutar_tareas(self, editor: str, paginas: list):
        """Ejecuta las tareas principales: asegurar editor, interactuar y navegar por la web"""
        self.editor_interactor.asegurar_editor_abierto(editor)
        self.editor_interactor.interactuar_editor()

        if paginas:
            self.web_interactor.interactuar_web()

    def ejecutar(self) -> int:
        """Si se pasa el editor por CLI usa la configuración de args; si no, muestra el menú interactivo"""
        parser = self.configurar_parser()
        args = parser.parse_args()

        if args.editor:
            config = configuracion_desde_args(args)
        else:
            config = menu_interactivo()

        if config is None:
            logging.info("Salida por menú; el bot no se ejecutó")
            return 0

        return self.gestionar_ejecucion(config)
