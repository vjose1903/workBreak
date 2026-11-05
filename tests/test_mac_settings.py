from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
if sys.platform == 'darwin':
    from AppKit import NSApplication
    from mac_menu import MenuWorkBreak
    from mac_settings import VentanaConfiguracion
    from app_preferences import cargar_preferencias


@unittest.skipUnless(sys.platform == 'darwin', 'Ventana nativa exclusiva de macOS')
class ConfiguracionMacTest(unittest.TestCase):
    def setUp(self):
        NSApplication.sharedApplication()
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        datos = patch('app_preferences.directorio_datos', return_value=Path(carpeta.name))
        datos.start()
        self.addCleanup(datos.stop)
        with patch('mac_menu.ControladorBot', return_value=MagicMock()), patch('mac_menu.cargar_preferencias', return_value=None):
            self.menu = MenuWorkBreak.alloc().init()
        self.menu.controlador.activo = False
        self.menu.construir_menu = MagicMock()
        self.menu.aviso = MagicMock()
        self.ventana = VentanaConfiguracion.alloc().init()
        self.ventana.preparar(self.menu)
        self.menu.ventana_configuracion = self.ventana
        self.addCleanup(self.ventana.ventana.close)

    def test_nombre_visible_de_la_ventana_es_wb(self):
        self.assertEqual(self.ventana.ventana.title(), 'Configuración de WB')

    def test_tiempos_compartidos_y_bloqueados_durante_corrida(self):
        tiempos = {'debounce': 3, 'editor': [1, 7], 'editor_alternado': [1, 7], 'navegador': [2, 4]}
        with patch('mac_menu.DialogoSegundos') as dialogo:
            dialogo.alloc.return_value.init.return_value.mostrar.return_value = tiempos
            self.ventana.accion_(self.ventana.controles_tiempo['editor'])
        from timing_config import temporizacion_config
        self.assertEqual(cargar_preferencias()['temporizacion'], temporizacion_config(tiempos))
        self.assertEqual(self.ventana.controles_tiempo['editor'].title(), 'Duración del editor…')
        self.assertNotIn('editor_alternado', self.ventana.controles_tiempo)
        self.menu.controlador.activo = True
        self.ventana.refrescar()
        self.assertTrue(all(not c.isEnabled() for c in self.ventana.controles_tiempo.values()))

    def test_selector_editor_muestra_solo_instalados_y_guarda_eleccion(self):
        opciones = {'vsCode': 'Visual Studio Code', 'cursor': 'Cursor'}
        with patch('mac_settings.editores_instalados', return_value=opciones), \
                patch('mac_menu.editores_instalados', return_value=opciones):
            self.ventana.ventana.close()
            self.ventana.preparar(self.menu)
            self.assertEqual(self.ventana.editor.titleOfSelectedItem(), 'Visual Studio Code')
            self.ventana.editor.selectItemAtIndex_(1)
            self.ventana.seleccionar_(self.ventana.editor)
        self.assertEqual(cargar_preferencias()['editor'], 'cursor')
        self.assertEqual(self.menu.config['editor'], 'cursor')

    def test_acciones_se_comparten_entre_menu_ventana_y_preferencias(self):
        vistas = {item.identifier(): item.view() for item in self.ventana.tabs.tabViewItems()}
        for (entorno, _), control in self.ventana.controles_acciones.items():
            self.assertEqual(control.superview(), vistas['Editor' if entorno == 'editor' else 'Navegador'])
        control = self.ventana.controles_acciones[('editor', 'escribir')]
        self.ventana.accion_(control)
        self.assertFalse(self.menu.config['acciones_editor']['escribir'])
        self.assertEqual(control.state(), 0)
        self.assertFalse(cargar_preferencias()['acciones_editor']['escribir'])
        self.menu.configurar('accion:web:click')
        self.assertEqual(self.ventana.controles_acciones[('web', 'click')].state(), 0)
        self.assertFalse(cargar_preferencias()['acciones_web']['click'])
        self.menu.controlador.activo = True
        self.ventana.refrescar()
        self.assertTrue(all(not c.isEnabled() for c in self.ventana.controles_acciones.values()))

    def test_descarga_bloquea_controles_y_luego_los_rehabilita(self):
        self.menu.actualizador.consultando = True
        self.ventana.refrescar()
        for control in (self.ventana.modo, self.ventana.tiempo, self.ventana.editor,
                        self.ventana.fuente, self.ventana.directorio, self.ventana.browser, self.ventana.webs):
            self.assertFalse(control.isEnabled())
        self.menu.actualizador.consultando = False
        self.ventana.refrescar()
        self.assertTrue(self.ventana.modo.isEnabled())

    def test_ventana_comparte_datos_y_persiste_al_cambiar(self):
        self.assertEqual([item.label() for item in self.ventana.tabs.tabViewItems()], ['General', 'Actividad', 'Editor', 'Navegador'])
        self.assertIs(self.ventana.config, self.menu.config)
        self.ventana.modo.selectItemAtIndex_(2)
        self.ventana.seleccionar_(self.ventana.modo)
        self.assertEqual(self.menu.config['modo'], 'web')
        self.assertEqual(cargar_preferencias()['modo'], 'web')
        self.assertFalse(self.ventana.fuente.isEnabled())
        self.assertTrue(self.ventana.browser.isEnabled())
        self.menu.construir_menu.assert_called_once()

    def test_cambiar_desde_menu_actualiza_la_ventana_abierta(self):
        compartida = self.menu.config
        self.menu.configurar('modo:editor')
        self.assertIs(self.menu.config, compartida)
        self.assertEqual(self.ventana.modo.indexOfSelectedItem(), 1)
        self.assertFalse(self.ventana.browser.isEnabled())
        self.assertFalse(self.ventana.webs.isEnabled())
        self.assertIn('solo editor', self.ventana.web_info.stringValue())
        self.menu.configurar('accion:editor:escribir')
        self.assertEqual(self.ventana.controles_acciones[('editor', 'escribir')].state(), 0)
        self.assertFalse(cargar_preferencias()['acciones_editor']['escribir'])

    def test_cerrar_conserva_cambios_compartidos(self):
        self.menu.configurar('modo:editor')
        self.ventana.accion_(self.boton('cerrar'))
        self.assertEqual(self.menu.config['modo'], 'editor')
        self.assertEqual(cargar_preferencias()['modo'], 'editor')

    def test_cambio_durante_sesion_activa_no_modifica_preferencias(self):
        self.menu.controlador.activo = True
        self.ventana.modo.selectItemAtIndex_(1)
        self.ventana.seleccionar_(self.ventana.modo)
        self.assertEqual(self.menu.config['modo'], 'ambos')
        self.assertEqual(self.ventana.modo.indexOfSelectedItem(), 0)
        self.assertIsNone(cargar_preferencias())
        self.menu.aviso.assert_called_once()

    def test_error_de_guardado_no_diverge_menu_y_ventana(self):
        with patch('mac_menu.guardar_preferencias', side_effect=OSError('sin espacio')):
            self.ventana.modo.selectItemAtIndex_(1)
            self.ventana.seleccionar_(self.ventana.modo)
        self.assertEqual(self.menu.config['modo'], 'ambos')
        self.assertEqual(self.ventana.modo.indexOfSelectedItem(), 0)
        self.menu.construir_menu.assert_not_called()
        self.menu.aviso.assert_called_once()

    def test_historial_se_comparte_sin_copiar_referencias_mutables(self):
        self.menu.historial = [{'modo': 'web', 'browser': 'chrome', 'paginas': ['https://example.com'], 'fases': 'mouse'}]
        self.ventana.refrescar()
        self.ventana.recientes.selectItemAtIndex_(1)
        self.ventana.cargarReciente_(self.ventana.recientes)
        self.assertIs(self.ventana.config, self.menu.config)
        self.assertEqual(self.menu.config['modo'], 'web')
        self.assertEqual(self.ventana.modo.indexOfSelectedItem(), 2)
        self.menu.config['paginas'].clear()
        self.assertEqual(self.menu.historial[0]['paginas'], ['https://example.com'])

    def test_dialogos_reutilizados_comparten_webs_nombres_y_tiempo(self):
        with patch('mac_menu.DialogoWebs') as dialogo:
            instancia = dialogo.alloc.return_value.init.return_value
            instancia.mostrar.return_value = ['https://example.com']
            instancia.nombres = {'https://example.com': 'Panel'}
            self.ventana.accion_(self.boton('webs'))
        self.assertEqual(self.menu.config['nombres_web'], {'https://example.com': 'Panel'})
        self.assertIn('1 webs', self.ventana.web_info.stringValue())
        with patch('mac_menu.DialogoTiempo') as dialogo:
            instancia = dialogo.alloc.return_value.init.return_value
            instancia.mostrar.return_value = True
            instancia.minutos = 75
            self.menu.configurar('tiempo')
        self.assertIn('01:15:00', self.ventana.tiempo.title())
        self.assertEqual(cargar_preferencias()['tiempo'], 75)
        self.assertEqual(cargar_preferencias()['nombres_web'], {'https://example.com': 'Panel'})

    def boton(self, comando):
        boton = MagicMock()
        boton.identifier.return_value = comando
        return boton
