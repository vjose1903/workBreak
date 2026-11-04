import logging
import os
import random
import stat
from pathlib import Path

EXTENSIONES_REACT = (".tsx", ".jsx", ".ts", ".js")
DIRS_IGNORADOS = {
    "node_modules", "dist", "build", ".next", ".git", ".cache",
    "coverage", "out", ".venv", "venv", "target", ".turbo",
}
MIN_LINEAS = 20
MAX_LINEAS = 400
MAX_BYTES = 2 * 1024 * 1024


class RealProjectSource:
    """Fuente de código basada en un directorio real.

    Escanea el directorio (ignorando node_modules, dist, build, etc.) y
    devuelve el contenido de archivos React/TS del proyecto real para usarlo
    como código a pegar en el editor. Solo considera archivos con más de 20
    y menos de 400 líneas de código.
    """

    def __init__(self, directorio, comprobar_cancelacion=None):
        self.comprobar_cancelacion = comprobar_cancelacion
        self.directorio = Path(directorio).expanduser().resolve()
        if not self.directorio.is_dir():
            raise ValueError(f"No existe el directorio: {self.directorio}")
        self.archivos = self._escanear()
        self._ultimo_archivo = None
        if not self.archivos:
            raise ValueError(
                f"No se encontraron archivos React/TypeScript de 20 a 400 líneas en: {self.directorio}"
            )
        logging.info(f"RealProjectSource: {len(self.archivos)} archivos encontrados")

    def _leer_lineas(self, ruta):
        # O_NONBLOCK y fstat evitan bloquear si el archivo se sustituye por un FIFO.
        descriptor = os.open(ruta, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as entrada:
            info = os.fstat(entrada.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                return []
            datos = bytearray()
            while len(datos) <= MAX_BYTES:
                if self.comprobar_cancelacion:
                    self.comprobar_cancelacion()
                bloque = entrada.read(min(65536, MAX_BYTES + 1 - len(datos)))
                if not bloque:
                    break
                datos.extend(bloque)
            if len(datos) > MAX_BYTES:
                return []
            return datos.decode('utf-8', errors='replace').splitlines()

    def _contar_lineas(self, ruta) -> int:
        try:
            return len(self._leer_lineas(ruta))
        except OSError:
            return -1

    def _escanear(self) -> list:
        """Escanea el directorio buscando archivos React/TS de 20 a 400 líneas."""
        componentes, otros = [], []
        for raiz, dirs, nombres in os.walk(self.directorio):
            if self.comprobar_cancelacion:
                self.comprobar_cancelacion()
            dirs[:] = [d for d in dirs if d not in DIRS_IGNORADOS]
            for nombre in nombres:
                if self.comprobar_cancelacion:
                    self.comprobar_cancelacion()
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
        candidatos = [archivo for archivo in self.archivos if archivo != self._ultimo_archivo]
        if not candidatos:
            candidatos = list(self.archivos)
        random.shuffle(candidatos)
        if self._ultimo_archivo is not None and self._ultimo_archivo not in candidatos:
            candidatos.append(self._ultimo_archivo)
        for archivo in candidatos:
            if self.comprobar_cancelacion:
                self.comprobar_cancelacion()
            try:
                lineas = self._leer_lineas(archivo)
            except OSError as e:
                logging.error(f"Error leyendo {archivo}: {e}")
                continue

            if not MIN_LINEAS <= len(lineas) <= MAX_LINEAS:
                continue
            self._ultimo_archivo = archivo
            logging.info(f"Fuente real: {archivo} ({len(lineas)} líneas)")
            return "\n".join(lineas)

        logging.error("No se pudo leer ningún archivo de la fuente real")
        raise ValueError('No quedan archivos fuente válidos y legibles')

    @property
    def nombre_archivo(self):
        """Nombre del último archivo entregado, para nombrar la pestaña del editor."""
        return self._ultimo_archivo.name if self._ultimo_archivo is not None else None

    def __str__(self) -> str:
        return f"Directorio real: {self.directorio}"
