import logging
from dataclasses import dataclass, field
from typing import Any, List, Optional

from code_generator import CodeGenerator
from code_source import RealProjectSource

EDITORES_VALIDOS = ["vsCode", "cursor"]
NAVEGADORES_VALIDOS = ["chrome", "edge", "opera", "firefox"]
NAVEGADOR_NINGUNO = {"ninguno", "none", "no", "0", ""}


@dataclass
class Configuracion:
    """Configuración completa del bot, construida desde el menú interactivo o los args CLI."""
    editor: Optional[str] = None
    browser: Optional[str] = None
    paginas: List[str] = field(default_factory=list)
    fuente: Any = None
    fuente_descripcion: str = "Código React/TS aleatorio"
    tiempo: Optional[int] = None

    def __post_init__(self):
        if self.fuente is None:
            self.fuente = CodeGenerator()

    def resumen(self) -> str:
        tiempo_str = f"{self.tiempo} min" if self.tiempo else "indefinido"
        return (
            f"  Editor        : {self.editor or 'NO DEFINIDO'}\n"
            f"  Navegador     : {self.browser or 'ninguno'}\n"
            f"  Webs          : {', '.join(self.paginas) if self.paginas else 'ninguna'}\n"
            f"  Fuente código : {self.fuente_descripcion}\n"
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


def _seleccionar_editor(config: Configuracion) -> None:
    print(f"\n  Editores disponibles: {', '.join(EDITORES_VALIDOS)}")
    editor = _preguntar("  Editor a usar: ", set(EDITORES_VALIDOS))
    config.editor = editor


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
        print("  [1] Elegir editor")
        print("  [2] Elegir navegador")
        print("  [3] Definir webs a simular")
        print("  [4] Elegir fuente de código")
        print("  [5] Definir tiempo (minutos)")
        print("  [6] INICIAR BOT")
        print("  [7] Salir")
        opcion = _preguntar("  Opción: ", {"1", "2", "3", "4", "5", "6", "7"})

        if opcion == "1":
            _seleccionar_editor(config)
        elif opcion == "2":
            _seleccionar_navegador(config)
        elif opcion == "3":
            _seleccionar_webs(config)
        elif opcion == "4":
            _seleccionar_fuente(config)
        elif opcion == "5":
            _seleccionar_tiempo(config)
        elif opcion == "6":
            if not config.editor:
                print("\n  Debes elegir un editor antes de iniciar (opción 1)")
                continue
            return config
        elif opcion == "7":
            return None


def configuracion_desde_args(args) -> Configuracion:
    """Construye la configuración a partir de argumentos CLI (modo avanzado)."""
    paginas = [u.strip() for u in args.web.split(",") if u.strip()] if args.web else []
    return Configuracion(
        editor=args.editor,
        browser=args.browser,
        paginas=paginas,
        fuente=CodeGenerator(),
        fuente_descripcion="Código React/TS aleatorio",
        tiempo=args.tiempo,
    )
