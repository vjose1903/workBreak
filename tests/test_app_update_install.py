import hashlib
import io
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from app_update_install import preparar_descarga, ActualizacionCancelada, limpiar_descarga, crear_script_instalacion, instalar_y_reiniciar
from app_version import APP_ID, GITHUB_REPO


class InstalacionTest(unittest.TestCase):
    def datos(self):
        contenido = b'dmg de prueba'
        return contenido, {'version': '1.2.3', 'bytes': len(contenido),
            'sha256': hashlib.sha256(contenido).hexdigest(),
            'url': f'https://github.com/{GITHUB_REPO}/releases/download/v1.2.3/WorkBreak-1.2.3-macos-arm64.dmg'}

    def preparar(self, nueva, contenido, cancelar=None, identificador=APP_ID):
        respuesta = io.BytesIO(contenido)
        respuesta.geturl = lambda: nueva['url']

        def proceso(args, **kwargs):
            if '--expand' in args:
                destino = Path(args[-1])
                destino.mkdir()
                (destino / 'PackageInfo').write_text(
                    f'<pkg-info identifier="{identificador}" version="1.2.3" install-location="/Applications"/>')
            return subprocess.CompletedProcess(args, 0)

        def ejecutar(args, **kwargs):
            if '-mountpoint' in args:
                montaje = Path(args[args.index('-mountpoint') + 1])
                (montaje / 'WorkBreak-1.2.3-macos-arm64.pkg').write_bytes(b'pkg')
            return proceso(args, **kwargs)

        with patch('app_update_install.platform.machine', return_value='arm64'), \
                patch('app_update_install.urlopen', return_value=respuesta), \
                patch('app_update_install.ejecutar_cancelable', side_effect=ejecutar):
            return preparar_descarga(nueva, lambda texto: self.progreso.append(texto), cancelar or threading.Event())

    def setUp(self):
        self.progreso = []

    def test_descarga_comprueba_sha_tamano_y_paquete(self):
        contenido, nueva = self.datos()
        preparada = self.preparar(nueva, contenido)
        try:
            self.assertTrue(Path(preparada['paquete']).is_file())
            self.assertIn('Descargando actualización… 100%', self.progreso)
            self.assertEqual(self.progreso[-1], 'Verificando instalador…')
        finally:
            limpiar_descarga(preparada)

    def test_rechaza_sha_erroneo_descarga_truncada_y_excesiva(self):
        contenido, nueva = self.datos()
        for cuerpo in (b'contenido diferente', contenido[:-1], b'X' * len(contenido)):
            with self.subTest(cuerpo=cuerpo), self.assertRaises(ValueError):
                self.preparar(nueva, cuerpo)

    def test_rechaza_instalador_de_otra_aplicacion(self):
        contenido, nueva = self.datos()
        with self.assertRaisesRegex(ValueError, 'no corresponde'):
            self.preparar(nueva, contenido, identificador='com.otra.app')

    def test_cancelacion_interrumpe_sin_instalar(self):
        contenido, nueva = self.datos()
        cancelacion = threading.Event()
        cancelacion.set()
        with self.assertRaises(ActualizacionCancelada):
            self.preparar(nueva, contenido, cancelacion)

    def test_rechaza_url_o_metadatos_inseguros(self):
        contenido, nueva = self.datos()
        for cambio in ({'url': 'https://otro.example/app.dmg'}, {'sha256': ''}, {'bytes': True}, {'bytes': 0}):
            with self.subTest(cambio=cambio), self.assertRaises(ValueError):
                self.preparar({**nueva, **cambio}, contenido)

    def test_auxiliar_valida_sintaxis_y_escapa_rutas(self):
        preparada = {'carpeta': "/tmp/workbreak-update-a'b c", 'paquete': "/tmp/workbreak-update-a'b c/volumen/app.pkg"}
        script = crear_script_instalacion(preparada, 1234)
        subprocess.run(['/bin/sh', '-n'], input=script, text=True, check=True)
        self.assertIn('kill -0 1234', script)
        self.assertIn('with administrator privileges', script)
        self.assertIn('/usr/bin/open /Applications/WorkBreak.app', script)
        self.assertNotIn('sudo', script)

    def test_no_instala_desde_python_o_build(self):
        with patch('app_update_install.sys.frozen', False, create=True), \
                patch('app_update_install.subprocess.Popen') as lanzar:
            with self.assertRaisesRegex(ValueError, 'Aplicaciones'):
                instalar_y_reiniciar({})
        lanzar.assert_not_called()
