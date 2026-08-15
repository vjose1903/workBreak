import logging
import os
import pyautogui
import random
import subprocess
import tempfile
import time

from base_automation import BaseAutomation, FailsafeActivo
from code_generator import CodeGenerator
from statistics_tracker import StatisticsTracker


class EditorInteractor(BaseAutomation):
    def __init__(self, stats_tracker: StatisticsTracker, fuente_codigo=None):
        super().__init__()
        pyautogui.PAUSE = 0.05

        self.stats_tracker = stats_tracker
        self.fuente_codigo = fuente_codigo or CodeGenerator()
        self.VALID_EDITORS = ["cursor", "vsCode"]
        self.EDITOR_STARTUP_TIME = 5
        self.EDITOR_WINDOW_OFFSET = 20
        self.EDITOR_ABIERTO = False
        self.editor_actual = None
        self._portapapeles_original = None
        self.ultimo_fragmento = None
        self.proyecto_simulado = None
        self.editor_commands = {
            "vsCode": ["code"],
            "cursor": ["cursor"] if self.is_windows else ["/Applications/Cursor.app/Contents/MacOS/Cursor"]
        }
        self.EDITOR_INFO = {
            "vsCode": {"proceso": "Visual Studio Code", "mac": "Visual Studio Code"},
            "cursor": {"proceso": "Cursor", "mac": "Cursor"},
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
        """Abre el editor una única vez por ejecución apuntando al proyecto simulado"""
        if self.EDITOR_ABIERTO:
            return

        try:
            ruta_proyecto = self._crear_proyecto_simulado()
            cmd = list(self.editor_commands[editor])
            if ruta_proyecto:
                cmd.append(os.path.join(ruta_proyecto, "src", "App.tsx"))
            else:
                logging.warning("Proyecto simulado no disponible; abriendo el editor sin argumento")

            self.ejecutar_comando(cmd)
            logging.info(f"Abriendo editor: {editor}")
            time.sleep(self.EDITOR_STARTUP_TIME)

            info = self.EDITOR_INFO[editor]
            if not self.activar_aplicacion(info["proceso"], info["mac"]):
                logging.warning("No se pudo activar la ventana del editor; fallback a mover el cursor")
                self.move_cursor_to_center()
            time.sleep(1)

            self.editor_actual = editor
            self.EDITOR_ABIERTO = True
        except Exception as e:
            self.manejar_error(f"Error al abrir el editor {editor}: {e}")

    def asegurar_editor_abierto(self, editor: str) -> None:
        """Asegura que el editor esté abierto y enfocado sin relanzarlo cada ciclo"""
        self.editor_actual = editor
        if not self.EDITOR_ABIERTO:
            self.abrir_editor(editor)
            return

        info = self.EDITOR_INFO[editor]
        self.activar_aplicacion(info["proceso"], info["mac"])
        time.sleep(1)

    def manejar_error(self, mensaje: str) -> None:
        """Registra el error y lo propaga para que el bot lo maneje (nunca sys.exit)"""
        logging.error(mensaje)
        raise RuntimeError(mensaje)

    def interactuar_editor(self) -> None:
        """Inyecta código una vez y alterna fases de escritura y mouse con duraciones variables"""
        tiempo_inicio = time.time()
        tiempo_restante = self.tiempo_restante()

        if tiempo_restante is not None and tiempo_restante <= 0:
            logging.info("Tiempo restante agotado; se omite la interacción con el editor")
            return

        if tiempo_restante is None:
            duracion = random.uniform(60, 240)
        else:
            duracion = min(random.uniform(60, 240), tiempo_restante)

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
        """Fase de escritura con duración variable: escribe y borra fragmentos solo al final del archivo"""
        duracion = self._duracion_fase_escritura()
        fin = min(time.monotonic() + duracion, tiempo_final)
        logging.info(f"Fase de escritura por {max(0.0, fin - time.monotonic()):.0f}s")

        if self.editor_actual:
            info = self.EDITOR_INFO[self.editor_actual]
            self.activar_aplicacion(info["proceso"], info["mac"])

        while time.monotonic() < fin:
            if not self._queda_tiempo_editor(tiempo_final):
                break
            self._escribir_y_borrar_fragmento()
            time.sleep(random.uniform(0.3, 1.5))

        if self._queda_tiempo_editor(tiempo_final):
            self._escribir_fragmento_al_final()

    def fase_mouse(self, tiempo_final: float) -> None:
        """Fase de mouse con duración variable: mueve el cursor, hace scroll y clics sin dañar el código"""
        duracion = self._duracion_fase_mouse()
        fin = min(time.monotonic() + duracion, tiempo_final)
        logging.info(f"Fase de mouse por {max(0.0, fin - time.monotonic()):.0f}s")

        while time.monotonic() < fin:
            if not self._queda_tiempo_editor(tiempo_final):
                break
            x = random.randint(-self.EDITOR_WINDOW_OFFSET, self.EDITOR_WINDOW_OFFSET)
            y = random.randint(-self.EDITOR_WINDOW_OFFSET, self.EDITOR_WINDOW_OFFSET)
            pyautogui.moveRel(x, y, duration=random.uniform(0.2, 0.6))

            if random.random() < 0.4:
                pyautogui.scroll(random.randint(-6, 6))

            if random.random() < 0.25:
                pyautogui.click()

            time.sleep(random.uniform(0.4, 2.0))

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

    def _escribir_y_borrar_fragmento(self) -> None:
        """Escribe un fragmento aleatorio al final del archivo y luego borra solo ese fragmento"""
        self._ir_al_final_del_archivo()
        fragmento = self.generar_texto_aleatorio(random.randint(4, 18))
        pyautogui.write(fragmento, interval=random.uniform(0.03, 0.12))
        self.ultimo_fragmento = fragmento
        time.sleep(random.uniform(0.4, 1.4))
        self._borrar_ultimo_fragmento()

    def _escribir_fragmento_al_final(self) -> None:
        """Deja un fragmento visible al final del archivo para que se note actividad de escritura"""
        self._ir_al_final_del_archivo()
        fragmento = self.generar_texto_aleatorio(random.randint(4, 14))
        pyautogui.write(fragmento, interval=random.uniform(0.03, 0.12))
        self.ultimo_fragmento = fragmento

    def _borrar_ultimo_fragmento(self) -> None:
        """Borra únicamente el último fragmento aleatorio escrito (no toca el código)"""
        if not self.ultimo_fragmento:
            return
        self._ir_al_final_del_archivo()
        pyautogui.press("backspace", presses=len(self.ultimo_fragmento),
                        interval=random.uniform(0.02, 0.08))
        self.ultimo_fragmento = None

    def _ir_al_final_del_archivo(self) -> None:
        """Mueve el cursor al final del archivo para que la escritura nunca dañe el código"""
        if self.is_windows:
            pyautogui.hotkey("ctrl", "end")
        else:
            pyautogui.hotkey("command", "down")
        time.sleep(0.05)

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
            self.activar_aplicacion(info["proceso"], info["mac"])

        pyautogui.hotkey(self.cmd_key, 'a')
        time.sleep(0.15)
        pyautogui.hotkey(self.cmd_key, 'v')
        time.sleep(0.3)

        lineas = len(codigo.splitlines())
        logging.info(f"Código inyectado: {lineas} líneas, {len(codigo)} caracteres")

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
