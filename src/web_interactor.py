import logging
import pyautogui
import subprocess
import time
import random
from typing import Optional
from base_automation import BaseAutomation, FailsafeActivo
from statistics_tracker import StatisticsTracker
from user_activity import PausaPorActividad


class WebInteractor(BaseAutomation):
    def __init__(self, stats_tracker: StatisticsTracker):
        super().__init__()

        self.stats_tracker = stats_tracker
        self.VALID_BROWSERS = ["chrome", "edge", "opera", "firefox"]
        self.paginas = []
        self.browser = None
        self.browser_abierto = False
        self._indice_pagina = 0
        self._turno_restante = None
        self._visita_restante = None
        self._contexto = None

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
                limite = time.monotonic() + 5
                while self._queda_tiempo(limite):
                    if self.activar_aplicacion(config['win'], config['mac']):
                        return True
                    self._esperar(0.2)

            logging.warning(f"Navegador {self.browser} no disponible y ya se intentó lanzar antes")
            return False
        except pyautogui.FailSafeException:
            raise
        except Exception as e:
            logging.error(f"Error activando navegador {self.browser}: {e}", exc_info=True)
            return False

    def _lanzar_navegador(self, config) -> None:
        """Lanza el navegador la primera vez que no está abierto (sin matar nada)"""
        self._antes_accion()
        if self.is_mac:
            self._ejecutar_proceso(config['cmd'][:1] + ['-g'] + config['cmd'][1:], check=True)
            logging.info(f"Navegador {self.browser} lanzado (macOS)")
        elif self.is_windows:
            subprocess.Popen(config['win'], shell=True)
            logging.info(f"Navegador {self.browser} lanzado (Windows)")
        self._esperar(1)

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

        duracion = self._turno_restante if self._turno_restante is not None else duracion_maxima
        tiempo_final = time.monotonic() + duracion if duracion is not None else float("inf")
        try:
            while self._indice_pagina < len(self.paginas) and self._queda_tiempo(tiempo_final):
                if self._procesar_pagina(self.paginas[self._indice_pagina], tiempo_final) is False:
                    break
                self._indice_pagina += 1
        except PausaPorActividad:
            self._turno_restante = max(0, tiempo_final - time.monotonic())
            raise
        if self._indice_pagina >= len(self.paginas):
            self._indice_pagina = 0
        self._turno_restante = None

    def _leer_url_actual(self):
        marcador = "workbreak:sin-url"
        if not self.copiar_al_portapapeles(marcador):
            raise RuntimeError("No se pudo comprobar la pestaña del navegador")
        self._hotkey(self.cmd_key, 'l')
        actual = self.copiar_seleccion()
        self._press('esc')
        if not actual or actual == marcador:
            raise RuntimeError("No se pudo leer la dirección de la pestaña")
        return actual

    def _procesar_pagina(self, pagina, tiempo_final=float("inf")) -> Optional[bool]:
        """Conserva la visita en una pausa y nunca cierra una pestaña intervenida."""
        if self._contexto is None:
            self._contexto = {'abierta': False, 'navegada': False, 'intervenida': False,
                              'pagina': pagina, 'url': pagina}
        contexto = self._contexto
        if contexto['intervenida']:
            # La URL no identifica una pestaña: no reutilizar ninguna tras una pausa.
            logging.info("Pausa web: se conserva la pestaña anterior y se continúa en una nueva")
            contexto = {'abierta': False, 'navegada': False, 'intervenida': False,
                        'pagina': pagina, 'url': pagina}
            self._contexto = contexto
        interrumpido = False
        try:
            if not self._queda_tiempo(tiempo_final):
                return False
            if not self.activar_navegador():
                raise RuntimeError("No se pudo activar el navegador")
            if not self._queda_tiempo(tiempo_final):
                return False

            if not contexto['abierta']:
                self._hotkey(self.cmd_key, 't')
                contexto['abierta'] = True
                self._esperar(0.4)

            if not contexto['navegada'] or contexto['pagina'] != pagina:
                if not self._queda_tiempo(tiempo_final):
                    return False
                if not self.copiar_al_portapapeles(pagina):
                    logging.error(f"No se pudo copiar la URL de {pagina}, se omite")
                    return
                self._hotkey(self.cmd_key, 'l')
                self._hotkey(self.cmd_key, 'v')
                if not self._queda_tiempo(tiempo_final):
                    return False
                contexto['navegacion_pendiente'] = True
                self._press('return')
                contexto.update(navegada=True, pagina=pagina, url=pagina)
                logging.info(f"Navegando a {pagina}")
                self._esperar(2)
                contexto['url'] = self._leer_url_actual()
                contexto['navegacion_pendiente'] = False

            if self._queda_tiempo(tiempo_final):
                self.interactuar_con_pagina(pagina, tiempo_final)
            # Los clics del propio bot pueden navegar: conservar la dirección resultante.
            if contexto['intervenida']:
                contexto['url'] = self._leer_url_actual()
        except PausaPorActividad:
            contexto['intervenida'] = True
            interrumpido = True
            raise
        except (FailsafeActivo, pyautogui.FailSafeException, KeyboardInterrupt):
            interrumpido = True
            raise
        finally:
            if contexto['abierta'] and not interrumpido and not contexto['intervenida']:
                self._limpiando = True
                try:
                    if self.activar_navegador():
                        self._hotkey(self.cmd_key, 'w')
                        self._contexto = None
                        logging.info(f"Cerrando pestaña de: {pagina}")
                except PausaPorActividad:
                    contexto['intervenida'] = True
                    raise
                finally:
                    self._limpiando = False

    def interactuar_con_pagina(self, pagina, tiempo_turno=float("inf")):
        """Interactúa con una página abierta en el navegador"""
        duracion = self._visita_restante if self._visita_restante is not None else random.uniform(10, 20)
        self._visita_restante = None
        if duracion <= 0:
            return
        restante = self.tiempo_restante()
        if restante is not None:
            duracion = min(duracion, restante)
        tiempo_final = min(time.monotonic() + duracion, tiempo_turno)
        tiempo_inicio = time.monotonic()
        logging.info(f"Interactuando con {pagina} por {duracion:.1f} segundos")

        try:
            if not self._queda_tiempo(tiempo_final):
                return
            config = self.browser_configs[self.browser]
            center_x, center_y = self._configurar_area_mouse(self.rectangulo_aplicacion(config['mac']))
            self._move_to(center_x, center_y, duration=0.3)
            self._click()

            while self._queda_tiempo(tiempo_final):
                # Clicks aleatorios dentro del radio
                x_offset = random.randint(-30, 30)
                y_offset = random.randint(-30, 30)
                target_x = center_x + x_offset
                target_y = center_y + y_offset

                self._move_to(target_x, target_y, duration=0.5)
                self._click()

                # Scroll aleatorio
                self._scroll(random.randint(-300, 300))
                self._esperar(random.uniform(1, 3))

            self._visita_restante = None
        except PausaPorActividad:
            restante = max(0, tiempo_final - time.monotonic())
            self._visita_restante = restante if restante > 0 else None
            raise
        except pyautogui.FailSafeException:
            logging.warning("Failsafe activado durante la navegación")
            raise FailsafeActivo("Failsafe activado durante la interacción web")
        except Exception as e:
            logging.error(f"Error interactuando con página {pagina}: {e}", exc_info=True)
        finally:
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
