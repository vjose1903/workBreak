"""Interfaz nativa de la barra de menús de macOS."""
import os
import copy
import fcntl
import hashlib
from pathlib import Path
import signal
import tempfile
import time
import sys
from urllib.parse import urlsplit

import objc
from AppKit import (
    NSAlert, NSApplication, NSApplicationActivationPolicyAccessory, NSFont, NSImage, NSMenu,
    NSMenuItem, NSModalPanelRunLoopMode, NSOpenPanel, NSScrollView, NSStatusBar,
    NSTextField, NSTextView, NSVariableStatusItemLength, NSWorkspace,
    NSButton, NSColor, NSStepper, NSSwitch, NSTableColumn, NSTableView, NSView,
)
from Foundation import NSObject, NSRunLoop, NSRunLoopCommonModes, NSTimer, NSURL

from app_paths import recurso
from app_version import VERSION, APP_ID
from app_updates import Actualizador
from app_preferences import cargar_preferencias, guardar_preferencias
from mac_settings import VentanaConfiguracion
from app_controller import ControladorBot
from menu import Configuracion, FASES_EDITOR, MODOS_INTERACCION, NAVEGADORES_VALIDOS, formatear_tiempo, _config_a_dict, cargar_historial


def normalizar_web(texto):
    entrada = texto.strip()
    url = entrada if '://' in entrada else 'https://' + entrada
    try:
        partes = urlsplit(url)
        partes.port
    except ValueError as error:
        raise ValueError(f'Dirección web inválida: {entrada}') from error
    if partes.scheme not in ('http', 'https') or not partes.hostname or any(c.isspace() for c in url):
        raise ValueError(f'Dirección web inválida: {entrada}')
    return url


def normalizar_webs(texto):
    return list(dict.fromkeys(normalizar_web(entrada) for entrada in texto.replace('\n', ',').split(',') if entrada.strip()))


