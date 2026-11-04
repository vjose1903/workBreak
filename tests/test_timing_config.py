import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from timing_config import PREDETERMINADOS, temporizacion_config
from menu import Configuracion, _config_a_dict, _dict_a_config, _registro_valido


class TemporizacionTest(unittest.TestCase):
    def test_configuraciones_antiguas_conservan_tiempos(self):
        self.assertEqual(_dict_a_config({}).temporizacion, PREDETERMINADOS)
        valores = temporizacion_config()
        valores['editor'][0] = 1
        self.assertEqual(PREDETERMINADOS['editor'], [60, 240])

    def test_configuracion_persiste_y_restaura_tiempos(self):
        tiempos = {'debounce': 3.5, 'editor': [1, 7], 'editor_alternado': [1, 7], 'navegador': [2, 4]}
        registro = _config_a_dict(Configuracion(temporizacion=tiempos))
        self.assertTrue(_registro_valido(registro))
        self.assertEqual(_dict_a_config(registro).temporizacion, temporizacion_config(tiempos))

    def test_rechaza_rangos_y_numeros_invalidos(self):
        for tiempos in ({'debounce': -1}, {'debounce': True}, {'debounce': 10 ** 400}, {'debounce': float('nan')},
                        {'editor': [7, 1]}, {'editor': [0, 1]}, {'editor': [1]},
                        {'navegador': [1, float('inf')]}, {'otro': 10}, []):
            with self.subTest(tiempos=tiempos):
                with self.assertRaises(ValueError):
                    temporizacion_config(tiempos)
                self.assertFalse(_registro_valido({'temporizacion': tiempos}))

    def test_admite_debounce_cero_y_turnos_fijos(self):
        tiempos = temporizacion_config({'debounce': 0, 'editor': [1, 1]})
        self.assertEqual(tiempos['debounce'], 0)
        self.assertEqual(tiempos['editor'], [1, 1])

    def test_tiempos_internos_conservan_predeterminados_y_admiten_cadencia_cero(self):
        tiempos = temporizacion_config({'editor_caracter': [0, 0], 'navegador_pausa_scroll': [2, 4]})
        self.assertEqual(tiempos['editor_caracter'], [0, 0])
        self.assertEqual(tiempos['navegador_pausa_scroll'], [2, 4])
        self.assertEqual(tiempos['editor_escritura'], [4, 115])
        self.assertEqual(tiempos['editor_mouse'], [2, 16])
        self.assertEqual(tiempos['navegador_visita'], [10, 20])
