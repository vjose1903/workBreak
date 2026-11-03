"""Interfaz nativa de la barra de menús de macOS."""
import copy
import fcntl
import hashlib
from pathlib import Path
import signal
import tempfile
import time
from urllib.parse import urlsplit

import objc
from AppKit import (
    NSAlert, NSApplication, NSApplicationActivationPolicyAccessory, NSFont, NSImage, NSMenu,
    NSMenuItem, NSModalPanelRunLoopMode, NSOpenPanel, NSScrollView, NSStatusBar,
    NSTextField, NSTextView, NSVariableStatusItemLength, NSWorkspace,
)
from Foundation import NSObject, NSRunLoop, NSRunLoopCommonModes, NSTimer

from app_controller import ControladorBot
from menu import Configuracion, FASES_EDITOR, MODOS_INTERACCION, NAVEGADORES_VALIDOS, _config_a_dict, cargar_historial


def normalizar_webs(texto):
    paginas = []
    for entrada in texto.replace('\n', ',').split(','):
        entrada = entrada.strip()
        if not entrada:
            continue
        url = entrada if '://' in entrada else 'https://' + entrada
        try:
            partes = urlsplit(url)
            partes.port  # Validar también puertos y direcciones IPv6 mal formadas.
        except ValueError as error:
            raise ValueError(f'Dirección web inválida: {entrada}') from error
        if partes.scheme not in ('http', 'https') or not partes.hostname or any(c.isspace() for c in url):
            raise ValueError(f'Dirección web inválida: {entrada}')
        if url not in paginas:
            paginas.append(url)
    return paginas


