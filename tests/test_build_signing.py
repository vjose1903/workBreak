"""La distribución no debe continuar silenciosamente con firma provisional."""
import importlib.util
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'workbreak_build', Path(__file__).resolve().parents[1] / 'scripts/build_macos.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class FirmaDistribucionTest(unittest.TestCase):
    def test_ci_rechaza_firma_ausente_y_equipos_distintos_antes_de_compilar(self):
        for entorno, argumentos in [
            ({'CI': 'true'}, []),
            ({'CI': 'true'}, ['--allow-adhoc']),
            ({'CI': 'true',
              'WORKBREAK_CODESIGN_IDENTITY': 'Developer ID Application: Nombre (AAAAAAAAAA)',
              'WORKBREAK_INSTALLER_IDENTITY': 'Developer ID Installer: Nombre (BBBBBBBBBB)',
              'WORKBREAK_TEAM_ID': 'AAAAAAAAAA'}, []),
        ]:
            with self.subTest(argumentos=argumentos, entorno=entorno), \
                    patch.dict(os.environ, entorno, clear=True), \
                    patch.object(build.sys, 'platform', 'darwin'), \
                    patch.object(build.sys, 'argv', ['build_macos.py'] + argumentos), \
                    patch('sys.stderr', new_callable=io.StringIO), \
                    patch.object(build, 'generar_icono') as compilar:
                with self.assertRaises(SystemExit) as error:
                    build.main()
                self.assertEqual(error.exception.code, 2)
                compilar.assert_not_called()
