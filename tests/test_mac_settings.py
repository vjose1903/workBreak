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

    def test_ventana_comparte_datos_y_persiste_al_cambiar(self):
        self.assertEqual([item.label() for item in self.ventana.tabs.tabViewItems()], ['General', 'Actividad', 'Editor', 'Navegador'])
        self.assertIs(self.ventana.config, self.menu.config)
        self.ventana.modo.selectItemAtIndex_(2)
        self.ventana.seleccionar_(self.ventana.modo)
        self.assertEqual(self.menu.config['modo'], 'web')
        self.assertEqual(cargar_preferencias()['modo'], 'web')
        self.assertFalse(self.ventana.fuente.isEnabled())
        self.assertFalse(self.ventana.fases.isEnabled())
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
        self.menu.configurar('fase:mouse')
        self.assertEqual(self.ventana.fases.indexOfSelectedItem(), 2)
        self.assertEqual(cargar_preferencias()['fases'], 'mouse')

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
