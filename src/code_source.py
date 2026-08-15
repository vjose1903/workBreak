import logging
import os
import random
from pathlib import Path

EXTENSIONES_REACT = (".tsx", ".jsx", ".ts", ".js")
DIRS_IGNORADOS = {
    "node_modules", "dist", "build", ".next", ".git", ".cache",
    "coverage", "out", ".venv", "venv", "target", ".turbo",
}
MAX_LINEAS = 400


class RealProjectSource:
    """Fuente de código basada en un directorio real.

    Escanea el directorio (ignorando node_modules, dist, build, etc.) y
    devuelve el contenido de archivos React/TS del proyecto real para usarlo
    como código a pegar en el editor.
    """

    def __init__(self, directorio):
        self.directorio = Path(directorio).expanduser().resolve()
        if not self.directorio.is_dir():
            raise ValueError(f"No existe el directorio: {self.directorio}")
        self.archivos = self._escanear()
        if not self.archivos:
            raise ValueError(
                f"No se encontraron archivos React/TypeScript en: {self.directorio}"
            )
        logging.info(f"RealProjectSource: {len(self.archivos)} archivos encontrados")

    def _escanear(self) -> list:
        """Escanea el directorio buscando archivos React/TS, excluyendo build dirs."""
        componentes, otros = [], []
        for raiz, dirs, nombres in os.walk(self.directorio):
            dirs[:] = [d for d in dirs if d not in DIRS_IGNORADOS]
            for nombre in nombres:
                ruta = Path(raiz) / nombre
                if nombre.endswith((".tsx", ".jsx")):
                    componentes.append(ruta)
                elif nombre.endswith((".ts", ".js")):
                    otros.append(ruta)
        # Los componentes React primero (más representativos para las capturas)
        return componentes + otros

    def obtener_codigo(self) -> str:
        """Devuelve el contenido de un archivo real elegido al azar (acotado en líneas)."""
        for _ in range(10):
            archivo = random.choice(self.archivos)
            try:
                contenido = archivo.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                logging.error(f"Error leyendo {archivo}: {e}")
                continue

            lineas = contenido.splitlines()
            if len(lineas) > MAX_LINEAS:
                lineas = lineas[:MAX_LINEAS]
            logging.info(f"Fuente real: {archivo} ({len(lineas)} líneas)")
            return "\n".join(lineas)

        logging.error("No se pudo leer ningún archivo de la fuente real")
        return "// No se pudo leer el archivo fuente"

    def __str__(self) -> str:
        return f"Directorio real: {self.directorio}"
