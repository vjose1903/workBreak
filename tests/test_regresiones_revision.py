import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from menu import _registro_valido, formatear_tiempo
from code_source import RealProjectSource, MAX_BYTES
from app_update_install import ejecutar_cancelable, ActualizacionCancelada
from app_updates import Actualizador
from mac_menu import normalizar_web


class RegresionesRevision(unittest.TestCase):
    def test_tiempos_extremos_no_desbordan(self):
        for valor in (10 ** 400, 1e308, float('nan'), float('inf'), 0.001, -1, True):
            self.assertFalse(_registro_valido({'tiempo': valor}))
            self.assertEqual(formatear_tiempo(valor), 'Indefinido')
        self.assertTrue(_registro_valido({'tiempo': 90}))
        self.assertEqual(formatear_tiempo(90), '01:30:00')

    def test_fuente_ignora_fifo_y_archivo_demasiado_grande(self):
        with tempfile.TemporaryDirectory() as carpeta:
            raiz = Path(carpeta)
            os.mkfifo(raiz / 'tuberia.tsx')
            (raiz / 'gigante.tsx').write_bytes(b'x' * (MAX_BYTES + 1))
            (raiz / 'valido.tsx').write_text('const x = 1;\n' * 20)
            fuente = RealProjectSource(carpeta)
            self.assertEqual([p.name for p in fuente.archivos], ['valido.tsx'])
            self.assertEqual(len(fuente.obtener_codigo().splitlines()), 20)

    def test_url_con_coma_se_conserva(self):
        self.assertEqual(normalizar_web('https://example.com/?ids=1,2'), 'https://example.com/?ids=1,2')
        with self.assertRaises(ValueError):
            normalizar_web('https://example.com https://otro.com')

    def test_cancelar_termina_y_recoge_el_proceso_propio(self):
        cancelar = threading.Event()
        cancelar.set()
        with self.assertRaises(ActualizacionCancelada):
            ejecutar_cancelable([sys.executable, '-c', 'import time; time.sleep(20)'], cancelar, 30)

    def test_timeout_termina_el_proceso_propio(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            ejecutar_cancelable([sys.executable, '-c', 'import time; time.sleep(20)'], threading.Event(), 0)

    def test_error_limpieza_no_bloquea_cierre(self):
        actualizador = Actualizador()
        actualizador.preparada = {'carpeta': '/tmp/descarga-prueba'}
        terminado = threading.Event()
        def fallo(_):
            terminado.set()
            raise OSError('volumen ocupado')
        with patch('app_updates.limpiar_descarga', side_effect=fallo):
            actualizador.descartar()
            self.assertTrue(terminado.wait(2))
        self.assertIsNone(actualizador.preparada)
