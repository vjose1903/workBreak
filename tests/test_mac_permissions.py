import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from mac_permissions import permisos_faltantes


class PermisosMacTest(unittest.TestCase):
    def test_detecta_cada_permiso_y_reconsulta_tras_autorizar(self):
        quartz = MagicMock()
        quartz.kCGEventKeyDown = 10
        quartz.kCGEventKeyUp = 11
        quartz.kCGEventFlagsChanged = 12
        quartz.CGEventTapCreate.return_value = None
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

    def test_preflight_negativo_no_bloquea_si_el_observador_funciona(self):
        quartz = MagicMock()
        quartz.kCGEventKeyDown = 10
        quartz.kCGEventKeyUp = 11
        quartz.kCGEventFlagsChanged = 12
        quartz.CGPreflightListenEventAccess.return_value = False
        quartz.CGEventTapIsEnabled.return_value = True
        tap = quartz.CGEventTapCreate.return_value
        with patch.dict(sys.modules, {'Quartz': quartz}), \
                patch('mac_accessibility._api', return_value={'AXIsProcessTrusted': lambda: True}):
            self.assertEqual(permisos_faltantes(), [])
        quartz.CGEventTapEnable.assert_called_once_with(tap, False)
        quartz.CFMachPortInvalidate.assert_called_once_with(tap)
        quartz.CFRunLoopAddSource.assert_not_called()
        quartz.CGRequestListenEventAccess.assert_not_called()

    def test_observador_desactivado_no_cuenta_como_permiso(self):
        quartz = MagicMock()
        quartz.kCGEventKeyDown = 10
        quartz.kCGEventKeyUp = 11
        quartz.kCGEventFlagsChanged = 12
        quartz.CGPreflightListenEventAccess.return_value = False
        quartz.CGEventTapIsEnabled.return_value = False
        with patch.dict(sys.modules, {'Quartz': quartz}), \
                patch('mac_accessibility._api', return_value={'AXIsProcessTrusted': lambda: True}):
            self.assertEqual(permisos_faltantes(), ['entrada'])
        quartz.CFMachPortInvalidate.assert_called_once()
