"""Descarga verificada y entrega al instalador nativo después de cerrar WorkBreak."""
import hashlib
import json
import logging
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from app_version import APP_ID, GITHUB_REPO, VERSION, version_numerica


class ActualizacionCancelada(Exception):
    pass


def ejecutar_cancelable(args, cancelar, timeout):
    if cancelar.is_set():
        raise ActualizacionCancelada()
    limite = time.monotonic() + timeout
    proceso = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        while True:
            if cancelar.is_set():
                raise ActualizacionCancelada()
            if time.monotonic() >= limite:
                raise subprocess.TimeoutExpired(args, timeout)
            try:
                salida, error = proceso.communicate(timeout=0.1)
                if proceso.returncode:
                    raise subprocess.CalledProcessError(proceso.returncode, args, salida, error)
                return
            except subprocess.TimeoutExpired:
                continue
    finally:
        if proceso.poll() is None:
            proceso.terminate()
            try:
                proceso.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                proceso.kill()
                proceso.communicate()


def limpiar_descarga(preparada):
    raiz = Path(preparada['carpeta'])
    montaje = raiz / 'volumen'
    if os.path.ismount(montaje):
        subprocess.run(['/usr/bin/hdiutil', 'detach', str(montaje)],
                       check=True, capture_output=True, timeout=3)
    shutil.rmtree(raiz, ignore_errors=False)


def preparar_descarga(nueva, informar, cancelar):
    import certifi
    if version_numerica(nueva['version']) <= version_numerica(VERSION):
        raise ValueError('La actualización debe ser posterior a la versión instalada')
    arquitectura = platform.machine()
    nombre = f"WorkBreak-{nueva['version']}-macos-{arquitectura}"
    url = f"https://github.com/{GITHUB_REPO}/releases/download/v{nueva['version']}/{nombre}.dmg"
    if nueva['url'] != url or arquitectura not in ('arm64', 'x86_64'):
        raise ValueError('La descarga no corresponde a este Mac y al repositorio de WorkBreak')
    if not re.fullmatch(r'[0-9a-f]{64}', nueva.get('sha256', '')):
        raise ValueError('La Release no tiene una suma SHA-256 válida')
    tamano = nueva.get('bytes')
    if type(tamano) is not int or not 0 < tamano <= 512 * 1024 * 1024:
        raise ValueError('El tamaño de la actualización no es válido')
    carpeta = Path(tempfile.mkdtemp(prefix='workbreak-update-'))
    preparada = {'carpeta': str(carpeta), 'version': nueva['version']}
    try:
        def comprobar_cancelacion():
            if cancelar.is_set():
                raise ActualizacionCancelada()

        comprobar_cancelacion()
        dmg = carpeta / (nombre + '.dmg')
        digest = hashlib.sha256()
        recibidos = 0
        limite_descarga = time.monotonic() + 900
        contexto = ssl.create_default_context(cafile=certifi.where())
        with urlopen(Request(url, headers={'User-Agent': 'WorkBreak-Updater'}),
                     timeout=15, context=contexto) as respuesta, dmg.open('xb') as salida:
            if not respuesta.geturl().startswith('https://'):
                raise ValueError('La descarga no utiliza HTTPS')
            while True:
                comprobar_cancelacion()
                if time.monotonic() >= limite_descarga:
                    raise TimeoutError('La descarga superó el tiempo máximo de 15 minutos')
                bloque = respuesta.read1(256 * 1024)
                comprobar_cancelacion()
                if not bloque:
                    break
                recibidos += len(bloque)
                if recibidos > tamano:
                    raise ValueError('La descarga supera el tamaño anunciado')
                salida.write(bloque)
                digest.update(bloque)
                informar(f'Descargando actualización… {recibidos * 100 // tamano}%')
        if recibidos != tamano or digest.hexdigest() != nueva['sha256']:
            raise ValueError('La descarga está incompleta o su SHA-256 no coincide. No se instalará.')
        comprobar_cancelacion()
        informar('Verificando instalador…')
        montaje = carpeta / 'volumen'
        montaje.mkdir()
        ejecutar_cancelable(['/usr/bin/hdiutil', 'attach', '-readonly', '-nobrowse',
                        '-mountpoint', str(montaje), str(dmg)],
                       cancelar=cancelar, timeout=60)
        comprobar_cancelacion()
        paquete = montaje / (nombre + '.pkg')
        if not paquete.is_file() or paquete.is_symlink():
            raise ValueError('El DMG no contiene el instalador esperado')
        expandido = carpeta / 'metadatos'
        ejecutar_cancelable(['/usr/sbin/pkgutil', '--expand', str(paquete), str(expandido)],
                       cancelar=cancelar, timeout=30)
        info = ElementTree.parse(expandido / 'PackageInfo').getroot()
        if (info.get('identifier') != APP_ID or info.get('version') != nueva['version']
                or info.get('install-location') != '/Applications'):
            raise ValueError('El instalador no corresponde a la versión de WorkBreak anunciada')
        comprobar_cancelacion()
        preparada['paquete'] = str(paquete)
        return preparada
    except BaseException:
        try:
            limpiar_descarga(preparada)
        except Exception as error:
            logging.warning('No se pudo limpiar la descarga: %s', json.dumps({'carpeta': str(carpeta), 'error': str(error)}))
        raise


