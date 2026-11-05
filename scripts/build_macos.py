#!/usr/bin/env python3
"""Genera app, instalador y DMG versionados sin escribir en /Applications."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))
from app_version import APP_ID, VERSION, version_numerica


def ejecutar(*args):
    subprocess.run([str(arg) for arg in args], check=True, cwd=ROOT)


def generar_icono(destino):
    from AppKit import (NSImage, NSBitmapImageRep, NSGraphicsContext,
                        NSDeviceRGBColorSpace, NSBitmapImageFileTypePNG,
                        NSCompositingOperationSourceOver)
    imagen = NSImage.alloc().initWithContentsOfFile_(str(ROOT / 'assets/icon.svg'))
    if imagen is None:
        raise ValueError('No se pudo leer assets/icon.svg')
    iconset = destino / 'WorkBreak.iconset'
    iconset.mkdir()
    for base in (16, 32, 128, 256, 512):
        for escala in (1, 2):
            lado = base * escala
            rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
                None, lado, lado, 8, 4, True, False, NSDeviceRGBColorSpace, 0, 0)
            contexto = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
            NSGraphicsContext.saveGraphicsState()
            try:
                NSGraphicsContext.setCurrentContext_(contexto)
                ancho, alto = imagen.size()
                factor = lado / max(ancho, alto)
                imagen.drawInRect_fromRect_operation_fraction_(
                    (((lado - ancho * factor) / 2, (lado - alto * factor) / 2), (ancho * factor, alto * factor)),
                    ((0, 0), (ancho, alto)), NSCompositingOperationSourceOver, 1)
            finally:
                NSGraphicsContext.restoreGraphicsState()
            nombre = f'icon_{base}x{base}' + ('@2x' if escala == 2 else '') + '.png'
            if not rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {}).writeToFile_atomically_(str(iconset / nombre), True):
                raise OSError('No se pudo generar el icono')
    icono = destino / 'WorkBreak.icns'
    ejecutar('iconutil', '-c', 'icns', iconset, '-o', icono)
    return icono


def script_preinstall():
    return ('#!/bin/sh\nif /usr/bin/pgrep -x WorkBreak >/dev/null; then\n'
            '  echo "Cierra WB desde su menú antes de instalar o actualizar." >&2\n'
            '  exit 1\nfi\n'
            'anterior="${3%/}/Applications/WorkBreak.app"\n'
            'destino="${3%/}/Applications/WB.app"\n'
            'if [ -d "$anterior" ] && [ ! -L "$anterior" ] && [ ! -e "$destino" ] && [ ! -L "$destino" ]; then\n'
            '  identificador=$(/usr/libexec/PlistBuddy -c "Print :CFBundleIdentifier" "$anterior/Contents/Info.plist" 2>/dev/null) || exit 1\n'
            f'  if [ "$identificador" = "{APP_ID}" ]; then\n'
            '    /bin/mv "$anterior" "$destino" || exit 1\n'
            '  fi\nfi\nexit 0\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-migrate', action='store_true', help='No copiar el historial local a Application Support')
    parser.add_argument('--allow-adhoc', action='store_true', help='Firma provisional solo para desarrollo local')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('El DMG debe compilarse en macOS')
    identidad = os.environ.get('WORKBREAK_CODESIGN_IDENTITY', '').strip()
    instalador = os.environ.get('WORKBREAK_INSTALLER_IDENTITY', '').strip()
    equipo = os.environ.get('WORKBREAK_TEAM_ID', '').strip()
    if args.allow_adhoc and os.environ.get('CI'):
        parser.error('--allow-adhoc solo se permite fuera de CI')
    provisional = args.allow_adhoc
    if provisional:
        identidad = '-'
    elif (not identidad.startswith('Developer ID Application:')
          or not instalador.startswith('Developer ID Installer:')
          or not re.fullmatch(r'[A-Z0-9]{10}', equipo)
          or not identidad.endswith(f'({equipo})')
          or not instalador.endswith(f'({equipo})')):
        parser.error('La distribución requiere Developer ID Application, Developer ID Installer '
                     'y WORKBREAK_TEAM_ID del mismo equipo. No se permite firma ad hoc en CI.')
    tag = os.environ.get('GITHUB_REF_NAME') if os.environ.get('GITHUB_REF_TYPE') == 'tag' else None
    if tag and tag != 'v' + VERSION:
        parser.error(f'El tag {tag} no coincide con VERSION ({VERSION})')
    if any(numero > limite for numero, limite in zip(version_numerica(VERSION), (9999, 99, 99))):
        parser.error('macOS admite como máximo la versión 9999.99.99')
    arquitectura = platform.machine()
    nombre = f'WorkBreak-{VERSION}-macos-{arquitectura}'
    salida = ROOT / 'dist'
    trabajo = ROOT / 'build' / nombre
    if trabajo.exists():
        shutil.rmtree(trabajo)  # Solo artefactos de esta compilación.
    trabajo.mkdir(parents=True)
    salida.mkdir(exist_ok=True)
    icono = generar_icono(trabajo)
    permisos = trabajo / 'entitlements.plist'
    # PyObjC genera callbacks nativos; libffi de Intel no utiliza MAP_JIT.
    entitlements = {'com.apple.security.automation.apple-events': True,
                    'com.apple.security.cs.allow-jit': True}
    if arquitectura == 'x86_64':
        entitlements['com.apple.security.cs.allow-unsigned-executable-memory'] = True
    permisos.write_bytes(plistlib.dumps(entitlements))
    ejecutar(sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--onedir',
             '--name', 'WorkBreak', '--osx-bundle-identifier', APP_ID, '--icon', icono,
             '--codesign-identity', identidad, '--osx-entitlements-file', permisos,
             '--add-data', f'{ROOT / "assets"}:assets', '--add-data', f'{ROOT / "VERSION"}:.',
             '--distpath', trabajo / 'app', '--workpath', trabajo / 'pyinstaller',
             '--specpath', trabajo, ROOT / 'src/main.py')
    app = trabajo / 'app/WorkBreak.app'
    destino_app = app.with_name('WB.app')
    app.rename(destino_app)
    app = destino_app
    plist = app / 'Contents/Info.plist'
    info = plistlib.loads(plist.read_bytes())
    info.update(CFBundleName='WB', CFBundleDisplayName='WB',
                CFBundleShortVersionString=VERSION, CFBundleVersion=VERSION,
                LSUIElement=True, LSMinimumSystemVersion='15.0', NSRequiresAquaSystemAppearance=False,
                NSAppleEventsUsageDescription='WorkBreak necesita activar y verificar el editor y el navegador para realizar las interacciones configuradas.')
    plist.write_bytes(plistlib.dumps(info))
    firma = ['codesign', '--force', '--deep', '--sign', identidad, '--entitlements', permisos]
    if identidad != '-':
        firma += ['--timestamp', '--options', 'runtime']
    ejecutar(*firma, app)
    ejecutar('codesign', '--verify', '--deep', '--strict', app)
    if identidad != '-':
        firma_real = subprocess.run(['codesign', '-dv', '--verbose=4', str(app)],
                                    capture_output=True, text=True, check=True).stderr
        if (f'TeamIdentifier={equipo}' not in firma_real.splitlines()
                or f'Identifier={APP_ID}' not in firma_real.splitlines()
                or f'Authority={identidad}' not in firma_real.splitlines()):
            raise RuntimeError('La identidad de la app firmada no coincide con el equipo configurado')
    permisos_firmados = subprocess.run(
        ['codesign', '-d', '--entitlements', ':-', str(app)],
        capture_output=True, check=True).stdout
    if plistlib.loads(permisos_firmados) != entitlements:
        raise RuntimeError('Los permisos del ejecutable firmado no coinciden con los requeridos por PyObjC')
    comprobacion = trabajo / 'package-check.json'
    subprocess.run([str(app / 'Contents/MacOS/WorkBreak'), '--comprobar-paquete', str(comprobacion)],
                   check=True, timeout=60)
    reporte = json.loads(comprobacion.read_text())
    if not (reporte['version'] == VERSION and reporte['hijo']['version'] == VERSION
            and reporte['hijo']['automatizacion_importada'] and reporte['hijo']['certificados_https']
            and reporte['icono'] and reporte['recursos']):
        raise RuntimeError('Falló la comprobación del ejecutable distribuido')
    escenario = trabajo / 'payload'
    escenario.mkdir()
    ejecutar('ditto', app, escenario / 'WB.app')
    componentes = trabajo / 'components.plist'
    componentes.write_bytes(plistlib.dumps([{
        'RootRelativeBundlePath': 'WB.app', 'BundleIsRelocatable': False,
        'BundleIsVersionChecked': True, 'BundleHasStrictIdentifier': True,
        'BundleOverwriteAction': 'upgrade',
    }]))
    scripts = trabajo / 'installer-scripts'
    scripts.mkdir()
    preinstall = scripts / 'preinstall'
    preinstall.write_text(script_preinstall())
    preinstall.chmod(0o755)
    paquete = salida / (nombre + '.pkg')
    ejecutar('pkgbuild', '--root', escenario, '--component-plist', componentes, '--scripts', scripts,
             '--identifier', APP_ID, '--version', VERSION, '--install-location', '/Applications', paquete)
    if instalador:
        firmado = trabajo / 'signed.pkg'
        ejecutar('productsign', '--sign', instalador, paquete, firmado)
        shutil.copy2(firmado, paquete)
    contenido = trabajo / 'dmg'
    contenido.mkdir()
    shutil.copy2(paquete, contenido / paquete.name)
    (contenido / 'LEEME.txt').write_text(
        f'WorkBreak {VERSION}\n\nAbre el archivo .pkg para instalar o actualizar WB en Aplicaciones.\n'
        'Cierra WB antes de actualizar. No borres la aplicación anterior.\n'
        'La configuración se conserva en ~/Library/Application Support/WorkBreak/.\n'
        'Al abrir WB por primera vez, permite Accesibilidad, Monitorización de entrada y Automatización.\n'
        'Después de una actualización sin firma Developer ID, macOS puede pedir renovar estos permisos.\n', encoding='utf-8')
    dmg = salida / (nombre + '.dmg')
    if dmg.exists():
        dmg.unlink()
    ejecutar('hdiutil', 'create', '-volname', f'WorkBreak {VERSION}', '-srcfolder', contenido,
             '-format', 'UDZO', '-ov', dmg)
    notary = os.environ.get('WORKBREAK_NOTARY_PROFILE')
    if notary:
        if identidad == '-' or not instalador:
            parser.error('La notarización requiere las identidades Developer ID de app e instalador')
        ejecutar('xcrun', 'notarytool', 'submit', dmg, '--keychain-profile', notary, '--wait')
        ejecutar('xcrun', 'stapler', 'staple', dmg)
    sumas = salida / (nombre + '.sha256')
    with sumas.open('w') as archivo_sumas:
        for archivo in (paquete, dmg):
            digest = hashlib.sha256()
            with archivo.open('rb') as entrada:
                for bloque in iter(lambda: entrada.read(1024 * 1024), b''):
                    digest.update(bloque)
            archivo_sumas.write(f'{digest.hexdigest()}  {archivo.name}\n')
    if not args.no_migrate and not os.environ.get('CI'):
        from app_paths import migrar_historial
        migrar_historial(ROOT / 'config_history.json')
    print(json.dumps({'version': VERSION, 'arquitectura': arquitectura,
                      'dmg': str(dmg), 'pkg': str(paquete), 'firma': identidad}, ensure_ascii=False))


if __name__ == '__main__':
    main()
