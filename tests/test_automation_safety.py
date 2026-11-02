import os
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


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

    def test_foco_anterior_no_evita_reactivacion(self):
        with patch.object(self.editor, 'activar_aplicacion', return_value=False) as activar:
            self.assertFalse(self.editor._activar_si_necesario('Code.exe', 'Visual Studio Code'))
            self.assertFalse(self.editor._activar_si_necesario('Code.exe', 'Visual Studio Code'))
        self.assertEqual(activar.call_count, 2)

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
