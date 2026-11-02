import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from menu import Configuracion, _config_a_dict, _dict_a_config, _cargar_config_previa


class FasesConfigTest(unittest.TestCase):
    def test_historial_anterior_usa_ambas_fases(self):
        self.assertEqual(_dict_a_config({}).fases, 'ambas')

    def test_cada_modo_se_conserva_al_serializar(self):
        for fases in ('ambas', 'escritura', 'mouse'):
            with self.subTest(fases=fases):
                registro = _config_a_dict(Configuracion(fases=fases))
                self.assertEqual(_dict_a_config(registro).fases, fases)

    def test_cargar_configuracion_previa_restaura_fases(self):
        config = Configuracion()
        registro = _config_a_dict(Configuracion(fases='mouse'))
        with patch('menu.cargar_historial', return_value=[registro]), \
                patch('menu._preguntar', return_value='1'), patch('builtins.print'):
            self.assertTrue(_cargar_config_previa(config))
        self.assertEqual(config.fases, 'mouse')


if __name__ == '__main__':
    unittest.main()
