import logging
import math
import pyautogui
import subprocess
import time
import random
from typing import Optional
from base_automation import BaseAutomation, FailsafeActivo
from statistics_tracker import StatisticsTracker
from user_activity import PausaPorActividad
from menu import normalizar_web, acciones_config


class NavegacionCambiada(RuntimeError):
    pass


class WebInteractor(BaseAutomation):
    def __init__(self, stats_tracker: StatisticsTracker):
        super().__init__()

        self.stats_tracker = stats_tracker
        self.VALID_BROWSERS = ["chrome", "edge", "opera", "firefox"]
        self.paginas = []
        self.acciones = acciones_config({}, "web")
        self.browser = None
        self.browser_abierto = False
        self._indice_pagina = 0
        self._turno_restante = None
        self._visita_restante = None
        self._contexto = None
        self._ventana_web = None
        self._url_interaccion = None
        self._pestana_bot = None
        self._url_silenciosa_disponible = True
        self._ultimo_click = None

        # Navegadores con diccionario AppleScript de Chromium: su URL se lee sin tocar la barra.
        self.url_applescript = {'chrome', 'edge'}

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

    def invalidar_pestana(self):
        self._pestana_bot = None
        if self._contexto is not None:
            self._contexto['intervenida'] = True

    def set_paginas(self, paginas: list) -> None:
        """Establece las páginas a las que navegar (descartando entradas vacías)"""
        normalizadas = list(dict.fromkeys(normalizar_web(p) for p in paginas if p and p.strip()))
        if normalizadas != self.paginas:
            self._indice_pagina = 0
            self._contexto = None
            self._turno_restante = None
            self._visita_restante = None
        self.paginas = normalizadas

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

    def _leer_url_silenciosa(self) -> Optional[str]:
        """URL de la pestaña activa vía AppleScript; None si el navegador no lo permite."""
        if not (self.is_mac and self.browser in self.url_applescript and self._url_silenciosa_disponible):
            return None
        nombre = self.browser_configs[self.browser]['mac']
        try:
            resultado = self._ejecutar_proceso(
                ['osascript', '-e', f'tell application "{nombre}" to get URL of active tab of front window'],
                capture_output=True, text=True, check=True, timeout=5)
        except subprocess.CalledProcessError as e:
            # Sin permiso de Automatización: no reintentar en cada acción.
            self._url_silenciosa_disponible = False
            logging.warning(f"No se pudo leer la URL de {nombre} sin la barra de direcciones: {(e.stderr or '').strip()}")
            return None
        except subprocess.TimeoutExpired:
            return None
        return resultado.stdout.strip() or None

    def _url_pestana(self):
        """Lee la URL sin tocar la barra cuando se puede; si no, con la barra de direcciones."""
        return self._leer_url_silenciosa() or self._leer_url_actual()

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
        reutilizable = False
        try:
            if not self._queda_tiempo(tiempo_final):
                return False
            if not self.activar_navegador():
                raise RuntimeError("No se pudo activar el navegador")
            if not self._queda_tiempo(tiempo_final):
                return False

            if not contexto['abierta'] and self._reutilizar_pestana(contexto, pagina):
                logging.info("Se reutiliza la pestaña abierta por el bot")
            if not contexto['abierta']:
                self._hotkey(self.cmd_key, 't')
                contexto['abierta'] = True
                self._esperar(0.4)

            if not contexto['navegada'] or contexto['pagina'] != pagina:
                if not self._queda_tiempo(tiempo_final):
                    return False
                if not self.copiar_al_portapapeles(pagina):
                    raise RuntimeError('No se pudo copiar la URL; se cancela la navegación')
                self._hotkey(self.cmd_key, 'l')
                self._hotkey(self.cmd_key, 'v')
                if not self._queda_tiempo(tiempo_final):
                    return False
                contexto['navegacion_pendiente'] = True
                self._press('return')
                contexto.update(navegada=True, pagina=pagina, url=pagina)
                logging.info(f"Navegando a {pagina}")
                self._esperar(2)
                contexto['url'] = self._url_pestana()
                contexto['navegacion_pendiente'] = False

            reutilizable = True
            if self._queda_tiempo(tiempo_final):
                self.interactuar_con_pagina(pagina, tiempo_final)
            # Los clics del propio bot pueden navegar: conservar la dirección resultante.
            if contexto['intervenida']:
                contexto['url'] = self._url_pestana()
        except NavegacionCambiada:
            reutilizable = False
            logging.info('La página navegó durante la interacción; se conserva la pestaña y finaliza la visita')
        except PausaPorActividad:
            contexto['intervenida'] = True
            interrumpido = True
            raise
        except (FailsafeActivo, pyautogui.FailSafeException, KeyboardInterrupt):
            interrumpido = True
            raise
        finally:
            if contexto['abierta'] and not interrumpido and not contexto['intervenida']:
                # La activación no confirma la pestaña: la próxima visita la reutiliza solo
                # si la pestaña activa sigue en la dirección que dejó el bot.
                self._contexto = None
                self._pestana_bot = ({'pagina': contexto['pagina'], 'url': contexto['url']}
                                     if reutilizable else None)
                logging.info("Visita finalizada; pestaña conservada")

    def _reutilizar_pestana(self, contexto, pagina) -> bool:
        """Evita abrir una pestaña nueva en cada visita o reintento."""
        anterior, self._pestana_bot = self._pestana_bot, None
        if anterior is None:
            return False
        try:
            actual = self._url_pestana()
        except RuntimeError:
            return False
        if actual != anterior['url']:
            return False
        contexto.update(abierta=True, navegada=anterior['pagina'] == pagina, pagina=pagina, url=actual)
        return True

    def _pausa_accion(self, clave, tiempo_final):
        segundos = self._duracion_configurada(clave)
        if segundos > 0:
            self._esperar(min(segundos, max(0, tiempo_final - time.monotonic())))

    def interactuar_con_pagina(self, pagina, tiempo_turno=float("inf")):
        """Interactúa con una página abierta en el navegador"""
        if not any(self.acciones.values()):
            return
        duracion = self._visita_restante if self._visita_restante is not None else self._duracion_configurada('navegador_visita')
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
            self._ventana_web = self.identidad_ventana_activa()
            # Sin lectura silenciosa no se comprueba la URL durante la visita: abrir la barra
            # de direcciones antes de cada acción interrumpe la página.
            self._url_interaccion = self._leer_url_silenciosa()
            self._ultimo_click = None
            center_x, center_y = self._configurar_area_mouse(self.rectangulo_aplicacion(config['mac']))
            if self.acciones['mover_mouse']:
                self._move_to(center_x, center_y, duration=self._duracion_configurada('navegador_centrado'))
            if self.acciones['click'] and self._mouse_en_area_segura():
                self._click_registrado()
                self._pausa_accion('navegador_pausa_click', tiempo_final)

            while self._queda_tiempo(tiempo_final):
                self._confirmar_destino_web()
                center_x, center_y = self._configurar_area_mouse(
                    self.rectangulo_aplicacion(config['mac']))
                # Cada acción respeta su configuración independiente.
                if self.acciones['mover_mouse']:
                    target_x, target_y = self._destino_lejano(center_x, center_y)
                    self._move_to(target_x, target_y, duration=self._duracion_configurada('navegador_movimiento'))
                if self._mouse_en_area_segura():
                    if self.acciones['click'] and (not self.acciones['mover_mouse'] or self._lejos_del_ultimo_click()):
                        self._click_registrado()
                        self._pausa_accion('navegador_pausa_click', tiempo_final)
                    if self.acciones['scroll'] and time.monotonic() < tiempo_final:
                        self._scroll(random.randint(-300, 300))
                        self._pausa_accion('navegador_pausa_scroll', tiempo_final)
                self._esperar(min(self._duracion_configurada('navegador_ciclo'), max(0, tiempo_final - time.monotonic())))

            self._visita_restante = None
        except PausaPorActividad:
            restante = max(0, tiempo_final - time.monotonic())
            self._visita_restante = restante if restante > 0 else None
            raise
        except pyautogui.FailSafeException:
            logging.warning("Failsafe activado durante la navegación")
            raise FailsafeActivo("Failsafe activado durante la interacción web")
        except NavegacionCambiada:
            raise
        except Exception as e:
            logging.error(f"Error interactuando con página {pagina}: {e}", exc_info=True)
            raise
        finally:
            self._ventana_web = None
            self._url_interaccion = None
            self.registrar_tiempo_interaccion(pagina, tiempo_inicio)

    def _distancia_minima_click(self):
        if self._area_mouse is None:
            return 0
        izquierda, arriba, derecha, abajo = self._area_mouse
        return max(80, 0.15 * min(derecha - izquierda, abajo - arriba))

    def _lejos_del_ultimo_click(self):
        if self._ultimo_click is None:
            return True
        x, y = self._posicion_mouse()
        return math.dist((x, y), self._ultimo_click) >= self._distancia_minima_click()

    def _destino_lejano(self, center_x, center_y):
        """Punto del área segura a una distancia moderada del último click (entre 1 y 2 veces la mínima)."""
        if self._area_mouse is None:
            return center_x + random.randint(-30, 30), center_y + random.randint(-30, 30)
        izquierda, arriba, derecha, abajo = self._area_mouse
        minimo = self._distancia_minima_click()
        origen = self._ultimo_click or self._posicion_mouse()
        mejor, mejor_distancia = None, -1
        for _ in range(20):
            angulo, radio = random.uniform(0, 2 * math.pi), random.uniform(minimo, 2 * minimo)
            punto = (round(min(max(origen[0] + radio * math.cos(angulo), izquierda), derecha)),
                     round(min(max(origen[1] + radio * math.sin(angulo), arriba), abajo)))
            distancia = math.dist(punto, origen)
            if distancia >= minimo:
                return punto
            if distancia > mejor_distancia:
                mejor, mejor_distancia = punto, distancia
        return mejor

    def _click_registrado(self):
        self._click()
        self._ultimo_click = self._posicion_mouse()

    def _antes_accion(self):
        super()._antes_accion()
        ventana = getattr(self, '_ventana_web', None)
        if ventana is not None and self.identidad_ventana_activa() != ventana:
            raise RuntimeError('Cambió la ventana del navegador; se cancela la interacción')

    def _comprobar_area_mouse(self):
        super()._comprobar_area_mouse()
        if self._ventana_web is None or self.identidad_ventana_activa() != self._ventana_web:
            raise RuntimeError('Cambió la ventana del navegador; se cancela la interacción')

    def _click(self):
        self._confirmar_destino_web()
        super()._click()

    def _scroll(self, cantidad):
        self._confirmar_destino_web()
        super()._scroll(cantidad)

    def _confirmar_destino_web(self):
        if self.identidad_ventana_activa() != self._ventana_web:
            raise RuntimeError('Cambió la ventana del navegador; se cancela la interacción')
        if self._url_interaccion is None:
            return
        actual = self._leer_url_silenciosa()
        if actual is not None and actual != self._url_interaccion:
            raise NavegacionCambiada('Cambió la dirección del navegador; se finaliza la visita')

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
