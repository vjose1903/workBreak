import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from user_activity import MonitorActividad, PausaPorActividad
import clipboard_state


class FailSafeException(Exception):
    pass


# Estas pruebas no importan los controladores reales de teclado/pantalla.
teclado = MagicMock()
teclado.FailSafeException = FailSafeException
teclado.size.return_value = (1920, 1080)
with patch.dict(sys.modules, {'pyautogui': teclado}):
    import base_automation
    from base_automation import TiempoAgotado, PortapapelesNoDisponible
    import editor_interactor
    from editor_interactor import EditorInteractor, EditorNoDisponible, LineaDesincronizada
    from statistics_tracker import StatisticsTracker
    from web_interactor import WebInteractor
    from automation_bot import AutomationBot
    from menu import Configuracion
    from code_source import RealProjectSource


class AutomationSafetyTest(unittest.TestCase):
    def test_activacion_mac_acepta_foco_real_aunque_la_solicitud_devuelva_false(self):
        objetivo = SimpleNamespace(processIdentifier=lambda: 42)
        workspace = SimpleNamespace(sharedWorkspace=lambda: SimpleNamespace(frontmostApplication=lambda: objetivo))
        with patch.dict(sys.modules, {'AppKit': SimpleNamespace(NSWorkspace=workspace)}), \
                patch('mac_accessibility._actualizar_workspace'), \
                patch('mac_accessibility.aplicacion', return_value=objetivo), \
                patch('mac_accessibility.activar_aplicacion', return_value=False):
            self.assertTrue(self.web._activar_aplicacion_mac('Google Chrome'))

    def test_activacion_mac_espera_el_foco_real_antes_de_continuar(self):
        objetivo = SimpleNamespace(processIdentifier=lambda: 42)
        otro = SimpleNamespace(processIdentifier=lambda: 7)
        workspace = MagicMock()
        workspace.sharedWorkspace.return_value.frontmostApplication.side_effect = [otro, objetivo]
        with patch.dict(sys.modules, {'AppKit': SimpleNamespace(NSWorkspace=workspace)}), \
                patch('mac_accessibility._actualizar_workspace'), \
                patch('mac_accessibility.aplicacion', return_value=objetivo), \
                patch('mac_accessibility.activar_aplicacion', return_value=True), \
                patch.object(self.web, '_esperar') as esperar:
            self.assertTrue(self.web._activar_aplicacion_mac('Google Chrome'))
        esperar.assert_called_once_with(0.05)

    def test_activacion_mac_rechaza_una_solicitud_que_no_cambia_el_foco(self):
        objetivo = SimpleNamespace(processIdentifier=lambda: 42)
        workspace = SimpleNamespace(sharedWorkspace=lambda: SimpleNamespace(
            frontmostApplication=lambda: SimpleNamespace(processIdentifier=lambda: 7)))
        with patch.dict(sys.modules, {'AppKit': SimpleNamespace(NSWorkspace=workspace)}), \
                patch('mac_accessibility._actualizar_workspace'), \
                patch('mac_accessibility.aplicacion', return_value=objetivo), \
                patch('mac_accessibility.activar_aplicacion', return_value=True), \
                patch('base_automation.time.monotonic', side_effect=[0, 3.1]):
            self.assertFalse(self.web._activar_aplicacion_mac('Google Chrome'))

    def test_lectura_url_reintenta_si_chrome_aun_no_entrega_la_copia(self):
        with patch.object(self.web, 'copiar_al_portapapeles', return_value=True), \
                patch.object(self.web, 'copiar_seleccion', side_effect=['workbreak:sin-url', '', 'https://example.com']) as copiar:
            self.assertEqual(WebInteractor._leer_url_actual(self.web), 'https://example.com')
        self.assertEqual(copiar.call_count, 3)
        self.assertEqual(teclado.press.call_args_list, [unittest.mock.call('esc')])

    def test_lectura_url_fallida_tiene_plazo_y_no_navega(self):
        with patch.object(self.web, 'copiar_al_portapapeles', return_value=True), \
                patch.object(self.web, 'copiar_seleccion', return_value='workbreak:sin-url'), \
                patch('web_interactor.time.monotonic', side_effect=[0, 2.1]):
            with self.assertRaisesRegex(RuntimeError, 'dirección de la pestaña'):
                WebInteractor._leer_url_actual(self.web)
        self.assertNotIn(unittest.mock.call('enter'), teclado.press.call_args_list)

    def test_actividad_durante_reintento_de_url_pausa_sin_escape_ni_navegacion(self):
        with patch.object(self.web, 'copiar_al_portapapeles', return_value=True), \
                patch.object(self.web, 'copiar_seleccion', side_effect=PausaPorActividad()):
            with self.assertRaises(PausaPorActividad):
                WebInteractor._leer_url_actual(self.web)
        teclado.press.assert_not_called()

    def test_espera_larga_termina_en_el_limite_global(self):
        self.editor.monitor_actividad = MagicMock()
        with patch.object(self.editor, 'tiempo_restante', return_value=2):
            with self.assertRaises(TiempoAgotado):
                self.editor._esperar(600)
        self.editor.monitor_actividad.esperar_intervalo.assert_called_once_with(2)

    def test_grupo_dividido_recupera_solo_el_archivo_temporal(self):
        self.editor.is_mac, self.editor.is_windows = True, False
        self.editor.reutilizar_ventana = True
        self.editor.editor_actual = 'vsCode'
        self.editor.ruta_archivo = '/tmp/bot.tsx'
        with patch.object(self.editor, '_activar_si_necesario', return_value=True), \
                patch.object(editor_interactor, 'documento_editor',
                             side_effect=['file:///tmp/bot.tsx', 'file:///tmp/usuario.tsx', 'file:///tmp/bot.tsx']), \
                patch.object(self.editor, '_comando_abrir_editor', return_value=['code', '--reuse-window', '/tmp/bot.tsx']), \
                patch.object(self.editor, 'ejecutar_comando', return_value=True) as abrir:
            self.editor._asegurar_destino()
        abrir.assert_called_once_with(['code', '--reuse-window', '/tmp/bot.tsx'])

    def test_arranque_editor_espera_un_inicio_en_frio_lento(self):
        reloj = [0.0]
        def esperar(segundos):
            reloj[0] += segundos
        with patch('editor_interactor.time.monotonic', side_effect=lambda: reloj[0]), \
                patch.object(self.editor, '_esperar', side_effect=esperar), \
                patch.object(self.editor, 'activar_aplicacion', side_effect=lambda *_: reloj[0] >= 6):
            self.assertTrue(self.editor._esperar_ventana_editor({'proceso': 'Code.exe', 'mac': 'Visual Studio Code'}))
        self.assertGreaterEqual(reloj[0], 6)

    def test_inyeccion_fallida_no_se_trata_como_turno_correcto(self):
        self.editor._portapapeles_original = 'usuario'
        with patch.object(self.editor, 'copiar_al_portapapeles', return_value=False):
            with self.assertRaisesRegex(EditorNoDisponible, 'copiar el código'):
                self.editor.inyectar_codigo()
        teclado.hotkey.assert_not_called()

    def test_restauracion_fallida_no_informa_exito(self):
        self.editor._portapapeles_original = 'usuario'
        self.editor.portapapeles_bot['ultimo'] = 'bot'
        with patch.object(self.editor, 'leer_portapapeles', return_value='bot'), \
                patch.object(self.editor, 'copiar_al_portapapeles', return_value=False), \
                patch('editor_interactor.logging.info') as informar:
            with self.assertRaises(PortapapelesNoDisponible):
                self.editor.restaurar_portapapeles()
        informar.assert_not_called()

    def test_texto_igual_copiado_por_usuario_no_pertenece_al_bot(self):
        self.editor.portapapeles_bot.update(ultimo='igual', version=1)
        with patch('clipboard_state.version', return_value=2):
            self.assertFalse(self.editor.portapapeles_es_del_bot('igual'))

    def test_revision_nueva_no_atribuye_una_copia_interrumpida_al_usuario(self):
        self.editor.portapapeles_bot.update(ultimo='marcador', version=1, copia_pendiente=True)
        with patch('clipboard_state.version', return_value=2):
            with self.assertRaises(PortapapelesNoDisponible):
                self.editor.portapapeles_es_del_bot('selección no confirmada')

    def test_copia_nativa_incompleta_impide_modificar_portapapeles(self):
        with patch('clipboard_state.capturar', side_effect=RuntimeError('formato no disponible')), \
                patch.object(self.editor, 'copiar_al_portapapeles') as copiar:
            with self.assertRaises(EditorNoDisponible):
                self.editor.inyectar_codigo()
        copiar.assert_not_called()

    def test_cualquier_pausa_invalida_pestana_aunque_ocurra_en_editor(self):
        bot = AutomationBot(solicitar_detencion=lambda: False)
        bot.web_interactor._pestana_bot = {'pagina': 'https://example.com', 'url': 'https://example.com'}
        with patch('automation_bot.MonitorActividad.iniciar'), \
                patch('automation_bot.MonitorActividad.esperar_inactividad', return_value=False), \
                patch.object(bot.editor_interactor, 'mantener_despierto_iniciar'), \
                patch.object(bot.editor_interactor, 'mantener_despierto_detener'), \
                patch.object(bot.editor_interactor, 'guardar_portapapeles_original'), \
                patch.object(bot.editor_interactor, 'restaurar_portapapeles'), \
                patch.object(bot, 'ejecutar_tareas', side_effect=PausaPorActividad()), \
                patch.object(bot, '_imprimir_y_cerrar', side_effect=lambda codigo: codigo):
            self.assertEqual(bot.gestionar_ejecucion(Configuracion()), 0)
        self.assertIsNone(bot.web_interactor._pestana_bot)

    def test_fallo_de_limpieza_finaliza_con_error(self):
        bot = AutomationBot(solicitar_detencion=lambda: True)
        with patch('automation_bot.MonitorActividad.iniciar'), \
                patch.object(bot.editor_interactor, 'mantener_despierto_iniciar'), \
                patch.object(bot.editor_interactor, 'mantener_despierto_detener'), \
                patch.object(bot.editor_interactor, 'restaurar_portapapeles', side_effect=PortapapelesNoDisponible('fallo')), \
                patch.object(bot, '_imprimir_y_cerrar', side_effect=lambda codigo: codigo):
            self.assertEqual(bot.gestionar_ejecucion(Configuracion()), 1)

    def test_detener_desde_interfaz_finaliza_y_ejecuta_limpieza_sin_enviar_entradas(self):
        bot = AutomationBot(solicitar_detencion=lambda: True)
        with patch('automation_bot.MonitorActividad.iniciar'), \
                patch.object(bot.editor_interactor, 'mantener_despierto_iniciar'), \
                patch.object(bot.editor_interactor, 'mantener_despierto_detener') as detener, \
                patch.object(bot.editor_interactor, 'restaurar_portapapeles') as restaurar, \
                patch.object(bot, '_imprimir_y_cerrar', side_effect=lambda codigo: codigo):
            self.assertEqual(bot.gestionar_ejecucion(Configuracion()), 0)
        detener.assert_called_once()
        restaurar.assert_called_once()
        teclado.hotkey.assert_not_called()
        teclado.write.assert_not_called()

    def test_antireposo_queda_vinculado_al_pid_y_recoge_el_auxiliar(self):
        self.editor.is_windows = False
        self.editor._antidespierto_activo = False
        with patch('base_automation.subprocess.Popen') as lanzar:
            self.editor.mantener_despierto_iniciar()
            self.assertEqual(lanzar.call_args.args[0][-2:], ['-w', str(os.getpid())])
            proceso = lanzar.return_value
            self.editor.mantener_despierto_detener()
        proceso.terminate.assert_called_once()
        proceso.wait.assert_called_once_with(timeout=1)

    def test_urls_web_solo_http_https_y_recorrido_se_reinicia_al_cambiar(self):
        self.web.set_paginas(['example.com', 'http://localhost:3000'])
        self.assertEqual(self.web.paginas, ['https://example.com', 'http://localhost:3000'])
        self.web._indice_pagina = 1
        self.web._contexto = {'pagina': 'anterior'}
        self.web.set_paginas(['https://otro.example'])
        self.assertEqual(self.web._indice_pagina, 0)
        self.assertIsNone(self.web._contexto)
        for url in ('file:///etc/passwd', 'javascript:alert(1)', 'https://example.com/\x00'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.web.set_paginas([url])
        self.assertEqual(self.web.paginas, ['https://otro.example'])

    def test_validacion_tiempo_cli_rechaza_valores_enormes(self):
        import argparse
        bot = AutomationBot()
        with self.assertRaises(argparse.ArgumentTypeError):
            bot.validar_tiempo(str(10 ** 400))

    def test_interaccion_web_no_pulsa_si_click_esta_desactivado(self):
        self.web.acciones['click'] = False
        with patch.object(self.web, '_queda_tiempo', side_effect=[True, False]), \
                patch.object(self.web, '_configurar_area_mouse', return_value=(300, 300)), \
                patch.object(self.web, '_leer_url_actual', return_value='https://example.com'), \
                patch.object(self.web, '_move_to'), patch.object(self.web, '_click') as pulsar:
            self.web.interactuar_con_pagina('https://example.com')
        pulsar.assert_not_called()

    def test_editor_sin_escritura_no_inyecta_codigo(self):
        self.editor.acciones = {'escribir': False, 'click': True, 'scroll': False, 'mover_mouse': False}
        with patch('editor_interactor.time.monotonic', side_effect=[0, 0, 0, 2, 2]), \
                patch.object(self.editor, 'tiempo_restante', return_value=None), \
                patch.object(self.editor, 'inyectar_codigo') as inyectar, \
                patch.object(self.editor, 'fase_escritura') as escribir, \
                patch.object(self.editor, 'fase_mouse') as mouse:
            self.editor.interactuar_editor(duracion_maxima=1)
        inyectar.assert_not_called()
        escribir.assert_not_called()
        mouse.assert_called_once()

    def test_accion_editor_click_no_mueve_ni_desplaza(self):
        self.editor.acciones = {'escribir': False, 'click': True, 'scroll': False, 'mover_mouse': False}
        with patch.object(self.editor, '_configurar_area_mouse'), \
                patch.object(self.editor, '_mouse_en_area_segura', return_value=True), \
                patch.object(self.editor, '_move_to') as mover, \
                patch.object(self.editor, '_move_rel') as mover_rel, \
                patch.object(self.editor, '_scroll') as scroll, \
                patch.object(self.editor, '_click') as click:
            self.editor._movimiento_fase_mouse()
        click.assert_called_once()
        mover.assert_not_called()
        mover_rel.assert_not_called()
        scroll.assert_not_called()

    def test_web_solo_scroll_no_mueve_ni_pulsa(self):
        self.web.acciones = {'click': False, 'scroll': True, 'mover_mouse': False}
        with patch.object(self.web, '_queda_tiempo', side_effect=[True, True, False]), \
                patch.object(self.web, '_configurar_area_mouse', return_value=(300, 300)), \
                patch.object(self.web, '_leer_url_actual', return_value='https://example.com'), \
                patch.object(self.web, '_confirmar_destino_web'), \
                patch.object(self.web, '_mouse_en_area_segura', return_value=True), \
                patch.object(self.web, '_move_to') as mover, \
                patch.object(self.web, '_click') as click, \
                patch.object(self.web, '_scroll') as scroll, patch.object(self.web, '_esperar'):
            self.web.interactuar_con_pagina('https://example.com')
        mover.assert_not_called()
        click.assert_not_called()
        scroll.assert_called_once()

    def test_navegador_cancela_movimiento_si_cambia_ventana(self):
        self.web._ventana_web = 1
        with patch.object(self.web, 'identidad_ventana_activa', return_value=2), \
                patch.object(teclado, 'moveTo') as mover:
            with self.assertRaisesRegex(RuntimeError, 'ventana del navegador'):
                self.web._move_to(200, 200)
        mover.assert_not_called()

    def test_escritura_cancela_antes_del_evento_si_cambia_ventana(self):
        self.editor._ventana_escritura_editor = 12
        with patch.object(self.editor, 'identidad_ventana_activa', return_value=13):
            with self.assertRaises(EditorNoDisponible):
                EditorInteractor._insertar_caracter(self.editor, 'a')
        teclado.write.assert_not_called()

    def test_guardian_editor_lee_identidad_sin_recursion(self):
        cuarzo = MagicMock()
        cuarzo.CGWindowListCopyWindowInfo.return_value = [
            {'kCGWindowLayer': 0, 'kCGWindowNumber': 12}]
        self.editor.is_windows = False
        self.editor.is_mac = True
        self.editor._ventana_mouse_editor = 12
        with patch.dict(sys.modules, {'Quartz': cuarzo}):
            self.editor._antes_accion()
        cuarzo.CGWindowListCopyWindowInfo.assert_called_once()

    def test_emergente_del_navegador_no_cambia_la_identidad_de_la_ventana(self):
        cuarzo = MagicMock()
        principal = {'kCGWindowLayer': 0, 'kCGWindowNumber': 7, 'kCGWindowOwnerPID': 50,
                     'kCGWindowBounds': {'X': 3712, 'Y': 0, 'Width': 1920, 'Height': 1080}}
        sugerencias = {'kCGWindowLayer': 0, 'kCGWindowNumber': 99, 'kCGWindowOwnerPID': 50,
                       'kCGWindowBounds': {'X': 3800, 'Y': 80, 'Width': 900, 'Height': 300}}
        otra_app = {'kCGWindowLayer': 0, 'kCGWindowNumber': 3, 'kCGWindowOwnerPID': 60,
                    'kCGWindowBounds': {'X': 3712, 'Y': 0, 'Width': 1920, 'Height': 1080}}
        self.editor.is_windows = False
        self.editor.is_mac = True
        with patch.dict(sys.modules, {'Quartz': cuarzo}):
            cuarzo.CGWindowListCopyWindowInfo.return_value = [principal, otra_app]
            sin_emergente = self.editor.identidad_ventana_activa()
            cuarzo.CGWindowListCopyWindowInfo.return_value = [sugerencias, principal, otra_app]
            con_emergente = self.editor.identidad_ventana_activa()
            # Una ventana pequeña de otra app delante sí es un cambio de foco.
            cuarzo.CGWindowListCopyWindowInfo.return_value = [dict(sugerencias, kCGWindowOwnerPID=60), principal]
            otra = self.editor.identidad_ventana_activa()
        self.assertEqual((sin_emergente, con_emergente, otra), (7, 7, 99))

    def test_reintento_tras_error_reutiliza_la_pestana_del_bot(self):
        url = 'https://example.com'
        with patch.object(self.web, 'activar_navegador', return_value=True), \
                patch.object(self.web, 'copiar_al_portapapeles', return_value=True), \
                patch.object(self.web, '_leer_url_actual', return_value=url), \
                patch.object(self.web, 'interactuar_con_pagina', side_effect=[RuntimeError('fallo'), None]) as interactuar:
            with self.assertRaises(RuntimeError):
                self.web._procesar_pagina(url)
            self.web._procesar_pagina(url)
        self.assertEqual(teclado.hotkey.call_args_list.count(unittest.mock.call(self.web.cmd_key, 't')), 1)
        self.assertEqual(interactuar.call_count, 2)

    def test_pestana_del_bot_cambiada_abre_una_nueva(self):
        url = 'https://example.com'
        with patch.object(self.web, 'activar_navegador', return_value=True), \
                patch.object(self.web, 'copiar_al_portapapeles', return_value=True), \
                patch.object(self.web, '_leer_url_actual', side_effect=[url, 'https://otro.example', url]), \
                patch.object(self.web, 'interactuar_con_pagina'):
            self.web._procesar_pagina(url)
            self.web._procesar_pagina(url)
        self.assertEqual(teclado.hotkey.call_args_list.count(unittest.mock.call(self.web.cmd_key, 't')), 2)

    def test_mouse_editor_no_envia_eventos_si_cambia_ventana(self):
        self.editor._ventana_mouse_editor = 12
        with patch.object(self.editor, 'identidad_ventana_activa', return_value=13):
            for accion in (lambda: self.editor._scroll(2), self.editor._click,
                           self.editor._inicio_archivo):
                with self.assertRaises(EditorNoDisponible):
                    accion()
        teclado.scroll.assert_not_called()
        teclado.click.assert_not_called()
        teclado.hotkey.assert_not_called()

    def test_navegacion_propia_finaliza_visita_sin_fallo(self):
        NavegacionCambiada = WebInteractor._procesar_pagina.__globals__['NavegacionCambiada']
        self.web._contexto = {'abierta': True, 'navegada': True, 'intervenida': False,
                             'pagina': 'https://example.com', 'url': 'https://example.com'}
        with patch.object(self.web, 'activar_navegador', return_value=True), \
                patch.object(self.web, 'interactuar_con_pagina', side_effect=NavegacionCambiada()):
            self.web._procesar_pagina('https://example.com')
        self.assertIsNone(self.web._contexto)

    def setUp(self):
        # Ninguna prueba de automatización lee ni escribe el portapapeles real.
        for nombre, resultado in (('capturar', {'version': 1, 'items': []}),
                                   ('version', 1), ('restaurar', True)):
            parche = patch('clipboard_state.' + nombre, return_value=resultado)
            parche.start()
            self.addCleanup(parche.stop)
        historial = patch('automation_bot.guardar_configuracion')
        historial.start()
        self.addCleanup(historial.stop)
        teclado.reset_mock(side_effect=True)
        # patch.object(teclado, ...) restaura el hijo fuera de _mock_children y reset_mock no lo alcanza.
        for nombre in ('hotkey', 'press', 'write', 'click', 'scroll', 'moveTo'):
            getattr(teclado, nombre).reset_mock(side_effect=True)
        teclado.size.return_value = (1920, 1080)
        locale_hijo = patch.object(base_automation, 'locale_utf8_disponible', return_value='es_ES.UTF-8')
        locale_hijo.start()
        self.addCleanup(locale_hijo.stop)
        self.editor = EditorInteractor(StatisticsTracker())
        documento = patch.object(editor_interactor, 'documento_editor',
                                 side_effect=lambda _bundle: Path(self.editor.ruta_archivo).as_uri())
        documento.start()
        self.addCleanup(documento.stop)
        self.editor.atajo_ir_linea = ('option', 'g')
        self.web = WebInteractor(StatisticsTracker())
        # Nunca enviar eventos Quartz reales, aunque las pruebas se ejecuten en un Mac.
        for interactor in (self.editor, self.web):
            posicion = patch.object(interactor, '_posicion_mouse', side_effect=teclado.position)
            posicion.start()
            self.addCleanup(posicion.stop)
            monitores = patch.object(interactor, '_monitores', return_value=[(0, 0, 1920, 1080)])
            monitores.start()
            self.addCleanup(monitores.stop)
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
        insertar = patch.object(self.editor, '_insertar_caracter',
                                side_effect=lambda c: self.editor._write(c, interval=0))
        insertar.start()
        self.addCleanup(insertar.stop)
        rectangulo = patch.object(self.web, 'rectangulo_aplicacion', return_value=(0, 0, 1000, 800))
        rectangulo.start()
        self.addCleanup(rectangulo.stop)
        for objeto, metodo in [(self.editor, '_verificar_seleccion_linea'),
                                (self.editor, '_fin_linea'),
                                (self.web, '_confirmar_destino_web')]:
            parche = patch.object(objeto, metodo)
            parche.start()
            self.addCleanup(parche.stop)
        ventana = patch.object(self.web, 'identidad_ventana_activa', return_value=1)
        ventana.start()
        self.addCleanup(ventana.stop)
        direccion = patch.object(self.web, '_leer_url_actual', return_value='https://example.com')
        direccion.start()
        self.addCleanup(direccion.stop)
        frente = patch.object(self.editor, '_esperar_editor_al_frente', return_value=True)
        frente.start()
        self.addCleanup(frente.stop)
        # Nunca consultar las ventanas reales del editor.
        ventanas_editor = patch.object(self.editor, '_editor_tiene_ventana', return_value=False)
        ventanas_editor.start()
        self.addCleanup(ventanas_editor.stop)
        # Nunca consultar el navegador real con AppleScript.
        silenciosa = patch.object(self.web, '_leer_url_silenciosa', return_value=None)
        silenciosa.start()
        self.addCleanup(silenciosa.stop)

    def test_seleccion_con_salto_o_vecina_no_autoriza_reemplazo(self):
        for seleccion in ['abc\n', 'abc\ndef', 'ab', None]:
            with self.subTest(seleccion=seleccion), \
                    patch.object(self.editor, '_leer_seleccion_mac', return_value=seleccion), \
                    patch.object(self.editor, '_press') as pulsar:
                with self.assertRaises(EditorNoDisponible):
                    EditorInteractor._verificar_seleccion_linea(self.editor, 'abc')
                pulsar.assert_called_once_with('left')

    def test_seleccion_incorrecta_impide_el_primer_caracter(self):
        self.editor.bloque_actual = ['abc']
        self.editor.necesita_reposicionar = False
        with patch.object(self.editor, '_leer_seleccion_mac', return_value='abc\n'), \
                patch.object(self.editor, '_verificar_seleccion_linea',
                             side_effect=lambda linea: EditorInteractor._verificar_seleccion_linea(self.editor, linea)), \
                patch.object(self.editor, '_insertar_caracter') as insertar:
            with self.assertRaises(EditorNoDisponible):
                self.editor._escribir_siguiente_linea(float('inf'))
        insertar.assert_not_called()

    def test_fallo_web_se_propaga_al_controlador(self):
        with patch.object(self.web, '_configurar_area_mouse', side_effect=RuntimeError('sin área')):
            with self.assertRaisesRegex(RuntimeError, 'sin área'):
                self.web.interactuar_con_pagina('https://example.com')

    def test_cambio_de_destino_impide_click_y_scroll(self):
        with patch.object(self.web, '_confirmar_destino_web', side_effect=RuntimeError('cambió el destino')):
            for accion in (self.web._click, lambda: self.web._scroll(1)):
                with self.assertRaises(RuntimeError):
                    accion()
        teclado.click.assert_not_called()
        teclado.scroll.assert_not_called()

    def test_reanudacion_avanza_el_prefijo_logico_sin_usar_fin_visual(self):
        self.editor.inicio_bloque = 4
        self.editor.indice_linea = 1
        self.editor.desplazamiento = 5
        with patch.object(self.editor, '_confirmar_linea_mac') as confirmar, \
                patch.object(self.editor, '_press') as pulsar:
            EditorInteractor._fin_linea(self.editor)
        confirmar.assert_called_once_with(6)
        self.assertEqual(pulsar.call_args_list, [unittest.mock.call('right')] * 5)

    def test_cambio_de_url_o_ventana_cancela_los_clicks(self):
        self.web._ventana_web = 1
        self.web._url_interaccion = 'https://example.com'
        with patch.object(self.web, '_leer_url_silenciosa', return_value='https://otra.example'):
            with self.assertRaises(RuntimeError):
                WebInteractor._confirmar_destino_web(self.web)
        with patch.object(self.web, 'identidad_ventana_activa', return_value=2), \
                patch.object(self.web, '_leer_url_silenciosa') as leer:
            with self.assertRaises(RuntimeError):
                WebInteractor._confirmar_destino_web(self.web)
            leer.assert_not_called()

    def test_comprobar_destino_no_abre_la_barra_de_direcciones(self):
        self.web._ventana_web = 1
        self.web._url_interaccion = 'https://example.com'
        with patch.object(self.web, '_leer_url_silenciosa', return_value='https://example.com'):
            WebInteractor._confirmar_destino_web(self.web)
        # Sin lectura silenciosa (Firefox, Opera o sin permiso) tampoco se usa la barra.
        WebInteractor._confirmar_destino_web(self.web)
        self.web._leer_url_actual.assert_not_called()
        teclado.hotkey.assert_not_called()

    def test_url_silenciosa_sin_permiso_no_se_reintenta(self):
        self.web.is_mac = True
        error = subprocess.CalledProcessError(1, 'osascript', stderr='-1743')
        with patch.object(self.web, '_ejecutar_proceso', side_effect=error) as ejecutar:
            self.assertIsNone(WebInteractor._leer_url_silenciosa(self.web))
            self.assertIsNone(WebInteractor._leer_url_silenciosa(self.web))
        ejecutar.assert_called_once()

    def test_clicks_consecutivos_quedan_alejados(self):
        self.web._area_mouse = (0, 0, 1000, 800)
        self.web._ultimo_click = (500, 400)
        minimo = self.web._distancia_minima_click()
        for _ in range(50):
            destino = self.web._destino_lejano(500, 400)
            distancia = ((destino[0] - 500) ** 2 + (destino[1] - 400) ** 2) ** .5
            self.assertGreaterEqual(distancia, minimo)
            self.assertLessEqual(distancia, 2 * minimo + 1)
        teclado.position.return_value = (520, 410)
        self.assertFalse(self.web._lejos_del_ultimo_click())
        teclado.position.return_value = (900, 100)
        self.assertTrue(self.web._lejos_del_ultimo_click())

    def test_fuente_fallida_conserva_codigo_y_no_pega(self):
        self.editor._portapapeles_original = 'usuario'
        self.editor.lineas_actuales = ['codigo anterior']
        with patch.object(self.editor.fuente_codigo, 'obtener_codigo', side_effect=ValueError('sin fuente')):
            with self.assertRaises(EditorNoDisponible):
                self.editor.inyectar_codigo()
        self.assertEqual(self.editor.lineas_actuales, ['codigo anterior'])
        teclado.hotkey.assert_not_called()

    def test_guardar_portapapeles_para_web_no_requiere_inyeccion(self):
        with patch.object(self.editor, 'leer_portapapeles', return_value='texto del usuario'):
            self.editor.guardar_portapapeles_original()
        self.editor.portapapeles_bot['ultimo'] = 'https://example.com'
        with patch.object(self.editor, 'leer_portapapeles', return_value='https://example.com'), \
                patch('clipboard_state.restaurar', return_value=True) as restaurar:
            self.editor.restaurar_portapapeles()
        restaurar.assert_called_once()
        self.assertEqual(self.editor._portapapeles_original, 'texto del usuario')

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

    def test_fases_internas_usan_sus_rangos_configurados(self):
        from timing_config import temporizacion_config
        self.editor.temporizacion = temporizacion_config({
            'editor_escritura': [3, 3], 'editor_mouse': [7, 7],
            'editor_movimiento': [0.8, 0.8], 'editor_caracter': [0.02, 0.02]})
        self.assertEqual(self.editor._duracion_fase_escritura(), 3)
        self.assertEqual(self.editor._duracion_fase_mouse(), 7)
        self.assertEqual(self.editor._duracion_configurada('editor_movimiento'), 0.8)
        self.assertEqual(self.editor._duracion_configurada('editor_caracter'), 0.02)

    def test_pausa_scroll_navegador_es_acotada_y_respeta_interrupcion(self):
        from timing_config import temporizacion_config
        self.web.temporizacion = temporizacion_config({'navegador_pausa_scroll': [4, 4]})
        with patch.object(self.web, '_esperar', side_effect=PausaPorActividad) as esperar, \
                patch('web_interactor.time.monotonic', return_value=10):
            with self.assertRaises(PausaPorActividad):
                self.web._pausa_accion('navegador_pausa_scroll', 12)
        esperar.assert_called_once_with(2)

    def test_turnos_respetan_rangos_configurados_en_segundos(self):
        from timing_config import temporizacion_config
        bot = AutomationBot.__new__(AutomationBot)
        bot.temporizacion = temporizacion_config({'editor_alternado': [1, 7], 'navegador': [2, 4]})
        bot._modo = 'ambos'
        bot._turno_actual = 'editor'
        bot.editor_interactor = MagicMock()
        bot.web_interactor = MagicMock()
        bot.ejecutar_tareas('vsCode', ['https://example.com'])
        editor = bot.editor_interactor.interactuar_editor.call_args.kwargs['duracion_maxima']
        navegador = bot.web_interactor.interactuar_web.call_args.kwargs['duracion_maxima']
        self.assertTrue(1 <= editor <= 7)
        self.assertTrue(2 <= navegador <= 4)

    def test_reanudacion_web_no_reinicia_el_editor(self):
        bot = AutomationBot.__new__(AutomationBot)
        from timing_config import temporizacion_config
        bot.temporizacion = temporizacion_config()
        bot._modo = 'ambos'
        bot._turno_actual = 'web'
        bot.editor_interactor = MagicMock()
        bot.web_interactor = MagicMock()
        bot.ejecutar_tareas('vsCode', ['https://example.com'])
        bot.editor_interactor.asegurar_editor_abierto.assert_not_called()
        bot.editor_interactor.interactuar_editor.assert_not_called()
        bot.web_interactor.interactuar_web.assert_called_once()
        self.assertEqual(bot._turno_actual, 'editor')

    def test_solo_web_no_abre_editor_y_sigue_en_web(self):
        bot = AutomationBot.__new__(AutomationBot)
        from timing_config import temporizacion_config
        bot.temporizacion = temporizacion_config()
        bot._modo = 'web'
        bot._turno_actual = 'web'
        bot.editor_interactor = MagicMock()
        bot.web_interactor = MagicMock()
        for _ in range(2):
            bot.ejecutar_tareas('vsCode', ['https://example.com'])
        self.assertEqual(bot.editor_interactor.mock_calls, [])
        self.assertEqual(bot.web_interactor.interactuar_web.call_count, 2)
        self.assertEqual(bot._turno_actual, 'web')

    def test_solo_web_requiere_navegador_y_paginas_antes_de_iniciar(self):
        bot = AutomationBot()
        for browser, paginas in [(None, []), ('chrome', []), (None, ['https://example.com'])]:
            with self.subTest(browser=browser, paginas=paginas):
                with self.assertRaises(ValueError):
                    bot.gestionar_ejecucion(Configuracion(modo='web', browser=browser, paginas=paginas))

    def test_portapapeles_copiado_en_pausa_se_conserva_al_final(self):
        self.editor._portapapeles_original = 'antiguo'
        self.editor.portapapeles_bot['ultimo'] = 'bot'
        with patch.object(self.editor, 'leer_portapapeles', return_value='texto nuevo del usuario'):
            self.editor.conservar_portapapeles_usuario()
        with patch.object(self.editor, 'leer_portapapeles', return_value='bot'), \
                patch('clipboard_state.restaurar', return_value=True) as restaurar:
            self.editor.restaurar_portapapeles()
        restaurar.assert_called_once()
        self.assertEqual(self.editor._portapapeles_original, 'texto nuevo del usuario')

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

    def test_visita_intervenida_se_conserva_y_continua_en_otra(self):
        url = 'https://example.com'
        self.web._contexto = {'abierta': True, 'navegada': True, 'intervenida': True,
                              'pagina': url, 'url': url}
        with patch.object(self.web, 'activar_navegador', return_value=True), \
                patch.object(self.web, 'copiar_al_portapapeles', return_value=True), \
                patch.object(self.web, '_leer_url_actual', return_value=url), \
                patch.object(self.web, 'interactuar_con_pagina', side_effect=[PausaPorActividad(), None]):
            with self.assertRaises(PausaPorActividad):
                self.web._procesar_pagina(url)
            self.web._procesar_pagina(url)
        self.assertEqual(teclado.hotkey.call_args_list.count(unittest.mock.call(self.web.cmd_key, 't')), 2)
        self.assertNotIn(unittest.mock.call(self.web.cmd_key, 'w'), teclado.hotkey.call_args_list)

    def test_otra_pestana_no_se_navega_ni_se_cierra(self):
        url = 'https://example.com'
        self.web._contexto = {'abierta': True, 'navegada': True, 'intervenida': True,
                              'pagina': url, 'url': url}
        with patch.object(self.web, 'activar_navegador', return_value=True), \
                patch.object(self.web, 'copiar_al_portapapeles', return_value=True), \
                patch.object(self.web, '_leer_url_actual', return_value='https://otro.example'), \
                patch.object(self.web, 'interactuar_con_pagina') as interactuar:
            self.web._procesar_pagina(url)
        interactuar.assert_called_once()
        # Se abre la nueva pestaña antes de pegar o cerrar; la anterior se conserva.
        self.assertEqual(teclado.hotkey.call_args_list[0], unittest.mock.call(self.web.cmd_key, 't'))

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
                        patch('editor_interactor.time.monotonic', side_effect=[0, 0, 0, 2, 2]), \
                        patch.object(self.editor, 'fase_escritura') as escribir, \
                        patch.object(self.editor, 'fase_mouse') as mover:
                    self.editor.interactuar_editor(duracion_maxima=1)
                self.assertEqual(escribir.call_count, escritura)
                self.assertEqual(mover.call_count, mouse)

    def test_rotacion_espera_a_terminar_la_linea_interrumpida(self):
        self.editor.fuente_codigo = unittest.mock.Mock(spec=RealProjectSource)
        self.editor._fases_con_archivo = 3
        self.editor.bloque_actual = ['    return total;']
        self.editor.desplazamiento = 2
        with patch.object(self.editor, '_duracion_fase_escritura', return_value=0), \
                patch.object(self.editor, '_asegurar_destino'), \
                patch.object(self.editor, 'inyectar_codigo') as cargar:
            self.editor.fase_escritura(float('inf'))
            cargar.assert_not_called()
            self.assertEqual(self.editor.desplazamiento, 2)
            self.assertEqual(self.editor.bloque_actual, ['    return total;'])
            self.editor.desplazamiento = 0
            self.editor.indice_linea = 1
            self.editor.fase_escritura(float('inf'))
            cargar.assert_called_once()

    def test_interrupciones_reanudan_linea_exacta_con_sangria_y_vecinas(self):
        from contextlib import ExitStack
        original = ['const before = 1;', '    const value = fn("abc", { x: [1, 2] });  ', 'const after = 2;']
        for modo in ('fase', 'pausa'):
            for corte in (1, 2, 4, 8, len(original[1]) - 1, len(original[1])):
                with self.subTest(modo=modo, corte=corte):
                    lineas = list(original)
                    estado = {'linea': 1, 'columna': 0, 'seleccion': False, 'interrumpir': True}
                    self.editor.lineas_actuales = list(original)
                    self.editor.bloque_actual = [original[1]]
                    self.editor.inicio_bloque = 1
                    self.editor.indice_linea = 0
                    self.editor.desplazamiento = 0
                    self.editor.necesita_reposicionar = True
                    self.editor._lineas_observadas.clear()

                    def ir(numero):
                        estado.update(linea=numero - 1, columna=0, seleccion=False)
                        self.editor._confirmar_linea_mac(numero)

                    def seleccionar():
                        estado['seleccion'] = True

                    def leer_linea():
                        estado.update(columna=0, seleccion=False)
                        return lineas[estado['linea']]

                    def insertar(caracter):
                        indice = estado['linea']
                        if estado['seleccion']:
                            lineas[indice] = ''
                            estado.update(columna=0, seleccion=False)
                        columna = estado['columna']
                        lineas[indice] = lineas[indice][:columna] + caracter + lineas[indice][columna:]
                        estado['columna'] += 1

                    def pulsar(tecla):
                        if tecla == 'right':
                            estado['columna'] += 1
                            self.assertLessEqual(estado['columna'], len(lineas[estado['linea']]))
                        elif tecla == 'left':
                            estado.update(columna=0, seleccion=False)
                        else:
                            self.fail(f'Tecla inesperada: {tecla}')

                    def queda(_):
                        return not (estado['interrumpir'] and modo == 'fase'
                                    and self.editor.desplazamiento >= corte)

                    def esperar(_):
                        if estado['interrumpir'] and modo == 'pausa' and self.editor.desplazamiento >= corte:
                            raise PausaPorActividad()

                    with ExitStack() as pila:
                        for nombre, accion in {
                            '_ir_a_linea': ir, '_limpiar_linea_actual': seleccionar,
                            '_fin_linea': lambda: EditorInteractor._fin_linea(self.editor),
                            '_verificar_seleccion_linea': lambda linea: EditorInteractor._verificar_seleccion_linea(self.editor, linea),
                            '_leer_seleccion_mac': lambda: lineas[estado['linea']],
                            '_leer_linea_completa_mac': leer_linea, '_insertar_caracter': insertar,
                            '_press': pulsar, '_queda_tiempo_editor': queda, '_esperar': esperar,
                            '_guardar_linea_actual_mac': lambda: EditorInteractor._guardar_linea_actual_mac(self.editor),
                        }.items():
                            pila.enter_context(patch.object(self.editor, nombre, side_effect=accion))
                        if modo == 'pausa':
                            with self.assertRaises(PausaPorActividad):
                                self.editor._escribir_siguiente_linea(float('inf'))
                        else:
                            self.editor._escribir_siguiente_linea(float('inf'))
                        if self.editor.indice_linea == 0:
                            self.assertEqual(self.editor.desplazamiento, corte)
                            self.assertEqual(lineas[1], original[1][:corte])
                            # Otra fase puede mover el cursor, sin alterar el fragmento pendiente.
                            estado.update(linea=0, columna=0, seleccion=False, interrumpir=False)
                            self.editor.necesita_reposicionar = True
                            self.editor._escribir_siguiente_linea(float('inf'))
                    self.assertEqual(lineas, original)
                    self.assertEqual(self.editor.indice_linea, 1)
                    self.assertEqual(self.editor.desplazamiento, 0)

    def test_cambia_fuente_real_tras_tres_fases(self):
        self.editor.fuente_codigo = unittest.mock.Mock(spec=RealProjectSource)
        self.editor._fases_con_archivo = 0

        def inyectar():
            self.editor._fases_con_archivo = 0

        with patch.object(self.editor, '_queda_tiempo_editor', return_value=True), \
                patch.object(self.editor, '_duracion_fase_escritura', return_value=0), \
                patch.object(self.editor, '_asegurar_destino'), \
                patch.object(self.editor, 'inyectar_codigo', side_effect=inyectar) as cargar:
            for _ in range(3):
                self.editor.fase_escritura(float('inf'))
            cargar.assert_not_called()
            self.editor.fase_escritura(float('inf'))
            cargar.assert_called_once()
            self.assertEqual(self.editor._fases_con_archivo, 1)

    def test_cambia_fuente_real_por_tiempo_aunque_haya_pocas_fases(self):
        self.editor.fuente_codigo = unittest.mock.Mock(spec=RealProjectSource)
        self.editor._fases_con_archivo = 1
        self.editor._duracion_archivo = 120
        with patch.object(self.editor, '_queda_tiempo_editor', return_value=True), \
                patch.object(self.editor, '_duracion_fase_escritura', return_value=0), \
                patch.object(self.editor, '_asegurar_destino'), \
                patch.object(self.editor, 'inyectar_codigo') as cargar:
            self.editor._archivo_desde = editor_interactor.time.monotonic() - 60
            self.editor.fase_escritura(float('inf'))
            cargar.assert_not_called()
            self.editor._archivo_desde = editor_interactor.time.monotonic() - 121
            self.editor.fase_escritura(float('inf'))
            cargar.assert_called_once()

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

    def test_verificacion_mac_consulta_documento_del_editor_seleccionado(self):
        self.editor.editor_actual = 'vsCode'
        self.editor.ruta_archivo = '/tmp/workbreak_unico.tsx'
        self.editor.is_windows = False
        self.editor.is_mac = True
        self.editor.cmd_key = 'command'
        with patch.object(self.editor, '_activar_si_necesario', return_value=True), \
                patch.object(editor_interactor, 'documento_editor',
                             return_value='file:///tmp/workbreak_unico.tsx') as documento:
            self.editor._asegurar_destino()
        self.assertEqual(documento.call_args_list, [unittest.mock.call('com.microsoft.VSCode')] * 2)

    def test_archivo_del_usuario_con_el_mismo_nombre_no_se_acepta(self):
        self.editor.editor_actual = 'vsCode'
        self.editor.ruta_archivo = '/tmp/bot/useCanvasFonts.ts'
        self.editor.is_windows = False
        self.editor.is_mac = True
        for documento in ('file:///Users/yo/proyecto/src/useCanvasFonts.ts', '', 'missing value'):
            with self.subTest(documento=documento), \
                    patch.object(self.editor, '_activar_si_necesario', return_value=True), \
                    patch.object(editor_interactor, 'documento_editor', return_value=documento):
                with self.assertRaisesRegex(EditorNoDisponible, 'no está activo'):
                    self.editor._asegurar_destino()

    def test_ruta_del_documento_admite_var_y_espacios_codificados(self):
        carpeta = tempfile.mkdtemp()
        ruta = os.path.join(carpeta, 'mi archivo.ts')
        open(ruta, 'w').close()
        url = 'file://' + os.path.realpath(ruta).replace(' ', '%20')
        self.assertTrue(editor_interactor._misma_ruta(url, ruta))
        self.assertFalse(editor_interactor._misma_ruta(url, os.path.join(carpeta, 'otro.ts')))

    def test_pestana_lleva_el_nombre_del_codigo_sin_marca_del_bot(self):
        ruta = self.editor._crear_archivo_temporal('useCanvasFonts.ts')
        self.assertEqual(os.path.basename(ruta), 'useCanvasFonts.ts')
        self.assertNotIn('workbreak', ruta.lower())
        # Un segundo archivo con el mismo nombre no pisa el primero.
        otra = self.editor._crear_archivo_temporal('useCanvasFonts.ts')
        self.assertNotEqual(ruta, otra)
        self.assertEqual(os.path.basename(otra), 'useCanvasFonts.ts')

    def test_cambio_de_fuente_cierra_la_pestana_anterior_y_abre_otra(self):
        self.editor.EDITOR_ABIERTO = True
        self.editor.editor_actual = 'vsCode'
        self.editor.ruta_archivo = self.editor._crear_archivo_temporal('Antes.tsx')
        self.editor.fuente_codigo = SimpleNamespace(obtener_codigo=lambda: 'const a = 1;',
                                                    nombre_archivo='Despues.ts')
        with patch.object(self.editor, 'guardar_portapapeles_original'), \
                patch.object(self.editor, '_asegurar_destino'), \
                patch.object(self.editor, 'copiar_al_portapapeles', return_value=True), \
                patch.object(self.editor, '_comando_abrir_editor', side_effect=lambda _e, ruta: ['code', ruta]), \
                patch.object(self.editor, 'ejecutar_comando', return_value=True) as abrir:
            anterior = self.editor.ruta_archivo
            self.editor.inyectar_codigo()
        self.assertEqual(os.path.basename(self.editor.ruta_archivo), 'Despues.ts')
        self.assertFalse(os.path.exists(anterior))
        abrir.assert_called_once_with(['code', self.editor.ruta_archivo])
        llamadas = teclado.hotkey.call_args_list
        self.assertLess(llamadas.index(unittest.mock.call(self.editor.cmd_key, 's')),
                        llamadas.index(unittest.mock.call(self.editor.cmd_key, 'w')))
        self.assertEqual(self.editor.lineas_actuales, ['const a = 1;'])

    def test_codigo_generado_nombra_la_pestana_con_su_componente(self):
        from code_generator import CodeGenerator
        generador = CodeGenerator()
        codigo = generador.obtener_codigo()
        self.assertTrue(generador.nombre_archivo.endswith(('.tsx', '.ts')))
        self.assertNotIn('workbreak', generador.nombre_archivo.lower())
        componente = generador.nombre_archivo.rsplit('.', 1)[0]
        self.assertTrue(f'export const {componente}' in codigo or generador.nombre_archivo in
                        [r.rsplit('/', 1)[-1] for r in generador.rutas_archivos])

    def test_error_mac_conserva_diagnostico_original(self):
        self.editor.editor_actual = 'vsCode'
        self.editor.ruta_archivo = '/tmp/workbreak_unico.tsx'
        self.editor.is_windows = False
        self.editor.is_mac = True
        error = ValueError('Acceso denegado: error de accesibilidad -25211')
        with patch.object(self.editor, '_activar_si_necesario', return_value=True), \
                patch.object(editor_interactor, 'documento_editor', side_effect=error):
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

    def test_nueva_escritura_actualiza_captura_antes_de_otra_pausa(self):
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
        self.assertEqual(self.editor._lineas_observadas[1], 'ab')
        with patch.object(self.editor, '_leer_linea_completa_mac', return_value='ab'):
            self.editor._confirmar_linea_mac(1)

    def test_consulta_rectangulo_editor_es_interrumpible(self):
        self.editor.is_windows = False
        self.editor.is_mac = True
        self.editor.editor_actual = 'vsCode'
        with patch.object(self.editor, '_antes_accion', side_effect=PausaPorActividad), \
                patch('mac_accessibility.rectangulo_aplicacion') as consultar:
            with self.assertRaises(PausaPorActividad):
                self.editor._rectangulo_ventana_editor()
        consultar.assert_not_called()

    def test_consulta_titulo_editor_es_interrumpible(self):
        self.editor.is_windows = False
        self.editor.is_mac = True
        self.editor.editor_actual = 'vsCode'
        self.editor.ruta_archivo = '/tmp/workbreak_unico.tsx'
        monitor = MagicMock()
        self.editor.monitor_actividad = monitor

        def leer_documento(_bundle):
            monitor.comprobar.side_effect = PausaPorActividad
            return 'file:///tmp/workbreak_unico.tsx'

        with patch.object(self.editor, '_activar_si_necesario', return_value=True), \
                patch.object(editor_interactor, 'documento_editor', side_effect=leer_documento):
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
        self.editor.bloque_actual = ['    return valor;']
        self.editor.inicio_bloque = 3
        self.editor.indice_linea = 0
        self.editor.desplazamiento = len('    return va')
        with patch.object(self.editor, '_leer_linea_completa_mac', return_value='    return va'):
            EditorInteractor._guardar_linea_actual_mac(self.editor)
        self.assertEqual(self.editor._lineas_observadas, {4: '    return va'})

    def test_lectura_selecciona_linea_completa_y_quita_solo_el_salto(self):
        self.editor.cmd_key = 'command'
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

    def test_reescritura_mac_conserva_sangria_sin_segundo_reemplazo(self):
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
                patch.object(self.editor, '_hotkey', side_effect=hotkey) as atajo, \
                patch.object(self.editor, '_write', side_effect=escribir):
            self.editor._escribir_siguiente_linea(float('inf'))
        self.assertEqual(estado['texto'], '    x')
        self.assertNotIn(unittest.mock.call('command', 'left'), atajo.call_args_list)
        self.assertNotIn(unittest.mock.call('command', 'v'), atajo.call_args_list)

    def test_lineas_vacias_no_seleccionan_ni_borran_el_salto(self):
        self.editor.bloque_actual = ['', '   ', 'const siguiente = 1;']
        with patch.object(self.editor, '_limpiar_linea_actual') as seleccionar, \
                patch.object(self.editor, '_ir_a_linea') as ir:
            self.editor._escribir_siguiente_linea(float('inf'))
            self.editor._escribir_siguiente_linea(float('inf'))
        seleccionar.assert_not_called()
        ir.assert_not_called()
        self.assertEqual(self.editor.indice_linea, 2)

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

    def test_copia_fallida_no_cierra_una_pestana_sin_identidad_confirmada(self):
        with patch.object(self.web, 'activar_navegador', return_value=True), \
                patch.object(self.web, 'copiar_al_portapapeles', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'copiar la URL'):
                self.web._procesar_pagina('https://example.com')
        self.assertEqual(teclado.hotkey.call_args_list,
                         [unittest.mock.call(self.web.cmd_key, 't')])

    def test_failsafe_se_propaga_sin_enviar_teclas_de_limpieza(self):
        with patch.object(self.web, 'activar_navegador', return_value=True), \
                patch.object(self.web, 'copiar_al_portapapeles', side_effect=FailSafeException):
            with self.assertRaises(FailSafeException):
                self.web._procesar_pagina('https://example.com')
        self.assertEqual(teclado.hotkey.call_args_list,
                         [unittest.mock.call(self.web.cmd_key, 't')])

    def test_copia_pendiente_no_se_atribuye_por_contador(self):
        self.editor._portapapeles_original = 'usuario'
        self.editor.portapapeles_bot.update(ultimo='marcador', copia_pendiente=True)
        with patch.object(self.editor, 'leer_portapapeles', return_value='fragmento'):
            self.editor.conservar_portapapeles_usuario()
        self.assertEqual(self.editor._portapapeles_original, 'fragmento')
        self.assertEqual(self.editor.portapapeles_bot['ultimo'], 'marcador')
        self.assertNotIn('copia_pendiente', self.editor.portapapeles_bot)

    def test_copia_ambigua_del_usuario_no_se_sobrescribe_al_salir(self):
        self.editor._portapapeles_original = 'antiguo'
        self.editor.portapapeles_bot.update(ultimo='marcador', copia_pendiente=True)
        with patch.object(self.editor, 'leer_portapapeles', return_value='nuevo'), \
                patch.object(self.editor, 'copiar_al_portapapeles') as copiar:
            self.editor.conservar_portapapeles_usuario()
            self.editor.restaurar_portapapeles()
        copiar.assert_not_called()
        self.assertEqual(self.editor._portapapeles_original, 'nuevo')

    def test_copia_interrumpida_conserva_formatos_actuales_antes_de_continuar(self):
        estado = {'version': 2, 'items': [[('public.png', b'imagen usuario')]]}
        self.editor._portapapeles_original = 'anterior'
        self.editor.portapapeles_bot.update(ultimo='bot', version=1, copia_pendiente=True)
        with patch('clipboard_state.version', return_value=2), \
                patch('clipboard_state.capturar', return_value=estado), \
                patch.object(self.editor, 'leer_portapapeles', return_value=''), \
                patch.object(self.editor, 'copiar_al_portapapeles') as copiar:
            self.editor.conservar_portapapeles_usuario()
        copiar.assert_not_called()
        self.assertEqual(self.editor._formatos_portapapeles, estado)
        self.assertNotIn('copia_pendiente', self.editor.portapapeles_bot)

    def test_lectura_fallida_no_guarda_un_portapapeles_vacio(self):
        self.editor._portapapeles_original = 'original'
        self.editor.portapapeles_bot['ultimo'] = 'bot'
        fallo = subprocess.CompletedProcess(['lectura'], 1, '', 'error')
        with patch.object(self.editor, '_ejecutar_proceso', return_value=fallo):
            with self.assertRaises(EditorNoDisponible):
                self.editor.conservar_portapapeles_usuario()
        self.assertEqual(self.editor._portapapeles_original, 'original')

    def test_timeout_de_lectura_no_se_convierte_en_texto_vacio(self):
        with patch.object(self.editor, '_ejecutar_proceso', side_effect=subprocess.TimeoutExpired('lectura', 5)):
            with self.assertRaises(PortapapelesNoDisponible):
                self.editor.leer_portapapeles()

    def test_portapapeles_realmente_vacio_sigue_siendo_valido(self):
        self.editor._portapapeles_original = 'original'
        self.editor.portapapeles_bot['ultimo'] = 'bot'
        lectura = subprocess.CompletedProcess(['lectura'], 0, '', '')
        with patch.object(self.editor, '_ejecutar_proceso', return_value=lectura):
            self.editor.conservar_portapapeles_usuario()
        self.assertEqual(self.editor._portapapeles_original, '')

    def test_inyeccion_se_cancela_si_no_puede_guardar_el_portapapeles(self):
        with patch.object(self.editor, 'leer_portapapeles', side_effect=PortapapelesNoDisponible('error')), \
                patch.object(self.editor, 'copiar_al_portapapeles') as copiar:
            with self.assertRaises(EditorNoDisponible):
                self.editor.inyectar_codigo()
        copiar.assert_not_called()
        teclado.hotkey.assert_not_called()

    def test_un_enlace_que_cambia_de_pestana_no_provoca_cierre_de_la_activa(self):
        estado = {'activa': 'original', 'cerradas': []}

        def atajo(*teclas):
            if teclas[-1] == 't':
                estado['activa'] = 'bot'
            elif teclas[-1] == 'w':
                estado['cerradas'].append(estado['activa'])

        def enlace(*_):
            estado['activa'] = 'enlace'

        with patch.object(self.web, 'activar_navegador', return_value=True), \
                patch.object(self.web, 'copiar_al_portapapeles', return_value=True), \
                patch.object(self.web, '_leer_url_actual', return_value='https://example.com'), \
                patch.object(self.web, '_hotkey', side_effect=atajo), \
                patch.object(self.web, 'interactuar_con_pagina', side_effect=enlace):
            self.web._procesar_pagina('https://example.com')
        self.assertEqual(estado['activa'], 'enlace')
        self.assertEqual(estado['cerradas'], [])

    def test_prefijo_igual_no_autoriza_sobrescribir_cambios_del_usuario(self):
        self.editor.lineas_actuales = ['return total;']
        self.editor.bloque_actual = ['return total;']
        self.editor.desplazamiento = 6
        self.editor._lineas_observadas[1] = 'return'
        with patch.object(self.editor, '_leer_linea_completa_mac', return_value='return secreto;'):
            with self.assertRaises(EditorNoDisponible):
                self.editor._confirmar_linea_mac(1)

    def test_caracter_se_escribe_sin_usar_portapapeles(self):
        with patch.object(self.editor, 'copiar_al_portapapeles') as copiar:
            EditorInteractor._insertar_caracter(self.editor, '(')
        copiar.assert_not_called()
        teclado.hotkey.assert_not_called()
        teclado.write.assert_called_once_with('(', interval=0)

    def test_escritura_reutiliza_ventana_existente_y_solo_crea_otra_si_no_hay(self):
        self.editor.acciones = {'escribir': True, 'click': True, 'scroll': True, 'mover_mouse': True}
        for existente in (True, False):
            with self.subTest(existente=existente), \
                    patch.object(self.editor, '_obtener_codigo', return_value='const a = 1;'), \
                    patch.object(self.editor, '_crear_archivo_temporal', return_value='/tmp/bot/archivo.tsx'), \
                    patch.object(self.editor, '_editor_tiene_ventana', return_value=existente), \
                    patch.object(self.editor, '_lanzar_editor', return_value='vsCode') as lanzar, \
                    patch.object(self.editor, '_esperar_ventana_editor', return_value=True), \
                    patch.object(self.editor, '_esperar'), \
                    patch.object(self.editor, '_comprobar_atajo_corrida'), \
                    patch.object(self.editor, '_asegurar_destino') as verificar, \
                    patch.object(self.editor, '_llevar_mouse_al_editor'):
                self.editor.EDITOR_ABIERTO = False
                self.editor.abrir_editor('vsCode')
                self.assertEqual(self.editor.reutilizar_ventana, existente)
                lanzar.assert_called_once_with('vsCode', '/tmp/bot/archivo.tsx')
                verificar.assert_called_once()

    @unittest.skipUnless(sys.platform == 'darwin', 'Lanzamiento nativo de VS Code en macOS')
    def test_abrir_espacio_nuevo_y_recuperar_solo_el_archivo(self):
        self.editor.is_mac = True
        self.editor.directorio_trabajo = '/tmp/workbreak_prueba'
        aplicacion = MagicMock()
        aplicacion.path.return_value = '/Applications/Visual Studio Code.app'
        with patch('AppKit.NSWorkspace') as workspace, \
                patch('editor_interactor.Path.is_file', return_value=True):
            workspace.sharedWorkspace.return_value.URLForApplicationWithBundleIdentifier_.return_value = aplicacion
            inicial = self.editor._comando_abrir_editor('vsCode', '/tmp/workbreak_prueba/archivo.tsx')
            self.assertEqual(inicial[1:], ['--new-window', '/tmp/workbreak_prueba', '/tmp/workbreak_prueba/archivo.tsx'])
            self.editor.EDITOR_ABIERTO = True
            recuperar = self.editor._comando_abrir_editor('vsCode', '/tmp/workbreak_prueba/archivo.tsx')
            self.assertEqual(recuperar[1:], ['/tmp/workbreak_prueba/archivo.tsx'])
            # Con una ventana del editor ya abierta, el archivo se abre en ella sin la carpeta.
            self.editor.EDITOR_ABIERTO = False
            self.editor.reutilizar_ventana = True
            existente = self.editor._comando_abrir_editor('vsCode', '/tmp/workbreak_prueba/archivo.tsx')
            self.assertEqual(existente[1:], ['--reuse-window', '/tmp/workbreak_prueba/archivo.tsx'])

    def test_atajos_esperan_a_que_el_editor_este_al_frente(self):
        self.editor.is_mac = True
        info = self.editor.EDITOR_INFO['vsCode']
        appkit = MagicMock()
        terminal = SimpleNamespace(bundleIdentifier=lambda: 'com.apple.Terminal', processIdentifier=lambda: 7)
        editor = SimpleNamespace(bundleIdentifier=lambda: info['bundle'], processIdentifier=lambda: 42)
        frentes = appkit.NSWorkspace.sharedWorkspace.return_value.frontmostApplication
        with patch.dict(sys.modules, {'AppKit': appkit}), \
                patch('mac_accessibility._actualizar_workspace'), \
                patch('mac_accessibility.aplicacion', return_value=editor), \
                patch.object(self.editor, '_activar_si_necesario', return_value=True):
            frentes.side_effect = [terminal, terminal, editor]
            self.assertTrue(EditorInteractor._esperar_editor_al_frente(self.editor, info))
            frentes.side_effect = None
            frentes.return_value = terminal
            self.assertFalse(EditorInteractor._esperar_editor_al_frente(self.editor, info, limite=0.3))

    def test_sin_editor_al_frente_no_se_envian_atajos(self):
        self.editor.editor_actual = 'vsCode'
        self.editor.ruta_archivo = '/tmp/workbreak_unico.tsx'
        with patch.object(self.editor, '_activar_si_necesario', return_value=True), \
                patch.object(self.editor, '_esperar_editor_al_frente', return_value=False):
            with self.assertRaisesRegex(EditorNoDisponible, 'primer plano'):
                self.editor._asegurar_destino()
        teclado.hotkey.assert_not_called()

    def test_detecta_ventana_abierta_del_editor(self):
        self.editor.is_mac = True
        appkit, cuarzo = MagicMock(), MagicMock()
        appkit.NSRunningApplication.runningApplicationsWithBundleIdentifier_.return_value = [
            SimpleNamespace(processIdentifier=lambda: 40)]
        ventana = {'kCGWindowLayer': 0, 'kCGWindowOwnerPID': 40,
                   'kCGWindowBounds': {'Width': 1200, 'Height': 800}}
        with patch.dict(sys.modules, {'AppKit': appkit, 'Quartz': cuarzo}):
            cuarzo.CGWindowListCopyWindowInfo.return_value = [ventana]
            self.assertTrue(EditorInteractor._editor_tiene_ventana(self.editor, 'vsCode'))
            # Ventanas de otra app o auxiliares diminutas no cuentan.
            cuarzo.CGWindowListCopyWindowInfo.return_value = [
                dict(ventana, kCGWindowOwnerPID=41),
                dict(ventana, kCGWindowBounds={'Width': 10, 'Height': 10})]
            self.assertFalse(EditorInteractor._editor_tiene_ventana(self.editor, 'vsCode'))
            appkit.NSRunningApplication.runningApplicationsWithBundleIdentifier_.return_value = []
            self.assertFalse(EditorInteractor._editor_tiene_ventana(self.editor, 'vsCode'))

    def test_ventana_reutilizada_toma_el_codigo_que_muestra_el_editor(self):
        self.editor.reutilizar_ventana = True
        self.editor.fuente_codigo = MagicMock(obtener_codigo=MagicMock(return_value='a\n    b'))
        with patch.object(self.editor, 'guardar_portapapeles_original'), \
                patch.object(self.editor, '_asegurar_destino'), \
                patch.object(self.editor, 'copiar_al_portapapeles', return_value=True), \
                patch.object(self.editor, '_leer_seleccion_mac', return_value='a\n  b\n'):
            self.editor.inyectar_codigo()
        # El formateo del usuario al pegar cambió la sangría: se usa lo que quedó.
        self.assertEqual(self.editor.lineas_actuales, ['a', '  b'])

    def test_ventana_reutilizada_resincroniza_en_vez_de_detenerse(self):
        self.editor.reutilizar_ventana = True
        self.editor.editor_actual = 'vsCode'
        self.editor.lineas_actuales = ['uno', 'dos']
        self.editor.bloque_actual = ['dos']
        self.editor.inicio_bloque = 1
        with patch.object(self.editor, '_asegurar_destino') as asegurar, \
                patch.object(self.editor, 'identidad_ventana_activa', return_value=1), \
                patch.object(self.editor, '_escribir_siguiente_linea', side_effect=LineaDesincronizada), \
                patch.object(self.editor, '_leer_seleccion_mac', return_value='uno\n  dos'):
            self.editor._editar_bloque_real(float('inf'))
            self.assertEqual(self.editor.lineas_actuales, ['uno', '  dos'])
            self.assertIsNone(self.editor.bloque_actual)
            # Tres desajustes seguidos se toleran; el cuarto detiene la edición.
            for _ in range(2):
                self.editor._editar_bloque_real(float('inf'))
            with self.assertRaises(EditorNoDisponible):
                self.editor._editar_bloque_real(float('inf'))
        asegurar.assert_called()

    def test_linea_distinta_en_ventana_propia_del_bot_sigue_deteniendo(self):
        self.editor.lineas_actuales = ['uno']
        with patch.object(self.editor, '_leer_linea_completa_mac', return_value='otra'):
            with self.assertRaises(EditorNoDisponible):
                self.editor._confirmar_linea_mac(1)
            self.editor.reutilizar_ventana = True
            with self.assertRaises(LineaDesincronizada):
                self.editor._confirmar_linea_mac(1)

    def test_ventana_reutilizada_va_a_la_linea_con_el_panel(self):
        self.editor.is_mac = True
        self.editor.cmd_key = 'command'
        self.editor.reutilizar_ventana = True
        self.editor.atajo_ir_linea = ('option', 'g')
        self.editor.directorio_trabajo = '/tmp/workbreak_prueba'
        with patch.object(self.editor, 'ejecutar_comando') as comando, \
                patch.object(self.editor, '_leer_seleccion_mac', return_value=':'), \
                patch.object(self.editor, '_confirmar_linea_mac') as confirmar:
            self.editor._ir_a_linea(14)
        comando.assert_not_called()
        teclado.hotkey.assert_any_call('option', 'g')
        teclado.write.assert_called_once_with(':14:1', interval=0.03)
        confirmar.assert_called_once_with(14)

    def test_copia_lenta_del_editor_se_espera_antes_de_fallar(self):
        marcador = 'workbreak:sin-seleccion'
        with patch.object(self.editor, 'copiar_al_portapapeles', return_value=True), \
                patch.object(self.editor, 'copiar_seleccion', return_value=marcador), \
                patch.object(self.editor, 'leer_portapapeles', side_effect=[marcador, 'linea copiada']):
            self.assertEqual(self.editor._leer_seleccion_mac(), 'linea copiada')
        with patch.object(self.editor, 'copiar_al_portapapeles', return_value=True), \
                patch.object(self.editor, 'copiar_seleccion', return_value=marcador), \
                patch.object(self.editor, 'leer_portapapeles', return_value=marcador), \
                patch('editor_interactor.time.monotonic', side_effect=[0, 0, 0.5, 1.1]):
            self.assertIsNone(self.editor._leer_seleccion_mac())

    def test_caracteres_se_teclean_sin_usar_portapapeles(self):
        for reutilizar in (False, True):
            self.editor.reutilizar_ventana = reutilizar
            with patch.object(self.editor, 'copiar_al_portapapeles') as copiar, \
                    patch.object(self.editor, '_write') as escribir:
                EditorInteractor._insertar_caracter(self.editor, '(')
            escribir.assert_called_once_with('(')
            copiar.assert_not_called()

    def test_atajo_se_resuelve_una_vez_por_corrida(self):
        self.editor.atajo_ir_linea = None
        self.editor.editor_actual = 'vsCode'
        with patch.object(editor_interactor, 'resolver_atajo', side_effect=[('option', 'g'), ('ctrl', 'l')]) as resolver:
            self.editor._comprobar_atajo_corrida()
            self.editor._comprobar_atajo_corrida()
            self.assertEqual(resolver.call_count, 1)
            self.assertEqual(self.editor.atajo_ir_linea, ('option', 'g'))
            self.editor.atajo_ir_linea = None
            self.editor._comprobar_atajo_corrida()
            self.assertEqual(resolver.call_count, 2)
            self.assertEqual(self.editor.atajo_ir_linea, ('ctrl', 'l'))

    def test_sin_atajo_confirmado_no_se_envia_teclado(self):
        self.editor.atajo_ir_linea = None
        with self.assertRaises(EditorNoDisponible):
            self.editor._ir_a_linea(25)
        teclado.hotkey.assert_not_called()
        teclado.write.assert_not_called()

    def test_archivo_windows_conserva_identidad_unica(self):
        self.editor.is_windows = True
        ruta = self.editor._crear_archivo_temporal('App.tsx')
        self.assertTrue(os.path.basename(ruta).startswith('workbreak_'))
        self.assertTrue(os.path.basename(ruta).endswith('_App.tsx'))
        self.assertIn(os.path.basename(self.editor.directorio_trabajo), os.path.basename(ruta))

    def test_movimientos_del_bot_se_anuncian_al_monitor(self):
        self.editor.monitor_actividad = MagicMock()
        teclado.position.return_value = (0, 0)
        self.editor._move_to(4000, 500)
        self.editor.monitor_actividad.marcar_movimiento_bot.assert_called_once_with(4000, 500)
        teclado.moveTo.assert_called_once_with(4000, 500, _pause=False)

    def test_inicio_del_editor_lleva_el_mouse_a_su_ventana(self):
        self.editor.acciones = {'escribir': True, 'click': False, 'scroll': False, 'mover_mouse': True}
        teclado.position.return_value = (3000, 500)
        with patch.object(self.editor, '_rectangulo_ventana_editor', return_value=(0, 0, 1000, 800)), \
                patch.object(self.editor, '_move_to') as mover:
            self.editor._llevar_mouse_al_editor()
        mover.assert_called_once()
        self.editor.acciones['mover_mouse'] = False
        with patch.object(self.editor, '_move_to') as mover:
            self.editor._llevar_mouse_al_editor()
        mover.assert_not_called()

    def test_navegacion_usa_el_atajo_detectado_y_confirma_el_panel(self):
        self.editor.is_mac = True
        self.editor.atajo_ir_linea = ('ctrl', 'l')
        with patch.object(self.editor, '_leer_seleccion_mac', return_value=':'), \
                patch.object(self.editor, '_confirmar_linea_mac') as confirmar:
            self.editor._ir_a_linea(25)
        teclado.hotkey.assert_any_call('ctrl', 'l')
        teclado.write.assert_called_once_with(':25:1', interval=0.03)
        confirmar.assert_called_once_with(25)

    def test_panel_tardio_no_recibe_coordenadas_hasta_confirmarse(self):
        self.editor.is_mac = True
        self.editor.atajo_ir_linea = ('ctrl', 'g')
        def leer():
            teclado.write.assert_not_called()
            return next(lecturas)
        lecturas = iter([None, 'codigo fuera del panel', ':23'])
        with patch.object(self.editor, '_leer_seleccion_mac', side_effect=leer), \
                patch.object(self.editor, '_confirmar_linea_mac') as confirmar:
            self.editor._ir_a_linea(25)
        teclado.hotkey.assert_any_call('ctrl', 'g')
        teclado.write.assert_called_once_with(':25:1', interval=0.03)
        confirmar.assert_called_once_with(25)

    def test_actividad_durante_lectura_del_panel_pausa_sin_escribir(self):
        self.editor.is_mac = True
        with patch.object(self.editor, '_leer_seleccion_mac', side_effect=PausaPorActividad), \
                patch.object(self.editor, '_confirmar_linea_mac') as confirmar:
            with self.assertRaises(PausaPorActividad):
                self.editor._ir_a_linea(25)
        teclado.write.assert_not_called()
        confirmar.assert_not_called()

    def test_error_navegando_no_autoriza_reescritura(self):
        self.editor.is_mac = True
        with patch.object(self.editor, '_leer_seleccion_mac', return_value='codigo fuera del panel'), \
                patch('editor_interactor.time.monotonic', side_effect=[0, 4]), \
                patch.object(self.editor, '_confirmar_linea_mac') as confirmar:
            with self.assertRaises(EditorNoDisponible):
                self.editor._ir_a_linea(25)
        confirmar.assert_not_called()
        teclado.write.assert_not_called()

    def test_espacio_temporal_aisla_autocierre_y_formateo(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temporal, \
                patch('editor_interactor.tempfile.mkdtemp', return_value=temporal):
            ruta = Path(self.editor._crear_archivo_temporal())
            self.assertEqual(ruta.read_text(), '')
            ajustes = json.loads((ruta.parent / '.vscode/settings.json').read_text())
            self.assertEqual(ajustes['editor.autoClosingBrackets'], 'never')
            self.assertFalse(ajustes['[typescriptreact]']['editor.formatOnType'])
            self.assertFalse(ajustes['editor.trimAutoWhitespace'])
            self.assertFalse(ajustes['editor.formatOnSave'])
            self.assertFalse(ajustes['files.trimTrailingWhitespace'])
            self.assertEqual(ajustes['files.autoSave'], 'off')
            self.assertEqual(self.editor.directorio_trabajo, str(ruta.parent))

    def test_mouse_se_limita_al_area_segura_y_no_pulsa_fuera(self):
        self.editor.is_mac = False
        self.editor._area_mouse = (100, 200, 500, 600)
        self.editor._move_to(2000, 0)
        teclado.moveTo.assert_called_once_with(500, 200, duration=0)
        teclado.position.return_value = (0, 0)
        with self.assertRaisesRegex(RuntimeError, 'fuera del área'):
            self.editor._click()
        teclado.click.assert_not_called()

    def test_area_mouse_en_monitores_a_derecha_izquierda_y_arriba(self):
        for monitor in [(1920, 0, 2560, 1440), (-1920, 0, 1920, 1080),
                        (0, -1440, 2560, 1440)]:
            with self.subTest(monitor=monitor), patch.object(
                    self.editor, '_monitores', return_value=[(0, 0, 1920, 1080), monitor]):
                x, y, ancho, alto = monitor
                centro = self.editor._configurar_area_mouse((x + 50, y + 50, 1200, 900))
                self.assertTrue(x <= centro[0] < x + ancho)
                self.assertTrue(y <= centro[1] < y + alto)
                self.assertEqual(self.editor._area_mouse,
                                 (x + 450, y + 210, x + 1220, y + 890))

    def test_ventana_entre_pantallas_elige_area_continua_y_evitar_huecos(self):
        with patch.object(self.editor, '_monitores', return_value=[
                (0, 0, 1920, 1080), (1920, -1080, 1920, 1080)]):
            self.editor._configurar_area_mouse((1500, -500, 1800, 1400))
            izquierda, arriba, derecha, abajo = self.editor._area_mouse
            self.assertGreaterEqual(izquierda, 1920)
            self.assertLess(abajo, 0)
            with self.assertRaisesRegex(RuntimeError, 'visible suficiente'):
                self.editor._configurar_area_mouse((-3000, 0, 1000, 800))
            self.assertIsNone(self.editor._area_mouse)

    def test_mac_usa_posicion_quartz_sin_conversion_retina(self):
        from base_automation import BaseAutomation
        quartz = SimpleNamespace(CGEventCreate=lambda _: 'evento',
                                CGEventGetLocation=lambda _: SimpleNamespace(x=-800, y=-350))
        self.editor.is_mac = True
        with patch.dict(sys.modules, {'Quartz': quartz}):
            self.assertEqual(BaseAutomation._posicion_mouse(self.editor), (-800, -350))

    def test_mac_click_y_scroll_reciben_coordenadas_globales(self):
        self.editor.is_mac = True
        self.editor._area_mouse = (-1800, -900, -100, -100)
        teclado.position.return_value = (-800, -350)
        self.editor._click()
        self.editor._scroll(4)
        teclado.click.assert_called_once_with(-800, -350)
        teclado.scroll.assert_called_once_with(4, -800, -350)

    def test_movimiento_mac_interpolado_llega_a_monitor_negativo(self):
        teclado.moveTo.reset_mock()
        self.editor.is_mac = True
        teclado.position.return_value = (800, 400)
        self.editor._area_mouse = (-1800, -900, -100, -100)
        self.editor._move_to(-800, -350, duration=0.03)
        self.assertEqual(teclado.moveTo.call_count, 3)
        teclado.moveTo.assert_called_with(-800, -350, _pause=False)

    def test_turnos_web_nuevos_empiezan_por_la_primera_pagina(self):
        self.web.set_paginas(['https://uno.example', 'https://dos.example', 'https://tres.example'])
        visitadas = []
        agotado = [False]

        def procesar(pagina, _fin):
            visitadas.append(pagina)
            agotado[0] = True

        with patch.object(self.web, '_procesar_pagina', side_effect=procesar), \
                patch.object(self.web, '_queda_tiempo', side_effect=lambda _: not agotado[0]):
            for _ in range(3):
                agotado[0] = False
                self.web.interactuar_web(30)
        self.assertEqual(visitadas, [self.web.paginas[0]] * 3)
        self.assertEqual(self.web._indice_pagina, 1)

    def test_turnos_web_reutilizan_pestana_sin_saltar_las_primeras_webs(self):
        uno, dos = 'https://uno.example', 'https://dos.example'
        self.web.set_paginas([uno, dos])
        with patch.object(self.web, 'activar_navegador', return_value=True), \
                patch.object(self.web, 'copiar_al_portapapeles', return_value=True) as copiar, \
                patch.object(self.web, '_url_pestana', side_effect=[uno, uno, dos, dos, uno, uno, dos]), \
                patch.object(self.web, 'interactuar_con_pagina') as interactuar:
            for _ in range(2):
                self.web.interactuar_web(30)
        self.assertEqual([c.args[0] for c in copiar.call_args_list], [uno, dos, uno, dos])
        self.assertEqual([c.args[0] for c in interactuar.call_args_list], [uno, dos, uno, dos])
        self.assertEqual(teclado.hotkey.call_args_list.count(unittest.mock.call(self.web.cmd_key, 't')), 1)

    def test_visita_agotada_no_contamina_la_siguiente(self):
        self.web._visita_restante = 0
        self.web.interactuar_con_pagina('https://example.com')
        self.assertIsNone(self.web._visita_restante)
        teclado.click.assert_not_called()

    def test_pagina_no_iniciada_por_fin_de_turno_sigue_pendiente(self):
        self.web.set_paginas(['https://uno.example', 'https://dos.example'])
        with patch.object(self.web, '_procesar_pagina', return_value=False):
            self.web.interactuar_web(30)
        self.assertEqual(self.web._indice_pagina, 0)

    def test_limite_agotado_impide_enviar_texto(self):
        self.editor.set_limite_tiempo(0)
        with self.assertRaises(TiempoAgotado):
            self.editor._write('texto')
        teclado.write.assert_not_called()

    def test_procesos_macos_usan_utf8_aunque_finder_no_defina_idioma(self):
        self.editor.is_mac = True
        entorno = {'PATH': '/usr/bin:/bin'}
        for asincrono in (False, True):
            self.editor.monitor_actividad = MagicMock() if asincrono else None
            proceso = MagicMock(returncode=0)
            proceso.communicate.return_value = ('inyección', '')
            with patch.dict('os.environ', entorno, clear=True), \
                    patch('base_automation.subprocess.run', return_value=proceso) as directo, \
                    patch('base_automation.subprocess.Popen', return_value=proceso) as separado:
                self.editor._ejecutar_proceso(['pbpaste'], capture_output=True, text=True)
            opciones = (separado if asincrono else directo).call_args.kwargs
            self.assertEqual(opciones['env']['LC_ALL'], 'es_ES.UTF-8')
            self.assertEqual(opciones['env']['PATH'], '/usr/bin:/bin')
            self.assertEqual(opciones['encoding'], 'utf-8')
            self.assertEqual(entorno, {'PATH': '/usr/bin:/bin'})

    def test_proceso_con_entrada_no_la_reenvia_tras_timeout(self):
        self.editor.monitor_actividad = MagicMock()
        proceso = MagicMock()
        proceso.returncode = 0
        proceso.communicate.side_effect = [subprocess.TimeoutExpired('pbcopy', .02), (None, None)]
        with patch('base_automation.subprocess.Popen', return_value=proceso):
            self.editor._ejecutar_proceso(['pbcopy'], input='texto', text=True)
        self.assertEqual(proceso.communicate.call_args_list[0].kwargs['input'], 'texto')
        self.assertIsNone(proceso.communicate.call_args_list[1].kwargs['input'])


if __name__ == '__main__':
    unittest.main()
