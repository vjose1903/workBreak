from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
import process_locale


class LocaleProcesoTest(unittest.TestCase):
    def test_conserva_el_locale_utf8_del_proceso_sin_cambiarlo(self):
        with patch.object(process_locale, 'locale') as sistema, patch.object(process_locale.subprocess, 'run') as ejecutar:
            sistema.setlocale.return_value = 'es_DO.UTF-8'
            sistema.nl_langinfo.return_value = 'UTF-8'
            self.assertEqual(process_locale.locale_utf8_disponible.__wrapped__(), 'es_DO.UTF-8')
            sistema.setlocale.assert_called_once_with(sistema.LC_CTYPE)
            ejecutar.assert_not_called()

    def test_elige_una_variante_instalada_y_no_presupone_region(self):
        for actual, disponibles, esperado in (
                ('es_ES.ISO8859-1', 'C\nes_ES.UTF-8\nfr_FR.UTF-8', 'es_ES.UTF-8'),
                ('C', 'C\nUTF-8\nja_JP.UTF-8', 'UTF-8'),
                ('C', 'C\nja_JP.UTF-8', 'ja_JP.UTF-8')):
            with self.subTest(actual=actual), patch.object(process_locale, 'locale') as sistema, \
                    patch.object(process_locale.subprocess, 'run', return_value=SimpleNamespace(stdout=disponibles)):
                sistema.setlocale.return_value = actual
                sistema.nl_langinfo.return_value = 'ASCII'
                self.assertEqual(process_locale.locale_utf8_disponible.__wrapped__(), esperado)

    def test_no_inventa_un_locale_si_no_hay_utf8_instalado(self):
        with patch.object(process_locale, 'locale') as sistema, \
                patch.object(process_locale.subprocess, 'run', return_value=SimpleNamespace(stdout='C\nPOSIX')):
            sistema.setlocale.return_value = 'C'
            sistema.nl_langinfo.return_value = 'ASCII'
            with self.assertRaises(RuntimeError):
                process_locale.locale_utf8_disponible.__wrapped__()
