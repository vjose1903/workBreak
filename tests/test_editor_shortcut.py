import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
import editor_shortcut
from mac_accessibility import PermisoAccesibilidad


class AtajoEditorTest(unittest.TestCase):
    def resolver(self, respuesta):
        reloj = [0.0]

        def esperar(segundos):
            reloj[0] += segundos

        teclado = SimpleNamespace(MacKeyboard=SimpleNamespace(KEY_CODES={'g': 5, 'l': 37}))
        with patch.dict(sys.modules, {'mac_keyboard': teclado}), \
                patch.object(editor_shortcut.time, 'monotonic', side_effect=lambda: reloj[0]), \
                patch.object(editor_shortcut, 'leer_atajo', return_value=respuesta):
            return editor_shortcut.resolver_atajo_mac('editor.bundle', esperar)

    def test_lee_modificadores_y_rechaza_atajos_inseguros(self):
        for respuesta, esperado in [(('G', 10), ('option', 'g')),
                                     (('L', 12), ('ctrl', 'l')),
                                     (('G', 0), ('command', 'g'))]:
            self.assertEqual(self.resolver(respuesta), esperado)
        for respuesta in (('', 8), ('G', 8), ('G', 16), ('GG', 10)):
            with self.subTest(respuesta=respuesta), self.assertRaises(ValueError):
                self.resolver(respuesta)

    def test_permiso_rechazado_no_se_reintenta(self):
        with patch.object(editor_shortcut, 'leer_atajo',
                          side_effect=PermisoAccesibilidad('Proceso no autorizado')) as leer:
            with self.assertRaisesRegex(PermisoAccesibilidad, 'Proceso no autorizado'):
                editor_shortcut.resolver_atajo_mac('editor.bundle', lambda _: None)
        leer.assert_called_once()

    def test_no_acepta_un_atajo_que_cambia_durante_la_carga(self):
        reloj = [0.0]
        def esperar(segundos):
            reloj[0] += segundos
        with patch.object(editor_shortcut.time, 'monotonic', side_effect=lambda: reloj[0]), \
                patch.object(editor_shortcut, 'leer_atajo',
                             side_effect=lambda *_: ('G', 10 if int(reloj[0]) % 2 else 0)):
            with self.assertRaisesRegex(ValueError, 'no se estabilizó'):
                editor_shortcut.resolver_atajo_mac('editor.bundle', esperar)
