import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from user_activity import MonitorActividad, PausaPorActividad, DetencionSolicitada


class MonitorActividadTest(unittest.TestCase):
    def test_detener_desde_interfaz_interrumpe_el_debounce_inmediatamente(self):
        monitor = MonitorActividad(solicitar_detencion=lambda: True)
        monitor.registrar()
        with self.assertRaises(DetencionSolicitada):
            monitor.esperar_inactividad()

    def test_detencion_permite_limpieza_sin_ignorar_actividad_del_usuario(self):
        monitor = MonitorActividad(solicitar_detencion=lambda: True)
        monitor.permitir_limpieza = True
        monitor.comprobar()
        monitor.registrar()
        with self.assertRaises(PausaPorActividad):
            monitor.comprobar()

    def test_parada_emergencia_se_comprueba_durante_el_debounce(self):
        monitor = MonitorActividad()
        monitor.registrar()
        monitor.comprobar_emergencia = MagicMock(side_effect=RuntimeError('emergencia'))
        with self.assertRaisesRegex(RuntimeError, 'emergencia'):
            monitor.esperar_inactividad()
        monitor.comprobar_emergencia.assert_called_once()

    def test_sin_actividad_no_hay_pausa(self):
        MonitorActividad().comprobar()

    def test_inicio_ignora_enter_y_activa_pausas_despues_de_cinco_segundos(self):
        monitor = MonitorActividad()
        reloj = [100.0]
        with patch('user_activity.time.monotonic', side_effect=lambda: reloj[0]), \
                patch('user_activity.threading.Thread') as hilo, \
                patch.object(monitor._listo, 'wait', return_value=True):
            hilo.return_value.start.side_effect = lambda: monitor.registrar(('tecla', 36), True)
            monitor.iniciar()
            monitor.registrar(('tecla', 36), False)
            reloj[0] = 104.999
            monitor.registrar(('mouse', 0), True)
            monitor.comprobar()
            self.assertFalse(monitor._pulsadas)
            self.assertIsNone(monitor._ultima)
            reloj[0] = 105
            monitor.registrar()
            with self.assertRaises(PausaPorActividad):
                monitor.comprobar()
        self.assertEqual(monitor.debounce, 10)
        self.assertEqual(monitor._ultima, 105)

    def test_cada_evento_reinicia_los_diez_segundos(self):
        monitor = MonitorActividad()
        reloj = [0.0]
        esperas = []

        def esperar(segundos):
            esperas.append(segundos)
            reloj[0] += segundos
            if reloj[0] == 2:
                monitor.registrar()  # Otra tecla/movimiento dos segundos después.

        with patch('user_activity.time.monotonic', side_effect=lambda: reloj[0]), \
                patch.object(monitor._condicion, 'wait', side_effect=esperar), \
                patch('user_activity.logging.info') as mensajes:
            monitor.registrar()
            with self.assertRaises(PausaPorActividad):
                monitor.comprobar()
            self.assertTrue(monitor.esperar_inactividad())
            monitor.comprobar()
            monitor.registrar()
            with self.assertRaises(PausaPorActividad):
                monitor.comprobar()
        self.assertEqual(esperas, [1] * 12)
        self.assertEqual(reloj[0], 12)
        textos = [llamada.args[0] for llamada in mensajes.call_args_list]
        self.assertTrue(any('Debounce reiniciado' in texto for texto in textos))
        self.assertTrue(any('9 segundos restantes' in texto for texto in textos))

    def test_actividad_cancela_una_espera_de_la_fase(self):
        monitor = MonitorActividad()
        with patch.object(monitor._condicion, 'wait', side_effect=lambda _: monitor.registrar()):
            with self.assertRaises(PausaPorActividad):
                monitor.esperar_intervalo(10)

    def test_liberacion_perdida_se_reconcilia_con_el_estado_fisico(self):
        monitor = MonitorActividad()
        monitor._esta_pulsada = lambda _: False
        reloj = [0.0]

        def esperar(segundos):
            reloj[0] += segundos

        with patch('user_activity.time.monotonic', side_effect=lambda: reloj[0]), \
                patch.object(monitor._condicion, 'wait', side_effect=esperar):
            monitor.registrar(('tecla', 1), True)
            reloj[0] = 2
            self.assertTrue(monitor.esperar_inactividad())
        self.assertFalse(monitor._pulsadas)
        self.assertEqual(reloj[0], 12)

    def test_sondeo_no_descarta_una_pulsacion_nueva(self):
        monitor = MonitorActividad()
        monitor.registrar(('tecla', 1), True)

        def estado(_):
            monitor.registrar(('tecla', 1), True)
            return False

        monitor._esta_pulsada = estado
        monitor.reconciliar_pulsadas()
        self.assertIn(('tecla', 1), monitor._pulsadas)

    def test_no_reanuda_mientras_se_mantiene_una_tecla_pulsada(self):
        monitor = MonitorActividad()
        reloj = [0.0]
        esperas = []

        def esperar(segundos):
            esperas.append(segundos)
            reloj[0] += segundos
            if reloj[0] == 13:
                monitor.registrar(('tecla', 1), False)

        with patch('user_activity.time.monotonic', side_effect=lambda: reloj[0]), \
                patch.object(monitor._condicion, 'wait', side_effect=esperar):
            monitor.registrar(('tecla', 1), True)
            self.assertTrue(monitor.esperar_inactividad())
        self.assertEqual(reloj[0], 23)
        self.assertEqual(esperas, [1] * 23)

    def test_no_reanuda_si_se_agota_el_limite_total(self):
        monitor = MonitorActividad()
        reloj = [0.0]

        def esperar(segundos):
            reloj[0] += segundos

        with patch('user_activity.time.monotonic', side_effect=lambda: reloj[0]), \
                patch.object(monitor._condicion, 'wait', side_effect=esperar):
            monitor.registrar()
            self.assertFalse(monitor.esperar_inactividad(limite=2))
            with self.assertRaises(PausaPorActividad):
                monitor.comprobar()

    def test_eventos_mac_del_bot_no_reinician_debounce(self):
        monitor = MonitorActividad()
        quartz = MagicMock()
        tipos = ['KeyDown', 'KeyUp', 'FlagsChanged', 'MouseMoved', 'LeftMouseDown',
                 'LeftMouseUp', 'RightMouseDown', 'RightMouseUp', 'OtherMouseDown',
                 'OtherMouseUp', 'LeftMouseDragged', 'RightMouseDragged',
                 'OtherMouseDragged', 'ScrollWheel']
        for numero, tipo in enumerate(tipos):
            setattr(quartz, 'kCGEvent' + tipo, numero)
        quartz.kCGEventTapDisabledByTimeout = -1
        quartz.kCGEventTapDisabledByUserInput = -2
        quartz.CGEventGetIntegerValueField.side_effect = lambda evento, _: evento['pid']

        def procesar(*_):
            callback = quartz.CGEventTapCreate.call_args.args[4]
            callback(None, quartz.kCGEventMouseMoved, {'pid': os.getpid()}, None)
            monitor.comprobar()  # El movimiento propio no pausa.
            callback(None, quartz.kCGEventKeyDown, {'pid': 0}, None)
            monitor._detener.set()

        quartz.CFRunLoopRunInMode.side_effect = procesar
        with patch.dict(sys.modules, {'Quartz': quartz}):
            monitor._escuchar_mac()
        self.assertEqual(monitor._version, 1)
        with self.assertRaises(PausaPorActividad):
            monitor.comprobar()


if __name__ == '__main__':
    unittest.main()
