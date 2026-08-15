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
        self.VALID_EDITORS = ["cursor", "vsCode"]
        self.EDITOR_STARTUP_TIME = 2
        self.EDITOR_WINDOW_OFFSET = 20
        self.EDITOR_ABIERTO = False
        self.editor_actual = None
        self._portapapeles_original = None
        self.lineas_actuales = None
        self.bloque_actual = None
        self.inicio_bloque = 0
        self.indice_linea = 0
        self.desplazamiento = 0
        self.necesita_reposicionar = True
        self.proyecto_simulado = None
        self.EDITOR_INFO = {
            "vsCode": {"proceso": "Visual Studio Code", "mac": "Visual Studio Code"},
            "cursor": {"proceso": "Cursor", "mac": "Cursor"},
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

    def _crear_proyecto_simulado(self) -> str:
        """Crea un proyecto React/TS simulado en un directorio temporal y devuelve su ruta"""
        if self.proyecto_simulado:
            return self.proyecto_simulado

        try:
            proyecto = tempfile.mkdtemp(prefix="workbreak_")
            os.makedirs(os.path.join(proyecto, "src", "components"), exist_ok=True)

            archivos = {
                "package.json": '{\n'
                                '  "name": "workbreak-dashboard",\n'
                                '  "private": true,\n'
                                '  "version": "1.0.0",\n'
                                '  "scripts": {\n'
                                '    "dev": "vite"\n'
                                '  },\n'
                                '  "dependencies": {\n'
                                '    "react": "^18.2.0",\n'
                                '    "typescript": "^5.0.0"\n'
                                '  }\n'
                                '}\n',
                "tsconfig.json": '{\n'
                                 '  "compilerOptions": {\n'
                                 '    "target": "ES2020",\n'
                                 '    "module": "ESNext",\n'
                                 '    "moduleResolution": "node",\n'
                                 '    "jsx": "react-jsx",\n'
                                 '    "strict": true,\n'
                                 '    "esModuleInterop": true,\n'
                                 '    "skipLibCheck": true,\n'
                                 '    "forceConsistentCasingInFileNames": true\n'
                                 '  },\n'
                                 '  "include": ["src"]\n'
                                 '}\n',
                os.path.join("src", "main.tsx"): """import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

const root = document.getElementById('root');

if (root) {
  ReactDOM.createRoot(root).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
}
""",
                os.path.join("src", "App.tsx"): """import React, { useState } from 'react';
import Header from './components/Header';
import DataTable from './components/DataTable';
import Spinner from './components/Spinner';

interface Row {
  id: string;
  name: string;
  status: 'active' | 'inactive';
}

const App: React.FC = () => {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);

  return (
    <main>
      <Header title="WorkBreak Dashboard" />
      {loading ? <Spinner size="lg" /> : <DataTable rows={rows} />}
    </main>
  );
};

export default App;
""",
                os.path.join("src", "components", "Header.tsx"): """import React from 'react';

interface HeaderProps {
  title: string;
  subtitle?: string;
}

const Header: React.FC<HeaderProps> = ({ title, subtitle }) => (
  <header>
    <h1>{title}</h1>
    {subtitle && <p>{subtitle}</p>}
  </header>
);

export default Header;
""",
                os.path.join("src", "components", "DataTable.tsx"): """import React from 'react';

interface Row {
  id: string;
  name: string;
  status: 'active' | 'inactive';
}

interface DataTableProps {
  rows: Row[];
}

const DataTable: React.FC<DataTableProps> = ({ rows }) => (
  <table>
    <thead>
      <tr>
        <th>ID</th>
        <th>Name</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody>
      {rows.map((row) => (
        <tr key={row.id}>
          <td>{row.id}</td>
          <td>{row.name}</td>
          <td>{row.status}</td>
        </tr>
      ))}
    </tbody>
  </table>
);

export default DataTable;
""",
                os.path.join("src", "components", "Spinner.tsx"): """import React from 'react';

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  label?: string;
}

const Spinner: React.FC<SpinnerProps> = ({ size = 'md', label }) => (
  <div className={`spinner spinner--${size}`} role="status">
    {label && <span>{label}</span>}
  </div>
);

export default Spinner;
""",
            }

            for ruta_relativa, contenido in archivos.items():
                ruta_absoluta = os.path.join(proyecto, ruta_relativa)
                with open(ruta_absoluta, "w", encoding="utf-8") as f:
                    f.write(contenido)

            self.proyecto_simulado = proyecto
            logging.info(f"Proyecto simulado creado en: {proyecto}")
            return proyecto
        except Exception as e:
            logging.error(f"Error creando el proyecto simulado: {e}")
            return None

    def abrir_editor(self, editor: str) -> None:
        """Abre el editor una única vez por ejecución apuntando al proyecto simulado.

        Si el editor elegido no está instalado, intenta con los demás editores válidos;
        si ninguno funciona, lanza EditorNoDisponible.
        """
        if self.EDITOR_ABIERTO:
            return

        try:
            ruta_proyecto = self._crear_proyecto_simulado()
            ruta_archivo = os.path.join(ruta_proyecto, "src", "App.tsx") if ruta_proyecto else None

            efectivo = self._lanzar_editor_primero_disponible(editor, ruta_archivo)
            if efectivo is None:
                raise EditorNoDisponible(
                    f"No se pudo abrir ningún editor instalado. "
                    f"Disponibles: {', '.join(self.EDITOR_INFO)} (instala Cursor o VS Code)"
                )

            info = self.EDITOR_INFO[efectivo]
            if not self._esperar_ventana_editor(info):
                logging.warning("No se pudo activar la ventana del editor; fallback a mover el cursor")
                self.move_cursor_to_center()
            time.sleep(1)

            self.editor_actual = efectivo
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
            time.sleep(0.5)
        return False

    def asegurar_editor_abierto(self, editor: str) -> None:
        """Asegura que el editor esté abierto y enfocado sin relanzarlo cada ciclo.

        Una vez abierto, usa el editor efectivo (el que realmente se pudo lanzar).
        """
        if not self.EDITOR_ABIERTO:
            self.abrir_editor(editor)
            return

        info = self.EDITOR_INFO[self.editor_actual]
        self._activar_si_necesario(info["proceso"], info["mac"])
        time.sleep(1)

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
            self.inyectar_codigo()

            while time.monotonic() < tiempo_final:
                self.fase_escritura(tiempo_final)
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

        if self.editor_actual:
            info = self.EDITOR_INFO[self.editor_actual]
            self._activar_si_necesario(info["proceso"], info["mac"])

        while time.monotonic() < fin:
            if not self._queda_tiempo_editor(tiempo_final):
                break
            self._editar_bloque_real(tiempo_final)
            time.sleep(random.uniform(0.4, 1.8))

    def fase_mouse(self, tiempo_final: float) -> None:
        """Fase de mouse: sube al inicio del archivo, hace clic y scroll arriba/abajo para que las
        capturas muestren el código; al terminar vuelve a la línea donde continuará la escritura"""
        duracion = self._duracion_fase_mouse()
        fin = min(time.monotonic() + duracion, tiempo_final)
        logging.info(f"Fase de mouse por {max(0.0, fin - time.monotonic()):.0f}s")

        if self.editor_actual:
            info = self.EDITOR_INFO[self.editor_actual]
            self._activar_si_necesario(info["proceso"], info["mac"])

        self.necesita_reposicionar = True
        self._iniciar_fase_mouse()

        while time.monotonic() < fin:
            if not self._queda_tiempo_editor(tiempo_final):
                break
            self._movimiento_fase_mouse()
            time.sleep(random.uniform(0.4, 2.0))

        self._volver_a_escritura_pendiente()

    def _iniciar_fase_mouse(self) -> None:
        """Sube al inicio del archivo y hace clic sobre el editor para enfocarlo"""
        try:
            pyautogui.hotkey("ctrl", "home")
            time.sleep(random.uniform(0.2, 0.5))
            rect = self._rectangulo_ventana_editor()
            if rect:
                x, y, ancho, alto = rect
                pyautogui.moveTo(x + ancho // 3, y + max(120, alto // 3),
                                 duration=random.uniform(0.2, 0.6))
            else:
                pyautogui.moveRel(random.randint(10, 40), random.randint(10, 40),
                                  duration=random.uniform(0.2, 0.6))
            pyautogui.click()
            time.sleep(random.uniform(0.2, 0.5))
        except pyautogui.FailSafeException:
            raise
        except Exception as e:
            logging.warning(f"No se pudo iniciar la fase de mouse: {e}")

    def _movimiento_fase_mouse(self) -> None:
        """Movimiento individual de la fase: scroll abajo/arriba (mayormente) y pequeños movimientos"""
        r = random.random()
        if r < 0.1:
            pyautogui.hotkey("ctrl", "home")
            time.sleep(0.1)
        elif r < 0.7:
            pyautogui.scroll(-random.randint(4, 12))
        elif r < 0.85:
            pyautogui.scroll(random.randint(3, 8))
        else:
            x = random.randint(-self.EDITOR_WINDOW_OFFSET, self.EDITOR_WINDOW_OFFSET)
            y = random.randint(-self.EDITOR_WINDOW_OFFSET, self.EDITOR_WINDOW_OFFSET)
            pyautogui.moveRel(x, y, duration=random.uniform(0.2, 0.6))
            if random.random() < 0.5:
                pyautogui.click()

    def _volver_a_escritura_pendiente(self) -> None:
        """Al terminar la fase de mouse, vuelve a la línea donde continuará la escritura"""
        if not self.bloque_actual or self.indice_linea >= len(self.bloque_actual):
            return
        try:
            self._ir_a_linea(self.inicio_bloque + self.indice_linea + 1)
            time.sleep(random.uniform(0.1, 0.3))
            if self.desplazamiento > 0:
                pyautogui.press("end")
                time.sleep(random.uniform(0.05, 0.15))
            self.necesita_reposicionar = False
        except pyautogui.FailSafeException:
            raise
        except Exception as e:
            logging.warning(f"No se pudo volver a la línea de escritura pendiente: {e}")
            self.necesita_reposicionar = True

    def _rectangulo_ventana_editor(self):
        """Devuelve (x, y, ancho, alto) de la ventana del editor o None si no se puede obtener"""
        if not self.editor_actual:
            return None
        info = self.EDITOR_INFO[self.editor_actual]
        try:
            if self.is_windows:
                import pygetwindow as gw
                ventanas = gw.getWindowsWithTitle(info["proceso"])
                if not ventanas:
                    return None
                ventana = ventanas[0]
                return (ventana.left, ventana.top, ventana.width, ventana.height)
            if self.is_mac:
                resultado = subprocess.run(
                    ["osascript", "-e",
                     f'tell application "System Events" to tell process "{info["mac"]}" to get {{position, size}} of window 1'],
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
        """Suelta cualquier modificador que pyautogui haya dejado 'pegado' (evita emojis/acciones raras)"""
        for tecla in ("ctrl", "command", "shift", "option"):
            try:
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
                self._preparar_bloque_para_escribir()
            elif self.necesita_reposicionar:
                self._ir_a_linea(self.inicio_bloque + self.indice_linea + 1)
                time.sleep(random.uniform(0.1, 0.3))
                self.necesita_reposicionar = False

            self._escribir_siguiente_linea(tiempo_final)
        except pyautogui.FailSafeException:
            raise
        except Exception:
            logging.exception("Error editando bloque real; se continúa con la siguiente iteración")

    def _preparar_bloque_para_escribir(self) -> None:
        """Salta al bloque, lo selecciona y lo borra, dejando el cursor listo para escribir"""
        n = len(self.bloque_actual)
        self.necesita_reposicionar = False
        self._ir_a_linea(self.inicio_bloque + 1)
        time.sleep(random.uniform(0.1, 0.3))
        pyautogui.keyDown("shift")
        try:
            pyautogui.press("down", presses=n, interval=random.uniform(0.02, 0.05))
        finally:
            pyautogui.keyUp("shift")
        time.sleep(random.uniform(0.05, 0.15))
        pyautogui.press("backspace")
        time.sleep(random.uniform(0.05, 0.15))
        pyautogui.press("enter")
        time.sleep(random.uniform(0.05, 0.15))
        self._liberar_modificadores()

    def _escribir_siguiente_linea(self, tiempo_final: float) -> None:
        """Escribe la línea en curso; si quedó a medias, continúa desde donde se interrumpió"""
        linea = self.bloque_actual[self.indice_linea]

        if self.desplazamiento == 0:
            self._limpiar_linea_actual()
        else:
            pyautogui.press("end")
            time.sleep(random.uniform(0.05, 0.15))

        texto = linea[self.desplazamiento:]
        for c in texto:
            if not self._queda_tiempo_editor(tiempo_final):
                return
            pyautogui.write(c, interval=0)
            time.sleep(random.uniform(0.03, 0.08))
            self.desplazamiento += 1

        if self.indice_linea < len(self.bloque_actual) - 1:
            pyautogui.press("enter")
            time.sleep(random.uniform(0.1, 0.4))
        self.indice_linea += 1
        self.desplazamiento = 0

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
        """Borra cualquier sangría automática del editor y deja el cursor en la columna 0"""
        pyautogui.press("end")
        pyautogui.hotkey(self.cmd_key, "shift", "left")
        pyautogui.press("backspace")
        self._liberar_modificadores()

    def _cerrar_paneles(self) -> None:
        """Cierra con Escape cualquier panel emergente (autocompletado, emojis, quick input)"""
        pyautogui.press("esc")
        time.sleep(0.1)

    def _ir_a_linea(self, numero: int) -> None:
        """Salta a la línea indicada usando el diálogo 'Ir a línea' del editor (Ctrl+G)"""
        pyautogui.hotkey("ctrl", "g")
        time.sleep(0.15)
        pyautogui.hotkey(self.cmd_key, "a")
        pyautogui.write(str(numero), interval=0.03)
        time.sleep(0.1)
        pyautogui.press("enter")
        time.sleep(0.1)
        self._liberar_modificadores()

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

        if self.editor_actual:
            info = self.EDITOR_INFO[self.editor_actual]
            self._activar_si_necesario(info["proceso"], info["mac"])

        pyautogui.hotkey(self.cmd_key, 'a')
        time.sleep(0.15)
        pyautogui.hotkey(self.cmd_key, 'v')
        time.sleep(0.3)
        self._liberar_modificadores()

        self.lineas_actuales = codigo.splitlines()
        self.bloque_actual = None
        self.inicio_bloque = 0
        self.indice_linea = 0
        self.desplazamiento = 0
        self.necesita_reposicionar = True
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
