"""Copia materializada del portapapeles; nunca conserva handles prestados."""
import sys
import struct


def version():
    if sys.platform == 'darwin':
        from AppKit import NSPasteboard
        return int(NSPasteboard.generalPasteboard().changeCount())
    if sys.platform == 'win32':
        import ctypes
        return int(ctypes.windll.user32.GetClipboardSequenceNumber())
    raise RuntimeError('No se puede proteger el portapapeles en este sistema')


def capturar():
    if sys.platform == 'darwin':
        from AppKit import NSPasteboard
        portapapeles = NSPasteboard.generalPasteboard()
        revision = version()
        items = []
        for item in portapapeles.pasteboardItems() or []:
            formatos = []
            for tipo in item.types():
                datos = item.dataForType_(tipo)
                if datos is None:
                    raise RuntimeError('No se pudo conservar un formato del portapapeles')
                formatos.append((str(tipo), bytes(datos)))
            items.append(formatos)
        if revision != version():
            raise RuntimeError('El portapapeles cambió mientras se guardaba')
        return {'version': revision, 'items': items}
    if sys.platform == 'win32':
        import win32clipboard as clipboard
        clipboard.OpenClipboard()
        try:
            revision = version()
            formatos, codigo = [], 0
            while True:
                codigo = clipboard.EnumClipboardFormats(codigo)
                if not codigo:
                    break
                formatos.append(codigo)
            items = []
            for codigo in formatos:
                # Windows sintetiza el bitmap a partir del DIB, que sí se puede copiar.
                if codigo == 2 and (8 in formatos or 17 in formatos):
                    continue
                datos = clipboard.GetClipboardData(codigo)
                if codigo == 15:  # CF_HDROP: reconstruir DROPFILES con sus rutas Unicode.
                    datos = struct.pack('<IiiII', 20, 0, 0, 0, 1) + ('\0'.join(datos) + '\0\0').encode('utf-16-le')
                if not isinstance(datos, (bytes, str)):
                    raise RuntimeError(f'No se puede conservar el formato {codigo}; no se modificó el portapapeles')
                items.append((codigo, datos))
            return {'version': revision, 'items': items}
        finally:
            clipboard.CloseClipboard()
    raise RuntimeError('No se puede proteger el portapapeles en este sistema')


def restaurar(estado, esperada=None):
    if sys.platform == 'darwin':
        from AppKit import NSPasteboard, NSPasteboardItem
        from Foundation import NSData
        items = []
        for formatos in estado['items']:
            item = NSPasteboardItem.alloc().init()
            for tipo, datos in formatos:
                if not item.setData_forType_(NSData.dataWithBytes_length_(datos, len(datos)), tipo):
                    raise RuntimeError('No se pudo preparar la restauración del portapapeles')
            items.append(item)
        portapapeles = NSPasteboard.generalPasteboard()
        if esperada is not None and version() != esperada:
            return False
        portapapeles.clearContents()
        if items and not portapapeles.writeObjects_(items):
            raise RuntimeError('El sistema rechazó la restauración del portapapeles')
        return True
    if sys.platform == 'win32':
        import win32clipboard as clipboard
        clipboard.OpenClipboard()
        try:
            if esperada is not None and version() != esperada:
                return False
            clipboard.EmptyClipboard()
            for codigo, datos in estado['items']:
                clipboard.SetClipboardData(codigo, datos)
            return True
        finally:
            clipboard.CloseClipboard()
    raise RuntimeError('No se puede restaurar el portapapeles en este sistema')
