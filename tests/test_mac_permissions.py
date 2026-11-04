import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from mac_permissions import permisos_faltantes


class PermisosMacTest(unittest.TestCase):
    def test_detecta_cada_permiso_y_reconsulta_tras_autorizar(self):
        quartz = MagicMock()
        confianza = MagicMock()
        with patch.dict(sys.modules, {'Quartz': quartz}), \
                patch('mac_accessibility._api', return_value={'AXIsProcessTrusted': confianza}):
            for accesibilidad, entrada, esperado in (
                (False, False, ['accesibilidad', 'entrada']),
                (True, False, ['entrada']), (False, True, ['accesibilidad']), (True, True, [])):
                confianza.return_value = accesibilidad
                quartz.CGPreflightListenEventAccess.return_value = entrada
                self.assertEqual(permisos_faltantes(), esperado)
        quartz.CGRequestListenEventAccess.assert_not_called()
