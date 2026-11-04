import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from editor_shortcut import resolver_atajo_mac


class AtajoEditorTest(unittest.TestCase):
    def test_lee_atajo_del_menu_y_rechaza_ausencias_o_formatos_ambiguos(self):
        # No crea eventos: solo valida la respuesta del lector de accesibilidad.
        teclado = SimpleNamespace(MacKeyboard=SimpleNamespace(KEY_CODES={'g': 5, 'l': 37}))
        with patch.dict(sys.modules, {'mac_keyboard': teclado}):
            for respuesta, esperado in [('G\t10\n', ('option', 'g')),
                                         ('L\t12\n', ('ctrl', 'l')),
                                         ('G\t0\n', ('command', 'g'))]:
                ejecutar = lambda *args, **kwargs: SimpleNamespace(stdout=respuesta)
                self.assertEqual(resolver_atajo_mac('editor.bundle', ejecutar), esperado)
            for respuesta in ('', 'missing value\t8', 'G\t8', 'G\t16', 'GG\t10'):
                with self.subTest(respuesta=respuesta), self.assertRaises(ValueError):
                    resolver_atajo_mac('editor.bundle', lambda *a, **k: SimpleNamespace(stdout=respuesta))
        with self.assertRaises(subprocess.TimeoutExpired):
            resolver_atajo_mac('editor.bundle', lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired('osascript', 10)))
