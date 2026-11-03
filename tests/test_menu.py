import os
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from menu import Configuracion, _config_a_dict, _dict_a_config, _cargar_config_previa, cargar_historial, guardar_historial


class FasesConfigTest(unittest.TestCase):
    def test_editor_elegido_se_conserva_en_historial(self):
        for editor in ('vsCode', 'cursor', 'windsurf', 'vsCodeInsiders'):
            with self.subTest(editor=editor):
                self.assertEqual(_dict_a_config(_config_a_dict(Configuracion(editor=editor))).editor, editor)
        self.assertEqual(_dict_a_config({}).editor, 'vsCode')
        with self.assertRaises(ValueError):
            Configuracion(editor='desconocido')

    def test_acciones_antiguas_migran_y_personalizadas_se_restauran(self):
        from menu import acciones_config, _registro_valido, validar_acciones_ejecucion
        self.assertEqual(acciones_config({'fases': 'escritura'}, 'editor'),
                         {'escribir': True, 'click': False, 'scroll': False, 'mover_mouse': False})
        self.assertFalse(_dict_a_config({'fases': 'mouse'}).acciones_editor['escribir'])
        config = Configuracion(acciones_editor={'escribir': False, 'click': False},
                               acciones_web={'scroll': False})
        restaurada = _dict_a_config(_config_a_dict(config))
        self.assertEqual(restaurada.acciones_editor, config.acciones_editor)
        self.assertEqual(restaurada.acciones_web, config.acciones_web)
        for valor in (None, [], {'click': 1}, {'desconocida': True}):
            self.assertFalse(_registro_valido({'acciones_editor': valor}))
        registro = _config_a_dict(Configuracion())
        registro['acciones_editor'] = dict.fromkeys(config.acciones_editor, False)
        with self.assertRaises(ValueError):
            validar_acciones_ejecucion(registro)
        registro.update(browser='chrome', paginas=['https://example.com'])
        self.assertEqual(validar_acciones_ejecucion(registro), (False, True))

    def test_tiempo_se_valida_tambien_en_terminal_y_configuracion_directa(self):
        from menu import _seleccionar_tiempo, MAX_MINUTOS, _registro_valido
        for valor in (-1, 10 ** 400, float('inf')):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                Configuracion(tiempo=valor)
        config = Configuracion(tiempo=5)
        for texto in ('-1', str(int(MAX_MINUTOS) + 1)):
            with patch('menu._preguntar', return_value=texto), patch('builtins.print'):
                _seleccionar_tiempo(config)
            self.assertEqual(config.tiempo, 5)
        for fuente in ([], {}, 'desconocida'):
            self.assertFalse(_registro_valido({'fuente_tipo': fuente}))
        self.assertFalse(_registro_valido({'fuente_tipo': 'directorio', 'directorio': ''}))

    def test_fallo_de_reemplazo_no_destruye_historial_anterior(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / 'historial.json'
            anterior = '[{"tiempo": 10}]'
            ruta.write_text(anterior, encoding='utf-8')
            with patch('menu.RUTA_HISTORIAL', ruta), \
                    patch('menu.os.replace', side_effect=OSError('disco ocupado')):
                guardar_historial([{'tiempo': 20}])
            self.assertEqual(ruta.read_text(), anterior)
            self.assertEqual(list(Path(carpeta).iterdir()), [ruta])

    def test_historial_descarta_elementos_y_campos_invalidos(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / 'historial.json'
            ruta.write_text('[null, 3, {"tiempo": "60"}, {"fases": []}, {}]', encoding='utf-8')
            with patch('menu.RUTA_HISTORIAL', ruta):
                self.assertEqual(cargar_historial(), [{}])

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
