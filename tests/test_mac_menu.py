from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

if sys.platform == 'darwin':
    from mac_menu import MenuWorkBreak, normalizar_webs


@unittest.skipUnless(sys.platform == 'darwin', 'Interfaz exclusiva de macOS')
class MenuMacTest(unittest.TestCase):
    def setUp(self):
        # Solo se ejercita configuración; no se crean iconos, ventanas ni procesos.
        with patch('mac_menu.ControladorBot', return_value=MagicMock()), \
                patch('mac_menu.cargar_preferencias', return_value=None):
            self.menu = MenuWorkBreak.alloc().init()
        self.menu.controlador.activo = False
        self.menu.controlador.permisos_pendientes = []
        self.menu.construir_menu = MagicMock()
        guardar = patch('mac_menu.guardar_preferencias')
        guardar.start()
        self.addCleanup(guardar.stop)

    def test_aviso_permisos_abre_panel_seleccionado(self):
        alerta = MagicMock()
        alerta.runModal.return_value = 1001
        with patch('mac_menu.NSAlert') as fabrica, \
                patch('mac_menu.abrir_configuracion', return_value=True) as abrir:
            fabrica.alloc.return_value.init.return_value = alerta
            self.menu.mostrar_permisos(['accesibilidad', 'entrada'])
        abrir.assert_called_once_with('entrada')

    def test_cancelar_aviso_no_abre_configuracion(self):
        alerta = MagicMock()
        alerta.runModal.return_value = 1001
        with patch('mac_menu.NSAlert') as fabrica, patch('mac_menu.abrir_configuracion') as abrir:
            fabrica.alloc.return_value.init.return_value = alerta
            self.menu.mostrar_permisos(['accesibilidad'])
        abrir.assert_not_called()

    def test_cierre_nativo_espera_limpieza_sin_bloquear_el_hilo_principal(self):
        self.menu.actualizador.preparada = {'carpeta': '/tmp/prueba'}
        with patch.object(self.menu.actualizador, 'descartar') as descartar, \
                patch.object(self.menu, 'solicitar_salida') as salir:
            def iniciar_limpieza():
                self.menu.actualizador._limpiezas.add('/tmp/prueba')
            descartar.side_effect = iniciar_limpieza
            self.assertEqual(self.menu.applicationShouldTerminate_(None), 0)
        salir.assert_called_once()

    def test_dialogo_tiempo_rechaza_numeros_extremos_sin_excepcion_nativa(self):
        from mac_menu import DialogoTiempo
        dialogo = DialogoTiempo.alloc().init()
        dialogo.preparar(1)
        dialogo.campos[0].setStringValue_('9'*5000)
        notificacion = MagicMock()
        notificacion.object.return_value = dialogo.campos[0]
        dialogo.controlTextDidChange_(notificacion)
        with patch('mac_menu.NSApplication') as app:
            dialogo.guardar_(None)
        app.sharedApplication.assert_not_called()
        self.assertIn('válidas', dialogo.error.stringValue())

    def test_webs_se_normalizan_y_se_eliminan_duplicados(self):
        self.assertEqual(normalizar_webs('example.com, https://example.com\nhttp://localhost:8000'),
                         ['https://example.com', 'http://localhost:8000'])

    def test_web_invalida_no_sustituye_la_configuracion(self):
        self.menu.config['paginas'] = ['https://example.com']
        with patch('mac_menu.DialogoWebs') as dialogo:
            dialogo.alloc.return_value.init.return_value.mostrar.return_value = None
            self.menu.configurar('webs')
        self.assertEqual(self.menu.config['paginas'], ['https://example.com'])

    def test_tiempo_y_acciones_se_configuran_sin_menu_terminal(self):
        with patch('mac_menu.DialogoTiempo') as dialogo:
            instancia = dialogo.alloc.return_value.init.return_value
            instancia.mostrar.return_value = True
            instancia.minutos = 15
            self.menu.configurar('tiempo')
        self.menu.configurar('accion:editor:escribir')
        self.menu.configurar('browser:chrome')
        self.assertEqual(self.menu.config['tiempo'], 15)
        self.assertFalse(self.menu.config['acciones_editor']['escribir'])
        self.assertEqual(self.menu.config['browser'], 'chrome')

    def test_cargar_historial_no_muta_el_registro_original(self):
        registro = {'paginas': ['https://example.com'], 'browser': 'chrome'}
        self.menu.historial = [registro]
        self.menu.configurar('historial:0')
        self.menu.config['paginas'].clear()
        self.assertEqual(registro['paginas'], ['https://example.com'])
        self.assertEqual(self.menu.config['fases'], 'ambas')

    def test_seleccionar_solo_navegador(self):
        self.menu.configurar('modo:web')
        self.assertEqual(self.menu.config['modo'], 'web')

    def test_tiempo_con_segundos_se_conserva(self):
        from menu import Configuracion, _config_a_dict, _dict_a_config, formatear_tiempo
        config = _dict_a_config(_config_a_dict(Configuracion(tiempo=4205 / 60)))
        self.assertEqual(round(config.tiempo * 60), 4205)
        self.assertEqual(formatear_tiempo(config.tiempo), '01:10:05')
        self.assertEqual(formatear_tiempo(None), 'Indefinido')

    def test_nombres_de_web_se_conservan_en_configuracion(self):
        from menu import Configuracion, _config_a_dict, _dict_a_config, _registro_valido
        config = Configuracion(paginas=['https://example.com'],
                               nombres_web={'https://example.com': 'Panel de administración'})
        registro = _config_a_dict(config)
        self.assertTrue(_registro_valido(registro))
        self.assertEqual(_dict_a_config(registro).nombres_web, config.nombres_web)
        registro['nombres_web']['https://example.com'] = '   '
        self.assertFalse(_registro_valido(registro))

    def test_instalar_actualizacion_entrega_auxiliar_antes_de_cerrar(self):
        self.menu.actualizador = MagicMock()
        with patch('mac_menu.NSAlert') as alerta, patch.object(self.menu, 'solicitar_salida') as salir:
            alerta.alloc.return_value.init.return_value.runModal.return_value = 1000
            self.menu.mostrar_actualizacion({'descargada': {'version': '1.2.3'}})
        self.menu.actualizador.instalar.assert_called_once()
        self.menu.actualizador.descartar.assert_not_called()
        salir.assert_called_once()

    def test_cancelar_instalacion_descarta_descarga_sin_cerrar(self):
        self.menu.actualizador = MagicMock()
        with patch('mac_menu.NSAlert') as alerta, patch.object(self.menu, 'solicitar_salida') as salir:
            alerta.alloc.return_value.init.return_value.runModal.return_value = 1001
            self.menu.mostrar_actualizacion({'descargada': {'version': '1.2.3'}})
        self.menu.actualizador.instalar.assert_not_called()
        self.menu.actualizador.descartar.assert_called_once()
        salir.assert_not_called()

    def test_fallo_del_auxiliar_no_cierra_la_aplicacion(self):
        self.menu.actualizador = MagicMock()
        self.menu.actualizador.instalar.side_effect = ValueError('No se pudo iniciar')
        with patch('mac_menu.NSAlert') as alerta, patch.object(self.menu, 'solicitar_salida') as salir, \
                patch.object(self.menu, 'aviso') as aviso:
            alerta.alloc.return_value.init.return_value.runModal.return_value = 1000
            self.menu.mostrar_actualizacion({'descargada': {'version': '1.2.3'}})
        salir.assert_not_called()
        aviso.assert_called_once()
