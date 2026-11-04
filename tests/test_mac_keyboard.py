import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))


class MacKeyboardTest(unittest.TestCase):
    def setUp(self):
        self.quartz = MagicMock()
        self.quartz.kCGEventFlagMaskCommand = 1 << 20
        self.quartz.kCGEventFlagMaskControl = 1 << 18
        self.quartz.kCGEventFlagMaskShift = 1 << 17
        self.quartz.kCGEventFlagMaskAlternate = 1 << 19
        self.pyautogui = MagicMock()
        self.pyautogui.DARWIN_CATCH_UP_TIME = 0
        ruta = Path(__file__).resolve().parent.parent / 'src' / 'mac_keyboard.py'
        spec = importlib.util.spec_from_file_location('mac_keyboard_prueba', ruta)
        modulo = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'Quartz': self.quartz, 'pyautogui': self.pyautogui}):
            spec.loader.exec_module(modulo)
        self.teclado = modulo.MacKeyboard()

    def test_actividad_durante_preparacion_impide_pulsar(self):
        from user_activity import PausaPorActividad
        self.teclado.antes_evento = MagicMock(side_effect=[None, PausaPorActividad()])
        with self.assertRaises(PausaPorActividad):
            self.teclado.write('a')
        self.quartz.CGEventPost.assert_not_called()

    def test_eventos_propios_tienen_marca_y_fuente_privada(self):
        from user_activity import MARCA_TECLADO_BOT
        self.teclado.hotkey('command', 'z')
        for llamada in self.quartz.CGEventCreateKeyboardEvent.call_args_list:
            self.assertIs(llamada.args[0], self.quartz.CGEventSourceCreate.return_value)
        self.assertEqual(self.quartz.CGEventSetIntegerValueField.call_count, 2)
        for llamada in self.quartz.CGEventSetIntegerValueField.call_args_list:
            self.assertEqual(llamada.args[2], MARCA_TECLADO_BOT)

    def test_texto_no_hereda_modificadores_del_sistema(self):
        self.teclado.write('e :()')
        self.assertEqual(self.quartz.CGEventSetFlags.call_count, 10)
        for llamada in self.quartz.CGEventSetFlags.call_args_list:
            self.assertEqual(llamada.args[1], 0)
        self.assertEqual(self.quartz.CGEventKeyboardSetUnicodeString.call_count, 10)
        self.pyautogui.hotkey.assert_not_called()
        self.pyautogui.keyDown.assert_not_called()

    def test_ir_a_linea_lleva_solo_option_y_luego_texto_sin_modificadores(self):
        self.teclado.hotkey('option', 'g')
        self.teclado.write('42:1')
        flags = [llamada.args[1] for llamada in self.quartz.CGEventSetFlags.call_args_list]
        self.assertEqual(flags, [1 << 19, 1 << 19] + [0] * 8)
        self.pyautogui.failSafeCheck.assert_called()

    def test_failsafe_impide_enviar_eventos(self):
        self.pyautogui.failSafeCheck.side_effect = RuntimeError('parada')
        with self.assertRaisesRegex(RuntimeError, 'parada'):
            self.teclado.write('e')
        self.quartz.CGEventPost.assert_not_called()

    def test_pausa_se_consulta_antes_de_cada_caracter(self):
        from user_activity import PausaPorActividad
        self.teclado.antes_evento = MagicMock(side_effect=[None, None, PausaPorActividad()])
        with self.assertRaises(PausaPorActividad):
            self.teclado.write('ab')
        self.assertEqual(self.quartz.CGEventPost.call_count, 2)  # Solo down/up de la primera letra.

    def test_no_pulsa_si_no_puede_preparar_la_liberacion(self):
        self.quartz.CGEventCreateKeyboardEvent.side_effect = [object(), None]
        with self.assertRaisesRegex(RuntimeError, 'crear el evento'):
            self.teclado.write('a')
        self.quartz.CGEventPost.assert_not_called()

    def test_un_error_al_pulsar_intenta_liberar_la_tecla(self):
        pulsar, soltar = object(), object()
        self.quartz.CGEventCreateKeyboardEvent.side_effect = [pulsar, soltar]
        self.quartz.CGEventPost.side_effect = [RuntimeError('fallo del evento'), None]
        with self.assertRaisesRegex(RuntimeError, 'fallo del evento'):
            self.teclado.write('a')
        self.assertIs(self.quartz.CGEventPost.call_args_list[-1].args[1], soltar)

    def test_actividad_durante_pulsacion_libera_y_pausa_antes_del_siguiente_caracter(self):
        from user_activity import MonitorActividad, PausaPorActividad
        monitor = MonitorActividad()
        self.teclado.antes_evento = monitor.comprobar
        def publicar(*_):
            monitor.registrar()
        self.quartz.CGEventPost.side_effect = publicar
        with self.assertRaises(PausaPorActividad):
            self.teclado.write('ab')
        self.assertEqual(self.quartz.CGEventPost.call_count, 2)
        self.assertEqual([c.args[2] for c in self.quartz.CGEventCreateKeyboardEvent.call_args_list], [True, False])


if __name__ == '__main__':
    unittest.main()
