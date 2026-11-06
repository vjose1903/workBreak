from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from mac_accessibility import identidad_ventana_aplicacion


class VentanaEnfocadaTest(unittest.TestCase):
    def ventana(self, numero, pid, rectangulo):
        return {'kCGWindowNumber': numero, 'kCGWindowOwnerPID': pid, 'kCGWindowLayer': 0,
                'kCGWindowBounds': dict(zip(('X', 'Y', 'Width', 'Height'), rectangulo))}

    def test_emergente_que_sobresale_no_sustituye_la_ventana_enfocada(self):
        quartz = MagicMock()
        principal = self.ventana(7, 42, (-1000, 0, 900, 800))
        emergente = self.ventana(8, 42, (-1000, 750, 600, 200))
        otra = self.ventana(9, 99, (-1000, 0, 900, 800))
        quartz.CGWindowListCopyWindowInfo.return_value = [otra, emergente, principal]
        with patch.dict(sys.modules, {'Quartz': quartz}), \
                patch('mac_accessibility.aplicacion', return_value=SimpleNamespace(processIdentifier=lambda: 42)), \
                patch('mac_accessibility.pid_aplicacion_al_frente', return_value=42), \
                patch('mac_accessibility.rectangulo_aplicacion', return_value=(-1000, 0, 900, 800)):
            self.assertEqual(identidad_ventana_aplicacion('Google Chrome'), 7)

    def test_cambio_real_de_aplicacion_antes_o_durante_la_lectura_no_se_acepta(self):
        quartz = MagicMock()
        quartz.CGWindowListCopyWindowInfo.return_value = [self.ventana(7, 42, (0, 0, 900, 800))]
        for foco in ([99], [42, 99]):
            with self.subTest(foco=foco), patch.dict(sys.modules, {'Quartz': quartz}), \
                    patch('mac_accessibility.aplicacion', return_value=SimpleNamespace(processIdentifier=lambda: 42)), \
                    patch('mac_accessibility.pid_aplicacion_al_frente', side_effect=foco), \
                    patch('mac_accessibility.rectangulo_aplicacion', return_value=(0, 0, 900, 800)):
                self.assertIsNone(identidad_ventana_aplicacion('Google Chrome'))

    def test_cambio_a_otra_ventana_del_mismo_navegador_se_identifica(self):
        quartz = MagicMock()
        quartz.CGWindowListCopyWindowInfo.return_value = [self.ventana(7, 42, (0, 0, 900, 800)),
                                                        self.ventana(8, 42, (1000, 0, 900, 800))]
        with patch.dict(sys.modules, {'Quartz': quartz}), \
                patch('mac_accessibility.aplicacion', return_value=SimpleNamespace(processIdentifier=lambda: 42)), \
                patch('mac_accessibility.pid_aplicacion_al_frente', return_value=42), \
                patch('mac_accessibility.rectangulo_aplicacion', return_value=(1000, 0, 900, 800)):
            self.assertEqual(identidad_ventana_aplicacion('Google Chrome'), 8)
