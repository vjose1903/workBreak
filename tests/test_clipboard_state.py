import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
import clipboard_state


class Item:
    def __init__(self, formatos=None):
        self.formatos = dict(formatos or {})

    def init(self):
        return self

    def types(self):
        return list(self.formatos)

    def dataForType_(self, tipo):
        return self.formatos[tipo]

    def setData_forType_(self, datos, tipo):
        self.formatos[tipo] = bytes(datos)
        return True


class Portapapeles:
    def __init__(self, items):
        self.items = items
        self.revision = 1

    def pasteboardItems(self):
        return self.items

    def changeCount(self):
        return self.revision

    def clearContents(self):
        self.items = []
        self.revision += 1

    def writeObjects_(self, items):
        self.items = list(items)
        self.revision += 1
        return True


class ClipboardStateTest(unittest.TestCase):
    def mac(self, portapapeles):
        return patch.dict(sys.modules, {
            'AppKit': SimpleNamespace(NSPasteboard=SimpleNamespace(generalPasteboard=lambda: portapapeles),
                                     NSPasteboardItem=SimpleNamespace(alloc=Item)),
            'Foundation': SimpleNamespace(NSData=SimpleNamespace(dataWithBytes_length_=lambda datos, largo: bytes(datos[:largo]))),
        })

    def test_mac_restaura_imagen_archivos_rtf_y_varios_items(self):
        originales = [Item({'public.png': b'\x89PNG\x00\xff', 'public.tiff': b'tiff'}),
                      Item({'public.file-url': b'file:///tmp/archivo'}),
                      Item({'public.utf8-plain-text': b'hola', 'public.rtf': b'{\\rtf1 hola}'})]
        portapapeles = Portapapeles(originales)
        with patch('clipboard_state.sys.platform', 'darwin'), self.mac(portapapeles):
            estado = clipboard_state.capturar()
            portapapeles.clearContents()
            portapapeles.writeObjects_([Item({'public.utf8-plain-text': b'bot'})])
            self.assertTrue(clipboard_state.restaurar(estado, esperada=3))
        self.assertEqual([i.formatos for i in portapapeles.items], [i.formatos for i in originales])

    def test_mac_no_reemplaza_un_cambio_externo_con_el_mismo_texto(self):
        portapapeles = Portapapeles([Item({'public.rtf': b'usuario'})])
        with patch('clipboard_state.sys.platform', 'darwin'), self.mac(portapapeles):
            self.assertFalse(clipboard_state.restaurar({'items': []}, esperada=0))
        self.assertEqual(portapapeles.items[0].formatos, {'public.rtf': b'usuario'})

    def test_mac_formato_no_materializable_cancela_sin_borrar(self):
        portapapeles = Portapapeles([Item({'public.png': None})])
        with patch('clipboard_state.sys.platform', 'darwin'), self.mac(portapapeles):
            with self.assertRaises(RuntimeError):
                clipboard_state.capturar()
        self.assertEqual(portapapeles.revision, 1)

    def test_mac_rechazo_de_escritura_propaga_el_error(self):
        portapapeles = Portapapeles([])
        with patch('clipboard_state.sys.platform', 'darwin'), self.mac(portapapeles), \
                patch.object(portapapeles, 'writeObjects_', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'rechazó'):
                clipboard_state.restaurar({'items': [[('public.png', b'imagen')]]})

    def test_windows_conserva_imagen_y_texto_sin_guardar_handles(self):
        clipboard = MagicMock()
        clipboard.EnumClipboardFormats.side_effect = [8, 2, 13, 0]
        clipboard.GetClipboardData.side_effect = lambda codigo: {8: b'imagen DIB', 13: 'texto'}[codigo]
        with patch('clipboard_state.sys.platform', 'win32'), \
                patch('clipboard_state.version', return_value=1), \
                patch.dict(sys.modules, {'win32clipboard': clipboard}):
            estado = clipboard_state.capturar()
            self.assertTrue(clipboard_state.restaurar(estado, esperada=1))
        self.assertEqual(estado['items'], [(8, b'imagen DIB'), (13, 'texto')])
        self.assertEqual(clipboard.SetClipboardData.call_args_list,
                         [unittest.mock.call(8, b'imagen DIB'), unittest.mock.call(13, 'texto')])

    def test_windows_archivos_se_materializan_como_dropfiles(self):
        clipboard = MagicMock()
        clipboard.EnumClipboardFormats.side_effect = [15, 0]
        clipboard.GetClipboardData.return_value = ('C:\\foto.png', 'C:\\niño.txt')
        with patch('clipboard_state.sys.platform', 'win32'), \
                patch('clipboard_state.version', return_value=1), \
                patch.dict(sys.modules, {'win32clipboard': clipboard}):
            estado = clipboard_state.capturar()
        datos = estado['items'][0][1]
        self.assertEqual(datos[20:].decode('utf-16-le'), 'C:\\foto.png\0C:\\niño.txt\0\0')

    def test_windows_formato_con_handle_cancela_antes_de_borrar(self):
        clipboard = MagicMock()
        clipboard.EnumClipboardFormats.side_effect = [14, 0]
        clipboard.GetClipboardData.return_value = 12345
        with patch('clipboard_state.sys.platform', 'win32'), \
                patch('clipboard_state.version', return_value=1), \
                patch.dict(sys.modules, {'win32clipboard': clipboard}):
            with self.assertRaises(RuntimeError):
                clipboard_state.capturar()
        clipboard.EmptyClipboard.assert_not_called()
        clipboard.CloseClipboard.assert_called_once()
