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
    if cambio == 'major':
        return f'{mayor + 1}.0.0'
    if cambio == 'minor':
        return f'{mayor}.{menor + 1}.0'
    return f'{mayor}.{menor}.{parche + 1}'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Actualiza la versión de WorkBreak')
    parser.add_argument('cambio', choices=('patch', 'minor', 'major'))
    args = parser.parse_args()
    nueva = incrementar(VERSION, args.cambio)
    (ROOT / 'VERSION').write_text(nueva + '\n', encoding='utf-8')
    print(f'{VERSION} → {nueva}. Próximo tag: v{nueva}')
