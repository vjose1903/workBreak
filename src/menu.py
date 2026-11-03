import json
import logging
import math
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from code_generator import CodeGenerator
from code_source import RealProjectSource

NAVEGADORES_VALIDOS = ["chrome", "edge", "opera", "firefox"]
NAVEGADOR_NINGUNO = {"ninguno", "none", "no", "0", ""}
MODOS_INTERACCION = {"ambos": "Editor y navegador", "editor": "Solo editor", "web": "Solo navegador"}
MAX_HISTORIAL = 5
FASES_EDITOR = {
    "ambas": "Escritura y mouse",
    "escritura": "Solo escritura",
    "mouse": "Solo mouse",
}

RUTA_HISTORIAL = Path(__file__).resolve().parent.parent / "config_history.json"


def formatear_tiempo(minutos):
    if not minutos:
        return 'Indefinido'
    segundos = round(minutos * 60)
    return f'{segundos // 3600:02d}:{segundos % 3600 // 60:02d}:{segundos % 60:02d}'


@dataclass
class Configuracion:
    """Configuración completa del bot, construida desde el menú interactivo o los args CLI."""
    editor: str = field(default="vsCode", init=False)
    browser: Optional[str] = None
    paginas: List[str] = field(default_factory=list)
    fuente: Any = None
    fuente_descripcion: str = "Código React/TS aleatorio"
    tiempo: Optional[float] = None
    fases: str = "ambas"
    modo: str = "ambos"
    directorio: Optional[str] = None
    nombres_web: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.modo not in MODOS_INTERACCION:
            raise ValueError("Modo de interacción inválido")
        if self.fuente is None:
            self.fuente = CodeGenerator()
        if self.fases not in FASES_EDITOR:
            self.fases = "ambas"

    def resumen(self) -> str:
        tiempo_str = formatear_tiempo(self.tiempo)
        return (
            f"  Interacción   : {MODOS_INTERACCION[self.modo]}\n"
            f"  Editor        : {self.editor or 'NO DEFINIDO'}\n"
            f"  Navegador     : {self.browser or 'ninguno'}\n"
            f"  Webs          : {', '.join(self.paginas) if self.paginas else 'ninguna'}\n"
            f"  Fuente código : {self.fuente_descripcion}\n"
            f"  Fases editor  : {FASES_EDITOR[self.fases]}\n"
            f"  Tiempo        : {tiempo_str}"
        )


def _preguntar(mensaje: str, validas: Optional[set] = None, por_defecto: Optional[str] = None) -> str:
    """Pide una entrada al usuario hasta que sea válida (o acepta el valor por defecto)."""
    while True:
        try:
            entrada = input(mensaje).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSaliendo del bot...")
            raise SystemExit(0)
        if not entrada and por_defecto is not None:
            return por_defecto
        if validas is None or entrada in validas:
            return entrada
        print(f"  Entrada inválida. Usa: {', '.join(sorted(validas))}")


def _seleccionar_navegador(config: Configuracion) -> None:
    print(f"\n  Navegadores disponibles: {', '.join(NAVEGADORES_VALIDOS)}")
    print("  Escribe 'ninguno' si no quieres simular navegación web")
    browser = _preguntar("  Navegador a usar: ")
    if browser in NAVEGADOR_NINGUNO:
        config.browser = None
        config.paginas = []
    elif browser in NAVEGADORES_VALIDOS:
        config.browser = browser
    else:
        print(f"  Navegador desconocido '{browser}'; se usa ninguno")
        config.browser = None


def _seleccionar_webs(config: Configuracion) -> None:
    print("\n  Escribe las webs separadas por coma (ej: confluence.atlassian.net, stackoverflow.com)")
    print("  Deja vacío para no simular interacción web")
    entrada = input("  Webs: ").strip()
    config.paginas = [u.strip() for u in entrada.split(",") if u.strip()]


def _seleccionar_fuente(config: Configuracion) -> None:
    print("\n  Fuente de código:")
    print("    1 = Código React/TypeScript aleatorio")
    print("    2 = Directorio real con código React/TS (más realista)")
    opcion = _preguntar("  Opción: ", {"1", "2"})
    if opcion == "1":
        config.fuente = CodeGenerator()
        config.directorio = None
        config.fuente_descripcion = "Código React/TS aleatorio"
        return

    directorio = input("  Ruta del directorio con código React: ").strip().strip("\"'")
    if not directorio:
        print("  Ruta vacía; se mantiene la fuente actual")
        return
    try:
        config.fuente = RealProjectSource(directorio)
        config.fuente_descripcion = str(config.fuente)
    except ValueError as e:
        print(f"  ERROR: {e}")
        print("  Se mantiene la fuente actual")


