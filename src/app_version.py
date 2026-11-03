import re
from app_paths import recurso

APP_ID = 'com.vjose1903.workbreak'
GITHUB_REPO = 'vjose1903/workBreak'


def version_numerica(texto):
    if not isinstance(texto, str) or not re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', texto):
        raise ValueError('La versión debe tener el formato X.Y.Z o vX.Y.Z')
    return tuple(int(parte) for parte in texto.removeprefix('v').split('.'))


VERSION = recurso('VERSION').read_text(encoding='utf-8').strip()
version_numerica(VERSION)
