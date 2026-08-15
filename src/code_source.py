import logging
import os
import random
from pathlib import Path

EXTENSIONES_REACT = (".tsx", ".jsx", ".ts", ".js")
DIRS_IGNORADOS = {
    "node_modules", "dist", "build", ".next", ".git", ".cache",
    "coverage", "out", ".venv", "venv", "target", ".turbo",
}
MIN_LINEAS = 20
MAX_LINEAS = 400


class RealProjectSource:
    """Fuente de código basada en un directorio real.

    Escanea el directorio (ignorando node_modules, dist, build, etc.) y
    devuelve el contenido de archivos React/TS del proyecto real para usarlo
    como código a pegar en el editor. Solo considera archivos con más de 20
    y menos de 400 líneas de código.
    """

    def __init__(self, directorio):
        self.directorio = Path(directorio).expanduser().resolve()
        if not self.directorio.is_dir():
            raise ValueError(f"No existe el directorio: {self.directorio}")
        self.archivos = self._escanear()
        if not self.archivos:
            raise ValueError(
                f"No se encontraron archivos React/TypeScript de 20 a 400 líneas en: {self.directorio}"
            )
        logging.info(f"RealProjectSource: {len(self.archivos)} archivos encontrados")

    def _contar_lineas(self, ruta) -> int:
        """Cuenta las líneas del archivo; deja de contar al superar MAX_LINEAS."""
        try:
            with open(ruta, encoding="utf-8", errors="replace") as f:
                n = 0
                for _ in f:
                    n += 1
                    if n > MAX_LINEAS:
                        return n
                return n
        except Exception:
            return -1

    def _escanear(self) -> list:
        """Escanea el directorio buscando archivos React/TS de 20 a 400 líneas."""
        componentes, otros = [], []
        for raiz, dirs, nombres in os.walk(self.directorio):
            dirs[:] = [d for d in dirs if d not in DIRS_IGNORADOS]
            for nombre in nombres:
                if not nombre.endswith(EXTENSIONES_REACT):
                    continue
                ruta = Path(raiz) / nombre
                lineas = self._contar_lineas(ruta)
                if lineas < MIN_LINEAS or lineas > MAX_LINEAS:
                    continue
                if nombre.endswith((".tsx", ".jsx")):
                    componentes.append(ruta)
                else:
                    otros.append(ruta)
        # Los componentes React primero (más representativos para las capturas)
        return componentes + otros

    def obtener_codigo(self) -> str:
        """Devuelve el contenido completo de un archivo real elegido al azar."""
        for _ in range(10):
            archivo = random.choice(self.archivos)
            try:
                contenido = archivo.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                logging.error(f"Error leyendo {archivo}: {e}")
                continue

            lineas = contenido.splitlines()
            logging.info(f"Fuente real: {archivo} ({len(lineas)} líneas)")
            return "\n".join(lineas)

        logging.error("No se pudo leer ningún archivo de la fuente real")
        return "// No se pudo leer el archivo fuente"

    def __str__(self) -> str:
        return f"Directorio real: {self.directorio}"