def crear_script_instalacion(preparada, pid):
    """El auxiliar no depende de Python ni de archivos del bundle que será reemplazado."""
    carpeta = shlex.quote(preparada['carpeta'])
    montaje = shlex.quote(str(Path(preparada['carpeta']) / 'volumen'))
    comando = shlex.join(['/usr/sbin/installer', '-pkg', preparada['paquete'], '-target', '/'])
    applescript = 'do shell script ' + json.dumps(comando, ensure_ascii=False) + ' with administrator privileges'
    alerta = ('display alert "No se pudo actualizar WorkBreak" message '
              '"La instalación se canceló o falló. Se intentará abrir la aplicación existente. '
              'Consulta ~/Library/Logs/WorkBreak/update.log."')
    return f'''#!/bin/sh
set -u
limpiar() {{
  /usr/bin/hdiutil detach {montaje} >/dev/null 2>&1 || return
  /bin/rm -rf {carpeta}
}}
trap limpiar EXIT
contador=0
while /bin/kill -0 {int(pid)} 2>/dev/null; do
  contador=$((contador + 1))
  if [ "$contador" -gt 60 ]; then
    /usr/bin/osascript -e {shlex.quote(alerta)}
    exit 1
  fi
  /bin/sleep 1
done
if ! /usr/bin/osascript -e {shlex.quote(applescript)}; then
  /usr/bin/osascript -e {shlex.quote(alerta)}
fi
if [ -d /Applications/WB.app ]; then
  /usr/bin/open /Applications/WB.app
else
  /usr/bin/open /Applications/WorkBreak.app
fi
'''


def instalar_y_reiniciar(preparada):
    destino = Path('/Applications/WB.app/Contents/MacOS/WorkBreak')
    if not getattr(sys, 'frozen', False) or Path(sys.executable).resolve() != destino.resolve():
        raise ValueError('La instalación automática requiere abrir WorkBreak desde Aplicaciones, no desde Python o build/.')
    carpeta = Path(preparada['carpeta'])
    script = carpeta / 'instalar.sh'
    script.write_text(crear_script_instalacion(preparada, os.getpid()), encoding='utf-8')
    script.chmod(0o700)
    registro = Path.home() / 'Library/Logs/WorkBreak/update.log'
    registro.parent.mkdir(parents=True, exist_ok=True)
    with registro.open('ab') as log:
        proceso = subprocess.Popen(['/bin/sh', str(script)], stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=log, start_new_session=True,
                                   close_fds=True, cwd=carpeta)
    # Detectar fallos inmediatos antes de solicitar el cierre de la aplicación.
    time.sleep(0.1)
    if proceso.poll() is not None:
        raise RuntimeError('No se pudo iniciar el instalador. Consulta update.log.')
    return proceso
