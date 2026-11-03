from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from session_lock import bloquear_sesion, SesionEnCurso


class BloqueoSesionTest(unittest.TestCase):
    def test_impide_sesiones_simultaneas_y_se_libera_incluso_con_error(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / 'sesion.lock'
            with self.assertRaisesRegex(ValueError, 'fallo'):
                with bloquear_sesion(ruta):
                    with self.assertRaises(SesionEnCurso):
                        with bloquear_sesion(ruta):
                            self.fail('Se admitió una segunda sesión')
                    raise ValueError('fallo')
            with bloquear_sesion(ruta):
                pass
