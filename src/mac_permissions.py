"""Comprobaciones sin solicitar permisos ni iniciar automatización."""

PERMISOS = {
    'accesibilidad': ('Accesibilidad', 'Privacy_Accessibility'),
    'entrada': ('Monitorización de entrada', 'Privacy_ListenEvent'),
}


def permisos_faltantes():
    import Quartz
    from mac_accessibility import _api
    faltantes = []
    if not _api()['AXIsProcessTrusted']():
        faltantes.append('accesibilidad')
    if not Quartz.CGPreflightListenEventAccess() and not _puede_observar_teclado(Quartz):
        faltantes.append('entrada')
    return faltantes


def _puede_observar_teclado(quartz):
    # El preflight puede denegar mientras Accesibilidad permite crear el observador.
    # Probar la misma ubicación y modalidad del monitor, sin consumir ni guardar teclas.
    tipos = (quartz.kCGEventKeyDown, quartz.kCGEventKeyUp, quartz.kCGEventFlagsChanged)
    callback = lambda _proxy, _tipo, evento, _contexto: evento
    tap = quartz.CGEventTapCreate(
        quartz.kCGHIDEventTap, quartz.kCGHeadInsertEventTap,
        quartz.kCGEventTapOptionListenOnly, sum(1 << tipo for tipo in tipos), callback, None)
    if tap is None:
        return False
    try:
        return bool(quartz.CGEventTapIsEnabled(tap))
    finally:
        quartz.CGEventTapEnable(tap, False)
        quartz.CFMachPortInvalidate(tap)


def abrir_configuracion(permiso):
    from AppKit import NSWorkspace
    from Foundation import NSURL
    panel = PERMISOS[permiso][1]
    workspace = NSWorkspace.sharedWorkspace()
    if workspace.openURL_(NSURL.URLWithString_(
            'x-apple.systempreferences:com.apple.preference.security?' + panel)):
        return True
    return bool(workspace.openURL_(NSURL.URLWithString_(
        'x-apple.systempreferences:com.apple.preference.security')))
