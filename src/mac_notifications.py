"""Notificaciones locales de la app instalada, con alternativa dentro de la interfaz."""
import json
import logging
import uuid
import objc
from Foundation import NSObject
from PyObjCTools.AppHelper import callAfter
from UserNotifications import (
    UNUserNotificationCenter, UNMutableNotificationContent, UNNotificationRequest,
    UNNotificationSound, UNAuthorizationOptionAlert, UNAuthorizationOptionSound,
    UNNotificationPresentationOptionBanner, UNNotificationPresentationOptionSound,
)


class Notificador(NSObject, protocols=[objc.protocolNamed('UNUserNotificationCenterDelegate')]):
    def init(self):
        self = objc.super(Notificador, self).init()
        if self is not None:
            self.centro = UNUserNotificationCenter.currentNotificationCenter()
            self.centro.setDelegate_(self)
        return self

    @objc.python_method
    def solicitar_permiso(self):
        def respuesta(_autorizado, error):
            if error:
                logging.warning('No se pudo solicitar notificaciones: %s', json.dumps({'error': str(error)}))
        self.centro.requestAuthorizationWithOptions_completionHandler_(
            UNAuthorizationOptionAlert | UNAuthorizationOptionSound, respuesta)

    @objc.python_method
    def enviar(self, titulo, mensaje, alternativa):
        def autorizado(permitido, error):
            if error or not permitido:
                callAfter(alternativa, titulo, mensaje)
                return
            contenido = UNMutableNotificationContent.alloc().init()
            contenido.setTitle_(titulo)
            contenido.setBody_(mensaje)
            contenido.setSound_(UNNotificationSound.defaultSound())
            peticion = UNNotificationRequest.requestWithIdentifier_content_trigger_(
                str(uuid.uuid4()), contenido, None)
            def enviado(error_envio):
                if error_envio:
                    logging.warning('No se pudo mostrar notificación: %s', json.dumps({'error': str(error_envio)}))
                    callAfter(alternativa, titulo, mensaje)
            self.centro.addNotificationRequest_withCompletionHandler_(peticion, enviado)
        self.centro.requestAuthorizationWithOptions_completionHandler_(
            UNAuthorizationOptionAlert | UNAuthorizationOptionSound, autorizado)

    def userNotificationCenter_willPresentNotification_withCompletionHandler_(self, _centro, _notificacion, completar):
        completar(UNNotificationPresentationOptionBanner | UNNotificationPresentationOptionSound)
