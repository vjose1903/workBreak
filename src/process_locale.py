"""Selecciona un locale UTF-8 disponible sin modificar el locale del proceso."""
from functools import lru_cache
import locale
import os
import subprocess


def _es_utf8(valor):
    return 'utf8' in valor.lower().replace('-', '')


@lru_cache(maxsize=1)
def locale_utf8_disponible():
    actual = locale.setlocale(locale.LC_CTYPE)  # Consulta; no cambia el locale global.
    if _es_utf8(locale.nl_langinfo(locale.CODESET)):
        return actual
    resultado = subprocess.run(
        ['/usr/bin/locale', '-a'], capture_output=True, text=True, encoding='ascii',
        env={**os.environ, 'LC_ALL': 'C'}, check=True, timeout=5)
    disponibles = sorted(nombre for nombre in resultado.stdout.splitlines() if _es_utf8(nombre))
    if not disponibles:
        raise RuntimeError('El sistema no ofrece un locale UTF-8 para los procesos auxiliares')
    region = actual.split('.', 1)[0].lower()
    idioma = region.split('_', 1)[0]
    for candidatos in (
            [n for n in disponibles if n.split('.', 1)[0].lower() == region],
            [n for n in disponibles if n.lower().startswith(idioma + '_')],
            [n for n in disponibles if n.lower().replace('-', '') in ('utf8', 'c.utf8')]):
        if candidatos:
            return candidatos[0]
    return disponibles[0]
