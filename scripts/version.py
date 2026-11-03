#!/usr/bin/env python3
"""Incrementa VERSION; crear y publicar el tag sigue siendo una acción explícita."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))
from app_version import VERSION, version_numerica


def incrementar(version, cambio):
    mayor, menor, parche = version_numerica(version)
    if cambio not in ('patch', 'minor', 'major'):
        raise ValueError('Cambio de versión inválido')
    if cambio == 'major':
        nueva = (mayor + 1, 0, 0)
    elif cambio == 'minor':
        nueva = (mayor, menor + 1, 0)
    else:
        nueva = (mayor, menor, parche + 1)
    if any(valor > limite for valor, limite in zip(nueva, (9999, 99, 99))):
        raise ValueError('La versión supera el límite de macOS: 9999.99.99')
    return '.'.join(map(str, nueva))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Actualiza la versión de WorkBreak')
    parser.add_argument('cambio', choices=('patch', 'minor', 'major'))
    args = parser.parse_args()
    try:
        nueva = incrementar(VERSION, args.cambio)
    except ValueError as error:
        parser.error(str(error))
    (ROOT / 'VERSION').write_text(nueva + '\n', encoding='utf-8')
    print(f'{VERSION} → {nueva}. Próximo tag: v{nueva}')
