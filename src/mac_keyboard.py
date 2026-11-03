import time

import pyautogui
import Quartz


class MacKeyboard:
    """Eventos con modificadores explícitos, sin heredar Fn ni teclas anteriores."""

    KEY_CODES = {
        'a': 0x00, 's': 0x01, 'g': 0x05, 'c': 0x08, 'v': 0x09, 'w': 0x0D, 't': 0x11,
        '1': 0x12, 'l': 0x25, 'enter': 0x24, 'return': 0x24, 'esc': 0x35,
        'left': 0x7B, 'right': 0x7C, 'down': 0x7D, 'up': 0x7E,
    }

    def __init__(self, antes_evento=None):
        self.antes_evento = antes_evento

    def _enviar(self, codigo, flags=0, texto=None):
        if self.antes_evento is not None:
            self.antes_evento()
        pyautogui.failSafeCheck()
        eventos = []
        for pulsada in (True, False):
            evento = Quartz.CGEventCreateKeyboardEvent(None, codigo, pulsada)
            if evento is None:
                raise RuntimeError('No se pudo crear el evento de teclado en macOS')
            Quartz.CGEventSetFlags(evento, flags)
            if texto is not None:
                longitud = len(texto.encode('utf-16-le')) // 2
                Quartz.CGEventKeyboardSetUnicodeString(evento, longitud, texto)
            eventos.append(evento)
        # El par se prepara completo y siempre libera la tecla antes de propagar una pausa/error.
        try:
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, eventos[0])
        finally:
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, eventos[1])

        time.sleep(pyautogui.DARWIN_CATCH_UP_TIME)

    def hotkey(self, *teclas):
        modificadores = {
            'command': Quartz.kCGEventFlagMaskCommand,
            'ctrl': Quartz.kCGEventFlagMaskControl,
            'shift': Quartz.kCGEventFlagMaskShift,
            'option': Quartz.kCGEventFlagMaskAlternate,
        }
        flags = 0
        for tecla in teclas[:-1]:
            flags |= modificadores[tecla]
        self._enviar(self.KEY_CODES[teclas[-1]], flags)

    def press(self, tecla):
        self._enviar(self.KEY_CODES[tecla])

    def write(self, texto, interval=0):
        for caracter in texto:
            # Texto Unicode sin modificadores: una 'e' no puede convertirse en Fn+E.
            self._enviar(0, texto=caracter)
            if interval:
                time.sleep(interval)
