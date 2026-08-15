import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from code_generator import CodeGenerator
from code_source import RealProjectSource


class RealProjectSourceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = self.tmp.name
        src = os.path.join(self.raiz, "src")
        os.makedirs(src, exist_ok=True)
        with open(os.path.join(src, "App.tsx"), "w") as f:
            f.write("import React from 'react';\nexport const App = () => <div>Hola</div>;\n")
        with open(os.path.join(src, "util.ts"), "w") as f:
            f.write("export const x = 1;\n")
        node_modules = os.path.join(self.raiz, "node_modules")
        os.makedirs(node_modules, exist_ok=True)
        with open(os.path.join(node_modules, "lib.tsx"), "w") as f:
            f.write("export const y = 2;\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_escanear_encuentra_react_y_excluye_node_modules(self):
        fuente = RealProjectSource(self.raiz)
        nombres = [p.name for p in fuente.archivos]
        self.assertIn("App.tsx", nombres)
        self.assertIn("util.ts", nombres)
        self.assertNotIn("lib.tsx", nombres)

    def test_obtener_codigo_devuelve_contenido_real(self):
        fuente = RealProjectSource(self.raiz)
        codigo = fuente.obtener_codigo()
        self.assertTrue(codigo.strip())
        self.assertIn("export", codigo)

    def test_directorio_invalido_lanza_error(self):
        with self.assertRaises(ValueError):
            RealProjectSource("/ruta/que/no/existe-xyz")

    def test_directorio_sin_archivos_lanza_error(self):
        with tempfile.TemporaryDirectory() as vacio:
            with self.assertRaises(ValueError):
                RealProjectSource(vacio)


class FuenteComunTest(unittest.TestCase):
    def test_generador_aleatorio_tiene_obtener_codigo(self):
        codigo = CodeGenerator().obtener_codigo()
        self.assertIsInstance(codigo, str)
        self.assertTrue(codigo)


if __name__ == "__main__":
    unittest.main()
