import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from app_preferences import cargar_preferencias, guardar_preferencias, estado_inicio, establecer_inicio
from menu import Configuracion, _config_a_dict


class PreferenciasTest(unittest.TestCase):
    def test_guardar_y_leer_sin_iniciar_sesion_del_bot(self):
        with tempfile.TemporaryDirectory() as carpeta, patch('app_preferences.directorio_datos', return_value=Path(carpeta)):
            config = _config_a_dict(Configuracion())
            config['modo'] = 'web'
            guardar_preferencias(config)
            self.assertEqual(cargar_preferencias(), config)
            self.assertEqual(json.loads((Path(carpeta) / 'preferences.json').read_text())['modo'], 'web')

    def test_archivo_gigante_anidado_o_no_regular_no_impide_arrancar(self):
        import os
        from app_paths import MAX_JSON_BYTES
        with tempfile.TemporaryDirectory() as carpeta, patch('app_preferences.directorio_datos', return_value=Path(carpeta)):
            ruta = Path(carpeta)/'preferences.json'
            for contenido in (b' '*(MAX_JSON_BYTES+1), b'['*1500+b'0'+b']'*1500):
                ruta.write_bytes(contenido)
                self.assertIsNone(cargar_preferencias())
            ruta.unlink()
            os.mkfifo(ruta)
            self.assertIsNone(cargar_preferencias())

    def test_guardar_configuracion_excesiva_preserva_anterior(self):
        from app_paths import MAX_JSON_BYTES
        with tempfile.TemporaryDirectory() as carpeta, patch('app_preferences.directorio_datos', return_value=Path(carpeta)):
            config = _config_a_dict(Configuracion())
            guardar_preferencias(config)
            with self.assertRaisesRegex(ValueError, '2 MiB'):
                guardar_preferencias({**config, 'fuente_descripcion': 'a' * MAX_JSON_BYTES})
            self.assertEqual(cargar_preferencias(), config)

    def test_error_de_escritura_preserva_configuracion_anterior(self):
        with tempfile.TemporaryDirectory() as carpeta, patch('app_preferences.directorio_datos', return_value=Path(carpeta)):
            config = _config_a_dict(Configuracion())
            guardar_preferencias(config)
            with patch('app_preferences.os.replace', side_effect=OSError('sin espacio')):
                with self.assertRaises(OSError):
                    guardar_preferencias({**config, 'modo': 'web'})
            self.assertEqual(cargar_preferencias(), config)
            self.assertEqual([p.name for p in Path(carpeta).iterdir()], ['preferences.json'])

    def test_descarta_preferencias_corruptas(self):
        with tempfile.TemporaryDirectory() as carpeta, patch('app_preferences.directorio_datos', return_value=Path(carpeta)):
            (Path(carpeta) / 'preferences.json').write_text('{roto')
            self.assertIsNone(cargar_preferencias())
            with self.assertRaises(ValueError):
                guardar_preferencias({'modo': 'invalido'})

    def test_inicio_desde_fuente_no_registra_servicios(self):
        with patch('app_preferences.inicio_disponible', return_value=False):
            self.assertFalse(estado_inicio()[0])
            with self.assertRaises(ValueError):
                establecer_inicio(True)

    def test_inicio_utiliza_api_nativa_y_lee_estado_real(self):
        servicio = MagicMock()
        servicio.registerAndReturnError_.return_value = (True, None)
        servicio.unregisterAndReturnError_.return_value = (True, None)
        framework = SimpleNamespace(SMAppService=SimpleNamespace(mainAppService=lambda: servicio))
        with patch.dict(sys.modules, {'ServiceManagement': framework}), patch('app_preferences.inicio_disponible', return_value=True):
            servicio.status.return_value = 1
            self.assertTrue(establecer_inicio(True)[0])
            servicio.registerAndReturnError_.assert_called_once_with(None)
            servicio.status.return_value = 2
            self.assertIn('Pendiente', estado_inicio()[1])
            servicio.status.return_value = 0
            self.assertFalse(establecer_inicio(False)[0])
            servicio.unregisterAndReturnError_.assert_called_once_with(None)

    def test_error_del_sistema_se_propaga(self):
        servicio = MagicMock()
        servicio.registerAndReturnError_.return_value = (False, SimpleNamespace(localizedDescription=lambda: 'Permiso denegado'))
        with patch.dict(sys.modules, {'ServiceManagement': SimpleNamespace(SMAppService=SimpleNamespace(mainAppService=lambda: servicio))}), \
                patch('app_preferences.inicio_disponible', return_value=True):
            with self.assertRaisesRegex(RuntimeError, 'Permiso denegado'):
                establecer_inicio(True)
