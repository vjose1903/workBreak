import importlib.util
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))
spec = importlib.util.spec_from_file_location('build_macos_name_test', ROOT / 'scripts/build_macos.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


@unittest.skipUnless(sys.platform == 'darwin', 'Migración del instalador de macOS')
class NombreAppTest(unittest.TestCase):
    def test_migracion_renombra_solo_la_app_anterior_y_no_reemplaza_wb(self):
        for identificador, wb_existente, migrar in [(build.APP_ID, False, True),
                                                   ('otra.app', False, False),
                                                   (build.APP_ID, True, False)]:
            with self.subTest(identificador=identificador, wb_existente=wb_existente), \
                    tempfile.TemporaryDirectory() as carpeta:
                raiz = Path(carpeta)
                anterior = raiz / 'Applications/WorkBreak.app'
                destino = raiz / 'Applications/WB.app'
                (anterior / 'Contents').mkdir(parents=True)
                (anterior / 'Contents/Info.plist').write_bytes(
                    plistlib.dumps({'CFBundleIdentifier': identificador}))
                if wb_existente:
                    destino.mkdir()
                    (destino / 'conservar').write_text('existente')
                # Simular que la app está cerrada; el resto del script es el del instalador.
                script = build.script_preinstall().replace('/usr/bin/pgrep -x "(WorkBreak|WB)"', '/usr/bin/false')
                subprocess.run(['/bin/sh', '-s', '--', 'paquete', '/', str(raiz)],
                               input=script, text=True, check=True)
                self.assertEqual(anterior.exists(), not migrar)
                self.assertEqual((destino / 'Contents/Info.plist').exists(), migrar)
                if wb_existente:
                    self.assertEqual((destino / 'conservar').read_text(), 'existente')
