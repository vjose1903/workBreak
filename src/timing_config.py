"""Duraciones en segundos compartidas por preferencias, menú y ejecución."""
import math

PREDETERMINADOS = {
    'debounce': 10.0,
    'editor': [60.0, 240.0],
    'editor_alternado': [30.0, 90.0],
    'navegador': [30.0, 60.0],
}
TITULOS = {
    'debounce': 'Pausa por inactividad',
    'editor': 'Duración del editor sin navegador',
    'editor_alternado': 'Duración del editor al alternar',
    'navegador': 'Duración del turno de navegador',
}
# Rangos de interacción; las esperas de verificación de destino no son preferencias.
DETALLES = {
    'editor_escritura': ('Fase de escritura', [4, 115]),
    'editor_mouse': ('Fase de mouse', [2, 16]),
    'editor_caracter': ('Pausa entre caracteres', [0.03, 0.08]),
    'editor_bloque': ('Pausa entre bloques de escritura', [0.4, 1.8]),
    'editor_reanudar': ('Pausa al retomar una línea', [0.05, 0.15]),
    'editor_movimiento': ('Duración de cada movimiento', [0.2, 0.6]),
    'editor_centrado': ('Movimiento inicial al centro', [0.3, 0.3]),
    'editor_preparacion': ('Pausa al preparar el mouse', [0.2, 0.5]),
    'editor_pausa_click': ('Pausa después de click', [0.4, 2]),
    'editor_pausa_scroll': ('Pausa después de scroll', [0.4, 2]),
    'editor_pausa_mover_mouse': ('Pausa después de mover el mouse', [0.4, 2]),
    'editor_archivo': ('Tiempo antes de cambiar de archivo', [120, 300]),
    'navegador_visita': ('Duración de la visita por página', [10, 20]),
    'navegador_movimiento': ('Duración de cada movimiento', [0.6, 1.2]),
    'navegador_centrado': ('Movimiento inicial al centro', [0.3, 0.3]),
    'navegador_ciclo': ('Pausa entre ciclos de acciones', [1, 3]),
    'navegador_pausa_click': ('Pausa adicional después de click', [0, 0]),
    'navegador_pausa_scroll': ('Pausa adicional después de scroll', [0, 0]),
}
for _clave, (_titulo, _rango) in DETALLES.items():
    PREDETERMINADOS[_clave] = list(_rango)
    TITULOS[_clave] = _titulo

# Solo los controles principales se muestran; preferencias anteriores se conservan.
CLAVES_EDITOR = ('editor', 'editor_alternado', 'editor_escritura', 'editor_mouse',
                 'editor_caracter', 'editor_pausa_click', 'editor_pausa_scroll')
CLAVES_NAVEGADOR = ('navegador', 'navegador_visita', 'navegador_movimiento', 'navegador_ciclo')
PERMITEN_CERO = {'debounce', *(k for k in DETALLES if any(p in k for p in ('pausa_', 'caracter', 'bloque', 'reanudar', 'preparacion', 'ciclo')))}

MAX_SEGUNDOS = 9999 * 3600 + 59 * 60 + 59


def temporizacion_config(valores=None):
    if valores is None:
        valores = {}
    if not isinstance(valores, dict) or any(k not in PREDETERMINADOS for k in valores):
        raise ValueError('Temporización inválida')
    resultado = {}
    for clave, defecto in PREDETERMINADOS.items():
        valor = valores.get(clave, defecto)
        numeros = [valor] if clave == 'debounce' else valor
        if (not isinstance(numeros, (tuple, list)) or len(numeros) != (1 if clave == 'debounce' else 2)
                or any(type(n) not in (int, float) or not (0 <= n <= MAX_SEGUNDOS)
                       or not math.isfinite(n) for n in numeros)
                or (clave != 'debounce' and ((numeros[0] == 0 and clave not in PERMITEN_CERO) or numeros[0] > numeros[1]))):
            raise ValueError(TITULOS[clave] + ': usa segundos válidos y mínimo ≤ máximo')
        resultado[clave] = float(valor) if clave == 'debounce' else list(map(float, valor))
    return resultado


def texto_tiempo(clave, valores=None):
    valor = temporizacion_config(valores)[clave]
    return f'{valor:g} s' if clave == 'debounce' else f'{valor[0]:g}–{valor[1]:g} s'


def temporizacion_valida(valores):
    try:
        temporizacion_config(valores)
        return True
    except ValueError:
        return False
