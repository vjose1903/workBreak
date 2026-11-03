import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from editor_catalog import editores_instalados


class EditoresInstaladosTest(unittest.TestCase):
    def test_filtra_instalados_y_prioriza_vscode(self):
        with patch('editor_catalog.binario_editor', side_effect=lambda clave: '/bin/editor' if clave in ('cursor', 'vsCode') else None):
            self.assertEqual(list(editores_instalados()), ['vsCode', 'cursor'])
        with patch('editor_catalog.binario_editor', return_value=None):
            self.assertEqual(editores_instalados(), {})
