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
    if not Quartz.CGPreflightListenEventAccess():
        faltantes.append('entrada')
    return faltantes


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
