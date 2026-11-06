"""Accesibilidad de macOS desde el propio proceso, sin System Events."""
from functools import lru_cache


class PermisoAccesibilidad(ValueError):
    pass


@lru_cache(maxsize=1)
def _api():
    import objc
    bundle = objc.loadBundle('WorkBreakAX', {},
                            bundle_path='/System/Library/Frameworks/ApplicationServices.framework')
    funciones = {}
    objc.loadBundleFunctions(bundle, funciones, [
        ('AXUIElementGetTypeID', b'Q'), ('AXValueGetTypeID', b'Q'),
        ('AXIsProcessTrusted', b'Z'),
    ])
    objc.registerCFSignature('AXUIElementRef', b'^{__AXUIElement=}',
                             funciones['AXUIElementGetTypeID']())
    objc.registerCFSignature('AXValueRef', b'^{__AXValue=}', funciones['AXValueGetTypeID']())
    objc.loadBundleFunctions(bundle, funciones, [
        ('AXUIElementCreateApplication', b'^{__AXUIElement=}i', '',
         {'retval': {'already_cfretained': True}}),
        ('AXUIElementCopyAttributeValue', b'i^{__AXUIElement=}@o^@', '',
         {'arguments': {2: {'already_cfretained': True}}}),
        ('AXValueGetValue', b'Z^{__AXValue=}io^{CGPoint=dd}'),
    ])
    return funciones


def atributo(elemento, nombre, opcional=False):
    codigo, valor = _api()['AXUIElementCopyAttributeValue'](elemento, nombre, None)
    if codigo == 0:
        return valor
    if opcional and codigo in (-25205, -25212):
        return None
    raise ValueError(f'No se pudo leer {nombre}: error de accesibilidad {codigo}')


def aplicacion(nombre):
    from AppKit import NSWorkspace
    from pathlib import Path
    _actualizar_workspace()
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        url = app.bundleURL()
        if (app.bundleIdentifier() == nombre or app.localizedName() == nombre
                or (url and Path(str(url.path())).stem == nombre)):
            return app
    raise ValueError(f'La aplicación no está abierta: {nombre}')


def elemento_aplicacion(nombre):
    api = _api()
    if not api['AXIsProcessTrusted']():
        raise PermisoAccesibilidad(
            'macOS no reconoce Accesibilidad para este proceso de WB; '
            'el permiso visible puede corresponder a otra compilación de la aplicación')
    return api['AXUIElementCreateApplication'](aplicacion(nombre).processIdentifier())


def _actualizar_workspace():
    # AppKit retiene sus propiedades hasta procesar el run loop, también en el worker sin UI.
    from Foundation import NSRunLoop, NSDate
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.001))


def pid_aplicacion_al_frente():
    from AppKit import NSWorkspace
    _actualizar_workspace()
    frente = NSWorkspace.sharedWorkspace().frontmostApplication()
    return frente.processIdentifier() if frente is not None else None


def documento_editor(bundle):
    pid = aplicacion(bundle).processIdentifier()

    def comprobar_foco():
        if pid_aplicacion_al_frente() != pid:
            raise ValueError('El editor no está al frente')

    comprobar_foco()
    ventana = atributo(elemento_aplicacion(bundle), 'AXFocusedWindow')
    documento = atributo(ventana, 'AXDocument', opcional=True)
    comprobar_foco()
    return str(documento or '')


def rectangulo_aplicacion(nombre):
    ventana = atributo(elemento_aplicacion(nombre), 'AXFocusedWindow')
    valores = []
    for nombre_atributo, tipo in (('AXPosition', 1), ('AXSize', 2)):
        valor = atributo(ventana, nombre_atributo)
        valido, punto = _api()['AXValueGetValue'](valor, tipo, None)
        if not valido:
            raise ValueError(f'No se pudo interpretar {nombre_atributo}')
        valores.extend((round(punto.x), round(punto.y)))
    return tuple(valores)


def identidad_ventana_aplicacion(nombre):
    """Identifica la ventana enfocada por Accesibilidad, sin confundir emergentes de Quartz."""
    import Quartz as q
    pid = aplicacion(nombre).processIdentifier()
    if pid_aplicacion_al_frente() != pid:
        return None
    x, y, ancho, alto = rectangulo_aplicacion(nombre)
    ventanas = q.CGWindowListCopyWindowInfo(q.kCGWindowListOptionOnScreenOnly, q.kCGNullWindowID) or []
    for ventana in ventanas:
        if ventana.get('kCGWindowOwnerPID') != pid or ventana.get('kCGWindowLayer') != 0:
            continue
        limites = ventana.get('kCGWindowBounds', {})
        if all(abs(limites.get(clave, float('inf')) - valor) <= 1
               for clave, valor in zip(('X', 'Y', 'Width', 'Height'), (x, y, ancho, alto))):
            if pid_aplicacion_al_frente() == pid:
                return ventana.get('kCGWindowNumber')
            return None
    return None


def activar_aplicacion(nombre):
    from AppKit import NSApplicationActivateIgnoringOtherApps
    return bool(aplicacion(nombre).activateWithOptions_(NSApplicationActivateIgnoringOtherApps))


def leer_atajo(bundle, coincide):
    barra = atributo(elemento_aplicacion(bundle), 'AXMenuBar')
    encontrados = []
    for entrada in atributo(barra, 'AXChildren') or []:
        if atributo(entrada, 'AXTitle', opcional=True) not in ('Go', 'Ir'):
            continue
        for menu in atributo(entrada, 'AXChildren') or []:
            for item in atributo(menu, 'AXChildren') or []:
                if coincide(str(atributo(item, 'AXTitle', opcional=True) or '')):
                    encontrados.append((str(atributo(item, 'AXMenuItemCmdChar') or ''),
                                        int(atributo(item, 'AXMenuItemCmdModifiers'))))
    if len(encontrados) != 1:
        raise ValueError('No se pudo identificar un único comando Ir a línea en el menú')
    return encontrados[0]
