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
        with patch('mac_menu.ControladorBot', return_value=MagicMock()):
            self.menu = MenuWorkBreak.alloc().init()

    def test_webs_se_normalizan_y_se_eliminan_duplicados(self):
        self.assertEqual(normalizar_webs('example.com, https://example.com\nhttp://localhost:8000'),
                         ['https://example.com', 'http://localhost:8000'])

    def test_web_invalida_no_sustituye_la_configuracion(self):
        self.menu.config['paginas'] = ['https://example.com']
        with patch('mac_menu.DialogoWebs') as dialogo:
            dialogo.alloc.return_value.init.return_value.mostrar.return_value = None
            self.menu.configurar('webs')
        self.assertEqual(self.menu.config['paginas'], ['https://example.com'])

    def test_tiempo_y_fases_se_configuran_sin_menu_terminal(self):
        with patch('mac_menu.DialogoTiempo') as dialogo:
            instancia = dialogo.alloc.return_value.init.return_value
            instancia.mostrar.return_value = True
            instancia.minutos = 15
            self.menu.configurar('tiempo')
        self.menu.configurar('fase:mouse')
        self.menu.configurar('browser:chrome')
        self.assertEqual(self.menu.config['tiempo'], 15)
        self.assertEqual(self.menu.config['fases'], 'mouse')
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
