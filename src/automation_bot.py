import argparse
from timing_config import temporizacion_config
import logging
import random
import time
from typing import Optional

import pyautogui

from base_automation import FailsafeActivo, TiempoAgotado
from editor_interactor import EditorInteractor, EditorNoDisponible
from editor_catalog import EDITORES
from menu import (Configuracion, configuracion_desde_args, guardar_configuracion,
                  menu_interactivo, MODOS_INTERACCION, tiempo_valido, _config_a_dict, validar_acciones_ejecucion)
from web_interactor import WebInteractor
from statistics_tracker import StatisticsTracker
from user_activity import MonitorActividad, PausaPorActividad, DetencionSolicitada
from session_lock import bloquear_sesion, SesionEnCurso

class AutomationBot:
    def __init__(self, solicitar_detencion=None, informar_estado=None):
        self.stats_tracker = StatisticsTracker()
        self.editor_interactor = EditorInteractor(self.stats_tracker)
        self.web_interactor = WebInteractor(self.stats_tracker)
        self.temporizacion = temporizacion_config()
        self._modo = "ambos"
        self._turno_actual = "editor"
        self.solicitar_detencion = solicitar_detencion
        self.informar_estado = informar_estado
        self.editor_interactor.informar_estado = informar_estado

    def _notificar_estado(self, estado, **datos):
        if getattr(self, 'informar_estado', None):
            self.informar_estado(estado, **datos)

    def validar_tiempo(self, value: str) -> Optional[int]:
        """Valida el tiempo proporcionado por el usuario (minutos positivos o 'indefinido')"""
        if value.lower() == 'indefinido':
            return None
        try:
            tiempo = int(value)
            if not tiempo_valido(tiempo):
                raise argparse.ArgumentTypeError("El tiempo debe ser 'indefinido' o un número positivo")
            return tiempo
        except ValueError:
            raise argparse.ArgumentTypeError("El tiempo debe ser 'indefinido' o un número positivo")

    def configurar_parser(self):
        """Configura el parser de argumentos para la ejecución del bot"""
        parser = argparse.ArgumentParser(description="Bot para descansos en el trabajo")
        parser.add_argument("-editor", choices=list(EDITORES), help="Editor compatible a utilizar")
        parser.add_argument("-browser", type=self.web_interactor.validar_browser, required=False,
                            help=f"Navegador a usar: {', '.join(self.web_interactor.VALID_BROWSERS)}")
        parser.add_argument("-web", type=str, required=False,
                            help="Lista de webs separadas por coma")
        parser.add_argument("-tiempo", type=self.validar_tiempo, default=None,
                            help="Tiempo total de ejecución en minutos (default: indefinido)")
        parser.add_argument("--modo", choices=list(MODOS_INTERACCION), default="ambos",
                            help="Interacción: ambos, editor o web")
        return parser

    def _tiempo_restante(self) -> float:
        """Segundos restantes de ejecución (infinito si no hay límite); usa time.monotonic()"""
        restante = self.editor_interactor.tiempo_restante()
        if restante is None:
            return float("inf")
        return restante

    def gestionar_ejecucion(self, config: Configuracion) -> int:
        try:
            with bloquear_sesion():
                return self._gestionar_ejecucion(config)
        except SesionEnCurso as error:
            logging.error(str(error))
            return 1

    def _gestionar_ejecucion(self, config: Configuracion) -> int:
        """Gestiona la ejecución del bot con resiliencia; devuelve el código de salida"""
        editor_activo, web_activa = validar_acciones_ejecucion(_config_a_dict(config))
        guardar_configuracion(config)
        self.temporizacion = temporizacion_config(config.temporizacion)
        self.editor_interactor.rango_duracion = self.temporizacion['editor']
        self.editor_interactor.temporizacion = temporizacion_config(self.temporizacion)
        self.web_interactor.temporizacion = temporizacion_config(self.temporizacion)
        self._modo = config.modo if editor_activo and web_activa else ('editor' if editor_activo else 'web')
        self._turno_actual = "web" if self._modo == "web" else "editor"
        self.editor_interactor.atajo_ir_linea = None  # Cada inicio vuelve a consultar; las pausas no.
        self.editor_interactor.acciones = dict(config.acciones_editor)
        self.web_interactor.acciones = dict(config.acciones_web)
        self.editor_interactor.fases = config.fases
        if config.fuente:
            self.editor_interactor.fuente_codigo = config.fuente

        paginas = list(config.paginas) if web_activa else []
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
        monitor = MonitorActividad(
            debounce=self.temporizacion['debounce'],
            solicitar_detencion=self.solicitar_detencion,
            informar_pausa=lambda segundos, pulsada: self._notificar_estado(
                'pausado', segundos=segundos, pulsada=pulsada))
        monitor.comprobar_emergencia = pyautogui.failSafeCheck
        self.editor_interactor.monitor_actividad = monitor
        self.web_interactor.monitor_actividad = monitor
        self.web_interactor.portapapeles_bot = self.editor_interactor.portapapeles_bot
        recuperar_editor = False
        recuperar_portapapeles = False
        reintentar_desde = 0

        try:
            self._notificar_estado('iniciando')
            monitor.iniciar()
            self.editor_interactor.mantener_despierto_iniciar()
            self._notificar_estado('ejecutando', fase=self._turno_actual)
            while self._tiempo_restante() > 0:
                try:
                    self.editor_interactor._antes_accion()
                    if time.monotonic() < reintentar_desde:
                        self.editor_interactor._esperar(max(0, min(0.1, reintentar_desde - time.monotonic())))
                        continue
                    if recuperar_portapapeles:
                        self.editor_interactor.conservar_portapapeles_usuario()
                        recuperar_portapapeles = False
                    self.editor_interactor.guardar_portapapeles_original()
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
                    self.web_interactor.invalidar_pestana()
                    self.editor_interactor.necesita_reposicionar = True
                    recuperar_editor = True
                    recuperar_portapapeles = True
                    logging.info("Actividad del usuario: bot pausado hasta completar %g segundos de inactividad", monitor.debounce)
                    limite = self.editor_interactor._tiempo_limite_absoluto
                    if not monitor.esperar_inactividad(limite=limite):
                        logging.info("Tiempo total agotado durante la pausa; finalizando bot")
                        break
                    logging.info("%g segundos sin actividad del usuario; reanudando bot", monitor.debounce)
                    self._notificar_estado('ejecutando', fase=self._turno_actual)
                    continue
                except TiempoAgotado:
                    logging.info("Tiempo total agotado; finalizando bot")
                    break
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
                    reintentar_desde = time.monotonic() + min(60, 2 ** fallos_consecutivos)

                if time.monotonic() - ultimo_log >= 300:
                    restante = self._tiempo_restante()
                    resto_str = f"{restante / 60:.1f} minutos" if restante != float("inf") else "indefinido"
                    logging.info(f"Bot activo; tiempo restante: {resto_str}")
                    ultimo_log = time.monotonic()
        except DetencionSolicitada:
            logging.info("Detención solicitada desde la interfaz; finalizando sesión")
        except TiempoAgotado:
            logging.info("Tiempo total agotado; finalizando bot")
        except (pyautogui.FailSafeException, FailsafeActivo):
            logging.warning("Parada de emergencia durante la pausa; deteniendo bot")
            codigo_salida = 2
        except KeyboardInterrupt:
            logging.info("Programa terminado por el usuario (Ctrl+C)")
            codigo_salida = 130
        except Exception as e:
            logging.error(f"No se pudo continuar la ejecución: {e}")
            codigo_salida = 1
        finally:
            monitor.permitir_limpieza = True
            self.editor_interactor._limpiando = True
            self.web_interactor._limpiando = True
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
                if codigo_salida == 0:
                    codigo_salida = 1
            monitor.detener()
            self.editor_interactor.monitor_actividad = None
            self.web_interactor.monitor_actividad = None
            self.editor_interactor._limpiando = False
            self.web_interactor._limpiando = False
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
        if self._modo == "web":
            self._notificar_estado("ejecutando", fase="navegador")
            self.web_interactor.interactuar_web(duracion_maxima=random.uniform(*self.temporizacion['navegador']))
            return
        if self._turno_actual == "editor":
            self.editor_interactor.asegurar_editor_abierto(editor)
            if paginas:
                self.editor_interactor.interactuar_editor(duracion_maxima=random.uniform(*self.temporizacion['editor_alternado']))
                self._turno_actual = "web"
            else:
                self.editor_interactor.interactuar_editor()
        if paginas and self._turno_actual == "web":
            self._notificar_estado('ejecutando', fase='navegador')
            self.web_interactor.interactuar_web(duracion_maxima=random.uniform(*self.temporizacion['navegador']))
            self._turno_actual = "editor"

    def ejecutar(self, argv=None) -> int:
        """Usa los argumentos proporcionados o muestra el menú interactivo."""
        parser = self.configurar_parser()
        args = parser.parse_args(argv)

        if argv or args.editor or args.browser or args.web is not None or args.tiempo is not None or args.modo != "ambos":
            config = configuracion_desde_args(args)
        else:
            config = menu_interactivo()

        if config is None:
            logging.info("Salida por menú; el bot no se ejecutó")
            return 0

        return self.gestionar_ejecucion(config)
