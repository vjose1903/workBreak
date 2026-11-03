import multiprocessing
import os
import queue
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from app_controller import ControladorBot, ejecutar_proceso_bot
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
    def setUp(self):
        # Las pruebas no dependen de los editores instalados en la máquina (los runners de CI no tienen ninguno).
        editores = patch('app_controller.editores_instalados', return_value={'vsCode': 'Visual Studio Code'})
        editores.start()
        self.addCleanup(editores.stop)

    def test_sin_editor_instalado_no_crea_proceso(self):
        controlador = ControladorBot()
        with patch('app_controller.sys.platform', 'darwin'), \
                patch('app_controller.editores_instalados', return_value={}):
            with self.assertRaisesRegex(ValueError, 'editor compatible'):
                controlador.iniciar(_config_a_dict(Configuracion()))
        self.assertIsNone(controlador.proceso)

    def test_error_abriendo_log_llega_a_la_interfaz(self):
        eventos = queue.Queue()
        with patch('app_controller.signal.signal'), \
                patch('app_controller.RotatingFileHandler', side_effect=PermissionError('sin permiso')):
            with self.assertRaises(SystemExit):
                ejecutar_proceso_bot({}, MagicMock(), eventos, '/no/log', os.getppid())
        self.assertIn('sin permiso', eventos.get_nowait()['mensaje'])
        self.assertEqual(eventos.get_nowait()['codigo'], 1)

    def test_fallo_de_arranque_libera_la_cola_y_el_proceso(self):
        contexto = MagicMock()
        contexto.Process.return_value.start.side_effect = OSError('sin recursos')
        with tempfile.TemporaryDirectory() as carpeta:
            controlador = ControladorBot(contexto=contexto, ruta_log=Path(carpeta)/'log')
            with self.assertRaisesRegex(OSError, 'sin recursos'):
                controlador.iniciar(_config_a_dict(Configuracion()))
        contexto.Queue.return_value.close.assert_called_once()
        contexto.Process.return_value.close.assert_called_once()
        self.assertIsNone(controlador.proceso)
        self.assertIsNone(controlador.eventos)
        self.assertIsNone(controlador.detencion)

    def test_actualizar_limita_el_trabajo_de_cada_tick(self):
        with tempfile.TemporaryDirectory() as carpeta:
            controlador = ControladorBot(ruta_log=Path(carpeta)/'log')
            controlador.eventos = MagicMock()
            controlador.eventos.get_nowait.return_value = {'tipo': 'registro', 'mensaje': 'dato'}
            controlador.actualizar()
            self.assertEqual(controlador.eventos.get_nowait.call_count, 256)

    def test_canal_roto_finaliza_con_error_controlado(self):
        with tempfile.TemporaryDirectory() as carpeta:
            controlador = ControladorBot(ruta_log=Path(carpeta)/'log')
            controlador.eventos = MagicMock()
            controlador.eventos.get_nowait.side_effect = EOFError('canal cerrado')
            controlador.proceso = MagicMock()
            controlador.proceso.is_alive.return_value = False
            controlador.proceso.exitcode = 0
            controlador.actualizar()
            self.assertEqual(controlador.estado['estado'], 'error')
            self.assertIn('canal cerrado', controlador.ultimo_error)

    def test_mensaje_largo_no_satura_el_canal_y_conserva_registro_original(self):
        import logging
        import pickle
        from app_controller import RegistroInterfaz
        eventos = queue.Queue()
        registro = logging.LogRecord('bot', logging.ERROR, '', 0, '🙂'*10000, (), None)
        RegistroInterfaz(eventos).emit(registro)
        evento = eventos.get_nowait()
        self.assertLess(len(pickle.dumps(evento)), 4096)
        self.assertIn('ver registro completo', evento['mensaje'])
        self.assertEqual(registro.getMessage(), '🙂'*10000)

    def test_worker_solo_web_acepta_directorio_sin_cargarlo(self):
        registro = _config_a_dict(Configuracion(modo='web', browser='chrome', paginas=['https://example.com']))
        registro.update(fuente_tipo='directorio', directorio='/fuente/no/disponible')
        detener = MagicMock()
        detener.is_set.return_value = False
        eventos = queue.Queue()
        modulo = MagicMock()
        bot = modulo.AutomationBot.return_value
        bot.gestionar_ejecucion.return_value = 0
        with tempfile.TemporaryDirectory() as carpeta, \
                patch('app_controller.signal.signal'), \
                patch.dict(sys.modules, {'automation_bot': modulo}):
            ejecutar_proceso_bot(registro, detener, eventos, str(Path(carpeta) / 'bot.log'), os.getppid())
        bot.gestionar_ejecucion.assert_called_once()
        self.assertEqual(bot.gestionar_ejecucion.call_args.args[0].modo, 'web')

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
