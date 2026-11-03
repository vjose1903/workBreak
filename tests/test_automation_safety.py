import os
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from user_activity import MonitorActividad, PausaPorActividad


class FailSafeException(Exception):
    pass


# Estas pruebas no importan los controladores reales de teclado/pantalla.
teclado = MagicMock()
teclado.FailSafeException = FailSafeException
teclado.size.return_value = (1920, 1080)
with patch.dict(sys.modules, {'pyautogui': teclado}):
    from editor_interactor import EditorInteractor, EditorNoDisponible
    from statistics_tracker import StatisticsTracker
    from web_interactor import WebInteractor
    from automation_bot import AutomationBot


class AutomationSafetyTest(unittest.TestCase):
    def setUp(self):
        teclado.reset_mock(side_effect=True)
        teclado.size.return_value = (1920, 1080)
        self.editor = EditorInteractor(StatisticsTracker())
        self.web = WebInteractor(StatisticsTracker())
        # Nunca enviar eventos Quartz reales, aunque las pruebas se ejecuten en un Mac.
        for interactor in (self.editor, self.web):
            interactor._mac_keyboard = SimpleNamespace(
                hotkey=lambda *args, **kwargs: teclado.hotkey(*args, **kwargs),
                press=lambda *args, **kwargs: teclado.press(*args, **kwargs),
                write=lambda *args, **kwargs: teclado.write(*args, **kwargs),
            )
        self.web.set_browser('chrome')
        self.pausa = patch('time.sleep')
        self.pausa.start()
        self.addCleanup(self.pausa.stop)
        captura = patch.object(self.editor, '_guardar_linea_actual_mac')
        captura.start()
        self.addCleanup(captura.stop)

    def test_foco_anterior_no_evita_reactivacion(self):
        with patch.object(self.editor, 'activar_aplicacion', return_value=False) as activar:
            self.assertFalse(self.editor._activar_si_necesario('Code.exe', 'Visual Studio Code'))
            self.assertFalse(self.editor._activar_si_necesario('Code.exe', 'Visual Studio Code'))
        self.assertEqual(activar.call_count, 2)

    def test_navegador_y_pruebas_comparten_la_misma_clase_de_pausa(self):
        self.assertIs(self.web._procesar_pagina.__globals__['PausaPorActividad'], PausaPorActividad)

    def test_proceso_auxiliar_se_cancela_si_interviene_el_usuario(self):
        monitor = MagicMock()
        monitor.comprobar.side_effect = [None, None, PausaPorActividad()]
        self.editor.monitor_actividad = monitor
        proceso = MagicMock()
        proceso.poll.return_value = None
        proceso.communicate.side_effect = [subprocess.TimeoutExpired('osascript', 0.02), ('', '')]
        with patch('base_automation.subprocess.Popen', return_value=proceso):
            with self.assertRaises(PausaPorActividad):
                self.editor._ejecutar_proceso(['osascript', '-e', 'activate'])
        proceso.terminate.assert_called_once()
        proceso.kill.assert_not_called()

    def test_reanudacion_web_no_reinicia_el_editor(self):
        bot = AutomationBot.__new__(AutomationBot)
        bot._turno_actual = 'web'
        bot.editor_interactor = MagicMock()
        bot.web_interactor = MagicMock()
        bot.ejecutar_tareas('vsCode', ['https://example.com'])
        bot.editor_interactor.asegurar_editor_abierto.assert_not_called()
        bot.editor_interactor.interactuar_editor.assert_not_called()
        bot.web_interactor.interactuar_web.assert_called_once()
        self.assertEqual(bot._turno_actual, 'editor')

    def test_portapapeles_copiado_en_pausa_se_conserva_al_final(self):
        self.editor._portapapeles_original = 'antiguo'
        self.editor.portapapeles_bot['ultimo'] = 'bot'
        with patch.object(self.editor, 'leer_portapapeles', return_value='texto nuevo del usuario'):
            self.editor.conservar_portapapeles_usuario()
        with patch.object(self.editor, 'leer_portapapeles', return_value='bot'), \
                patch.object(self.editor, 'copiar_al_portapapeles', return_value=True) as copiar:
            self.editor.restaurar_portapapeles()
        copiar.assert_called_once_with('texto nuevo del usuario')

    def test_portapapeles_ajeno_no_se_sobrescribe_al_salir(self):
        self.editor._portapapeles_original = 'antiguo'
        self.editor.portapapeles_bot['ultimo'] = 'bot'
        with patch.object(self.editor, 'leer_portapapeles', return_value='texto nuevo del usuario'), \
                patch.object(self.editor, 'copiar_al_portapapeles') as copiar:
            self.editor.restaurar_portapapeles()
        copiar.assert_not_called()

    def test_pausa_editor_registra_el_trabajo_antes_de_esperar(self):
        self.editor.lineas_actuales = ['codigo cargado']
        with patch.object(self.editor, 'fase_escritura', side_effect=PausaPorActividad), \
                patch.object(self.editor, 'registrar_tiempo_interaccion') as registrar:
            with self.assertRaises(PausaPorActividad):
                self.editor.interactuar_editor(duracion_maxima=1)
        registrar.assert_called_once()

    def test_pausa_web_registra_el_trabajo_antes_de_esperar(self):
        with patch.object(self.web, '_move_to', side_effect=PausaPorActividad), \
                patch.object(self.web, 'registrar_tiempo_interaccion') as registrar:
            with self.assertRaises(PausaPorActividad):
                self.web.interactuar_con_pagina('https://example.com')
        registrar.assert_called_once()
        self.assertIsNotNone(self.web._visita_restante)

    def test_visita_intervenida_se_retoma_sin_abrir_ni_cerrar_pestanas(self):
        url = 'https://example.com'
        self.web._contexto = {'abierta': True, 'navegada': True, 'intervenida': True,
                              'pagina': url, 'url': url}
        with patch.object(self.web, 'activar_navegador', return_value=True), \
                patch.object(self.web, '_leer_url_actual', return_value=url), \
                patch.object(self.web, 'interactuar_con_pagina', side_effect=[PausaPorActividad(), None]):
            with self.assertRaises(PausaPorActividad):
                self.web._procesar_pagina(url)
            self.web._procesar_pagina(url)
        teclado.hotkey.assert_not_called()
        self.assertIsNotNone(self.web._contexto)

    def test_otra_pestana_no_se_navega_ni_se_cierra(self):
        url = 'https://example.com'
        self.web._contexto = {'abierta': True, 'navegada': True, 'intervenida': True,
                              'pagina': url, 'url': url}
        with patch.object(self.web, 'activar_navegador', return_value=True), \
                patch.object(self.web, '_leer_url_actual', return_value='https://otro.example'), \
                patch.object(self.web, 'interactuar_con_pagina') as interactuar:
            with self.assertRaisesRegex(RuntimeError, 'pestaña cambió'):
                self.web._procesar_pagina(url)
        interactuar.assert_not_called()
        teclado.hotkey.assert_not_called()

    def test_navegacion_pendiente_conserva_pestana_y_reintenta_en_otra(self):
        url = 'https://example.com'
        anterior = {'abierta': True, 'navegada': True, 'intervenida': True,
                    'pagina': url, 'url': url, 'navegacion_pendiente': True}
        self.web._contexto = anterior
        with patch.object(self.web, 'activar_navegador', return_value=True), \
                patch.object(self.web, 'copiar_al_portapapeles', return_value=True), \
                patch.object(self.web, '_leer_url_actual', return_value='https://destino.example'), \
                patch.object(self.web, 'interactuar_con_pagina') as interactuar:
            self.web._procesar_pagina(url)
        self.assertEqual(teclado.hotkey.call_args_list[0], unittest.mock.call(self.web.cmd_key, 't'))
        interactuar.assert_called_once()
        self.assertTrue(anterior['abierta'])

    def test_pausa_antes_de_confirmar_url_mantiene_navegacion_pendiente(self):
        with patch.object(self.web, 'activar_navegador', return_value=True), \
                patch.object(self.web, 'copiar_al_portapapeles', return_value=True), \
                patch.object(self.web, '_leer_url_actual', side_effect=PausaPorActividad):
            with self.assertRaises(PausaPorActividad):
                self.web._procesar_pagina('https://example.com')
        self.assertTrue(self.web._contexto['navegacion_pendiente'])
        teclado.hotkey.assert_any_call(self.web.cmd_key, 't')
        self.assertNotIn(unittest.mock.call(self.web.cmd_key, 'w'), teclado.hotkey.call_args_list)

    def test_reanuda_el_recorrido_desde_la_pagina_interrumpida(self):
        self.web.set_paginas(['https://uno.example', 'https://dos.example'])
        with patch.object(self.web, '_procesar_pagina', side_effect=[None, PausaPorActividad()]) as procesar:
            with self.assertRaises(PausaPorActividad):
                self.web.interactuar_web(duracion_maxima=30)
        self.assertEqual(self.web._indice_pagina, 1)
        with patch.object(self.web, '_procesar_pagina') as procesar:
            self.web.interactuar_web(duracion_maxima=30)
        self.assertEqual([llamada.args[0] for llamada in procesar.call_args_list], ['https://dos.example'])

    def test_actividad_impide_teclas_clicks_scroll_y_activar_ventanas(self):
        monitor = MonitorActividad()
        self.editor.monitor_actividad = monitor
        self.web.monitor_actividad = monitor
        monitor.registrar()
        for accion in (lambda: self.editor._write('x'), self.editor._click,
                       lambda: self.editor._scroll(3),
                       lambda: self.web._hotkey('command', 't'),
                       lambda: self.editor.activar_aplicacion('Code.exe', 'Visual Studio Code')):
            with self.assertRaises(PausaPorActividad):
                accion()
        teclado.write.assert_not_called()
        teclado.click.assert_not_called()
        teclado.scroll.assert_not_called()
        teclado.hotkey.assert_not_called()

    def test_actividad_interrumpe_movimiento_animado_del_mouse(self):
        monitor = MonitorActividad()
        self.editor.monitor_actividad = monitor
        teclado.position.return_value = (100, 100)
        with patch.object(teclado, 'moveTo', side_effect=lambda *_args, **_kwargs: monitor.registrar()):
            with self.assertRaises(PausaPorActividad):
                self.editor._move_to(200, 200, duration=0.5)
            self.assertEqual(teclado.moveTo.call_count, 1)

    def test_pausa_no_cierra_pestanas_del_usuario(self):
        with patch.object(self.web, 'activar_navegador', return_value=True), \
                patch.object(self.web, 'copiar_al_portapapeles', side_effect=PausaPorActividad):
            with self.assertRaises(PausaPorActividad):
                self.web._procesar_pagina('https://example.com')
        self.assertEqual(teclado.hotkey.call_args_list,
                         [unittest.mock.call(self.web.cmd_key, 't')])

    def test_pausa_tras_caracter_conserva_el_desplazamiento(self):
        self.editor.bloque_actual = ['abc']
        self.editor.necesita_reposicionar = False
        with patch.object(self.editor, '_limpiar_linea_actual'), \
                patch.object(self.editor, '_queda_tiempo_editor', return_value=True), \
                patch.object(self.editor, '_esperar', side_effect=PausaPorActividad):
            with self.assertRaises(PausaPorActividad):
                self.editor._escribir_siguiente_linea(float('inf'))
        self.assertEqual(self.editor.desplazamiento, 1)

    def test_editor_ejecuta_solo_las_fases_seleccionadas(self):
        for modo, escritura, mouse in [('ambas', 1, 1), ('escritura', 1, 0), ('mouse', 0, 1)]:
            with self.subTest(modo=modo):
                self.editor.fases = modo
                self.editor.lineas_actuales = ['codigo cargado']
                with patch.object(self.editor, 'tiempo_restante', return_value=None), \
                        patch('editor_interactor.time.monotonic', side_effect=[0, 0, 2]), \
                        patch.object(self.editor, 'fase_escritura') as escribir, \
                        patch.object(self.editor, 'fase_mouse') as mover:
                    self.editor.interactuar_editor(duracion_maxima=1)
                self.assertEqual(escribir.call_count, escritura)
                self.assertEqual(mover.call_count, mouse)

    def test_inyeccion_cancelada_si_falla_activacion(self):
        self.editor.editor_actual = 'vsCode'
        self.editor.ruta_archivo = '/tmp/workbreak_unico.tsx'
        with patch.object(self.editor, 'copiar_al_portapapeles', return_value=True), \
                patch.object(self.editor, 'leer_portapapeles', return_value='original'), \
                patch.object(self.editor, '_activar_si_necesario', return_value=False):
            with self.assertRaises(EditorNoDisponible):
                self.editor.inyectar_codigo()
        teclado.hotkey.assert_not_called()

    def test_otro_archivo_no_recibe_seleccionar_todo_ni_pegar(self):
        self.editor.editor_actual = 'vsCode'
        self.editor.ruta_archivo = '/tmp/workbreak_unico.tsx'
        self.editor.is_windows = True
        self.editor.is_mac = False
        self.editor.cmd_key = 'ctrl'
        ventanas = SimpleNamespace(GetWindowText=lambda _: 'archivo_del_usuario.tsx',
                                   GetForegroundWindow=lambda: 1)
        with patch.object(self.editor, '_activar_si_necesario', return_value=True), \
                patch.dict(sys.modules, {'win32gui': ventanas}):
            with self.assertRaises(EditorNoDisponible):
                self.editor._asegurar_destino()
        self.assertNotIn(unittest.mock.call('ctrl', 'a'), teclado.hotkey.call_args_list)
        self.assertNotIn(unittest.mock.call('ctrl', 'v'), teclado.hotkey.call_args_list)

    def test_ventana_windows_se_busca_por_proceso(self):
        ventanas = SimpleNamespace(
            IsWindowVisible=lambda _: True,
            GetWindowText=lambda _: 'Mi página - Google Chrome',
            EnumWindows=lambda callback, dato: callback(7, dato),
            GetForegroundWindow=lambda: 7,
        )
        procesos = SimpleNamespace(GetWindowThreadProcessId=lambda _: (0, 42))
        psutil = SimpleNamespace(Process=lambda _: SimpleNamespace(name=lambda: 'chrome.exe'),
                                 NoSuchProcess=LookupError, AccessDenied=PermissionError)
        with patch.dict(sys.modules, {'win32gui': ventanas, 'win32process': procesos,
                                     'psutil': psutil}):
            self.assertTrue(self.web._activar_aplicacion_windows('chrome.exe'))

    def test_verificacion_mac_utiliza_bloques_applescript_completos(self):
        self.editor.editor_actual = 'vsCode'
        self.editor.ruta_archivo = '/tmp/workbreak_unico.tsx'
        self.editor.is_windows = False
        self.editor.is_mac = True
        self.editor.cmd_key = 'command'
        resultado = SimpleNamespace(stdout='workbreak_unico.tsx — Visual Studio Code\n')
        with patch.object(self.editor, '_activar_si_necesario', return_value=True), \
                patch('editor_interactor.subprocess.run', return_value=resultado) as ejecutar:
            self.editor._asegurar_destino()
        script = ejecutar.call_args.args[0][2]
        self.assertEqual(script.splitlines(), [
            'set appBundleId to id of application "Visual Studio Code"',
            'tell application "System Events"',
            'tell (first application process whose bundle identifier is appBundleId)',
            'if frontmost is false then error "Editor sin foco"',
            'get name of front window',
            'end tell',
            'end tell',
        ])

    def test_error_mac_conserva_diagnostico_original(self):
        self.editor.editor_actual = 'vsCode'
        self.editor.ruta_archivo = '/tmp/workbreak_unico.tsx'
        self.editor.is_windows = False
        self.editor.is_mac = True
        error = subprocess.CalledProcessError(1, 'osascript', stderr='Acceso denegado (-1743)')
        with patch.object(self.editor, '_activar_si_necesario', return_value=True), \
                patch('editor_interactor.subprocess.run', side_effect=error):
            with self.assertRaisesRegex(EditorNoDisponible, 'Acceso denegado'):
                self.editor._asegurar_destino()
        self.assertNotIn(unittest.mock.call('command', 'a'), teclado.hotkey.call_args_list)
        self.assertNotIn(unittest.mock.call('command', 'v'), teclado.hotkey.call_args_list)

    def test_nuevo_bloque_navega_una_vez_y_reescribe_directamente(self):
        self.editor.lineas_actuales = ['antes', 'otra', 'abc', 'despues']
        with patch.object(self.editor, '_asegurar_destino'), \
                patch.object(self.editor, '_cerrar_paneles'), \
                patch.object(self.editor, '_elegir_bloque', return_value=(2, ['abc'])), \
                patch.object(self.editor, '_ir_a_linea') as ir, \
                patch.object(self.editor, '_queda_tiempo_editor', return_value=True), \
                patch.object(self.editor, 'copiar_al_portapapeles', return_value=True):
            self.editor._editar_bloque_real(float('inf'))
        ir.assert_called_once_with(3)
        self.assertEqual([c.args[0] for c in teclado.write.call_args_list], list('abc'))
        self.assertNotIn(unittest.mock.call('enter'), teclado.press.call_args_list)

    def test_reanuda_linea_sin_repetir_navegacion_si_no_hubo_mouse(self):
        self.editor.bloque_actual = ['abc']
        self.editor.desplazamiento = 1
        self.editor.necesita_reposicionar = False
        with patch.object(self.editor, '_asegurar_destino'), \
                patch.object(self.editor, '_ir_a_linea') as ir, \
                patch.object(self.editor, '_queda_tiempo_editor', return_value=True), \
                patch.object(self.editor, 'copiar_al_portapapeles', return_value=True):
            self.editor._escribir_siguiente_linea(float('inf'))
        ir.assert_not_called()
        self.assertEqual([c.args[0] for c in teclado.write.call_args_list], list('bc'))

    def test_nueva_escritura_invalida_captura_antes_de_otra_pausa(self):
        self.editor.lineas_actuales = ['abc']
        self.editor.bloque_actual = ['abc']
        self.editor.inicio_bloque = 0
        self.editor.indice_linea = 0
        self.editor.desplazamiento = 1
        self.editor.necesita_reposicionar = False
        self.editor._lineas_observadas[1] = 'a'
        with patch.object(self.editor, '_queda_tiempo_editor', return_value=True), \
                patch.object(self.editor, '_esperar', side_effect=[None, PausaPorActividad()]):
            with self.assertRaises(PausaPorActividad):
                self.editor._escribir_siguiente_linea(float('inf'))
        self.assertEqual(self.editor.desplazamiento, 2)
        self.assertNotIn(1, self.editor._lineas_observadas)
        with patch.object(self.editor, '_leer_linea_completa_mac', return_value='ab'):
            self.editor._confirmar_linea_mac(1)

    def test_consulta_rectangulo_editor_es_interrumpible(self):
        self.editor.is_windows = False
        self.editor.is_mac = True
        self.editor.editor_actual = 'vsCode'
        with patch.object(self.editor, '_ejecutar_proceso', side_effect=PausaPorActividad):
            with self.assertRaises(PausaPorActividad):
                self.editor._rectangulo_ventana_editor()

    def test_consulta_titulo_editor_es_interrumpible(self):
        self.editor.is_windows = False
        self.editor.is_mac = True
        self.editor.editor_actual = 'vsCode'
        self.editor.ruta_archivo = '/tmp/workbreak_unico.tsx'
        with patch.object(self.editor, '_activar_si_necesario', return_value=True), \
                patch.object(self.editor, '_ejecutar_proceso', side_effect=PausaPorActividad):
            with self.assertRaises(PausaPorActividad):
                self.editor._asegurar_destino()

    def test_ir_a_linea_solo_escribe_tras_confirmar_panel(self):
        for tecla in ('ctrl', 'command'):
            with self.subTest(tecla=tecla):
                teclado.reset_mock()
                self.editor.cmd_key = tecla
                self.editor.is_mac = tecla == 'command'
                with patch.object(self.editor, '_leer_seleccion_mac', return_value=':'), \
                        patch.object(self.editor, '_confirmar_linea_mac'):
                    self.editor._ir_a_linea(25)
                destino = ':25:1' if self.editor.is_mac else '25:1'
                teclado.write.assert_called_once_with(destino, interval=0.03)
                if self.editor.is_mac:
                    teclado.hotkey.assert_any_call('option', 'g')

    def test_dialogo_no_abierto_no_escribe_coordenadas(self):
        self.editor.is_mac = True
        with patch.object(self.editor, '_leer_seleccion_mac', return_value='const codigo = 1;'):
            with self.assertRaises(EditorNoDisponible):
                self.editor._ir_a_linea(115)
        teclado.write.assert_not_called()
        teclado.press.assert_called_once_with('esc')

    def test_no_continua_si_el_dialogo_no_devuelve_foco_al_codigo(self):
        self.editor.is_mac = True
        self.editor.lineas_actuales = ['const codigo = 1;']
        with patch.object(self.editor, '_leer_seleccion_mac', side_effect=[':', ':1:1']):
            with self.assertRaises(EditorNoDisponible):
                self.editor._ir_a_linea(1)
        teclado.write.assert_called_once_with(':1:1', interval=0.03)

    def test_confirma_linea_destino_sin_modificar_texto(self):
        self.editor.lineas_actuales = ['antes', 'const codigo = 1;', 'despues']
        with patch.object(self.editor, '_leer_seleccion_mac', return_value='const codigo = 1;'):
            self.editor._confirmar_linea_mac(2)
        teclado.press.assert_called_once_with('left')
        teclado.write.assert_not_called()

    def test_confirma_el_contenido_observado_de_una_linea_parcial(self):
        self.editor.lineas_actuales = ['    return valor;']
        self.editor._lineas_observadas[1] = '        return va'
        with patch.object(self.editor, '_leer_linea_completa_mac', return_value='        return va'):
            self.editor._confirmar_linea_mac(1)

    def test_rechaza_cambios_posteriores_a_la_captura(self):
        self.editor.lineas_actuales = ['return valor;']
        self.editor._lineas_observadas[1] = 'return va'
        with patch.object(self.editor, '_leer_linea_completa_mac', return_value='otro texto'):
            with self.assertRaises(EditorNoDisponible):
                self.editor._confirmar_linea_mac(1)

    def test_guarda_la_linea_real_para_la_siguiente_fase(self):
        self.editor.is_mac = True
        self.editor.bloque_actual = ['return valor;']
        self.editor.inicio_bloque = 3
        self.editor.indice_linea = 0
        with patch.object(self.editor, '_leer_linea_completa_mac', return_value='    return va'):
            EditorInteractor._guardar_linea_actual_mac(self.editor)
        self.assertEqual(self.editor._lineas_observadas, {4: '    return va'})

    def test_lectura_selecciona_linea_completa_y_quita_solo_el_salto(self):
        with patch.object(self.editor, '_leer_seleccion_mac', return_value='  return valor;\n'):
            self.assertEqual(self.editor._leer_linea_completa_mac(), '  return valor;')
        teclado.hotkey.assert_called_once_with('command', 'l')

    def test_lectura_rechaza_seleccion_de_varias_lineas(self):
        with patch.object(self.editor, '_leer_seleccion_mac', return_value='primera\nsegunda\n'):
            with self.assertRaises(EditorNoDisponible):
                self.editor._leer_linea_completa_mac()

    def test_error_editando_no_habilita_otra_inyeccion_completa(self):
        original = ['antes', 'fragmento', 'despues']
        self.editor.lineas_actuales = original
        with patch.object(self.editor, '_asegurar_destino'), \
                patch.object(self.editor, '_cerrar_paneles'), \
                patch.object(self.editor, '_elegir_bloque', side_effect=RuntimeError('fallo')):
            with self.assertRaises(EditorNoDisponible):
                self.editor._editar_bloque_real(float('inf'))
        self.assertIs(self.editor.lineas_actuales, original)

    def test_reescritura_preserva_lineas_vecinas_y_linea_vacia(self):
        for is_windows in (True, False):
            with self.subTest(is_windows=is_windows):
                lineas = ['antes', '    const a = 1;', '', '   ', 'const b = 2;', 'despues']
                original = list(lineas)
                estado = {'linea': 0, 'seleccion': False, 'portapapeles': ''}

                def ir(numero):
                    estado['linea'] = numero - 1
                    estado['seleccion'] = False

                def hotkey(*teclas):
                    if 'shift' in teclas:
                        estado['seleccion'] = True
                    elif teclas[-1] == 'v':
                        escribir(estado['portapapeles'])

                def escribir(texto, **_):
                    idx = estado['linea']
                    if estado['seleccion']:
                        lineas[idx] = texto
                        estado['seleccion'] = False
                    else:
                        lineas[idx] += texto

                def copiar(texto):
                    estado['portapapeles'] = texto
                    return True

                self.editor.is_windows = is_windows
                self.editor.cmd_key = 'ctrl' if is_windows else 'command'
                self.editor.bloque_actual = original[1:5]
                self.editor.inicio_bloque = 1
                self.editor.indice_linea = 0
                self.editor.desplazamiento = 0
                with patch.object(self.editor, '_ir_a_linea', side_effect=ir), \
                        patch.object(self.editor, '_asegurar_destino'), \
                        patch.object(self.editor, '_queda_tiempo_editor', return_value=True), \
                        patch.object(self.editor, 'copiar_al_portapapeles', side_effect=copiar), \
                        patch.object(teclado, 'hotkey', side_effect=hotkey), \
                        patch.object(teclado, 'write', side_effect=escribir):
                    for _ in self.editor.bloque_actual:
                        self.editor._escribir_siguiente_linea(float('inf'))
                self.assertEqual(lineas, original)
                self.assertNotIn(unittest.mock.call('enter'), teclado.press.call_args_list)
                self.assertNotIn(unittest.mock.call('backspace'), teclado.press.call_args_list)

    def test_restauracion_mac_incluye_la_sangria_original(self):
        self.editor.is_mac = True
        self.editor.is_windows = False
        self.editor.cmd_key = 'command'
        self.editor.bloque_actual = ['    x']
        self.editor.necesita_reposicionar = False
        estado = {'texto': '    x', 'posicion': 0, 'seleccion': None, 'clipboard': ''}

        def hotkey(*teclas):
            if teclas == ('command', 'left'):
                primera = len(estado['texto']) - len(estado['texto'].lstrip())
                estado['posicion'] = 0 if estado['posicion'] == primera else primera
            elif teclas == ('command', 'shift', 'right'):
                estado['seleccion'] = estado['posicion']
            elif teclas == ('command', 'v'):
                escribir(estado['clipboard'])

        def escribir(texto, **_):
            if estado['seleccion'] is not None:
                estado['texto'] = estado['texto'][:estado['seleccion']] + texto
                estado['seleccion'] = None
            else:
                estado['texto'] += texto
            estado['posicion'] = len(estado['texto'])

        def copiar(texto):
            estado['clipboard'] = texto
            return True

        with patch.object(self.editor, '_asegurar_destino'), \
                patch.object(self.editor, '_queda_tiempo_editor', return_value=True), \
                patch.object(self.editor, 'copiar_al_portapapeles', side_effect=copiar), \
                patch.object(self.editor, '_hotkey', side_effect=hotkey), \
                patch.object(self.editor, '_write', side_effect=escribir):
            self.editor._escribir_siguiente_linea(float('inf'))
        self.assertEqual(estado['texto'], '    x')

    def test_no_abre_paginas_con_limite_global_agotado(self):
        self.web.set_paginas(['https://example.com', 'https://example.org'])
        self.web.set_limite_tiempo(0)
        with patch.object(self.web, '_procesar_pagina') as procesar:
            self.web.interactuar_web(30)
        procesar.assert_not_called()

    def test_expiracion_durante_activacion_no_abre_pestana(self):
        def activar():
            self.web.set_limite_tiempo(0)
            return True

        with patch.object(self.web, 'activar_navegador', side_effect=activar):
            self.web._procesar_pagina('https://example.com')
        teclado.hotkey.assert_not_called()

    def test_copia_fallida_cierra_pestana_creada(self):
        with patch.object(self.web, 'activar_navegador', return_value=True), \
                patch.object(self.web, 'copiar_al_portapapeles', return_value=False):
            self.web._procesar_pagina('https://example.com')
        self.assertEqual(teclado.hotkey.call_args_list,
                         [unittest.mock.call(self.web.cmd_key, 't'),
                          unittest.mock.call(self.web.cmd_key, 'w')])

    def test_failsafe_se_propaga_sin_enviar_teclas_de_limpieza(self):
        with patch.object(self.web, 'activar_navegador', return_value=True), \
                patch.object(self.web, 'copiar_al_portapapeles', side_effect=FailSafeException):
            with self.assertRaises(FailSafeException):
                self.web._procesar_pagina('https://example.com')
        self.assertEqual(teclado.hotkey.call_args_list,
                         [unittest.mock.call(self.web.cmd_key, 't')])


if __name__ == '__main__':
    unittest.main()
