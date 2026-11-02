import json
import logging
import os
import pyautogui
import random
import re
import subprocess
import tempfile
import time
from typing import Optional

from base_automation import BaseAutomation, FailsafeActivo
from code_generator import CodeGenerator
from statistics_tracker import StatisticsTracker


class EditorNoDisponible(Exception):
    """Excepción para cuando no se puede abrir ningún editor instalado"""


class EditorInteractor(BaseAutomation):
    def __init__(self, stats_tracker: StatisticsTracker, fuente_codigo=None):
        super().__init__()
        pyautogui.PAUSE = 0.05

        self.stats_tracker = stats_tracker
        self.fuente_codigo = fuente_codigo or CodeGenerator()
        self.VALID_EDITORS = ["vsCode"]
        self.EDITOR_STARTUP_TIME = 2
        self.EDITOR_WINDOW_OFFSET = 20
        self.EDITOR_ABIERTO = False
        self.editor_actual = None
        self._portapapeles_original = None
        self.lineas_actuales = None
        self.fases = "ambas"
        self.bloque_actual = None
        self.inicio_bloque = 0
        self.indice_linea = 0
        self.desplazamiento = 0
        self.necesita_reposicionar = True
        self.ruta_archivo = None
        self.EDITOR_INFO = {
            "vsCode": {"proceso": "Code.exe", "mac": "Visual Studio Code"},
        }

    def validar_editor(self, value: str) -> str:
        """Valida que el editor esté en la lista de editores válidos"""
        if value not in self.VALID_EDITORS:
            raise ValueError(f"El editor debe ser uno de {self.VALID_EDITORS}")
        return value

    def _comando_abrir_editor(self, editor: str, ruta_archivo: Optional[str]) -> Optional[list]:
        """Construye el comando para abrir el editor con el archivo indicado; None si no se soporta"""
        if editor not in self.VALID_EDITORS:
            return None
        if self.is_windows:
            binarios = {"vsCode": "code", "cursor": "cursor"}
            cmd = [binarios[editor]]
            if ruta_archivo:
                cmd.append(ruta_archivo)
            return cmd
        if self.is_mac:
            nombre_app = self.EDITOR_INFO[editor]["mac"]
            cmd = ["open", "-a", nombre_app]
            if ruta_archivo:
                cmd.append(ruta_archivo)
            return cmd
        return None

    def ejecutar_comando(self, cmd: list) -> bool:
        """Ejecuta el comando para abrir el editor; True si se lanzó correctamente"""
        self._antes_accion()
        logging.info(f"Ejecutando comando: {cmd}")
        try:
            if self.is_windows:
                subprocess.Popen(cmd, shell=True)
                return True
            resultado = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if resultado.returncode != 0:
                mensaje = (resultado.stderr or resultado.stdout or "").strip()
                logging.error(f"Error lanzando el editor ({cmd}): {mensaje}")
                return False
            return True
        except FileNotFoundError:
            logging.error(f"No se encontró el ejecutable para abrir el editor: {cmd}")
            return False
        except subprocess.TimeoutExpired:
            logging.error(f"Timeout lanzando el editor: {cmd}")
            return False
        except Exception as e:
            logging.error(f"Error lanzando el editor ({cmd}): {e}")
            return False

    def _crear_archivo_temporal(self) -> str:
        """Crea una pestaña de trabajo vacía con nombre único por sesión."""
        descriptor, ruta = tempfile.mkstemp(prefix="workbreak_", suffix=".tsx")
        os.close(descriptor)
        return ruta

    def abrir_editor(self, editor: str) -> None:
        """Abre VS Code con el archivo temporal; falla si no está disponible."""
        if self.EDITOR_ABIERTO:
            return

        try:
            # El nombre único permite distinguir esta pestaña de las del usuario.
            self.ruta_archivo = self._crear_archivo_temporal()

            efectivo = self._lanzar_editor_primero_disponible(editor, self.ruta_archivo)
            if efectivo is None:
                raise EditorNoDisponible(
                    f"No se pudo abrir ningún editor instalado. "
                    "Instala Visual Studio Code para ejecutar el bot."
                )

            info = self.EDITOR_INFO[efectivo]
            if not self._esperar_ventana_editor(info):
                raise EditorNoDisponible("No se pudo confirmar la ventana del editor")
            self._esperar(1)

            self.editor_actual = efectivo
            self._asegurar_destino()
            self.EDITOR_ABIERTO = True
        except EditorNoDisponible:
            raise
        except Exception as e:
            self.manejar_error(f"Error al abrir el editor {editor}: {e}")

    def _lanzar_editor_primero_disponible(self, editor: str, ruta_archivo: Optional[str]) -> Optional[str]:
        """Intenta lanzar el editor pedido y luego los demás; devuelve el efectivo o None"""
        candidatos = [editor] + [e for e in self.VALID_EDITORS if e != editor]
        for e in candidatos:
            cmd = self._comando_abrir_editor(e, ruta_archivo)
            if not cmd:
                continue
            logging.info(f"Abriendo editor: {e}")
            if self.ejecutar_comando(cmd):
                return e
            logging.warning(f"El editor '{e}' no pudo abrirse; se intenta con el siguiente")
        return None

    def _esperar_ventana_editor(self, info: dict) -> bool:
        """Espera (reintentando) a que la ventana del editor esté disponible y la activa"""
        limite = time.monotonic() + self.EDITOR_STARTUP_TIME
        while time.monotonic() < limite:
            if self.activar_aplicacion(info["proceso"], info["mac"]):
                return True
            self._esperar(0.5)
        return False

    def asegurar_editor_abierto(self, editor: str) -> None:
        """Asegura que el editor esté abierto y enfocado sin relanzarlo cada ciclo.

        Una vez abierto, usa el editor efectivo (el que realmente se pudo lanzar).
        """
        if not self.EDITOR_ABIERTO:
            self.abrir_editor(editor)
            return

        self._asegurar_destino()

    def _asegurar_destino(self) -> None:
        """Rechaza la entrada si no está activo el archivo temporal de esta sesión."""
        if not self.editor_actual or not self.ruta_archivo:
            raise EditorNoDisponible("No hay archivo temporal confirmado")
        info = self.EDITOR_INFO[self.editor_actual]
        if not self._activar_si_necesario(info["proceso"], info["mac"]):
            raise EditorNoDisponible("No se pudo enfocar el editor; se cancela la entrada")
        # La comprobación del título se hace después de enfocar el grupo de código.
        self._hotkey(self.cmd_key, "1")
        self._esperar(0.15)
        try:
            if self.is_windows:
                import win32gui
                titulo = win32gui.GetWindowText(win32gui.GetForegroundWindow())
            elif self.is_mac:
                resultado = subprocess.run(
                    ["osascript", "-e",
                     f'set appBundleId to id of application "{info["mac"]}"\n'
                     'tell application "System Events"\n'
                     'tell (first application process whose bundle identifier is appBundleId)\n'
                     'if frontmost is false then error "Editor sin foco"\n'
                     'get name of front window\nend tell\nend tell'],
                    capture_output=True, text=True, check=True, timeout=5,
                )
                titulo = resultado.stdout.strip()
            else:
                raise EditorNoDisponible("Sistema operativo no soportado")
            if os.path.basename(self.ruta_archivo) not in titulo:
                raise EditorNoDisponible("El archivo temporal no está activo; se cancela la entrada")
        except EditorNoDisponible:
            raise
        except Exception as e:
            stderr = getattr(e, "stderr", None)
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            detalle = {
                "editor": self.editor_actual,
                "archivo": self.ruta_archivo,
                "tipo": type(e).__name__,
                "error": str(e),
                "stderr": stderr,
            }
            logging.error("Fallo verificando el editor: %s", json.dumps(detalle, ensure_ascii=False))
            motivo = stderr or str(e)
            raise EditorNoDisponible(f"No se pudo verificar el archivo temporal: {motivo.strip()}") from e

    def manejar_error(self, mensaje: str) -> None:
        """Registra el error y lo propaga para que el bot lo maneje (nunca sys.exit)"""
        logging.error(mensaje)
        raise RuntimeError(mensaje)

    def interactuar_editor(self, duracion_maxima: Optional[float] = None) -> None:
        """Inyecta código una vez y alterna fases de escritura y mouse con duraciones variables.

        `duracion_maxima` limita el turno actual (usado al alternar con el navegador).
        """
        tiempo_inicio = time.time()
        tiempo_restante = self.tiempo_restante()

        if tiempo_restante is not None and tiempo_restante <= 0:
            logging.info("Tiempo restante agotado; se omite la interacción con el editor")
            return

        if tiempo_restante is None:
            duracion = random.uniform(60, 240)
        else:
            duracion = min(random.uniform(60, 240), tiempo_restante)

        if duracion_maxima is not None:
            duracion = min(duracion, duracion_maxima)

        tiempo_final = time.monotonic() + duracion

        logging.info(f"Iniciando interacción con editor por {duracion / 60:.1f} minutos")

        try:
            if self.lineas_actuales is None:
                self.inyectar_codigo()
                if self.lineas_actuales is None:
                    return

            while time.monotonic() < tiempo_final:
                if self.fases in ("ambas", "escritura"):
                    self.fase_escritura(tiempo_final)
                if self.fases in ("ambas", "mouse"):
                    self.fase_mouse(tiempo_final)

            self.registrar_tiempo_interaccion(tiempo_inicio)
        except pyautogui.FailSafeException:
            logging.warning("Failsafe activado - mouse en esquina superior izquierda")
            self.registrar_tiempo_interaccion(tiempo_inicio)
            raise FailsafeActivo()
        except Exception:
            logging.exception("Error durante la interacción con el editor")
            self.registrar_tiempo_interaccion(tiempo_inicio)
            raise

    def fase_escritura(self, tiempo_final: float) -> None:
        """Fase de escritura con duración variable: borra y reescribe bloques reales de código"""
        duracion = self._duracion_fase_escritura()
        fin = min(time.monotonic() + duracion, tiempo_final)
        logging.info(f"Fase de escritura por {max(0.0, fin - time.monotonic()):.0f}s")

        self._asegurar_destino()

        while time.monotonic() < fin:
            if not self._queda_tiempo_editor(tiempo_final):
                break
            self._editar_bloque_real(fin)
            self._esperar(random.uniform(0.4, 1.8))

    def fase_mouse(self, tiempo_final: float) -> None:
        """Fase de mouse: sube al inicio del archivo, hace clic y scroll arriba/abajo para que las
        capturas muestren el código; al terminar vuelve a la línea donde continuará la escritura"""
        if not self._queda_tiempo_editor(tiempo_final):
            return
        duracion = self._duracion_fase_mouse()
        fin = min(time.monotonic() + duracion, tiempo_final)
        logging.info(f"Fase de mouse por {max(0.0, fin - time.monotonic()):.0f}s")

        self._asegurar_destino()

        self.necesita_reposicionar = True
        self._iniciar_fase_mouse()

        while time.monotonic() < fin:
            if not self._queda_tiempo_editor(tiempo_final):
                break
            self._movimiento_fase_mouse()
            self._esperar(random.uniform(0.4, 2.0))

    def _iniciar_fase_mouse(self) -> None:
        """Sube al inicio del archivo y hace clic sobre el editor para enfocarlo"""
        try:
            self._inicio_archivo()
            self._esperar(random.uniform(0.2, 0.5))
            rect = self._rectangulo_ventana_editor()
            if rect:
                x, y, ancho, alto = rect
                self._move_to(x + ancho // 3, y + max(120, alto // 3),
                                 duration=random.uniform(0.2, 0.6))
            else:
                self._move_rel(random.randint(10, 40), random.randint(10, 40),
                                  duration=random.uniform(0.2, 0.6))
            self._click()
            self._esperar(random.uniform(0.2, 0.5))
        except pyautogui.FailSafeException:
            raise
        except Exception as e:
            logging.warning(f"No se pudo iniciar la fase de mouse: {e}")

    def _movimiento_fase_mouse(self) -> None:
        """Movimiento individual de la fase: scroll abajo/arriba (mayormente) y pequeños movimientos"""
        r = random.random()
        if r < 0.1:
            self._inicio_archivo()
            self._esperar(0.1)
        elif r < 0.7:
            self._scroll(-random.randint(4, 12))
        elif r < 0.85:
            self._scroll(random.randint(3, 8))
        else:
            x = random.randint(-self.EDITOR_WINDOW_OFFSET, self.EDITOR_WINDOW_OFFSET)
            y = random.randint(-self.EDITOR_WINDOW_OFFSET, self.EDITOR_WINDOW_OFFSET)
            self._move_rel(x, y, duration=random.uniform(0.2, 0.6))
            if random.random() < 0.5:
                self._click()

    def _rectangulo_ventana_editor(self):
        """Devuelve (x, y, ancho, alto) de la ventana del editor o None si no se puede obtener"""
        if not self.editor_actual:
            return None
        info = self.EDITOR_INFO[self.editor_actual]
        try:
            if self.is_windows:
                import win32gui
                izquierda, arriba, derecha, abajo = win32gui.GetWindowRect(win32gui.GetForegroundWindow())
                return (izquierda, arriba, derecha - izquierda, abajo - arriba)
            if self.is_mac:
                resultado = subprocess.run(
                    ["osascript", "-e",
                     f'set appBundleId to id of application "{info["mac"]}"\n'
                     'tell application "System Events"\n'
                     'tell (first application process whose bundle identifier is appBundleId)\n'
                     'get {position, size} of front window\nend tell\nend tell'],
                    capture_output=True, text=True, timeout=5
                )
                if resultado.returncode != 0 or not resultado.stdout.strip():
                    return None
                numeros = re.findall(r"-?\d+", resultado.stdout)
                if len(numeros) >= 4:
                    x, y, ancho, alto = (int(v) for v in numeros[:4])
                    return (x, y, ancho, alto)
        except Exception as e:
            logging.warning(f"No se pudo obtener el rectángulo de la ventana: {e}")
        return None

    def _liberar_modificadores(self) -> None:
        """En macOS los modificadores pertenecen al evento, no se mantienen pulsados."""
        if self.is_mac:
            return
        for tecla in ("ctrl", "shift", "alt"):
            try:
                self._antes_accion()
                pyautogui.keyUp(tecla)
            except Exception:
                pass

    def _duracion_fase_escritura(self) -> float:
        """Duración aleatoria de la fase de escritura (corta, media, larga)"""
        return random.choice([
            random.uniform(2, 6),
            random.uniform(8, 15),
            random.uniform(25, 45),
            random.uniform(60, 100),
        ])

    def _duracion_fase_mouse(self) -> float:
        """Duración aleatoria de la fase de mouse"""
        return random.choice([
            random.uniform(2, 4),
            random.uniform(5, 9),
            random.uniform(10, 16),
        ])

    def _editar_bloque_real(self, tiempo_final: float) -> None:
        """Edita el bloque en curso o toma uno nuevo; continúa donde quedó la última iteración"""
        if not self.lineas_actuales:
            return

        try:
            self._asegurar_destino()
            self._cerrar_paneles()

            if self.bloque_actual is None or self.indice_linea >= len(self.bloque_actual):
                inicio, bloque = self._elegir_bloque()
                if not bloque:
                    return
                self.bloque_actual = bloque
                self.inicio_bloque = inicio
                self.indice_linea = 0
                self.desplazamiento = 0
                n = len(bloque)
                logging.info(f"Nuevo bloque: líneas {inicio + 1} a {inicio + n} ({n} líneas)")
                self.necesita_reposicionar = True

            self._escribir_siguiente_linea(tiempo_final)
        except (pyautogui.FailSafeException, EditorNoDisponible):
            raise
        except Exception as e:
            # No reiniciar la inyección completa si se pierde el estado de una edición.
            raise EditorNoDisponible("Se interrumpió la edición del fragmento; no se reemplazará el archivo completo") from e

    def _escribir_siguiente_linea(self, tiempo_final: float) -> None:
        """Escribe la línea en curso; si quedó a medias, continúa desde donde se interrumpió"""
        linea = self.bloque_actual[self.indice_linea]

        if self.necesita_reposicionar:
            self._ir_a_linea(self.inicio_bloque + self.indice_linea + 1)
            self.necesita_reposicionar = False

        if self.desplazamiento == 0:
            self._limpiar_linea_actual()
        else:
            self._fin_linea()
            self._esperar(random.uniform(0.05, 0.15))

        texto = linea[self.desplazamiento:]
        for c in texto:
            if not self._queda_tiempo_editor(tiempo_final):
                return
            self._write(c, interval=0)
            self.desplazamiento += 1
            self._esperar(random.uniform(0.03, 0.08))

        # El editor puede insertar comillas o paréntesis automáticamente al teclear.
        if linea:
            self._asegurar_destino()
            # El cursor sigue en esta línea: no volver a abrir Ir a línea para restaurarla.
            if self.is_windows:
                self._press("home")
                if linea.strip():
                    self._press("home")
            else:
                self._hotkey("command", "left")
                if linea.strip():
                    # VS Code puede detenerse primero en el primer carácter no blanco.
                    # El segundo salto incluye también la sangría en el reemplazo.
                    self._hotkey("command", "left")
            if not self.copiar_al_portapapeles(linea):
                raise RuntimeError("No se pudo restaurar exactamente la línea reescrita")
            self._limpiar_linea_actual()
            self._hotkey(self.cmd_key, "v")
        self.indice_linea += 1
        self.desplazamiento = 0
        self.necesita_reposicionar = True

    def _max_bloque_segun_tamano(self) -> int:
        """Tamaño máximo del bloque según el tamaño del archivo para no borrarlo entero"""
        n = len(self.lineas_actuales)
        if n < 40:
            return random.randint(1, 2)
        if n < 80:
            return random.randint(1, 3)
        if n < 150:
            return random.randint(1, 4)
        return random.randint(1, 6)

    def _elegir_bloque(self) -> tuple:
        """Elige un bloque contiguo de líneas reales que se pueda reescribir con el teclado"""
        lineas = self.lineas_actuales

        if len(lineas) < 2:
            for idx, linea in enumerate(lineas):
                if self._linea_escribible(linea):
                    return idx, [linea]
            return 0, []

        for _ in range(25):
            inicio = random.randrange(len(lineas) - 1)
            if not self._linea_escribible(lineas[inicio]) or len(lineas[inicio]) > 160:
                continue
            max_bloque = self._max_bloque_segun_tamano()
            bloque = [lineas[inicio]]
            for idx in range(inicio + 1, len(lineas) - 1):
                if len(bloque) >= max_bloque:
                    break
                if not self._linea_escribible(lineas[idx]) or len(lineas[idx]) > 160:
                    break
                bloque.append(lineas[idx])
            if any(l.strip() for l in bloque):
                return inicio, bloque

        return 0, []

    def _linea_escribible(self, linea: str) -> bool:
        """Indica si la línea puede reescribirse con pyautogui (solo ASCII imprimible, sin tabulaciones)"""
        return all(0x20 <= ord(c) <= 0x7E for c in linea)

    def _limpiar_linea_actual(self) -> None:
        """Selecciona desde la columna 1 confirmada, sin borrar el salto de línea."""
        if self.is_windows:
            self._hotkey("shift", "end")
        else:
            self._hotkey("command", "shift", "right")
        self._liberar_modificadores()

    def _fin_linea(self) -> None:
        if self.is_windows:
            self._press("end")
        else:
            self._hotkey("command", "right")

    def _inicio_archivo(self) -> None:
        if self.is_windows:
            self._hotkey("ctrl", "home")
        else:
            self._hotkey("command", "up")

    def _cerrar_paneles(self) -> None:
        """Cierra con Escape cualquier panel emergente (autocompletado, emojis, quick input)"""
        self._press("esc")
        self._esperar(0.1)

    def _ir_a_linea(self, numero: int) -> None:
        """Confirma el contenido de Ir a línea antes de enviar coordenadas."""
        if self.is_mac:
            self._hotkey("option", "g")
        else:
            self._hotkey("ctrl", "g")
        self._esperar(0.2)
        if self.is_mac:
            # Seleccionar/copiar no modifica el archivo si el panel no se abrió.
            self._hotkey("command", "a")
            campo = self._leer_seleccion_mac()
            if campo is None or re.fullmatch(r":\d*(?::\d*)?", campo) is None:
                self._press("esc")
                raise EditorNoDisponible("No se confirmó el panel Ir a línea; no se enviaron coordenadas")
            destino = f":{numero}:1"
        else:
            destino = f"{numero}:1"
        self._write(destino, interval=0.03)
        self._esperar(0.1)
        self._press("enter")
        self._esperar(0.2)
        if self.is_mac:
            self._confirmar_linea_mac(numero)
        self._liberar_modificadores()

    def _leer_seleccion_mac(self) -> Optional[str]:
        marcador = "workbreak:sin-seleccion"
        if not self.copiar_al_portapapeles(marcador):
            raise EditorNoDisponible("No se pudo preparar la comprobación del cursor")
        self._hotkey("command", "c")
        self._esperar(0.15)
        contenido = self.leer_portapapeles()
        return None if contenido == marcador else contenido

    def _confirmar_linea_mac(self, numero: int) -> None:
        if not self.lineas_actuales or not 1 <= numero <= len(self.lineas_actuales):
            raise EditorNoDisponible("La línea solicitada no pertenece al código cargado")
        esperada = self.lineas_actuales[numero - 1]
        self._hotkey("command", "shift", "right")
        actual = self._leer_seleccion_mac()
        if actual is not None:
            actual = actual.rstrip("\r\n")
        self._press("left")  # Colapsa la selección al comienzo sin modificar texto.
        coincide = actual == esperada or (not esperada and actual in (None, ""))
        if (self.bloque_actual and self.desplazamiento > 0
                and numero == self.inicio_bloque + self.indice_linea + 1):
            prefijo = esperada[:self.desplazamiento]
            coincide = actual is not None and actual.startswith(prefijo)
        if not coincide:
            raise EditorNoDisponible("El cursor no está en la línea esperada; se cancela la edición del fragmento")

    def _queda_tiempo_editor(self, tiempo_final: float) -> bool:
        """Indica si queda tiempo (duración de la fase y límite global)"""
        if time.monotonic() >= tiempo_final:
            return False
        restante = self.tiempo_restante()
        if restante is not None and restante <= 0:
            return False
        return True

    def inyectar_codigo(self) -> None:
        """Reemplaza el contenido del editor con un bloque grande de código realista"""
        if self._portapapeles_original is None:
            try:
                self._portapapeles_original = self.leer_portapapeles()
                logging.info("Portapapeles del usuario guardado")
            except Exception as e:
                logging.warning(f"No se pudo guardar el portapapeles original: {e}")

        codigo = self.fuente_codigo.obtener_codigo()

        if not self.copiar_al_portapapeles(codigo):
            logging.error("No se pudo copiar el código; se omite el pegado")
            return

        self._asegurar_destino()

        self._hotkey(self.cmd_key, 'a')
        self._esperar(0.15)
        self._hotkey(self.cmd_key, 'v')
        self.lineas_actuales = codigo.splitlines()
        self.bloque_actual = None
        self.inicio_bloque = 0
        self.indice_linea = 0
        self.desplazamiento = 0
        self.necesita_reposicionar = True
        self._esperar(0.3)
        self._liberar_modificadores()
        logging.info(f"Código inyectado: {len(self.lineas_actuales)} líneas, {len(codigo)} caracteres")

    def restaurar_portapapeles(self) -> None:
        """Restaura el portapapeles del usuario al valor guardado en la primera inyección"""
        if self._portapapeles_original is None:
            return
        try:
            self.copiar_al_portapapeles(self._portapapeles_original)
            logging.info("Portapapeles del usuario restaurado")
        except Exception as e:
            logging.error(f"No se pudo restaurar el portapapeles: {e}")

    def registrar_tiempo_interaccion(self, tiempo_inicio: float) -> None:
        """Registra el tiempo de interacción con el editor"""
        tiempo_real = time.time() - tiempo_inicio
        self.stats_tracker.register_editor_session(tiempo_real)
        logging.info(f"Interacción con editor finalizada, duración real: {tiempo_real / 60:.1f} minutos")
