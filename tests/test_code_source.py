import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from code_generator import CodeGenerator
from code_source import RealProjectSource
from user_activity import DetencionSolicitada


class RealProjectSourceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = self.tmp.name
        src = os.path.join(self.raiz, "src")
        os.makedirs(src, exist_ok=True)
        with open(os.path.join(src, "App.tsx"), "w") as f:
            f.write("import React from 'react';\n")
            for i in range(30):
                f.write(f"export const item{i} = {i};\n")
            f.write("export const App = () => <div>Hola</div>;\n")
        with open(os.path.join(src, "util.ts"), "w") as f:
            for i in range(25):
                f.write(f"export const valor{i} = {i};\n")
        with open(os.path.join(src, "corto.tsx"), "w") as f:
            f.write("export const corto = 1;\n")
        node_modules = os.path.join(self.raiz, "node_modules")
        os.makedirs(node_modules, exist_ok=True)
        with open(os.path.join(node_modules, "lib.tsx"), "w") as f:
            for i in range(30):
                f.write(f"export const y{i} = {i};\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_escanear_encuentra_react_y_excluye_node_modules(self):
        fuente = RealProjectSource(self.raiz)
        nombres = [p.name for p in fuente.archivos]
        self.assertIn("App.tsx", nombres)
        self.assertIn("util.ts", nombres)
        self.assertNotIn("lib.tsx", nombres)
        self.assertNotIn("corto.tsx", nombres)

    def test_la_interfaz_puede_cancelar_el_escaneo(self):
        def cancelar():
            raise DetencionSolicitada()
        with self.assertRaises(DetencionSolicitada):
            RealProjectSource(self.raiz, comprobar_cancelacion=cancelar)

    def test_obtener_codigo_devuelve_contenido_real(self):
        fuente = RealProjectSource(self.raiz)
        codigo = fuente.obtener_codigo()
        self.assertTrue(codigo.strip())
        self.assertIn("export", codigo)

    def test_nombre_archivo_es_el_del_ultimo_codigo_entregado(self):
        fuente = RealProjectSource(self.raiz)
        self.assertIsNone(fuente.nombre_archivo)
        codigo = fuente.obtener_codigo()
        self.assertIn(fuente.nombre_archivo, ('App.tsx', 'util.ts'))
        self.assertEqual(codigo.splitlines()[0].startswith('import'), fuente.nombre_archivo == 'App.tsx')

    def test_no_repite_archivos_consecutivos(self):
        fuente = RealProjectSource(self.raiz)
        anterior = fuente.obtener_codigo()
        for _ in range(6):
            actual = fuente.obtener_codigo()
            self.assertNotEqual(actual, anterior)
            anterior = actual

    def test_directorio_con_un_archivo_sigue_funcionando(self):
        fuente = RealProjectSource(self.raiz)
        fuente.archivos = fuente.archivos[:1]
        self.assertEqual(fuente.obtener_codigo(), fuente.obtener_codigo())

    def test_si_otro_archivo_desaparece_reutiliza_el_anterior(self):
        fuente = RealProjectSource(self.raiz)
        codigo = fuente.obtener_codigo()
        for archivo in fuente.archivos:
            if archivo != fuente._ultimo_archivo:
                archivo.unlink()
        self.assertEqual(fuente.obtener_codigo(), codigo)

    def test_si_no_queda_fuente_lanza_error_en_lugar_de_codigo_falso(self):
        fuente = RealProjectSource(self.raiz)
        for archivo in fuente.archivos:
            archivo.unlink()
        with self.assertRaises(ValueError):
            fuente.obtener_codigo()

    def test_revalida_archivos_modificados_despues_del_escaneo(self):
        fuente = RealProjectSource(self.raiz)
        for archivo in fuente.archivos:
            archivo.write_text('archivo ahora vacío de código\n')
        with self.assertRaises(ValueError):
            fuente.obtener_codigo()

    def test_directorio_invalido_lanza_error(self):
        with self.assertRaises(ValueError):
            RealProjectSource("/ruta/que/no/existe-xyz")

    def test_directorio_sin_archivos_lanza_error(self):
        with tempfile.TemporaryDirectory() as vacio:
            with self.assertRaises(ValueError):
                RealProjectSource(vacio)

    def test_archivo_mas_de_400_lineas_excluido(self):
        with tempfile.TemporaryDirectory() as dir_proyecto:
            with open(os.path.join(dir_proyecto, "grande.tsx"), "w") as f:
                for i in range(500):
                    f.write(f"export const v{i} = {i};\n")
            with self.assertRaises(ValueError):
                RealProjectSource(dir_proyecto)


class FuenteComunTest(unittest.TestCase):
    def test_generador_aleatorio_tiene_obtener_codigo(self):
        codigo = CodeGenerator().obtener_codigo()
        self.assertIsInstance(codigo, str)
        self.assertTrue(codigo)


if __name__ == "__main__":
    unittest.main()
