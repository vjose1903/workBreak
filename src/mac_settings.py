"""Ventana nativa que reúne las preferencias de WorkBreak."""
import objc
from timing_config import TITULOS, texto_tiempo
from AppKit import (NSApplication, NSButton, NSColor, NSFont, NSPopUpButton,
                    NSSwitch, NSTabView, NSTabViewItem, NSTextField, NSView, NSWindow,
                    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
                    NSBackingStoreBuffered)
from Foundation import NSObject

from app_preferences import estado_inicio, establecer_inicio, inicio_disponible
from app_version import VERSION
from editor_catalog import editores_instalados
from menu import MODOS_INTERACCION, NAVEGADORES_VALIDOS, formatear_tiempo, ACCIONES_EDITOR, ACCIONES_WEB, acciones_config


class VentanaConfiguracion(NSObject):
    @objc.python_method
    def preparar(self, menu):
        self.menu = menu
        self.config = menu.config
        self.opciones = {}
        self.ventana = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((0, 0), (740, 600)), NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered, False)
        self.ventana.setTitle_('Configuración de WorkBreak')
        self.ventana.setReleasedWhenClosed_(False)
        raiz = self.ventana.contentView()
        self.etiqueta(raiz, 'Configuración', 28, 538, 500, 30, 23, True)
        self.etiqueta(raiz, 'Las mismas opciones, compartidas con el menú de la barra.', 28, 510, 650, 22)
        self.tabs = NSTabView.alloc().initWithFrame_(((24, 78), (692, 420)))
        raiz.addSubview_(self.tabs)
        general = self.pestana('General')
        actividad = self.pestana('Actividad')
        editor = self.pestana('Editor')
        navegador = self.pestana('Navegador')

        self.etiqueta(general, 'Inicio de sesión', 20, 235, 500, 25, 16, True)
        self.etiqueta(general, 'Abrir WorkBreak al iniciar sesión', 20, 190, 540, 25, 14)
        self.inicio = NSSwitch.alloc().initWithFrame_(((598, 188), (45, 28)))
        self.inicio.setTarget_(self)
        self.inicio.setAction_('alternarInicio:')
        self.inicio.setAccessibilityLabel_('Abrir WorkBreak al iniciar sesión')
        general.addSubview_(self.inicio)
        self.inicio_info = self.etiqueta(general, '', 20, 125, 620, 55)
        self.etiqueta(general, f'WorkBreak {VERSION}', 20, 78, 500, 22, 14, True)
        self.etiqueta(general, 'Los cambios se guardan automáticamente, también desde el menú de la barra.',
                      20, 25, 620, 44)

        self.etiqueta(actividad, 'Cómo quieres trabajar', 20, 235, 600, 25, 16, True)
        self.modo = self.selector(actividad, 'Interacción', 190, 'modo', MODOS_INTERACCION)
        self.tiempo = self.boton(actividad, 'Tiempo de ejecución…', 20, 132, 300, 'tiempo')
        self.recientes = NSPopUpButton.alloc().initWithFrame_pullsDown_(((20, 72), (620, 30)), False)
        self.recientes.setTarget_(self)
        self.recientes.setAction_('cargarReciente:')
        actividad.addSubview_(self.recientes)

        self.etiqueta(editor, 'Código y editor', 20, 235, 380, 25, 16, True)
        self.editor = self.selector(editor, 'Editor', 190, 'editor',
                                    editores_instalados() or {None: 'Ninguno compatible instalado'},
                                    x=170, ancho=220, ancho_etiqueta=145)
        self.fuente = self.selector(editor, 'Fuente de código', 140, 'fuente_tipo',
                                    {'aleatorio': 'React / TypeScript aleatorio', 'directorio': 'Directorio de un proyecto'},
                                    x=170, ancho=220, ancho_etiqueta=145)
        self.directorio = self.boton(editor, 'Elegir directorio…', 20, 87, 250, 'fuente:directorio')
        self.ruta = self.etiqueta(editor, '', 20, 20, 380, 60)

        self.etiqueta(navegador, 'Navegación web', 20, 235, 380, 25, 16, True)
        self.browser = self.selector(navegador, 'Navegador', 185, 'browser',
                                     {None: 'Ninguno', **{clave: clave.capitalize() for clave in NAVEGADORES_VALIDOS}},
                                     x=170, ancho=220, ancho_etiqueta=145)
        self.webs = self.boton(navegador, 'Administrar webs…', 20, 125, 300, 'webs')
        self.web_info = self.etiqueta(navegador, '', 20, 50, 380, 60)
        self.controles_acciones = {}
        for entorno, titulo, opciones, vista in (
                ('editor', 'En el editor', ACCIONES_EDITOR, editor),
                ('web', 'En el navegador', ACCIONES_WEB, navegador)):
            self.etiqueta(vista, 'Acciones', 430, 235, 210, 25, 16, True)
            for indice, (clave, etiqueta) in enumerate(opciones.items()):
                control = NSButton.alloc().initWithFrame_(((430, 190 - indice * 34), (210, 28)))
                control.setButtonType_(3)
                control.setTitle_(etiqueta)
                control.setAccessibilityLabel_(titulo + ': ' + etiqueta)
                control.setIdentifier_(f'accion:{entorno}:{clave}')
                control.setTarget_(self)
                control.setAction_('accion:')
                if clave == 'mover_mouse':
                    control.setToolTip_('Si está desactivado, el click y el scroll requieren el cursor dentro del área segura.')
                vista.addSubview_(control)
                self.controles_acciones[(entorno, clave)] = control
        self.etiqueta(editor, 'Sin «Escribir» no se carga ni reescribe código.', 430, 12, 210, 60)
        self.etiqueta(navegador, 'Sin «Mover mouse», el click y el scroll requieren el cursor dentro del área segura.',
                      430, 12, 210, 80)
        # Reservar la zona inferior para los tiempos sin solapar los controles existentes.
        for vista in (general, actividad, editor, navegador):
            for control in vista.subviews():
                posicion = control.frame().origin
                control.setFrameOrigin_((posicion.x, posicion.y + 100))
        self.controles_tiempo = {}
        for clave, vista, y in (('debounce', actividad, 30), ('editor', editor, 30), ('navegador', navegador, 30)):
            control = self.boton(vista, '', 20, y, 620, 'temporizacion:' + clave)
            self.controles_tiempo[clave] = control
        self.etiqueta(raiz, 'Cambios guardados automáticamente.', 28, 27, 490, 25)
        cerrar = self.boton(raiz, 'Cerrar', 595, 24, 125, 'cerrar')
        cerrar.setKeyEquivalent_('\r')
        self.refrescar()
        self.refrescar_inicio()
        self.ventana.center()

    @objc.python_method
    def etiqueta(self, vista, texto, x, y, ancho, alto, tamano=13, negrita=False):
        campo = NSTextField.wrappingLabelWithString_(texto)
        campo.setFrame_(((x, y), (ancho, alto)))
        campo.setFont_(NSFont.boldSystemFontOfSize_(tamano) if negrita else NSFont.systemFontOfSize_(tamano))
        campo.setTextColor_(NSColor.labelColor() if negrita or tamano >= 14 else NSColor.secondaryLabelColor())
        vista.addSubview_(campo)
        return campo

    @objc.python_method
    def pestana(self, nombre):
        item = NSTabViewItem.alloc().initWithIdentifier_(nombre)
        item.setLabel_(nombre)
        vista = NSView.alloc().initWithFrame_(((0, 0), (660, 278)))
        item.setView_(vista)
        self.tabs.addTabViewItem_(item)
        return vista

    @objc.python_method
    def boton(self, vista, titulo, x, y, ancho, comando):
        boton = NSButton.alloc().initWithFrame_(((x, y), (ancho, 32)))
        boton.setTitle_(titulo)
        boton.setBezelStyle_(1)
        boton.setIdentifier_(comando)
        boton.setTarget_(self)
        boton.setAction_('accion:')
        vista.addSubview_(boton)
        return boton

    @objc.python_method
    def selector(self, vista, titulo, y, clave, opciones, x=245, ancho=395, ancho_etiqueta=220):
        self.etiqueta(vista, titulo, 20, y + 3, ancho_etiqueta, 24, 14)
        selector = NSPopUpButton.alloc().initWithFrame_pullsDown_(((x, y), (ancho, 30)), False)
        selector.addItemsWithTitles_(list(opciones.values()))
        selector.setIdentifier_(clave)
        selector.setAccessibilityLabel_(titulo)
        selector.setTarget_(self)
        selector.setAction_('seleccionar:')
        vista.addSubview_(selector)
        self.opciones[clave] = list(opciones)
        return selector

    @objc.python_method
    def refrescar(self):
        for clave, control in [('modo', self.modo), ('editor', self.editor),
                               ('browser', self.browser), ('fuente_tipo', self.fuente)]:
            valores = self.opciones[clave]
            valor = self.config.get(clave)
            control.selectItemAtIndex_(valores.index(valor) if valor in valores else 0)
        self.recientes.removeAllItems()
        self.recientes.addItemWithTitle_('Cargar una configuración reciente…')
        for registro in self.menu.historial:
            self.recientes.addItemWithTitle_(f"{MODOS_INTERACCION[registro.get('modo', 'ambos')]} · {formatear_tiempo(registro.get('tiempo'))}")
        bloqueada = bool(self.menu.controlador.activo or self.menu.actualizador.consultando or self.menu.saliendo)
        self.recientes.setEnabled_(bool(self.menu.historial) and not bloqueada)
        self.modo.setEnabled_(not bloqueada)
        self.tiempo.setEnabled_(not bloqueada)
        solo_web = self.config.get('modo') == 'web'
        solo_editor = self.config.get('modo') == 'editor'
        for control in (self.fuente, self.directorio):
            control.setEnabled_(not solo_web and not bloqueada)
        self.editor.setEnabled_(not solo_web and not bloqueada and self.opciones['editor'] != [None])
        self.browser.setEnabled_(not solo_editor and not bloqueada)
        self.webs.setEnabled_(not solo_editor and not bloqueada)
        for (entorno, clave), control in self.controles_acciones.items():
            control.setState_(int(acciones_config(self.config, entorno)[clave]))
            control.setEnabled_(not bloqueada and not (solo_web if entorno == 'editor' else solo_editor))
        for clave, control in self.controles_tiempo.items():
            control.setTitle_('Duración del editor…' if clave == 'editor' else
                              TITULOS[clave] + ': ' + texto_tiempo(clave, self.config.get('temporizacion')) + '…')
            control.setEnabled_(not bloqueada and not (
                solo_web if clave.startswith('editor') else solo_editor if clave == 'navegador' else False))
        self.tiempo.setTitle_('Tiempo: ' + formatear_tiempo(self.config.get('tiempo')) + '…')
        self.ruta.setStringValue_('Configurado solo navegador.' if solo_web else
                                 self.config.get('directorio') or 'Se generará código React / TypeScript aleatorio.')
        self.web_info.setStringValue_('Configurado solo editor.' if solo_editor else
                                     f"{len(self.config.get('paginas', []))} webs configuradas. Cada dirección puede tener un nombre.")

    @objc.python_method
    def refrescar_inicio(self):
        try:
            activo, mensaje = estado_inicio()
            self.inicio.setState_(int(activo))
            self.inicio.setEnabled_(inicio_disponible())
            self.inicio_info.setStringValue_(mensaje)
        except Exception as error:
            self.inicio.setEnabled_(False)
            self.inicio_info.setStringValue_(str(error))

    def alternarInicio_(self, sender):
        try:
            establecer_inicio(bool(sender.state()))
        except Exception as error:
            self.menu.aviso('Inicio de sesión', str(error))
        self.refrescar_inicio()

    def seleccionar_(self, sender):
        try:
            clave = str(sender.identifier())
            valor = self.opciones[clave][sender.indexOfSelectedItem()]
            if clave == 'fuente_tipo':
                self.menu.configurar('fuente:' + valor)
            else:
                prefijo = {'modo': 'modo', 'browser': 'browser', 'editor': 'editor'}[clave]
                self.menu.configurar(prefijo + ':' + (valor or ''))
        except Exception as error:
            self.menu.aviso('Configuración', str(error))
        finally:
            self.refrescar()

    def cargarReciente_(self, sender):
        try:
            indice = sender.indexOfSelectedItem() - 1
            if indice >= 0:
                self.menu.configurar(f'historial:{indice}')
        except Exception as error:
            self.menu.aviso('Configuración', str(error))
        finally:
            self.refrescar()
            sender.selectItemAtIndex_(0)

    def accion_(self, sender):
        comando = str(sender.identifier())
        try:
            if comando == 'cerrar':
                self.ventana.close()
            else:
                self.menu.configurar(comando)
                self.refrescar()
        except Exception as error:
            self.menu.aviso('Configuración', str(error))

    @objc.python_method
    def mostrar(self):
        self.refrescar_inicio()
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.ventana.makeKeyAndOrderFront_(None)
