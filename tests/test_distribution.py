import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from app_paths import migrar_historial, recurso, ruta_historial
from app_updates import interpretar_release, Actualizador, _consultar_github_http, consultar_github
from app_update_install import ActualizacionCancelada
from app_version import GITHUB_REPO, version_numerica


def _consulta_bloqueada_para_test(_resultados):
    threading.Event().wait(30)


class DistribucionTest(unittest.TestCase):
    def test_cancelacion_recoge_proceso_real_sin_red(self):
        cancelar = threading.Event()
        temporizador = threading.Timer(0.4, cancelar.set)
        inicio = time.monotonic()
        temporizador.start()
        try:
            with patch('app_updates._consulta_separada', _consulta_bloqueada_para_test):
                with self.assertRaises(ActualizacionCancelada):
                    consultar_github(cancelar)
        finally:
            temporizador.cancel()
            temporizador.join(timeout=1)
        self.assertLess(time.monotonic() - inicio, 5)
    def test_consulta_se_cancela_aunque_el_http_este_bloqueado(self):
        contexto = MagicMock()
        cancelar = MagicMock()
        cancelar.is_set.side_effect = [False, True]
        with patch('app_updates.multiprocessing.get_context', return_value=contexto):
            with self.assertRaises(ActualizacionCancelada):
                consultar_github(cancelar)
        contexto.Process.return_value.terminate.assert_called_once()
        contexto.Queue.return_value.close.assert_called_once()

    def test_consulta_tiene_limite_total_incluido_dns(self):
        contexto = MagicMock()
        with patch('app_updates.multiprocessing.get_context', return_value=contexto), \
                patch('app_updates.time.monotonic', side_effect=[0, 31]):
            with self.assertRaisesRegex(TimeoutError, '30 segundos'):
                consultar_github(threading.Event())
        contexto.Process.return_value.terminate.assert_called_once()

    def test_consulta_cancelada_no_muestra_error_de_red(self):
        actualizador = Actualizador()
        with patch('app_updates.consultar_github', side_effect=ActualizacionCancelada()):
            actualizador._consultar()
        self.assertEqual(actualizador.obtener_resultado(), {'cancelada': True})
        self.assertFalse(actualizador.consultando)

    def test_consulta_github_verifica_https_con_certificados_incluidos(self):
        from types import SimpleNamespace
        with patch.dict(sys.modules, {'certifi': SimpleNamespace(where=lambda: '/CA/bundle.pem')}), \
                patch('app_updates.ssl.create_default_context') as contexto, \
                patch('app_updates.urlopen') as abrir:
            abrir.return_value.__enter__.return_value.read.return_value = b'{"tag_name": "v1.0.0"}'
            self.assertIsNone(_consultar_github_http())
        contexto.assert_called_once_with(cafile='/CA/bundle.pem')
        self.assertIs(abrir.call_args.kwargs['context'], contexto.return_value)

    def release(self, tag='v1.1.0', arch='x86_64'):
        nombre = f'WorkBreak-{tag[1:]}-macos-{arch}.dmg'
        return {'tag_name': tag, 'assets': [{'name': nombre,
                'browser_download_url': f'https://github.com/{GITHUB_REPO}/releases/download/{tag}/{nombre}'}]}

    def test_selecciona_instalador_por_arquitectura(self):
        for arch in ('x86_64', 'arm64'):
            nueva = interpretar_release(self.release(arch=arch), '1.0.0', arch)
            self.assertEqual(nueva['version'], '1.1.0')
            self.assertTrue(nueva['url'].endswith(f'{arch}.dmg'))

    def test_respuesta_con_assets_malformados_se_rechaza(self):
        for assets in (None, {}, ['archivo']):
            with self.subTest(assets=assets), self.assertRaisesRegex(ValueError, 'lista de instaladores'):
                interpretar_release({'tag_name': 'v9.0.0', 'assets': assets}, '1.0.0', 'arm64')

    def test_helper_python_respeta_limites_de_version_de_macos(self):
        import importlib.util
        ruta = Path(__file__).resolve().parent.parent/'scripts/version.py'
        spec = importlib.util.spec_from_file_location('workbreak_version_test', ruta)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        self.assertEqual(modulo.incrementar('1.2.3', 'patch'), '1.2.4')
        for version, cambio in (('9999.0.0', 'major'), ('1.99.0', 'minor'), ('1.0.99', 'patch'), ('1.0.0', 'otro')):
            with self.subTest(version=version, cambio=cambio), self.assertRaises(ValueError):
                modulo.incrementar(version, cambio)

    def test_version_menor_o_igual_no_es_actualizacion(self):
        for actual in ('1.1.0', '2.0.0'):
            self.assertIsNone(interpretar_release(self.release(), actual, 'x86_64'))

    def test_comparacion_numerica_no_alfabetica(self):
        self.assertIsNotNone(interpretar_release(self.release('v1.10.0'), '1.9.0', 'x86_64'))

    def test_rechaza_descargas_fuera_del_repositorio(self):
        release = self.release()
        release['assets'][0]['browser_download_url'] = 'https://ejemplo.com/instalador.dmg'
        with self.assertRaises(ValueError):
            interpretar_release(release, '1.0.0', 'x86_64')

    def test_no_ofrece_asset_de_otra_arquitectura(self):
        with self.assertRaises(ValueError):
            interpretar_release(self.release(arch='arm64'), '1.0.0', 'x86_64')

    def test_ignora_prereleases(self):
        self.assertIsNone(interpretar_release({'tag_name': 'v1.1.0-beta', 'prerelease': True}))

    def test_version_semantica_invalida_no_se_acepta(self):
        for version in ('1.0', '01.0.0', '../1.0.0', 'v1.2.3-beta'):
            with self.assertRaises(ValueError):
                version_numerica(version)

    def test_error_del_actualizador_se_entrega_sin_bloquear_ui(self):
        actualizador = Actualizador()
        with patch('app_updates.consultar_github', side_effect=ValueError('sin conexión')):
            actualizador.consultando = True
            actualizador._consultar()
        self.assertEqual(actualizador.obtener_resultado(), {'error': 'sin conexión'})
        self.assertFalse(actualizador.consultando)

    def test_migracion_preserva_el_historial_y_no_lo_sobrescribe(self):
        with tempfile.TemporaryDirectory() as carpeta:
            origen = Path(carpeta) / 'anterior.json'
            destino = Path(carpeta) / 'datos/config_history.json'
            anterior = [{'modo': 'web', 'nombres_web': {'https://example.com': 'Panel'}}]
            origen.write_text(json.dumps(anterior))
            self.assertTrue(migrar_historial(origen, destino))
            self.assertEqual(json.loads(destino.read_text()), anterior)
            origen.write_text('[]')
            self.assertFalse(migrar_historial(origen, destino))
            self.assertEqual(json.loads(destino.read_text()), anterior)

    def test_bundle_no_escribe_configuracion_dentro_de_app(self):
        with patch('app_paths.sys.frozen', True, create=True), \
                patch('app_paths.sys._MEIPASS', '/Applications/WorkBreak.app/Contents/Frameworks', create=True):
            self.assertNotIn('WorkBreak.app', str(ruta_historial()))
            self.assertEqual(str(recurso('VERSION')), '/Applications/WorkBreak.app/Contents/Frameworks/VERSION')
