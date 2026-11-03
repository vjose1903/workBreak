import multiprocessing
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from app_controller import ControladorBot
from menu import Configuracion, _config_a_dict, _dict_a_config
from main import main


def trabajador_simulado(registro, detener, eventos, ruta_log, pid_interfaz):
    """No importa la automatización ni envía eventos a la computadora."""
    eventos.put({'tipo': 'estado', 'estado': 'ejecutando', 'fase': 'escritura'})
    detener.wait(5)
    eventos.put({'tipo': 'finalizado', 'codigo': 0, 'estadisticas': {'editor': 2}})


class ContextoSimulado:
    def __init__(self):
        self.contexto = multiprocessing.get_context('spawn')

    def Queue(self, **opciones):
        return self.contexto.Queue(**opciones)

    def Event(self):
        return self.contexto.Event()

    def Process(self, **opciones):
        opciones['target'] = trabajador_simulado
        return self.contexto.Process(**opciones)


class ContextoCancelado(ContextoSimulado):
    def Event(self):
        evento = self.contexto.Event()
        evento.set()
        return evento

    def Process(self, **opciones):
        return self.contexto.Process(**opciones)


class ControladorBotTest(unittest.TestCase):
    def test_solo_web_conserva_directorio_sin_escanearlo(self):
        registro = _config_a_dict(Configuracion(modo='web', browser='chrome', paginas=['https://example.com']))
        registro.update(fuente_tipo='directorio', directorio='/fuente/no/disponible',
                        fuente_descripcion='Directorio real: /fuente/no/disponible')
        with patch('menu.RealProjectSource', wraps=__import__('menu').RealProjectSource) as fuente:
            config = _dict_a_config(registro)
            fuente.assert_not_called()
        guardado = _config_a_dict(config)
        self.assertEqual(guardado['modo'], 'web')
        self.assertEqual(guardado['directorio'], registro['directorio'])
        self.assertEqual(guardado['fuente_tipo'], 'directorio')

    def test_solo_web_sin_paginas_no_crea_proceso(self):
        controlador = ControladorBot()
        with self.assertRaises(ValueError):
            controlador.iniciar(_config_a_dict(Configuracion(modo='web', browser='chrome')))
        self.assertIsNone(controlador.proceso)

    def test_worker_real_cancelado_no_llega_a_inicializar_la_automatizacion(self):
        with tempfile.TemporaryDirectory() as carpeta:
            controlador = ControladorBot(ContextoCancelado(), Path(carpeta) / 'bot.log')
            try:
                registro = _config_a_dict(Configuracion())
                registro.update(fuente_tipo='directorio', directorio='/directorio/que/no/existe')
                controlador.iniciar(registro)
                limite = time.monotonic() + 8
                while controlador.activo and time.monotonic() < limite:
                    controlador.actualizar()
                    time.sleep(.01)
                controlador.actualizar()
                self.assertFalse(controlador.activo)
                self.assertEqual(controlador.estado['estado'], 'finalizado')
                self.assertEqual(controlador.estadisticas, {})
                self.assertTrue(controlador.ruta_log.exists())
            finally:
                if controlador.activo:
                    controlador.proceso.terminate()
                    controlador.proceso.join(timeout=2)
                controlador.cerrar()

    def test_inicio_detencion_y_resultado_en_un_proceso_real_sin_automatizacion(self):
        with tempfile.TemporaryDirectory() as carpeta:
            controlador = ControladorBot(ContextoSimulado(), Path(carpeta) / 'bot.log')
            try:
                controlador.iniciar(_config_a_dict(Configuracion()))
                limite = time.monotonic() + 8
                while controlador.estado['estado'] != 'ejecutando' and time.monotonic() < limite:
                    controlador.actualizar()
                    time.sleep(.01)
                self.assertEqual(controlador.estado['estado'], 'ejecutando')
                with self.assertRaisesRegex(ValueError, 'Ya hay una sesión'):
                    controlador.iniciar(_config_a_dict(Configuracion()))
                controlador.detener()
                self.assertTrue(controlador.detencion.is_set())
                while controlador.activo and time.monotonic() < limite:
                    controlador.actualizar()
                    time.sleep(.01)
                controlador.actualizar()
                self.assertFalse(controlador.activo)
                self.assertEqual(controlador.estado['estado'], 'finalizado')
                self.assertEqual(controlador.estadisticas['editor'], 2)
                controlador.iniciar(_config_a_dict(Configuracion()))
                controlador.detener()
            finally:
                if controlador.proceso is not None:
                    controlador.detener()
                    controlador.proceso.join(timeout=8)
                    if controlador.activo:
                        controlador.proceso.terminate()
                        controlador.proceso.join(timeout=2)
                controlador.cerrar()
                self.assertIsNone(controlador.detencion)

    def test_webs_sin_navegador_no_inician_un_proceso(self):
        with tempfile.TemporaryDirectory() as carpeta:
            contexto = MagicMock()
            controlador = ControladorBot(contexto, Path(carpeta) / 'bot.log')
            registro = _config_a_dict(Configuracion(paginas=['https://example.com']))
            with self.assertRaisesRegex(ValueError, 'Selecciona un navegador'):
                controlador.iniciar(registro)
            contexto.Process.assert_not_called()


class InicioInterfazTest(unittest.TestCase):
    def test_mac_sin_argumentos_abre_solo_la_interfaz(self):
        interfaz = MagicMock()
        interfaz.ejecutar_interfaz.return_value = 0
        with patch('sys.platform', 'darwin'), patch.dict(sys.modules, {'mac_menu': interfaz}):
            self.assertEqual(main([]), 0)
        interfaz.ejecutar_interfaz.assert_called_once()

    def test_terminal_explicito_conserva_el_menu_anterior(self):
        modulo = MagicMock()
        modulo.AutomationBot.return_value.ejecutar.return_value = 0
        with patch('sys.platform', 'darwin'), patch.dict(sys.modules, {'automation_bot': modulo}):
            self.assertEqual(main(['--terminal']), 0)
        modulo.AutomationBot.return_value.ejecutar.assert_called_once_with([])

    def test_argumentos_siguen_utilizando_el_modo_cli(self):
        modulo = MagicMock()
        modulo.AutomationBot.return_value.ejecutar.return_value = 0
        with patch('sys.platform', 'darwin'), patch.dict(sys.modules, {'automation_bot': modulo}):
            main(['-tiempo', '10'])
        modulo.AutomationBot.return_value.ejecutar.assert_called_once_with(['-tiempo', '10'])


if __name__ == '__main__':
    unittest.main()
