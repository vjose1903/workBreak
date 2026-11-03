import argparse
import logging
import random
import time
from typing import Optional

import pyautogui

from base_automation import FailsafeActivo
from editor_interactor import EditorInteractor, EditorNoDisponible
from menu import (Configuracion, configuracion_desde_args, guardar_configuracion,
                  menu_interactivo)
from web_interactor import WebInteractor
from statistics_tracker import StatisticsTracker
from user_activity import MonitorActividad, PausaPorActividad

class AutomationBot:
    def __init__(self):
        self.stats_tracker = StatisticsTracker()
        self.editor_interactor = EditorInteractor(self.stats_tracker)
        self.web_interactor = WebInteractor(self.stats_tracker)
        self._turno_actual = "editor"

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
        # Compatibilidad con comandos anteriores; el editor siempre es VS Code.
        parser.add_argument("-editor", choices=["vsCode"], help=argparse.SUPPRESS)
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
        self.editor_interactor.fases = config.fases
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

        codigo_salida = 0
        fallos_consecutivos = 0
        ultimo_log = time.monotonic()
        monitor = MonitorActividad()
        self.editor_interactor.monitor_actividad = monitor
        self.web_interactor.monitor_actividad = monitor
        self.web_interactor.portapapeles_bot = self.editor_interactor.portapapeles_bot
        recuperar_editor = False
        recuperar_portapapeles = False

        try:
            monitor.iniciar()
            self.editor_interactor.mantener_despierto_iniciar()
            while self._tiempo_restante() > 0:
                try:
                    monitor.comprobar()
                    if recuperar_portapapeles:
                        self.editor_interactor.conservar_portapapeles_usuario()
                        recuperar_portapapeles = False
                    if recuperar_editor and self._turno_actual == "editor":
                        if self.editor_interactor.EDITOR_ABIERTO:
                            cmd = self.editor_interactor._comando_abrir_editor(
                                config.editor, self.editor_interactor.ruta_archivo)
                            if not self.editor_interactor.ejecutar_comando(cmd):
                                raise EditorNoDisponible("No se pudo recuperar el archivo del bot tras la pausa")
                            self.editor_interactor._esperar(0.3)
                        recuperar_editor = False
                    self.ejecutar_tareas(config.editor, paginas)
                    fallos_consecutivos = 0
                except PausaPorActividad:
                    self.editor_interactor.necesita_reposicionar = True
                    recuperar_editor = True
                    recuperar_portapapeles = True
                    logging.info("Actividad del usuario: bot pausado hasta completar 10 segundos de inactividad")
                    limite = self.editor_interactor._tiempo_limite_absoluto
                    if not monitor.esperar_inactividad(limite=limite):
                        logging.info("Tiempo total agotado durante la pausa; finalizando bot")
                        break
                    logging.info("Diez segundos sin actividad del usuario; reanudando bot")
                    continue
                except (pyautogui.FailSafeException, FailsafeActivo):
                    logging.warning("Failsafe activado (mouse en esquina); deteniendo el bot")
                    codigo_salida = 2
                    break
                except EditorNoDisponible as e:
                    logging.error(str(e))
                    codigo_salida = 1
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
        except Exception as e:
            logging.error(f"No se pudo continuar la ejecución: {e}")
            codigo_salida = 1
        finally:
            try:
                self.editor_interactor.mantener_despierto_detener()
            except Exception as e:
                logging.error(f"Error deteniendo anti-reposo: {e}")
            try:
                self.editor_interactor.restaurar_portapapeles()
            except PausaPorActividad:
                pass  # No reemplazar el portapapeles mientras el usuario utiliza el equipo.
            except Exception as e:
                logging.error(f"Error restaurando el portapapeles: {e}")
            monitor.detener()
            self.editor_interactor.monitor_actividad = None
            self.web_interactor.monitor_actividad = None
            codigo_salida = self._imprimir_y_cerrar(codigo_salida)

        return codigo_salida

    def _imprimir_y_cerrar(self, codigo_salida: int) -> int:
        """Imprime las estadísticas finales y devuelve el código de salida"""
        logging.info("Finalizando ejecución...")
        self.stats_tracker.print_statistics()
        return codigo_salida

    def ejecutar_tareas(self, editor: str, paginas: list):
        """Ejecuta las tareas principales: asegurar el editor y alternar editor/navegador.

        Si hay webs configuradas, las fases del editor y del navegador se alternan en
        turnos acotados para que ambas arranquen apenas su aplicación está abierta,
        en lugar de esperar a que termine toda la fase del editor.
        """
        if self._turno_actual == "editor":
            self.editor_interactor.asegurar_editor_abierto(editor)
            if paginas:
                self.editor_interactor.interactuar_editor(duracion_maxima=random.uniform(30, 90))
                self._turno_actual = "web"
            else:
                self.editor_interactor.interactuar_editor()
        if paginas and self._turno_actual == "web":
            self.web_interactor.interactuar_web(duracion_maxima=random.uniform(30, 60))
            self._turno_actual = "editor"

    def ejecutar(self) -> int:
        """Usa los argumentos proporcionados o muestra el menú interactivo."""
        parser = self.configurar_parser()
        args = parser.parse_args()

        if args.editor or args.browser or args.web is not None or args.tiempo is not None:
            config = configuracion_desde_args(args)
        else:
            config = menu_interactivo()

        if config is None:
            logging.info("Salida por menú; el bot no se ejecutó")
            return 0

        guardar_configuracion(config)
        return self.gestionar_ejecucion(config)