class MenuWorkBreak(NSObject):
    def init(self):
        self = objc.super(MenuWorkBreak, self).init()
        if self is None:
            return None
        self.controlador = ControladorBot()
        self.config = _config_a_dict(Configuracion())
        self.historial = []
        self.saliendo = False
        self._estaba_activo = False
        self.timer = None
        self.item_barra = None
        return self

    def applicationDidFinishLaunching_(self, _notificacion):
        self.preparar()

    def applicationShouldTerminate_(self, _aplicacion):
        if self.controlador.activo:
            self.saliendo = True
            self.controlador.detener()
            return 0  # Cerrar después de que el bot termine su limpieza.
        return 1

    @objc.python_method
    def preparar(self):
        if hasattr(NSImage, 'imageWithSystemSymbolName_accessibilityDescription_'):
            imagen = NSImage.imageWithSystemSymbolName_accessibilityDescription_('w.square.fill', 'WorkBreak')
            if imagen is not None:
                NSApplication.sharedApplication().setApplicationIconImage_(imagen)
        self.item_barra = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        boton = self.item_barra.button()
        ruta_icono = Path(__file__).resolve().parent.parent / 'assets' / 'icon.svg'
        icono = NSImage.alloc().initWithContentsOfFile_(str(ruta_icono))
        if icono is not None and icono.size().height > 0:
            tamano = icono.size()
            icono.setSize_((22 * tamano.width / tamano.height, 22))
            icono.setTemplate_(False)  # Conservar el degradado del SVG.
            boton.setImage_(icono)
            boton.setTitle_('')
        else:
            boton.setTitle_('W')
            boton.setFont_(NSFont.boldSystemFontOfSize_(14))
        boton.setToolTip_('WorkBreak — Detenido')
        boton.setAccessibilityLabel_('WorkBreak')
        self.construir_menu()
        self.timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            0.2, self, 'actualizar:', None, True)
        bucle = NSRunLoop.mainRunLoop()
        bucle.addTimer_forMode_(self.timer, NSRunLoopCommonModes)
        bucle.addTimer_forMode_(self.timer, NSModalPanelRunLoopMode)

    @objc.python_method
    def item(self, menu, titulo, comando=None, marcado=False, habilitado=True):
        elemento = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            titulo, 'accion:' if comando else None, '')
        if comando:
            elemento.setTarget_(self)
            elemento.setRepresentedObject_(comando)
        elemento.setEnabled_(bool(comando) and habilitado)
        elemento.setState_(1 if marcado else 0)
        menu.addItem_(elemento)
        return elemento

    @objc.python_method
    def submenu(self, menu, titulo):
        elemento = self.item(menu, titulo)
        elemento.setEnabled_(True)
        hijo = NSMenu.alloc().initWithTitle_(titulo)
        hijo.setAutoenablesItems_(False)
        elemento.setSubmenu_(hijo)
        return hijo, elemento

    @objc.python_method
    def construir_menu(self):
        menu = NSMenu.alloc().initWithTitle_('WorkBreak')
        menu.setAutoenablesItems_(False)
        self.estado_item = self.item(menu, 'WorkBreak — Detenido')
        self.fase_item = self.item(menu, 'Listo para iniciar')
        menu.addItem_(NSMenuItem.separatorItem())
        self.config_items = []

        modos, item = self.submenu(menu, 'Interacción')
        self.config_items.append(item)
        for clave, titulo in MODOS_INTERACCION.items():
            self.item(modos, titulo, 'modo:' + clave, self.config.get('modo', 'ambos') == clave)

        navegadores, item = self.submenu(menu, 'Navegador')
        self.config_items.append(item)
        self.item(navegadores, 'Ninguno', 'browser:', self.config.get('browser') is None)
        for navegador in NAVEGADORES_VALIDOS:
            self.item(navegadores, navegador.capitalize(), 'browser:' + navegador,
                      self.config.get('browser') == navegador)
        self.config_items.append(self.item(menu, f"Webs… ({len(self.config.get('paginas', []))})", 'webs'))

        fuente, item = self.submenu(menu, 'Fuente de código')
        self.config_items.append(item)
        real = self.config.get('fuente_tipo') == 'directorio'
        self.item(fuente, 'Código React/TypeScript aleatorio', 'fuente:aleatorio', not real)
        self.item(fuente, 'Elegir directorio…', 'fuente:directorio')
        if real:
            ruta = self.config.get('directorio', '')
            self.item(fuente, Path(ruta).name, 'fuente:directorio', marcado=True).setToolTip_(ruta)

        tiempo = self.config.get('tiempo')
        etiqueta = f'{tiempo} minutos' if tiempo else 'Indefinido'
        self.config_items.append(self.item(menu, f'Tiempo… ({etiqueta})', 'tiempo'))
        fases, item = self.submenu(menu, 'Fases del editor')
        self.config_items.append(item)
        for clave, titulo in FASES_EDITOR.items():
            self.item(fases, titulo, 'fase:' + clave, self.config.get('fases') == clave)

        recientes, item = self.submenu(menu, 'Configuraciones recientes')
        self.config_items.append(item)
        self.historial = cargar_historial()
        if not self.historial:
            self.item(recientes, 'Todavía no hay sesiones guardadas')
        for indice, registro in enumerate(self.historial):
            tiempo = registro.get('tiempo')
            titulo = (f"{MODOS_INTERACCION[registro.get('modo', 'ambos')]} · "
                      f"{registro.get('browser') or 'Sin navegador'} · "
                      f"{FASES_EDITOR.get(registro.get('fases'), FASES_EDITOR['ambas'])} · "
                      f"{str(tiempo) + ' min' if tiempo else 'Indefinido'}")
            self.item(recientes, titulo, f'historial:{indice}').setToolTip_(
                registro.get('fuente_descripcion', '') + ' — ' + str(registro.get('fecha', '')))

        menu.addItem_(NSMenuItem.separatorItem())
        self.iniciar_item = self.item(menu, 'Iniciar bot', 'iniciar')
        self.detener_item = self.item(menu, 'Detener bot', 'detener', habilitado=False)
        menu.addItem_(NSMenuItem.separatorItem())
        self.item(menu, 'Estado y estadísticas…', 'estadisticas')
        self.item(menu, 'Ver registro…', 'registro')
        self.salir_item = self.item(menu, 'Salir de WorkBreak', 'salir')
        self.item_barra.setMenu_(menu)
        self.actualizar(None)

    def actualizar_(self, _timer):
        self.actualizar(_timer)

    @objc.python_method
    def actualizar(self, _timer):
        self.controlador.actualizar()
        activo = self.controlador.activo
        finalizo = self._estaba_activo and not activo
        self._estaba_activo = activo
        if finalizo and not self.saliendo:
            self.construir_menu()
            return
        estado = self.controlador.estado.get('estado', 'detenido')
        titulos = {
            'detenido': 'Detenido', 'iniciando': 'Iniciando…', 'ejecutando': 'Ejecutándose',
            'pausado': 'Pausado por actividad', 'deteniendo': 'Deteniendo…',
            'finalizado': 'Sesión finalizada', 'error': 'Error en la sesión',
        }
        titulo = titulos.get(estado, estado)
        self.estado_item.setTitle_('WorkBreak — ' + titulo)
        self.item_barra.button().setToolTip_('WorkBreak — ' + titulo)
        detalle = MODOS_INTERACCION[self.config.get('modo', 'ambos')]
        if self.config.get('modo') != 'web':
            detalle += ' · ' + FASES_EDITOR[self.config.get('fases', 'ambas')]
        if estado == 'pausado':
            datos = self.controlador.estado
            detalle = ('Esperando a que sueltes la tecla o el botón' if datos.get('pulsada')
                       else f"Reanudación en {datos.get('segundos', 10)} segundos")
        elif estado == 'ejecutando':
            detalle = 'Fase: ' + self.controlador.estado.get('fase', 'editor')
        elif estado == 'error':
            detalle = 'Abre Estado y estadísticas para ver el motivo'
        elif self.controlador.deteniendo:
            detalle = 'Terminando la sesión y restaurando el estado'
        self.fase_item.setTitle_(detalle)
        self.iniciar_item.setEnabled_(not activo and not self.saliendo)
        self.detener_item.setEnabled_(activo and not self.controlador.deteniendo)
        for item in self.config_items:
            item.setEnabled_(not activo and not self.saliendo)
        self.salir_item.setTitle_('Deteniendo antes de salir…' if self.saliendo else 'Salir de WorkBreak')
        self.salir_item.setEnabled_(not self.saliendo)
        if self.saliendo and not activo:
            self.controlador.cerrar()
            if self.timer:
                self.timer.invalidate()
            NSStatusBar.systemStatusBar().removeStatusItem_(self.item_barra)
            NSApplication.sharedApplication().terminate_(None)

    @objc.python_method
    def aviso(self, titulo, mensaje):
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        alerta = NSAlert.alloc().init()
        alerta.setMessageText_(titulo)
        alerta.setInformativeText_(mensaje)
        alerta.addButtonWithTitle_('Aceptar')
        alerta.runModal()

    @objc.python_method
    def preguntar(self, titulo, mensaje, valor):
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        alerta = NSAlert.alloc().init()
        alerta.setMessageText_(titulo)
        alerta.setInformativeText_(mensaje)
        alerta.addButtonWithTitle_('Guardar')
        alerta.addButtonWithTitle_('Cancelar')
        campo = NSTextField.alloc().initWithFrame_(((0, 0), (380, 55)))
        campo.setStringValue_(valor)
        alerta.setAccessoryView_(campo)
        alerta.window().setInitialFirstResponder_(campo)
        return campo.stringValue() if alerta.runModal() == 1000 else None

    def accion_(self, sender):
        comando = str(sender.representedObject())
        try:
            if comando == 'detener':
                self.controlador.detener()
            elif comando == 'salir':
                self.solicitar_salida()
            elif comando == 'estadisticas':
                self.mostrar_estadisticas()
            elif comando == 'registro':
                if self.controlador.ruta_log.exists():
                    if not NSWorkspace.sharedWorkspace().openFile_(str(self.controlador.ruta_log)):
                        self.aviso('Registro de WorkBreak', 'No se pudo abrir: ' + str(self.controlador.ruta_log))
                else:
                    self.aviso('Registro de WorkBreak', 'Todavía no se ha iniciado ninguna sesión.')
            elif self.controlador.activo or self.saliendo:
                return
            elif comando == 'iniciar':
                self.controlador.iniciar(self.config)
            else:
                self.configurar(comando)
                self.construir_menu()
            self.actualizar(None)
        except Exception as error:
            self.aviso('WorkBreak', str(error))

    @objc.python_method
    def configurar(self, comando):
        if comando.startswith('modo:'):
            self.config['modo'] = comando.split(':', 1)[1]
        elif comando.startswith('browser:'):
            self.config['browser'] = comando.split(':', 1)[1] or None
        elif comando.startswith('fase:'):
            self.config['fases'] = comando.split(':', 1)[1]
        elif comando.startswith('historial:'):
            self.config = copy.deepcopy(self.historial[int(comando.split(':', 1)[1])])
            self.config.setdefault('fases', 'ambas')
            self.config.setdefault('modo', 'ambos')
        elif comando == 'webs':
            texto = self.preguntar('Webs del bot', 'Separa las direcciones por comas.',
                                   ', '.join(self.config.get('paginas', [])))
            if texto is not None:
                self.config['paginas'] = normalizar_webs(texto)
        elif comando == 'tiempo':
            texto = self.preguntar('Tiempo de ejecución', 'Minutos. Vacío o 0 significa indefinido.',
                                   str(self.config.get('tiempo') or ''))
            if texto is not None:
                texto = texto.strip()
                if texto and (not texto.isdecimal() or int(texto) < 0):
                    raise ValueError('Introduce un número entero de minutos, 0 o deja el campo vacío.')
                self.config['tiempo'] = int(texto) if texto and int(texto) else None
        elif comando == 'fuente:aleatorio':
            self.config.update(fuente_tipo='aleatorio', directorio=None,
                               fuente_descripcion='Código React/TS aleatorio')
        elif comando == 'fuente:directorio':
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            selector = NSOpenPanel.openPanel()
            selector.setTitle_('Directorio con código React o TypeScript')
            selector.setCanChooseDirectories_(True)
            selector.setCanChooseFiles_(False)
            selector.setAllowsMultipleSelection_(False)
            if selector.runModal() == 1:
                ruta = str(selector.URL().path())
                self.config.update(fuente_tipo='directorio', directorio=ruta,
                                   fuente_descripcion='Directorio real: ' + ruta)

    @objc.python_method
    def mostrar_estadisticas(self):
        self.controlador.actualizar()
        stats = self.controlador.estadisticas
        mensaje = self.estado_item.title() + '\n' + self.config.get('fuente_descripcion', '')
        total = stats.get('total', 0)
        if self.controlador.activo and self.controlador.inicio is not None:
            total = time.monotonic() - self.controlador.inicio
        mensaje += f'\nTiempo de sesión: {total / 60:.1f} min'
        mensaje += f"\nTiempo registrado en editor: {stats.get('editor', 0) / 60:.1f} min"
        mensaje += f"\nTiempo registrado en navegador: {stats.get('navegador', 0) / 60:.1f} min"
        mensaje += f"\nSesiones de editor: {stats.get('sesiones_editor', 0)}"
        if self.controlador.ultimo_error:
            mensaje += '\n\nÚltimo error:\n' + self.controlador.ultimo_error
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        alerta = NSAlert.alloc().init()
        alerta.setMessageText_('Estado y estadísticas de WorkBreak')
        alerta.addButtonWithTitle_('Aceptar')
        scroll = NSScrollView.alloc().initWithFrame_(((0, 0), (460, 230)))
        scroll.setHasVerticalScroller_(True)
        texto = NSTextView.alloc().initWithFrame_(((0, 0), (440, 230)))
        texto.setEditable_(False)
        texto.setVerticallyResizable_(True)
        texto.setHorizontallyResizable_(False)
        texto.textContainer().setWidthTracksTextView_(True)
        texto.setFont_(NSFont.systemFontOfSize_(13))
        texto.setString_(mensaje)
        scroll.setDocumentView_(texto)
        alerta.setAccessoryView_(scroll)
        alerta.runModal()

    @objc.python_method
    def solicitar_salida(self):
        self.saliendo = True
        self.controlador.detener()
        self.actualizar(None)


def ejecutar_interfaz():
    # Una sola interfaz por checkout; el archivo se libera también ante una salida inesperada.
    identificador = hashlib.sha256(str(Path(__file__).resolve().parent).encode()).hexdigest()[:12]
    ruta_lock = Path(tempfile.gettempdir()) / f'workbreak-{identificador}.lock'
    with ruta_lock.open('a') as bloqueo:
        try:
            fcntl.flock(bloqueo, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('WorkBreak ya está abierto. Busca la W en la barra de menús.')
            return 0
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        delegado = MenuWorkBreak.alloc().init()
        app.setDelegate_(delegado)
        for senal in (signal.SIGINT, signal.SIGTERM):
            signal.signal(senal, lambda *_: delegado.solicitar_salida())
        app.run()
    return 0
