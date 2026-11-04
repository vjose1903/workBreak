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
                or (clave != 'debounce' and (numeros[0] <= 0 or numeros[0] > numeros[1]))):
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