def _seleccionar_tiempo(config: Configuracion) -> None:
    entrada = _preguntar("  Tiempo en minutos (0 o vacío = indefinido): ", por_defecto="0")
    try:
        tiempo = int(entrada)
    except ValueError:
        print("  No es un número; se mantiene la configuración actual")
        return
    config.tiempo = tiempo if tiempo > 0 else None


def _seleccionar_fases(config: Configuracion) -> None:
    print("\n  Fases del editor:")
    print("    1 = Escritura y mouse")
    print("    2 = Solo escritura")
    print("    3 = Solo mouse")
    opcion = _preguntar("  Opción: ", {"1", "2", "3"})
    config.fases = {"1": "ambas", "2": "escritura", "3": "mouse"}[opcion]


def menu_interactivo() -> Optional[Configuracion]:
    """Presenta el menú interactivo de configuración; devuelve None si el usuario sale."""
    print("=" * 60)
    print("  BOT DE ACTIVIDAD EN EL TRABAJO")
    print("  Configuración interactiva")
    print("=" * 60)

    config = Configuracion()

    while True:
        print("\n--- Configuración actual ---")
        print(config.resumen())
        print("----------------------------")
        print("  [1] Elegir navegador")
        print("  [2] Definir webs a simular")
        print("  [3] Elegir fuente de código")
        print("  [4] Definir tiempo (minutos)")
        print("  [5] Usar configuración previa")
        print("  [6] Elegir fases del editor")
        print("  [7] INICIAR BOT")
        print("  [8] Salir")
        print("  [9] Elegir interacción: editor, navegador o ambos")
        opcion = _preguntar("  Opción: ", {"1", "2", "3", "4", "5", "6", "7", "8", "9"})

        if opcion == "1":
            _seleccionar_navegador(config)
        elif opcion == "2":
            _seleccionar_webs(config)
        elif opcion == "3":
            _seleccionar_fuente(config)
        elif opcion == "4":
            _seleccionar_tiempo(config)
        elif opcion == "5":
            _cargar_config_previa(config)
        elif opcion == "6":
            _seleccionar_fases(config)
        elif opcion == "7":
            return config
        elif opcion == "8":
            return None
        elif opcion == "9":
            config.modo = _preguntar("  Interacción (ambos/editor/web): ", set(MODOS_INTERACCION))


def _config_a_dict(config: Configuracion) -> dict:
    """Convierte una configuración en un registro serializable para el historial."""
    directorio = str(config.fuente.directorio) if isinstance(config.fuente, RealProjectSource) else config.directorio
    es_directorio = directorio is not None
    return {
        "editor": config.editor,
        "browser": config.browser,
        "paginas": list(config.paginas),
        "nombres_web": {url: nombre for url, nombre in config.nombres_web.items() if url in config.paginas},
        "fuente_tipo": "directorio" if es_directorio else "aleatorio",
        "fuente_descripcion": config.fuente_descripcion,
        "directorio": directorio,
        "tiempo": config.tiempo,
        "fases": config.fases,
        "modo": config.modo,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _dict_a_config(d: dict, comprobar_cancelacion=None) -> Configuracion:
    """Reconstruye una configuración a partir de un registro del historial."""
    if not _registro_valido(d):
        raise ValueError("Configuración del historial inválida")
    if d.get("modo", "ambos") != "web" and d.get("fuente_tipo") == "directorio" and d.get("directorio"):
        try:
            fuente = RealProjectSource(d["directorio"], comprobar_cancelacion=comprobar_cancelacion)
            descripcion = str(fuente)
        except ValueError as e:
            logging.warning(f"No se pudo restaurar el directorio real '{d['directorio']}': {e}")
            fuente = CodeGenerator()
            descripcion = "Código React/TS aleatorio"
    else:
        fuente = CodeGenerator()
        descripcion = d.get("fuente_descripcion", "Código React/TS aleatorio")

    return Configuracion(
        browser=d.get("browser"),
        paginas=[p for p in (d.get("paginas") or []) if isinstance(p, str)],
        nombres_web=dict(d.get("nombres_web", {})),
        fuente=fuente,
        fuente_descripcion=descripcion,
        tiempo=d.get("tiempo"),
        fases=d.get("fases", "ambas"),
        modo=d.get("modo", "ambos"),
        directorio=d.get("directorio") if d.get("modo") == "web" and d.get("fuente_tipo") == "directorio" else None,
    )


def _registro_valido(registro) -> bool:
    if not isinstance(registro, dict):
        return False
    browser = registro.get('browser')
    paginas = registro.get('paginas', [])
    tiempo = registro.get('tiempo')
    fases = registro.get('fases', 'ambas')
    return (
        (browser is None or isinstance(browser, str) and browser in NAVEGADORES_VALIDOS)
        and isinstance(registro.get("nombres_web", {}), dict)
        and all(isinstance(url, str) and isinstance(nombre, str) and bool(nombre.strip())
                for url, nombre in registro.get("nombres_web", {}).items())
        and isinstance(paginas, list) and all(isinstance(p, str) for p in paginas)
        and (tiempo is None or type(tiempo) in (int, float) and tiempo > 0 and math.isfinite(tiempo))
        and isinstance(registro.get("modo", "ambos"), str) and registro.get("modo", "ambos") in MODOS_INTERACCION
        and isinstance(fases, str) and fases in FASES_EDITOR
        and isinstance(registro.get('fuente_descripcion', ''), str)
        and (registro.get('directorio') is None or isinstance(registro['directorio'], str))
    )


def cargar_historial() -> list:
    """Lee las configuraciones de las últimas sesiones; crea el archivo si no existe."""
    try:
        if not RUTA_HISTORIAL.exists():
            return []
        datos = json.loads(RUTA_HISTORIAL.read_text(encoding="utf-8"))
        if not isinstance(datos, list):
            return []
        validos = [registro for registro in datos if _registro_valido(registro)]
        if len(validos) != len(datos):
            logging.warning("Se descartaron registros inválidos del historial: %s", json.dumps({
                'descartados': len(datos) - len(validos)}))
        return validos[:MAX_HISTORIAL]
    except Exception as e:
        logging.warning(f"No se pudo leer el historial de configuraciones: {e}")
        return []


def guardar_historial(registros: list) -> None:
    """Guarda los registros de configuración en el archivo de historial."""
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         dir=RUTA_HISTORIAL.parent, delete=False) as archivo:
            temporal = Path(archivo.name)
            json.dump(registros, archivo, ensure_ascii=False, indent=2)
            archivo.flush()
            os.fsync(archivo.fileno())
        os.replace(temporal, RUTA_HISTORIAL)
    except Exception as e:
        logging.warning(f"No se pudo guardar el historial de configuraciones: {e}")
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)


