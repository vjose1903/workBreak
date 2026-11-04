"""Lectura del atajo efectivo desde el menú del editor, sin enviar teclado ni clicks."""
import ctypes
import re
import sys
import time

from mac_accessibility import leer_atajo, PermisoAccesibilidad


TITULOS_IR_LINEA = (
    'Go to Line/Column', 'Go to Line', 'Ir a línea/columna',
    'Ir a la línea/columna', 'Ir a línea', 'Ir a la línea',
)


def _es_ir_linea(titulo):
    titulo = titulo.split('\t', 1)[0].rstrip('.… ').casefold()
    return titulo in {t.casefold() for t in TITULOS_IR_LINEA}


def resolver_atajo_mac(bundle, esperar):
    # Esperar a que el editor termine de cargar sus atajos y personalizaciones.
    inicio = desde = time.monotonic()
    anterior = None
    ultimo_error = ''
    while True:
        try:
            actual = leer_atajo(bundle, _es_ir_linea)
            ultimo_error = ''
        except PermisoAccesibilidad:
            raise
        except ValueError as error:
            actual = None
            ultimo_error = str(error)
        ahora = time.monotonic()
        if actual != anterior:
            anterior, desde = actual, ahora
        if actual and ahora - inicio >= 5 and ahora - desde >= 2:
            break
        if ahora - inicio >= 15:
            raise ValueError(ultimo_error or 'El atajo Ir a línea no se estabilizó')
        esperar(0.25)
    caracter, mascara = actual
    if len(caracter) != 1:
        raise ValueError('El editor no expone un atajo simple para Ir a línea')
    letra = caracter.lower()
    if mascara < 0 or mascara > 15:
        raise ValueError('El atajo de Ir a línea usa modificadores no compatibles')
    from mac_keyboard import MacKeyboard
    if letra not in MacKeyboard.KEY_CODES:
        raise ValueError('La tecla de Ir a línea no es compatible: ' + letra)
    teclas = [nombre for bit, nombre in ((1, 'shift'), (2, 'option'), (4, 'ctrl')) if mascara & bit]
    if not mascara & 8:
        teclas.append('command')
    if not teclas:
        raise ValueError('Ir a línea debe tener un modificador para evitar insertar texto')
    return tuple(teclas + [letra])


def resolver_atajo_windows():
    # Los menús nativos exponen el acelerador después de una tabulación.
    from ctypes import wintypes as w
    usuario = ctypes.WinDLL('user32', use_last_error=True)
    usuario.GetForegroundWindow.restype = w.HWND
    usuario.GetMenu.argtypes = [w.HWND]
    usuario.GetMenu.restype = w.HMENU
    usuario.GetSubMenu.argtypes = [w.HMENU, ctypes.c_int]
    usuario.GetSubMenu.restype = w.HMENU
    usuario.GetMenuItemCount.argtypes = [w.HMENU]
    usuario.GetMenuStringW.argtypes = [w.HMENU, w.UINT, w.LPWSTR, ctypes.c_int, w.UINT]
    encontrados = []

    def recorrer(menu, profundidad=0):
        if not menu or profundidad > 5:
            return
        for indice in range(usuario.GetMenuItemCount(menu)):
            texto = ctypes.create_unicode_buffer(1024)
            usuario.GetMenuStringW(menu, indice, texto, len(texto), 0x400)
            titulo = texto.value.replace('&', '')
            if _es_ir_linea(titulo):
                encontrados.append(titulo)
            recorrer(usuario.GetSubMenu(menu, indice), profundidad + 1)

    recorrer(usuario.GetMenu(usuario.GetForegroundWindow()))
    if len(encontrados) != 1 or '\t' not in encontrados[0]:
        raise ValueError('El editor no expone el atajo Ir a línea en un menú nativo; no se enviará un atajo supuesto')
    atajo = encontrados[0].split('\t', 1)[1].lower()
    if not re.fullmatch(r'(?:(?:ctrl|alt|shift)\+)+[a-z0-9]', atajo):
        raise ValueError('El atajo de Ir a línea no es una combinación simple compatible')
    return tuple(atajo.split('+'))


def resolver_atajo(editor, esperar):
    if sys.platform == 'darwin':
        from editor_catalog import EDITORES
        return resolver_atajo_mac(EDITORES[editor]['bundle'], esperar)
    if sys.platform == 'win32':
        return resolver_atajo_windows()
    raise ValueError('La detección del atajo requiere macOS o Windows')
