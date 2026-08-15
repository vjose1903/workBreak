import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from code_generator import CodeGenerator


def _quitar_strings(codigo):
    codigo = re.sub(r"'(?:[^'\\]|\\.)*'", "''", codigo)
    codigo = re.sub(r'"(?:[^"\\]|\\.)*"', '""', codigo)
    return codigo


def _esta_balanceado(codigo):
    codigo = _quitar_strings(codigo)
    for apertura, cierre in (('{', '}'), ('(', ')'), ('[', ']')):
        if codigo.count(apertura) != codigo.count(cierre):
            return False
    return True


def _sin_bugs_conocidos(codigo):
    if 'styles.' in codigo:
        return False
    if '{title}' in codigo:
        return False
    if 'const [isLoading, setIsLoading] = useState(false);' not in codigo:
        return False
    return True


class CodeGeneratorTest(unittest.TestCase):
    def setUp(self):
        self.generador = CodeGenerator()

    def test_numero_de_lineas_en_rango(self):
        codigo = self.generador.generar_codigo()
        lineas = codigo.splitlines()
        self.assertGreaterEqual(len(lineas), 45)
        self.assertLessEqual(len(lineas), 115)

    def test_ausencia_de_bugs_conocidos(self):
        codigo = self.generador.generar_codigo()
        self.assertTrue(_sin_bugs_conocidos(codigo))
        self.assertIn('setIsLoading(true);', codigo)
        self.assertIn('setIsLoading(false)', codigo)
        self.assertIn('export default', codigo)

    def test_llaves_y_parentesis_balanceados(self):
        for _ in range(10):
            codigo = self.generador.generar_codigo()
            self.assertTrue(_esta_balanceado(codigo))

    def test_variacion_20_bloques(self):
        codigos = [self.generador.generar_codigo() for _ in range(20)]
        for codigo in codigos:
            self.assertTrue(_sin_bugs_conocidos(codigo))
            self.assertIn('export default', codigo)
            self.assertTrue(_esta_balanceado(codigo))
        self.assertGreaterEqual(len(set(codigos)), 2)

    def test_comentario_de_ruta_y_docstring(self):
        codigo = self.generador.generar_codigo()
        lineas = codigo.splitlines()
        self.assertTrue(lineas[0].startswith('// src/'))
        self.assertIn('/**', codigo)
        self.assertIn('Última modificación:', codigo)

    def test_patrones_de_react_typescript_presentes(self):
        codigo = self.generador.generar_codigo()
        for patron in ('useState', 'useEffect', 'useMemo', 'useCallback',
                       'export const', 'export interface', 'export type',
                       'async', ': FC<', 'Promise<', 'export default'):
            self.assertIn(patron, codigo)

    def test_truncado_respeta_limite_sin_cortar_bloques(self):
        codigo = self.generador.generar_codigo(min_lineas=40, max_lineas=45)
        self.assertGreaterEqual(len(codigo.splitlines()), 40)
        self.assertTrue(_esta_balanceado(codigo))


if __name__ == '__main__':
    unittest.main()