def guardar_configuracion(config: Configuracion) -> None:
    """Guarda la configuración usada en la sesión; conserva solo las últimas 5."""
    registros = cargar_historial()
    nuevo = _config_a_dict(config)

    clave = {k: nuevo.get(k) for k in ("editor", "browser", "paginas", "fuente_tipo", "directorio", "tiempo", "fases", "modo", "nombres_web")}
    if registros:
        clave_ultimo = {k: registros[0].get(k) for k in clave}
        if clave_ultimo == clave:
            return

    registros.insert(0, nuevo)
    del registros[MAX_HISTORIAL:]
    guardar_historial(registros)


def _cargar_config_previa(config: Configuracion) -> bool:
    """Carga una de las configuraciones previas; la más reciente se auto-selecciona por defecto."""
    registros = cargar_historial()
    if not registros:
        print("  No hay configuraciones previas guardadas")
        return False

    print("\n  Configuraciones de las últimas sesiones:")
    for i, r in enumerate(registros, 1):
        editor = config.editor
        browser = r.get("browser") or "ninguno"
        webs = ", ".join(r.get("paginas") or []) or "ninguna"
        fuente = r.get("fuente_descripcion", "?")
        tiempo = formatear_tiempo(r.get("tiempo"))
        fases = FASES_EDITOR.get(r.get("fases"), FASES_EDITOR["ambas"])
        modo = MODOS_INTERACCION[r.get('modo', 'ambos')]
        print(f"    [{i}] {modo} | {editor} | {browser} | {webs} | {fuente} | {fases} | {tiempo} | {r.get('fecha', '')}")

    print("  (Enter = la más reciente)")
    opcion = _preguntar(
        f"  Selecciona una configuración [1-{len(registros)}]: ",
        {str(i) for i in range(1, len(registros) + 1)},
        por_defecto="1",
    )
    d = registros[int(opcion) - 1]
    previa = _dict_a_config(d)

    config.browser = previa.browser
    config.paginas = previa.paginas
    config.nombres_web = previa.nombres_web
    config.fuente = previa.fuente
    config.fuente_descripcion = previa.fuente_descripcion
    config.tiempo = previa.tiempo
    config.fases = previa.fases
    config.modo = previa.modo
    config.directorio = previa.directorio
    print("  Configuración previa cargada")
    return True


def configuracion_desde_args(args) -> Configuracion:
    """Construye la configuración a partir de argumentos CLI (modo avanzado)."""
    paginas = [u.strip() for u in args.web.split(",") if u.strip()] if args.web else []
    return Configuracion(
        browser=args.browser,
        paginas=paginas,
        fuente=CodeGenerator(),
        fuente_descripcion="Código React/TS aleatorio",
        tiempo=args.tiempo,
        modo=getattr(args, "modo", "ambos"),
    )
