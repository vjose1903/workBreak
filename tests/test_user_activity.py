import os
import sys
import unittest
from types import SimpleNamespace
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
            self.assertIn(('mouse', 0), monitor._pulsadas)
            monitor.registrar(('mouse', 0), False)
            self.assertFalse(monitor._pulsadas)
            self.assertIsNone(monitor._ultima)
            reloj[0] = 105
            monitor.registrar()
            with self.assertRaises(PausaPorActividad):
                monitor.comprobar()
        self.assertEqual(monitor.debounce, 10)
        self.assertEqual(monitor._ultima, 105)

    def test_pulsacion_mantenida_en_el_margen_inicial_pausa_al_terminar_el_margen(self):
        monitor = MonitorActividad()
        monitor._detectar_desde = 105
        with patch('user_activity.time.monotonic', return_value=104):
            monitor.registrar(('tecla', 36), True)
            monitor.comprobar()
        with patch('user_activity.time.monotonic', return_value=105):
            with self.assertRaises(PausaPorActividad):
                monitor.comprobar()
        self.assertEqual(monitor._ultima, 105)

    def test_liberacion_perdida_en_el_margen_no_provoca_pausa_falsa(self):
        monitor = MonitorActividad()
        monitor._detectar_desde = 105
        with patch('user_activity.time.monotonic', return_value=104):
            monitor.registrar(('tecla', 36), True)
        monitor._esta_pulsada = lambda _: False
        with patch('user_activity.time.monotonic', return_value=105):
            monitor.comprobar()
        self.assertFalse(monitor._pulsadas)
        self.assertIsNone(monitor._ultima)

    def test_detecta_tecla_ya_pulsada_antes_de_crear_el_monitor(self):
        monitor = MonitorActividad()
        monitor._detectar_desde = 105
        monitor._pulsadas_fisicas = MagicMock(return_value=[('tecla', 36)])
        with patch('user_activity.time.monotonic', return_value=104):
            monitor.comprobar()
        monitor._pulsadas_fisicas.assert_not_called()
        with patch('user_activity.time.monotonic', return_value=105):
            with self.assertRaises(PausaPorActividad):
                monitor.comprobar()
        monitor._pulsadas_fisicas.assert_called_once()
        self.assertIn(('tecla', 36), monitor._pulsadas)

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

    def test_debounce_cero_espera_a_soltar_la_tecla(self):
        monitor = MonitorActividad(debounce=0)
        monitor.registrar(('tecla', 1), True)
        with patch.object(monitor._condicion, 'wait',
                          side_effect=lambda _: monitor.registrar(('tecla', 1), False)) as esperar:
            self.assertTrue(monitor.esperar_inactividad())
        esperar.assert_called_once()
        self.assertFalse(monitor._pulsadas)

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

    def test_teclas_y_modificadores_mac_pausan_incluso_en_margen_inicial(self):
        from user_activity import MARCA_TECLADO_BOT
        tipos = ['KeyDown', 'KeyUp', 'FlagsChanged', 'MouseMoved', 'LeftMouseDown',
                 'LeftMouseUp', 'RightMouseDown', 'RightMouseUp', 'OtherMouseDown',
                 'OtherMouseUp', 'LeftMouseDragged', 'RightMouseDragged',
                 'OtherMouseDragged', 'ScrollWheel']
        for codigo in (0x37, 0x36, 0x38, 0x3A, 0x3B, 0x3F, 0x39, 0x06):
            with self.subTest(codigo=codigo):
                monitor = MonitorActividad()
                monitor._detectar_desde = float('inf')
                quartz = MagicMock()
                quartz.CGEventSourceFlagsState.return_value = 0
                for numero, tipo in enumerate(tipos):
                    setattr(quartz, 'kCGEvent' + tipo, numero)
                quartz.kCGEventTapDisabledByTimeout = -1
                quartz.kCGEventTapDisabledByUserInput = -2
                quartz.kCGEventSourceUnixProcessID = 'pid'
                quartz.kCGEventSourceUserData = 'marca'
                quartz.kCGKeyboardEventKeycode = 'codigo'
                for indice, nombre in enumerate(('Command', 'Control', 'Shift', 'Alternate', 'SecondaryFn')):
                    setattr(quartz, 'kCGEventFlagMask' + nombre, 1 << (indice + 16))
                quartz.CGEventGetFlags.return_value = (1 << 21) - 1
                quartz.CGEventGetIntegerValueField.side_effect = lambda evento, campo: evento[campo]

                def procesar(*_):
                    callback = quartz.CGEventTapCreate.call_args.args[4]
                    tipo = quartz.kCGEventFlagsChanged if codigo != 0x06 else quartz.kCGEventKeyDown
                    evento = {'pid': os.getpid(), 'marca': MARCA_TECLADO_BOT, 'codigo': codigo}
                    callback(None, tipo, evento, None)
                    monitor.comprobar()  # Los atajos marcados del bot no pausan.
                    evento['marca'] = 0
                    callback(None, tipo, evento, None)
                    with self.assertRaises(PausaPorActividad):
                        monitor.comprobar()
                    monitor._detener.set()

                quartz.CFRunLoopRunInMode.side_effect = procesar
                with patch.dict(sys.modules, {'Quartz': quartz}):
                    monitor._escuchar_mac()
                self.assertEqual(quartz.CGEventTapCreate.call_args.args[0], quartz.kCGHIDEventTap)
                self.assertEqual(monitor._version, 1)

    def test_eventos_mac_del_bot_no_reinician_debounce(self):
        monitor = MonitorActividad()
        quartz = MagicMock()
        quartz.CGEventSourceFlagsState.return_value = 0
        for indice, nombre in enumerate(('Command', 'Control', 'Shift', 'Alternate', 'SecondaryFn')):
            setattr(quartz, 'kCGEventFlagMask' + nombre, 1 << (indice + 16))
        tipos = ['KeyDown', 'KeyUp', 'FlagsChanged', 'MouseMoved', 'LeftMouseDown',
                 'LeftMouseUp', 'RightMouseDown', 'RightMouseUp', 'OtherMouseDown',
                 'OtherMouseUp', 'LeftMouseDragged', 'RightMouseDragged',
                 'OtherMouseDragged', 'ScrollWheel']
        for numero, tipo in enumerate(tipos):
            setattr(quartz, 'kCGEvent' + tipo, numero)
        quartz.kCGEventTapDisabledByTimeout = -1
        quartz.kCGEventTapDisabledByUserInput = -2
        quartz.CGEventGetIntegerValueField.side_effect = lambda evento, _: evento['pid']

        quartz.CGEventGetLocation.side_effect = lambda evento: SimpleNamespace(x=evento['x'], y=evento['y'])

        def procesar(*_):
            callback = quartz.CGEventTapCreate.call_args.args[4]
            callback(None, quartz.kCGEventMouseMoved, {'pid': os.getpid(), 'x': 0, 'y': 0}, None)
            monitor.comprobar()  # El movimiento propio no pausa.
            # macOS reemite el movimiento del bot con otro origen al llegar a su destino.
            monitor.marcar_movimiento_bot(4000, 500)
            callback(None, quartz.kCGEventMouseMoved, {'pid': 0, 'x': 4000.5, 'y': 501}, None)
            monitor.comprobar()
            callback(None, quartz.kCGEventKeyDown, {'pid': 0}, None)
            monitor._detener.set()

        quartz.CFRunLoopRunInMode.side_effect = procesar
        with patch.dict(sys.modules, {'Quartz': quartz}):
            monitor._escuchar_mac()
        self.assertEqual(monitor._version, 1)
        with self.assertRaises(PausaPorActividad):
            monitor.comprobar()


    def test_movimiento_ajeno_lejos_del_destino_del_bot_si_pausa(self):
        monitor = MonitorActividad(margen_inicial=0)
        monitor._detectar_desde = 0
        monitor.marcar_movimiento_bot(4000, 500)
        self.assertTrue(monitor._es_movimiento_bot(4001, 499))
        self.assertFalse(monitor._es_movimiento_bot(3900, 500))
        monitor.marcar_movimiento_bot(4000, 500, margen=-1)
        self.assertFalse(monitor._es_movimiento_bot(4000, 500))

    def test_pausa_informa_su_causa(self):
        monitor = MonitorActividad(debounce=10)
        monitor._detectar_desde = 0
        reloj = [0.0]

        def esperar(segundos):
            reloj[0] += segundos

        with patch('user_activity.time.monotonic', side_effect=lambda: reloj[0]), \
                patch.object(monitor._condicion, 'wait', side_effect=esperar):
            monitor.registrar(causa='evento 5 del proceso 0')
            with self.assertLogs(level='INFO') as registros:
                self.assertTrue(monitor.esperar_inactividad())
        self.assertIn('causa: evento 5 del proceso 0', '\n'.join(registros.output))
        self.assertEqual(reloj[0], 10)

    def test_modificador_ya_mantenido_al_iniciar_se_registra_antes_del_bot(self):
        monitor = MonitorActividad(margen_inicial=0)
        monitor._detectar_desde = 0
        quartz = MagicMock()
        quartz.kCGEventFlagMaskCommand = 1 << 20
        quartz.kCGEventFlagMaskControl = 1 << 18
        quartz.kCGEventFlagMaskShift = 1 << 17
        quartz.kCGEventFlagMaskAlternate = 1 << 19
        quartz.kCGEventFlagMaskSecondaryFn = 1 << 23
        quartz.CGEventSourceFlagsState.return_value = quartz.kCGEventFlagMaskShift
        quartz.CGEventSourceKeyState.side_effect = lambda _estado, codigo: codigo == 0x38
        quartz.CGEventSourceButtonState.return_value = False
        quartz.CFRunLoopRunInMode.side_effect = lambda *_: monitor._detener.set()
        with patch.dict(sys.modules, {'Quartz': quartz}):
            monitor._escuchar_mac()
        self.assertIn(('modificador', 1 << 17), monitor._pulsadas)
        with self.assertRaises(PausaPorActividad):
            monitor.comprobar()
        # Los flags de un atajo sintético posterior no borran la pulsación física inicial.
        quartz.CGEventSourceFlagsState.return_value = 0
        self.assertTrue(monitor._esta_pulsada(('modificador', 1 << 17)))
        # Una liberación perdida también se recupera sin recibir flagsChanged.
        quartz.CGEventSourceKeyState.side_effect = lambda *_: False
        monitor.reconciliar_pulsadas()
        self.assertNotIn(('modificador', 1 << 17), monitor._pulsadas)
        monitor._pulsadas.add(('modificador', 1 << 17))
        quartz.kCGEventFlagsChanged = 'flags'
        quartz.kCGEventSourceUnixProcessID = 'pid'
        quartz.kCGEventSourceUserData = 'marca'
        quartz.kCGKeyboardEventKeycode = 'codigo'
        quartz.CGEventGetIntegerValueField.side_effect = lambda evento, campo: evento[campo]
        quartz.CGEventGetFlags.return_value = 0
        quartz.CGEventSourceKeyState.side_effect = lambda *_: False
        callback = quartz.CGEventTapCreate.call_args.args[4]
        callback(None, 'flags', {'pid': os.getpid() + 1, 'codigo': 0x38, 'marca': 0}, None)
        self.assertNotIn(('modificador', 1 << 17), monitor._pulsadas)
        self.assertFalse(monitor._esta_pulsada(('modificador', 1 << 17)))

    def test_modificadores_que_dejan_los_atajos_del_bot_no_cuentan_como_pulsados(self):
        monitor = MonitorActividad()
        quartz = MagicMock()
        quartz.CGEventSourceFlagsState.return_value = 0
        for indice, nombre in enumerate(('Command', 'Control', 'Shift', 'Alternate', 'SecondaryFn')):
            setattr(quartz, 'kCGEventFlagMask' + nombre, 1 << (indice + 16))
        quartz.CFRunLoopRunInMode.side_effect = lambda *_: monitor._detener.set()
        # macOS reporta ⌘ izquierdo (55) pulsado tras un atajo del bot; Enter (36) sí es real.
        quartz.CGEventSourceKeyState.side_effect = lambda _estado, codigo: codigo in (36, 55)
        quartz.CGEventSourceButtonState.return_value = False
        with patch.dict(sys.modules, {'Quartz': quartz}):
            monitor._escuchar_mac()
            self.assertEqual(monitor._pulsadas_fisicas(), [('tecla', 36)])


if __name__ == '__main__':
    unittest.main()