class DialogoTiempo(NSObject):
    @objc.python_method
    def preparar(self, minutos):
        self.minutos = minutos
        self.alerta = NSAlert.alloc().init()
        self.alerta.setMessageText_('Tiempo de ejecución')
        self.alerta.setInformativeText_('Define una duración o activa el tiempo indefinido.')
        icono = NSImage.alloc().initWithContentsOfFile_(str(recurso('assets/icon.svg')))
        if icono is not None:
            self.alerta.setIcon_(icono)
        guardar = self.alerta.addButtonWithTitle_('Guardar')
        guardar.setTarget_(self)
        guardar.setAction_('guardar:')
        self.alerta.addButtonWithTitle_('Cancelar')
        segundos = round((minutos or 0) * 60)
        valores = [segundos // 3600, segundos % 3600 // 60, segundos % 60]
        vista = NSView.alloc().initWithFrame_(((0, 0), (440, 180)))
        etiqueta_indefinido = NSTextField.labelWithString_('Tiempo indefinido')
        etiqueta_indefinido.setFrame_(((0, 150), (260, 22)))
        etiqueta_indefinido.setFont_(NSFont.boldSystemFontOfSize_(13))
        vista.addSubview_(etiqueta_indefinido)
        self.indefinido = NSSwitch.alloc().initWithFrame_(((390, 146), (45, 28)))
        self.indefinido.setState_(0 if minutos else 1)
        self.indefinido.setTarget_(self)
        self.indefinido.setAction_('alternarIndefinido:')
        self.indefinido.setAccessibilityLabel_('Tiempo indefinido')
        vista.addSubview_(self.indefinido)
        self.campos, self.controles = [], []
        for indice, (titulo, valor) in enumerate(zip(('Horas', 'Minutos', 'Segundos'), valores)):
            x = indice * 150
            etiqueta = NSTextField.labelWithString_(titulo)
            etiqueta.setFrame_(((x, 105), (125, 20)))
            etiqueta.setTextColor_(NSColor.secondaryLabelColor())
            vista.addSubview_(etiqueta)
            campo = NSTextField.alloc().initWithFrame_(((x, 40), (106, 58)))
            campo.setFont_(NSFont.monospacedDigitSystemFontOfSize_weight_(36, 0))
            campo.setTextColor_(NSColor.controlAccentColor())
            campo.setAlignment_(2)
            campo.setStringValue_(f'{valor:02d}')
            campo.setAccessibilityLabel_(titulo)
            campo.setDelegate_(self)
            campo.setTag_(indice)
            vista.addSubview_(campo)
            control = NSStepper.alloc().initWithFrame_(((x + 112, 52), (20, 30)))
            control.setMinValue_(0)
            control.setMaxValue_(max(9999, valor) if indice == 0 else 59)
            control.setIncrement_(1)
            control.setIntegerValue_(valor)
            control.setValueWraps_(False)
            control.setTag_(indice)
            control.setTarget_(self)
            control.setAction_('cambiar:')
            control.setAccessibilityLabel_(titulo)
            vista.addSubview_(control)
            self.campos.append(campo)
            self.controles.append(control)
        self.error = NSTextField.labelWithString_('')
        self.error.setFrame_(((0, 0), (440, 32)))
        self.error.setTextColor_(NSColor.systemRedColor())
        vista.addSubview_(self.error)
        self.alerta.setAccessoryView_(vista)
        self.alternarIndefinido_(self.indefinido)
        self.alerta.window().setInitialFirstResponder_(self.indefinido if self.indefinido.state() else self.campos[0])

    def alternarIndefinido_(self, sender):
        activo = bool(self.indefinido.state())
        if activo:
            self.alerta.window().makeFirstResponder_(self.indefinido)
        for campo, control in zip(self.campos, self.controles):
            if activo:
                campo.setStringValue_('00')
                control.setIntegerValue_(0)
            campo.setEnabled_(not activo)
            campo.setTextColor_(NSColor.disabledControlTextColor() if activo else NSColor.controlAccentColor())
            control.setEnabled_(not activo)
        self.error.setStringValue_('')

    def controlTextDidChange_(self, notificacion):
        campo = notificacion.object()
        texto = campo.stringValue()
        control = self.controles[campo.tag()]
        if texto.isdecimal() and int(texto) <= control.maxValue():
            control.setIntegerValue_(int(texto))

    def cambiar_(self, sender):
        self.campos[sender.tag()].setStringValue_(f'{sender.integerValue():02d}')
        self.error.setStringValue_('')

    def guardar_(self, sender):
        if self.indefinido.state():
            self.minutos = None
            NSApplication.sharedApplication().stopModalWithCode_(1000)
            return
        valores = []
        for campo, control in zip(self.campos, self.controles):
            texto = campo.stringValue().strip()
            if not texto.isdecimal() or int(texto) > control.maxValue():
                self.error.setStringValue_('Introduce horas válidas y minutos/segundos entre 00 y 59.')
                return
            valores.append(int(texto))
        segundos = valores[0] * 3600 + valores[1] * 60 + valores[2]
        if not segundos:
            self.error.setStringValue_('Define un tiempo mayor que cero o activa Tiempo indefinido.')
            return
        self.minutos = segundos / 60 if segundos else None
        NSApplication.sharedApplication().stopModalWithCode_(1000)

    @objc.python_method
    def mostrar(self):
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        return self.alerta.runModal() == 1000


class DialogoWebs(NSObject):
    @objc.python_method
    def preparar(self, paginas, nombres=None):
        self.paginas = list(paginas)
        self.nombres = {url: (nombres or {}).get(url) or urlsplit(url).hostname or url for url in paginas}
        self.alerta = NSAlert.alloc().init()
        self.alerta.setMessageText_('Webs del bot')
        icono = NSImage.alloc().initWithContentsOfFile_(str(recurso('assets/icon.svg')))
        if icono is not None:
            self.alerta.setIcon_(icono)
        self.alerta.setInformativeText_('Identifica cada web con un nombre y agrega su dirección.')
        guardar = self.alerta.addButtonWithTitle_('Guardar')
        guardar.setTarget_(self)
        guardar.setAction_('guardar:')
        self.alerta.addButtonWithTitle_('Cancelar')
        vista = NSView.alloc().initWithFrame_(((0, 0), (760, 390)))
        self.nombre = NSTextField.alloc().initWithFrame_(((0, 335), (222, 32)))
        self.nombre.setPlaceholderString_('Ej. Panel de administración')
        self.nombre.setFont_(NSFont.systemFontOfSize_(14))
        self.nombre.setAccessibilityLabel_('Nombre de la web, obligatorio')
        vista.addSubview_(self.nombre)
        for titulo, x, ancho in [('Nombre *', 0, 222), ('Dirección web *', 238, 402)]:
            etiqueta = NSTextField.labelWithString_(titulo)
            etiqueta.setFrame_(((x, 372), (ancho, 18)))
            etiqueta.setFont_(NSFont.boldSystemFontOfSize_(12))
            vista.addSubview_(etiqueta)
        self.campo = NSTextField.alloc().initWithFrame_(((238, 335), (402, 32)))
        self.campo.setPlaceholderString_('https://ejemplo.com')
        self.campo.setFont_(NSFont.systemFontOfSize_(14))
        self.campo.setAccessibilityLabel_('Dirección web')
        self.campo.setTarget_(self)
        self.campo.setAction_('agregar:')
        vista.addSubview_(self.campo)
        agregar = NSButton.alloc().initWithFrame_(((652, 335), (108, 32)))
        agregar.setTitle_('Agregar')
        agregar.setBezelStyle_(1)
        agregar.setTarget_(self)
        agregar.setAction_('agregar:')
        vista.addSubview_(agregar)
        self.error = NSTextField.labelWithString_('')
        self.error.setFrame_(((0, 297), (760, 30)))
        self.error.setTextColor_(NSColor.systemRedColor())
        vista.addSubview_(self.error)
        scroll = NSScrollView.alloc().initWithFrame_(((0, 52), (760, 238)))
        scroll.setHasVerticalScroller_(True)
        scroll.setHasHorizontalScroller_(True)
        scroll.setAutohidesScrollers_(True)
        scroll.setWantsLayer_(True)
        scroll.layer().setCornerRadius_(8)
        scroll.layer().setMasksToBounds_(True)
        self.tabla = NSTableView.alloc().initWithFrame_(scroll.bounds())
        columna = NSTableColumn.alloc().initWithIdentifier_('url')
        columna_nombre = NSTableColumn.alloc().initWithIdentifier_('nombre')
        columna_nombre.setTitle_('Nombre')
        columna_nombre.setWidth_(222)
        columna_nombre.dataCell().setFont_(NSFont.boldSystemFontOfSize_(13))
        self.tabla.addTableColumn_(columna_nombre)
        columna.setTitle_('Dirección web')
        columna.setWidth_(518)
        columna.dataCell().setFont_(NSFont.systemFontOfSize_(13))
        self.columna_url = columna
        self.tabla.setColumnAutoresizingStyle_(0)
        self.tabla.setRowHeight_(36)
        self.tabla.setUsesAlternatingRowBackgroundColors_(True)
        self.tabla.setAccessibilityLabel_('Direcciones web configuradas')
        self.tabla.addTableColumn_(columna)
        self.tabla.setDataSource_(self)
        self.tabla.setDelegate_(self)
        scroll.setDocumentView_(self.tabla)
        vista.addSubview_(scroll)
        self.quitar = NSButton.alloc().initWithFrame_(((0, 6), (165, 32)))
        self.quitar.setTitle_('Quitar seleccionada')
        self.quitar.setBezelStyle_(1)
        self.quitar.setTarget_(self)
        self.quitar.setAction_('quitar:')
        self.quitar.setEnabled_(False)
        vista.addSubview_(self.quitar)
        self.contador = NSTextField.labelWithString_('')
        self.contador.setFrame_(((185, 12), (575, 20)))
        vista.addSubview_(self.contador)
        self.alerta.setAccessoryView_(vista)
        self.alerta.window().setInitialFirstResponder_(self.nombre)
        self.refrescar()

    def numberOfRowsInTableView_(self, tabla):
        return len(self.paginas)

    def tableView_objectValueForTableColumn_row_(self, tabla, columna, fila):
        url = self.paginas[fila]
        return self.nombres[url] if columna.identifier() == 'nombre' else url

    def tableViewSelectionDidChange_(self, notificacion):
        self.quitar.setEnabled_(self.tabla.selectedRow() >= 0)

    @objc.python_method
    def refrescar(self):
        self.columna_url.setWidth_(max(518, max((len(url) * 8 for url in self.paginas), default=0)))
        self.tabla.reloadData()
        self.quitar.setEnabled_(self.tabla.selectedRow() >= 0)
        cantidad = len(self.paginas)
        self.contador.setTextColor_(NSColor.secondaryLabelColor())
        self.contador.setStringValue_(f'{cantidad} dirección configurada' if cantidad == 1 else f'{cantidad} direcciones configuradas')

    @objc.python_method
    def agregar_pendiente(self):
        texto = self.campo.stringValue().strip()
        nombre = self.nombre.stringValue().strip()
        if not texto and not nombre:
            return True
        if not nombre or not texto:
            self.error.setStringValue_('Completa el nombre y la dirección web. Ambos son obligatorios.')
            return False
        try:
            nuevas = [normalizar_web(texto)]
        except ValueError as error:
            self.error.setStringValue_(str(error))
            return False
        if len(nuevas) != 1:
            self.error.setStringValue_('Agrega una sola dirección por nombre.')
            return False
        url = nuevas[0]
        if url in self.paginas:
            self.error.setStringValue_('Esta dirección ya está en la lista.')
            return False
        self.paginas.append(url)
        self.nombres[url] = nombre
        self.nombre.setStringValue_('')
        self.campo.setStringValue_('')
        self.error.setStringValue_('')
        self.refrescar()
        return True

    def agregar_(self, sender):
        if not self.nombre.stringValue().strip() and not self.campo.stringValue().strip():
            self.error.setStringValue_('Completa el nombre y la dirección web. Ambos son obligatorios.')
            return
        if self.agregar_pendiente():
            self.alerta.window().makeFirstResponder_(self.nombre)

    def quitar_(self, sender):
        fila = self.tabla.selectedRow()
        if 0 <= fila < len(self.paginas):
            self.nombres.pop(self.paginas[fila], None)
            del self.paginas[fila]
            self.error.setStringValue_('')
            self.tabla.deselectAll_(None)
            self.refrescar()

    def guardar_(self, sender):
        if self.agregar_pendiente():
            NSApplication.sharedApplication().stopModalWithCode_(1000)

    @objc.python_method
    def mostrar(self):
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        return list(self.paginas) if self.alerta.runModal() == 1000 else None


class MenuWorkBreak(NSObject):
    def init(self):
        self = objc.super(MenuWorkBreak, self).init()
        if self is None:
            return None
        self.controlador = ControladorBot()
        self.actualizador = Actualizador()
        self.config = _config_a_dict(Configuracion())
        self.historial = []
        if getattr(sys, 'frozen', False):
            historial = cargar_historial()
            if historial:
                self.config.update(copy.deepcopy(historial[0]))
        self.config.update(cargar_preferencias() or {})
        self.ventana_configuracion = None
        self.saliendo = False
        self._estaba_activo = False
        self.timer = None
        self.item_barra = None
        return self

    def applicationDidFinishLaunching_(self, _notificacion):
        self.preparar()

    def applicationShouldTerminate_(self, _aplicacion):
        if self.controlador.activo or self.actualizador.consultando:
            self.actualizador.cancelar()
            self.solicitar_salida()
            return 0  # Cerrar después de que el bot termine su limpieza.
        self.actualizador.descartar()
        return 1

    @objc.python_method
    def preparar(self):
        # Los diálogos necesitan el menú Edición para los atajos del responder nativo.
        aplicacion = NSApplication.sharedApplication()
        if aplicacion.mainMenu() is None:
            principal = NSMenu.alloc().initWithTitle_('WorkBreak')
            edicion = NSMenu.alloc().initWithTitle_('Edición')
            entrada = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Edición', None, '')
            entrada.setSubmenu_(edicion)
            principal.addItem_(entrada)
            for titulo, accion, tecla in [('Deshacer', 'undo:', 'z'), ('Cortar', 'cut:', 'x'),
                                          ('Copiar', 'copy:', 'c'), ('Pegar', 'paste:', 'v'),
                                          ('Seleccionar todo', 'selectAll:', 'a')]:
                edicion.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(titulo, accion, tecla))
            aplicacion.setMainMenu_(principal)
        if hasattr(NSImage, 'imageWithSystemSymbolName_accessibilityDescription_'):
            imagen = NSImage.imageWithSystemSymbolName_accessibilityDescription_('w.square.fill', 'WorkBreak')
            if imagen is not None:
                NSApplication.sharedApplication().setApplicationIconImage_(imagen)
        self.item_barra = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        boton = self.item_barra.button()
        ruta_icono = recurso('assets/icon.svg')
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
        self.config_editor_items = []

        modos, item = self.submenu(menu, 'Interacción')
        self.config_items.append(item)
        for clave, titulo in MODOS_INTERACCION.items():
            self.item(modos, titulo, 'modo:' + clave, self.config.get('modo', 'ambos') == clave)

        solo_editor = self.config.get('modo') == 'editor'
        motivo_web = ' — Configurado solo editor' if solo_editor else ''
        navegadores, item = self.submenu(menu, 'Navegador' + motivo_web)
        self.config_web_items = [item]
        self.config_items.append(item)
        self.item(navegadores, 'Ninguno', 'browser:', self.config.get('browser') is None)
        for navegador in NAVEGADORES_VALIDOS:
            self.item(navegadores, navegador.capitalize(), 'browser:' + navegador,
                      self.config.get('browser') == navegador)
        item_webs = self.item(menu, f"Webs… ({len(self.config.get('paginas', []))})" + motivo_web, 'webs')
        self.config_items.append(item_webs)
        self.config_web_items.append(item_webs)

        fuente, item = self.submenu(menu, 'Fuente de código')
        self.config_items.append(item)
        self.config_editor_items.append(item)
        real = self.config.get('fuente_tipo') == 'directorio'
        self.item(fuente, 'Código React/TypeScript aleatorio', 'fuente:aleatorio', not real)
        self.item(fuente, 'Elegir directorio…', 'fuente:directorio')
        if real:
            ruta = self.config.get('directorio', '')
            self.item(fuente, Path(ruta).name, 'fuente:directorio', marcado=True).setToolTip_(ruta)

        tiempo = self.config.get('tiempo')
        etiqueta = formatear_tiempo(tiempo)
        self.config_items.append(self.item(menu, f'Tiempo… ({etiqueta})', 'tiempo'))
        fases, item = self.submenu(menu, 'Fases del editor')
        self.config_items.append(item)
        self.config_editor_items.append(item)
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
                      f"{formatear_tiempo(tiempo)}")
            self.item(recientes, titulo, f'historial:{indice}').setToolTip_(
                registro.get('fuente_descripcion', '') + ' — ' + str(registro.get('fecha', '')))

        self.config_items.append(self.item(menu, 'Configuración…', 'configuracion'))
        menu.addItem_(NSMenuItem.separatorItem())
        self.iniciar_item = self.item(menu, 'Iniciar bot', 'iniciar')
        self.detener_item = self.item(menu, 'Detener bot', 'detener', habilitado=False)
        menu.addItem_(NSMenuItem.separatorItem())
        self.item(menu, 'Estado y estadísticas…', 'estadisticas')
        self.item(menu, 'Ver registro…', 'registro')
        self.actualizar_item = self.item(menu, 'Buscar actualizaciones…', 'actualizaciones')
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
        self.estado_item.setTitle_(f'WorkBreak {VERSION} — ' + titulo)
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
        self.iniciar_item.setEnabled_(not activo and not self.saliendo and not self.actualizador.consultando
                                      and not (self.ventana_configuracion is not None
                                               and self.ventana_configuracion.ventana.isVisible()))
        self.detener_item.setEnabled_(activo and not self.controlador.deteniendo)
        for item in self.config_items:
            item.setEnabled_(not activo and not self.saliendo)
        for item in self.config_web_items:
            item.setEnabled_(not activo and not self.saliendo and self.config.get('modo') != 'editor')
        for item in self.config_editor_items:
            item.setEnabled_(not activo and not self.saliendo and self.config.get('modo') != 'web')
        self.actualizar_item.setEnabled_(not activo and not self.saliendo and not self.actualizador.consultando)
        self.actualizar_item.setTitle_(self.actualizador.texto_menu if self.actualizador.consultando else 'Buscar actualizaciones…')
        self.salir_item.setTitle_('Deteniendo antes de salir…' if self.saliendo else 'Salir de WorkBreak')
        self.salir_item.setEnabled_(not self.saliendo)
        if not activo and not self.saliendo:
            resultado = self.actualizador.obtener_resultado()
            if resultado is not None:
                self.mostrar_actualizacion(resultado)
        if self.saliendo and not activo and not self.actualizador.consultando:
            self.actualizador.descartar()
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
    def mostrar_actualizacion(self, resultado):
        if resultado.get('cancelada'):
            return
        if resultado.get('error'):
            self.aviso('Actualizaciones de WorkBreak', resultado['error'])
            return
        if resultado.get('descargada'):
            alerta = NSAlert.alloc().init()
            icono = NSImage.alloc().initWithContentsOfFile_(str(recurso('assets/icon.svg')))
            if icono is not None:
                alerta.setIcon_(icono)
            alerta.setMessageText_(f"WorkBreak {resultado['descargada']['version']} listo para instalar")
            alerta.setInformativeText_('WorkBreak se cerrará, instalará la actualización y volverá a abrirse. '
                                      'Tu configuración se conservará. macOS puede solicitar autorización de administrador.')
            alerta.addButtonWithTitle_('Instalar y reiniciar')
            alerta.addButtonWithTitle_('Ahora no')
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            if alerta.runModal() == 1000:
                try:
                    self.actualizador.instalar()
                    self.solicitar_salida()
                except Exception as error:
                    self.actualizador.descartar()
                    self.aviso('No se pudo iniciar la instalación', str(error))
            else:
                self.actualizador.descartar()
            return
        nueva = resultado.get('actualizacion')
        if nueva is None:
            self.aviso('WorkBreak está actualizado', f'Versión instalada: {VERSION}.')
            return
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        alerta = NSAlert.alloc().init()
        icono = NSImage.alloc().initWithContentsOfFile_(str(recurso('assets/icon.svg')))
        if icono is not None:
            alerta.setIcon_(icono)
        alerta.setMessageText_(f"WorkBreak {nueva['version']} disponible")
        alerta.setInformativeText_(f'Versión instalada: {VERSION}. La actualización se descargará aquí. '
                                  'Después podrás instalar y reiniciar sin abrir el DMG ni perder tu configuración.')
        alerta.addButtonWithTitle_('Descargar actualización')
        alerta.addButtonWithTitle_('Ahora no')
        if alerta.runModal() == 1000:
            self.actualizador.descargar(nueva)

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
            elif self.controlador.activo or self.saliendo or self.actualizador.consultando:
                return
            elif comando == 'actualizaciones':
                self.actualizador.buscar()
            elif comando == 'configuracion':
                if self.ventana_configuracion is None or not self.ventana_configuracion.ventana.isVisible():
                    self.ventana_configuracion = VentanaConfiguracion.alloc().init()
                    self.ventana_configuracion.preparar(self)
                self.ventana_configuracion.mostrar()
            elif comando == 'iniciar':
                if self.ventana_configuracion is not None and self.ventana_configuracion.ventana.isVisible():
                    return
                self.controlador.iniciar(self.config)
            else:
                self.configurar(comando)
            self.actualizar(None)
        except Exception as error:
            self.aviso('WorkBreak', str(error))

    @objc.python_method
    def configurar(self, comando, config=None):
        compartida = config is None
        config = copy.deepcopy(self.config) if compartida else config
        if comando.startswith('modo:'):
            config['modo'] = comando.split(':', 1)[1]
        elif comando.startswith('browser:'):
            config['browser'] = comando.split(':', 1)[1] or None
        elif comando.startswith('fase:'):
            config['fases'] = comando.split(':', 1)[1]
        elif comando.startswith('historial:'):
            registro = copy.deepcopy(self.historial[int(comando.split(':', 1)[1])])
            config.clear()
            config.update(registro)
            config.setdefault('fases', 'ambas')
            config.setdefault('modo', 'ambos')
        elif comando == 'webs':
            dialogo = DialogoWebs.alloc().init()
            dialogo.preparar(config.get('paginas', []), config.get('nombres_web', {}))
            paginas = dialogo.mostrar()
            if paginas is not None:
                config['paginas'] = paginas
                config['nombres_web'] = dict(dialogo.nombres)
        elif comando == 'tiempo':
            dialogo = DialogoTiempo.alloc().init()
            dialogo.preparar(config.get('tiempo'))
            if dialogo.mostrar():
                config['tiempo'] = dialogo.minutos
        elif comando == 'fuente:aleatorio':
            config.update(fuente_tipo='aleatorio', directorio=None,
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
                config.update(fuente_tipo='directorio', directorio=ruta,
                                   fuente_descripcion='Directorio real: ' + ruta)

        if compartida and config != self.config:
            self.aplicar_configuracion(config)

    @objc.python_method
    def aplicar_configuracion(self, config):
        if self.controlador.activo or self.actualizador.consultando or self.saliendo:
            raise ValueError('Detén el bot o espera a que termine la actualización antes de configurar.')
        nueva = copy.deepcopy(config)
        guardar_preferencias(nueva)
        self.config.clear()
        self.config.update(nueva)
        self.construir_menu()
        if self.ventana_configuracion is not None:
            self.ventana_configuracion.refrescar()

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
        self.actualizador.cancelar()
        self.saliendo = True
        self.controlador.detener()
        self.actualizar(None)


def ejecutar_interfaz():
    # Una interfaz por usuario, incluso entre distintas instalaciones.
    identificador = hashlib.sha256(f"{APP_ID}:{os.getuid()}".encode()).hexdigest()[:12]
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
