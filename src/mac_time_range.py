"""Rango de tiempo compacto con dos extremos y edición numérica accesible."""
import objc
from AppKit import (NSControl, NSView, NSBezierPath, NSColor, NSFont, NSTextField,
                    NSEventMaskLeftMouseDragged, NSEventMaskLeftMouseUp, NSAccessibilitySliderRole)
from timing_config import temporizacion_config, PERMITEN_CERO, MAX_SEGUNDOS


class SliderDoble(NSControl):
    @objc.python_method
    def preparar(self, valores, minimo, maximo, paso):
        self.valores = list(valores)
        self.minimo, self.maximo, self.paso = minimo, maximo, paso
        self.extremo = 0
        self.setAccessibilityRole_(NSAccessibilitySliderRole)
        self.setAccessibilityLabel_('Rango de tiempo; flechas izquierda y derecha ajustan, arriba y abajo eligen extremo')

    def acceptsFirstResponder(self):
        return True

    @objc.python_method
    def posicion(self, valor):
        return 12 + (self.bounds().size.width - 24) * (valor - self.minimo) / (self.maximo - self.minimo)

    def drawRect_(self, _rect):
        ancho = self.bounds().size.width
        NSColor.separatorColor().setFill()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(((12, 13), (ancho - 24, 4)), 2, 2).fill()
        izquierda, derecha = map(self.posicion, self.valores)
        NSColor.controlAccentColor().setFill()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(((izquierda, 13), (max(1, derecha - izquierda), 4)), 2, 2).fill()
        for indice, x in enumerate((izquierda, derecha)):
            circulo = NSBezierPath.bezierPathWithOvalInRect_(((x - 7, 8), (14, 14)))
            NSColor.whiteColor().setFill()
            circulo.fill()
            (NSColor.controlAccentColor() if indice == self.extremo else NSColor.secondaryLabelColor()).setStroke()
            circulo.setLineWidth_(2)
            circulo.stroke()

    @objc.python_method
    def cambiar(self, valor):
        valor = min(self.maximo, max(self.minimo, round(valor / self.paso) * self.paso))
        if self.extremo == 0:
            self.valores[0] = min(valor, self.valores[1])
        else:
            self.valores[1] = max(valor, self.valores[0])
        self.setAccessibilityValue_(f'{self.valores[0]:g} a {self.valores[1]:g} segundos')
        self.setNeedsDisplay_(True)
        self.sendAction_to_(self.action(), self.target())

    def mouseDown_(self, evento):
        self.window().makeFirstResponder_(self)
        punto = self.convertPoint_fromView_(evento.locationInWindow(), None)
        distancias = [abs(punto.x - self.posicion(v)) for v in self.valores]
        self.extremo = 0 if distancias[0] < distancias[1] else 1
        while True:
            punto = self.convertPoint_fromView_(evento.locationInWindow(), None)
            self.cambiar(self.minimo + (punto.x - 12) / (self.bounds().size.width - 24) * (self.maximo - self.minimo))
            evento = self.window().nextEventMatchingMask_(NSEventMaskLeftMouseDragged | NSEventMaskLeftMouseUp)
            if evento is None or evento.type() == 2:  # NSEventTypeLeftMouseUp
                break

    def keyDown_(self, evento):
        codigo = evento.keyCode()
        if codigo in (125, 126):
            self.extremo = 0 if codigo == 125 else 1
            self.setNeedsDisplay_(True)
        elif codigo in (123, 124):
            self.cambiar(self.valores[self.extremo] + (-1 if codigo == 123 else 1) * self.paso)
        else:
            objc.super(SliderDoble, self).keyDown_(evento)


class RangoTiempo(NSView):
    @objc.python_method
    def preparar(self, clave, titulo, valores):
        self.clave = clave
        ancho = self.bounds().size.width
        etiqueta = NSTextField.labelWithString_(titulo)
        etiqueta.setFont_(NSFont.boldSystemFontOfSize_(13))
        etiqueta.setFrame_(((0, 61), (ancho, 20)))
        self.addSubview_(etiqueta)
        paso = 0.01 if clave.endswith('caracter') else 0.1 if valores[1] < 10 else 1
        if valores[0] > 0:
            paso = min(paso, valores[0])
        self.slider = SliderDoble.alloc().initWithFrame_(((0, 27), (ancho, 30)))
        self.slider.preparar(valores, 0 if clave in PERMITEN_CERO else paso, min(MAX_SEGUNDOS, max(valores[1] * 2, paso * 100)), paso)
        self.slider.setTarget_(self)
        self.slider.setAction_('deslizar:')
        self.addSubview_(self.slider)
        self.campos = []
        for indice, (nombre, x) in enumerate((('Mín.', 0), ('Máx.', ancho - 142))):
            label = NSTextField.labelWithString_(nombre)
            label.setFrame_(((x, 3), (35, 20)))
            label.setTextColor_(NSColor.secondaryLabelColor())
            self.addSubview_(label)
            campo = NSTextField.alloc().initWithFrame_(((x + 38, 0), (80, 24)))
            campo.setStringValue_(f'{valores[indice]:g}')
            campo.setAlignment_(2)
            campo.setAccessibilityLabel_(titulo + ': ' + nombre + ' en segundos')
            campo.setDelegate_(self)
            self.addSubview_(campo)
            self.campos.append(campo)
            unidad = NSTextField.labelWithString_('s')
            unidad.setFrame_(((x + 122, 3), (20, 20)))
            unidad.setTextColor_(NSColor.secondaryLabelColor())
            self.addSubview_(unidad)

    def deslizar_(self, _sender):
        for campo, valor in zip(self.campos, self.slider.valores):
            campo.setStringValue_(f'{valor:g}')

    @objc.python_method
    def leer(self):
        valores = [float(str(c.stringValue()).strip().replace(',', '.')) for c in self.campos]
        return temporizacion_config({self.clave: valores})[self.clave]

    def controlTextDidChange_(self, _notificacion):
        try:
            valores = self.leer()
        except ValueError:
            return
        self.slider.valores = valores
        if self.clave not in PERMITEN_CERO:
            self.slider.paso = min(self.slider.paso, valores[0])
            self.slider.minimo = min(self.slider.minimo, valores[0])
        self.slider.maximo = min(MAX_SEGUNDOS, max(self.slider.maximo, valores[1] * 1.1))
        self.slider.setNeedsDisplay_(True)
