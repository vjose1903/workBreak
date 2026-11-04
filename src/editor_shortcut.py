"""Lectura del atajo efectivo desde el menú del editor, sin enviar teclado ni clicks."""
import ctypes
import re
import sys


TITULOS_IR_LINEA = (
    'Go to Line/Column', 'Go to Line', 'Ir a línea/columna',
    'Ir a la línea/columna', 'Ir a línea', 'Ir a la línea',
)


def _es_ir_linea(titulo):
    titulo = titulo.split('\t', 1)[0].rstrip('.… ').casefold()
    return titulo in {t.casefold() for t in TITULOS_IR_LINEA}


def resolver_atajo_mac(bundle, ejecutar):
    # El menú lo resuelve el propio editor: incluye perfil, extensiones y personalizaciones.
    titulos = ', '.join('"' + t + '"' for t in TITULOS_IR_LINEA)
    script = '''on leerAtajo(bundleId)
        tell application "System Events"
            tell (first application process whose bundle identifier is bundleId)
                set barra to first menu bar item of menu bar 1 whose name is "Go" or name is "Ir"
                set titulos to name of every menu item of menu 1 of barra
                set indice to 0
                set coincidencias to 0
                repeat with n from 1 to count titulos
                    set titulo to item n of titulos
                    if titulo is not missing value then
                        repeat with esperado in {TITULOS}
                            if titulo is (esperado as text) or titulo is ((esperado as text) & "…") or titulo is ((esperado as text) & "...") then
                                set indice to n
                                set coincidencias to coincidencias + 1
                            end if
                        end repeat
                    end if
                end repeat
                if coincidencias is not 1 then error "No se pudo identificar un único comando Ir a línea en el menú"
                set entrada to menu item indice of menu 1 of barra
                set letra to value of attribute "AXMenuItemCmdChar" of entrada
                set modificadores to value of attribute "AXMenuItemCmdModifiers" of entrada
                if letra is missing value or letra is "" then error "Ir a línea no tiene un atajo simple disponible"
                return letra & tab & (modificadores as text)
            end tell
        end tell
    end leerAtajo
    on run argv
        set inicio to current date
        set desde to inicio
        set anterior to ""
        set ultimoError to ""
        set ultimoCodigo to 0
        repeat
            set actual to ""
            try
                set actual to my leerAtajo(item 1 of argv)
                set ultimoError to ""
                set ultimoCodigo to 0
            on error mensaje number codigo
                set ultimoError to mensaje
                set ultimoCodigo to codigo
                if codigo is -1743 or codigo is -25211 or codigo is -10004 then
                    error ("macOS rechazó el acceso al menú del editor: " & mensaje & ". Revisa Accesibilidad y Automatización de WorkBreak en Privacidad y seguridad.") number codigo
                end if
            end try
            set ahora to current date
            if actual is not anterior then
                set desde to ahora
                set anterior to actual
            end if
            if actual is not "" and (ahora - inicio) ≥ 5 and (ahora - desde) ≥ 2 then return actual
            if (ahora - inicio) ≥ 15 then
                if ultimoError is not "" then
                    error ("No se pudo consultar Ir a línea. Último error (" & ultimoCodigo & "): " & ultimoError)
                end if
                error ("El atajo Ir a línea no se estabilizó. Último valor leído: " & anterior)
            end if
            delay 0.25
        end repeat
    end run'''.replace('TITULOS', titulos)
    resultado = ejecutar(['osascript', '-e', script, bundle], capture_output=True,
                         text=True, check=True, timeout=20)
    partes = resultado.stdout.strip().split('\t')
    if len(partes) != 2 or len(partes[0]) != 1:
        raise ValueError('El editor no expone un atajo simple para Ir a línea')
    letra, mascara = partes[0].lower(), int(partes[1])
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


def resolver_atajo(editor, ejecutar):
    if sys.platform == 'darwin':
        from editor_catalog import EDITORES
        return resolver_atajo_mac(EDITORES[editor]['bundle'], ejecutar)
    if sys.platform == 'win32':
        return resolver_atajo_windows()
    raise ValueError('La detección del atajo requiere macOS o Windows')
