import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
DISPONIBLE = sys.platform == 'darwin' and importlib.util.find_spec('UserNotifications') is not None
if DISPONIBLE:
    from mac_notifications import Notificador


@unittest.skipUnless(DISPONIBLE, 'Requiere el framework UserNotifications de macOS')
class NotificacionesMacTest(unittest.TestCase):
    def test_envia_notificacion_con_permiso(self):
        with patch('mac_notifications.UNUserNotificationCenter') as centro:
            notificador = Notificador.alloc().init()
        cliente = centro.currentNotificationCenter.return_value
        cliente.requestAuthorizationWithOptions_completionHandler_.side_effect = lambda _, completar: completar(True, None)
        alternativa = MagicMock()
        notificador.enviar('Error', 'Motivo', alternativa)
        cliente.addNotificationRequest_withCompletionHandler_.assert_called_once()
        alternativa.assert_not_called()

    def test_permiso_denegado_o_error_de_envio_muestra_alternativa(self):
        for permitido in (True, False):
            with self.subTest(permitido=permitido), \
                    patch('mac_notifications.UNUserNotificationCenter') as centro, \
                    patch('mac_notifications.callAfter', side_effect=lambda funcion, *args: funcion(*args)):
                notificador = Notificador.alloc().init()
                cliente = centro.currentNotificationCenter.return_value
                cliente.requestAuthorizationWithOptions_completionHandler_.side_effect = lambda _, completar: completar(permitido, None)
                cliente.addNotificationRequest_withCompletionHandler_.side_effect = lambda _, completar: completar('Error de entrega')
                alternativa = MagicMock()
                notificador.enviar('Error', 'Motivo', alternativa)
                alternativa.assert_called_once_with('Error', 'Motivo')
