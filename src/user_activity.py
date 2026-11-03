import os
import logging
import math
import platform
import threading
import time


class PausaPorActividad(BaseException):
    # Una cancelación del turno no debe quedar absorbida por except Exception.
    pass


class DetencionSolicitada(BaseException):
    """Detiene la sesión desde la interfaz, incluso durante el debounce."""


class MonitorActividad:
    def __init__(self, debounce=10.0, margen_inicial=5.0, solicitar_detencion=None, informar_pausa=None):
        self.debounce = debounce
        self.margen_inicial = margen_inicial
        self._detectar_desde = None
        self._condicion = threading.Condition()
        self._ultima = None
        self._version = 0
        self._reanudada = 0
        self._error = None
        self._listo = threading.Event()
        self._detener = threading.Event()
        self._hilo = None
        self._runloop = None
        self._thread_id = None
        self._pulsadas = set()
        self._esta_pulsada = None
        self.comprobar_emergencia = None
        self.solicitar_detencion = solicitar_detencion
        self.informar_pausa = informar_pausa
        self.permitir_limpieza = False

    def _comprobar_detencion(self):
        if not self.permitir_limpieza and self.solicitar_detencion and self.solicitar_detencion():
            raise DetencionSolicitada()

    def reconciliar_pulsadas(self):
        """Descarta liberaciones perdidas consultando el estado físico actual."""
        with self._condicion:
            pendientes = set(self._pulsadas)
            version = self._version
        if self._esta_pulsada is None or not pendientes:
            return
        soltadas = {tecla for tecla in pendientes if not self._esta_pulsada(tecla)}
        with self._condicion:
            if soltadas and version == self._version:
                self._pulsadas.difference_update(soltadas)
                self._ultima = time.monotonic()
                self._version += 1
                self._condicion.notify_all()

    def registrar(self, identificador=None, pulsada=None):
        with self._condicion:
            ahora = time.monotonic()
            if self._detectar_desde is not None and ahora < self._detectar_desde:
                return
            if identificador is not None:
                if pulsada:
                    self._pulsadas.add(identificador)
                else:
                    self._pulsadas.discard(identificador)
            self._ultima = ahora
            self._version += 1
            self._condicion.notify_all()

    def comprobar(self):
        self._comprobar_detencion()
        with self._condicion:
            if self._error is not None:
                raise RuntimeError(f"El monitor de actividad dejó de funcionar: {self._error}")
            if self._version != self._reanudada:
                raise PausaPorActividad()

    def esperar_intervalo(self, segundos):
        fin = time.monotonic() + segundos
        with self._condicion:
            while True:
                self.comprobar()
                restante = fin - time.monotonic()
                if restante <= 0:
                    return
                self._condicion.wait(min(restante, 0.1) if self.solicitar_detencion else restante)

    def esperar_inactividad(self, limite=None):
        """Reinicia el plazo con cada evento; respeta el límite global del bot."""
        version_informada = None
        ultimo_log = float('-inf')
        contador_informado = None
        while True:
            self._comprobar_detencion()
            if self.comprobar_emergencia is not None:
                self.comprobar_emergencia()
            self.reconciliar_pulsadas()
            mensaje = None
            with self._condicion:
                if self._error is not None:
                    raise RuntimeError(f"El monitor de actividad dejó de funcionar: {self._error}")
                ahora = time.monotonic()
                if limite is not None and ahora >= limite:
                    return False
                if self._pulsadas:
                    restante = self.debounce
                else:
                    restante = 0 if self._ultima is None else self._ultima + self.debounce - ahora
                if restante <= 0:
                    self._reanudada = self._version
                    return True
                contador = math.ceil(restante)
                version = self._version
                if version != version_informada and ahora - ultimo_log >= 1:
                    if version_informada is None:
                        mensaje = f"Pausa: {contador} segundos de inactividad pendientes"
                    else:
                        mensaje = f"Debounce reiniciado por actividad del usuario: pausa por {self.debounce:g} segundos"
                    version_informada = version
                elif not self._pulsadas and contador != contador_informado and ahora - ultimo_log >= 1:
                    mensaje = f"Pausa: {contador} segundos restantes para reanudar"
                if mensaje:
                    if self._pulsadas:
                        mensaje += " (tecla o botón pulsado; la cuenta comenzará al soltarlo)"
                    ultimo_log = ahora
                    contador_informado = contador
                if limite is not None:
                    restante = min(restante, limite - ahora)
                espera = min(restante, 0.1 if self.solicitar_detencion else 1)
            # No bloquear el callback nativo mientras se escribe en la terminal.
            if mensaje:
                logging.info(mensaje)
                if self.informar_pausa:
                    self.informar_pausa(contador, bool(self._pulsadas))
            with self._condicion:
                if self._version == version:
                    self._condicion.wait(espera)

    def iniciar(self):
        # Ignorar también el Enter y los eventos recibidos al preparar el monitor nativo.
        self._detectar_desde = float('inf')
        self._hilo = threading.Thread(target=self._escuchar, daemon=True, name="actividad-usuario")
        self._hilo.start()
        fin = time.monotonic() + 5
        listo = self._listo.wait(0.1)
        while not listo:
            self._comprobar_detencion()
            if time.monotonic() >= fin:
                break
            listo = self._listo.wait(0.1)
        if not listo:
            self.detener()
            raise RuntimeError("No se pudo iniciar el monitor de teclado y mouse")
        if self._error is not None:
            raise RuntimeError(f"No se pudo iniciar el monitor de actividad: {self._error}")
        with self._condicion:
            self._detectar_desde = time.monotonic() + self.margen_inicial
        logging.info("Inicio del bot: las pausas por actividad se activarán en %g segundos", self.margen_inicial)

    def _escuchar(self):
        try:
            if platform.system() == 'Darwin':
                self._escuchar_mac()
            elif os.name == 'nt':
                self._escuchar_windows()
            else:
                raise RuntimeError("La pausa por actividad admite macOS y Windows")
        except Exception as error:
            with self._condicion:
                self._error = str(error)
                self._condicion.notify_all()
            self._listo.set()

    def _escuchar_mac(self):
        import Quartz as q

        def esta_pulsada(identificador):
            tipo, codigo = identificador
            if tipo == 'tecla':
                return q.CGEventSourceKeyState(q.kCGEventSourceStateHIDSystemState, codigo)
            if tipo == 'mouse':
                return q.CGEventSourceButtonState(q.kCGEventSourceStateHIDSystemState, codigo)
            return bool(q.CGEventSourceFlagsState(q.kCGEventSourceStateHIDSystemState) & codigo)

        self._esta_pulsada = esta_pulsada

        tipos = (q.kCGEventKeyDown, q.kCGEventKeyUp, q.kCGEventFlagsChanged,
                 q.kCGEventMouseMoved, q.kCGEventLeftMouseDown, q.kCGEventLeftMouseUp,
                 q.kCGEventRightMouseDown, q.kCGEventRightMouseUp,
                 q.kCGEventOtherMouseDown, q.kCGEventOtherMouseUp,
                 q.kCGEventLeftMouseDragged, q.kCGEventRightMouseDragged,
                 q.kCGEventOtherMouseDragged, q.kCGEventScrollWheel)

        def evento(_proxy, tipo, evento, _contexto):
            if tipo in (q.kCGEventTapDisabledByTimeout, q.kCGEventTapDisabledByUserInput):
                q.CGEventTapEnable(tap, True)
                if not q.CGEventTapIsEnabled(tap):
                    with self._condicion:
                        self._error = "macOS desactivó la observación de teclado/mouse"
                        self._condicion.notify_all()
            elif q.CGEventGetIntegerValueField(evento, q.kCGEventSourceUnixProcessID) != os.getpid():
                if tipo in (q.kCGEventKeyDown, q.kCGEventKeyUp):
                    codigo = q.CGEventGetIntegerValueField(evento, q.kCGKeyboardEventKeycode)
                    self.registrar(('tecla', codigo), tipo == q.kCGEventKeyDown)
                elif tipo == q.kCGEventFlagsChanged:
                    codigo = q.CGEventGetIntegerValueField(evento, q.kCGKeyboardEventKeycode)
                    mascaras = {0x36: q.kCGEventFlagMaskCommand, 0x37: q.kCGEventFlagMaskCommand,
                                0x38: q.kCGEventFlagMaskShift, 0x3C: q.kCGEventFlagMaskShift,
                                0x3A: q.kCGEventFlagMaskAlternate, 0x3D: q.kCGEventFlagMaskAlternate,
                                0x3B: q.kCGEventFlagMaskControl, 0x3E: q.kCGEventFlagMaskControl,
                                0x3F: q.kCGEventFlagMaskSecondaryFn}
                    mascara = mascaras.get(codigo)
                    self.registrar(('modificador', mascara) if mascara is not None else None,
                                   bool(q.CGEventGetFlags(evento) & mascara) if mascara is not None else None)
                elif tipo in (q.kCGEventLeftMouseDown, q.kCGEventLeftMouseUp,
                               q.kCGEventRightMouseDown, q.kCGEventRightMouseUp,
                               q.kCGEventOtherMouseDown, q.kCGEventOtherMouseUp):
                    boton = q.CGEventGetIntegerValueField(evento, q.kCGMouseEventButtonNumber)
                    self.registrar(('mouse', boton), tipo in (q.kCGEventLeftMouseDown,
                                   q.kCGEventRightMouseDown, q.kCGEventOtherMouseDown))
                else:
                    self.registrar()
            return evento

        tap = q.CGEventTapCreate(q.kCGSessionEventTap, q.kCGHeadInsertEventTap,
                                 q.kCGEventTapOptionListenOnly,
                                 sum(1 << tipo for tipo in tipos), evento, None)
        if tap is None:
            raise RuntimeError("macOS no permite observar teclado/mouse. Habilita Monitorización de entrada "
                               "y Accesibilidad para la aplicación que ejecuta Python")
        fuente = q.CFMachPortCreateRunLoopSource(None, tap, 0)
        self._runloop = q.CFRunLoopGetCurrent()
        q.CFRunLoopAddSource(self._runloop, fuente, q.kCFRunLoopCommonModes)
        q.CGEventTapEnable(tap, True)
        self._listo.set()
        try:
            while not self._detener.is_set():
                q.CFRunLoopRunInMode(q.kCFRunLoopDefaultMode, 0.1, False)
        finally:
            q.CGEventTapEnable(tap, False)
            q.CFRunLoopRemoveSource(self._runloop, fuente, q.kCFRunLoopCommonModes)
            q.CFMachPortInvalidate(tap)

    def _escuchar_windows(self):
        import ctypes as c
        from ctypes import wintypes as w

        usuario = c.WinDLL('user32', use_last_error=True)
        kernel = c.WinDLL('kernel32', use_last_error=True)
        usuario.GetAsyncKeyState.argtypes = [c.c_int]
        usuario.GetAsyncKeyState.restype = c.c_short
        botones_fisicos = {0: 1, 1: 2, 2: 4, 3: 5, 4: 6}
        self._esta_pulsada = lambda tecla: bool(usuario.GetAsyncKeyState(
            botones_fisicos[tecla[1]] if tecla[0] == 'mouse' else tecla[1]) & 0x8000)
        callback_type = c.WINFUNCTYPE(c.c_ssize_t, c.c_int, w.WPARAM, w.LPARAM)

        class Teclado(c.Structure):
            _fields_ = [('vk', w.DWORD), ('scan', w.DWORD), ('flags', w.DWORD),
                        ('time', w.DWORD), ('extra', c.c_size_t)]

        class Mouse(c.Structure):
            _fields_ = [('pos', w.POINT), ('data', w.DWORD), ('flags', w.DWORD),
                        ('time', w.DWORD), ('extra', c.c_size_t)]

        usuario.SetWindowsHookExW.argtypes = [c.c_int, callback_type, w.HINSTANCE, w.DWORD]
        usuario.SetWindowsHookExW.restype = w.HANDLE
        usuario.CallNextHookEx.argtypes = [w.HANDLE, c.c_int, w.WPARAM, w.LPARAM]
        usuario.CallNextHookEx.restype = c.c_ssize_t
        usuario.UnhookWindowsHookEx.argtypes = [w.HANDLE]
        usuario.GetMessageW.argtypes = [c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
        kernel.GetModuleHandleW.argtypes = [w.LPCWSTR]
        kernel.GetModuleHandleW.restype = w.HMODULE

        @callback_type
        def teclado(codigo, mensaje, datos):
            if codigo >= 0 and not c.cast(datos, c.POINTER(Teclado)).contents.flags & 0x10:
                tecla = c.cast(datos, c.POINTER(Teclado)).contents.vk
                self.registrar(('tecla', tecla), mensaje in (0x0100, 0x0104))
            return usuario.CallNextHookEx(None, codigo, mensaje, datos)

        @callback_type
        def mouse(codigo, mensaje, datos):
            if codigo >= 0 and not c.cast(datos, c.POINTER(Mouse)).contents.flags & 0x01:
                botones = {0x0201: (0, True), 0x0202: (0, False),
                           0x0204: (1, True), 0x0205: (1, False),
                           0x0207: (2, True), 0x0208: (2, False)}
                boton = botones.get(mensaje)
                if mensaje in (0x020B, 0x020C):
                    extra = c.cast(datos, c.POINTER(Mouse)).contents.data >> 16
                    boton = (extra + 2, mensaje == 0x020B)
                self.registrar(('mouse', boton[0]) if boton else None, boton[1] if boton else None)
            return usuario.CallNextHookEx(None, codigo, mensaje, datos)

        hooks = []
        self._thread_id = kernel.GetCurrentThreadId()
        try:
            modulo = kernel.GetModuleHandleW(None)
            for tipo, callback in ((13, teclado), (14, mouse)):
                hook = usuario.SetWindowsHookExW(tipo, callback, modulo, 0)
                if not hook:
                    raise c.WinError(c.get_last_error())
                hooks.append(hook)
            mensaje = w.MSG()
            usuario.PeekMessageW(c.byref(mensaje), None, 0, 0, 0)
            self._listo.set()
            while not self._detener.is_set():
                resultado = usuario.GetMessageW(c.byref(mensaje), None, 0, 0)
                if resultado == -1:
                    raise c.WinError(c.get_last_error())
                if resultado == 0:
                    break
                usuario.TranslateMessage(c.byref(mensaje))
                usuario.DispatchMessageW(c.byref(mensaje))
        finally:
            for hook in hooks:
                usuario.UnhookWindowsHookEx(hook)

    def detener(self):
        self._detener.set()
        if self._thread_id:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
        if self._hilo:
            self._hilo.join(timeout=1)
