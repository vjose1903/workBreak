"""Exclusión de sesiones que comparten teclado, mouse y portapapeles."""
from contextlib import contextmanager
from pathlib import Path
import os
import tempfile


class SesionEnCurso(RuntimeError):
    pass


@contextmanager
def bloquear_sesion(ruta=None):
    ruta = Path(ruta) if ruta else Path(tempfile.gettempdir()) / 'workbreak-automation.lock'
    with ruta.open('a+b') as archivo:
        if os.name == 'nt':
            import msvcrt
            archivo.seek(0, 2)
            if archivo.tell() == 0:
                archivo.write(b'0')
                archivo.flush()
            archivo.seek(0)
            try:
                msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise SesionEnCurso('Ya hay un bot ejecutándose. Detén la otra sesión antes de iniciar.') from error
            try:
                yield
            finally:
                archivo.seek(0)
                msvcrt.locking(archivo.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(archivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise SesionEnCurso('Ya hay un bot ejecutándose. Detén la otra sesión antes de iniciar.') from error
            try:
                yield
            finally:
                fcntl.flock(archivo, fcntl.LOCK_UN)
