# Bot de Interacción con Editor y Navegador

Este bot permite interactuar automáticamente con un editor de código y un navegador web, simulando escritura, movimientos del mouse y clics.

## Requisitos

* Python 3.x
* Pip (administrador de paquetes de Python)
* Dependencias: `pyautogui`, `argparse`, `webbrowser`, `subprocess`, `os`

## Instalación

### 1. Clonar el repositorio

```
    git clone https://github.com/vjose1903/workBreak
    cd workBreak
```

### 2. Instalar dependencias

#### En macOS/Linux

```
    chmod +x setup.sh
    ./setup.sh
```

#### En Windows

```
    setup.bat
```

## Uso

Ejecutar el script con los parámetros requeridos:

```
    python src/bot.py -editor vsCode -browser chrome -web "https://google.com,https://chat.openai.com"
```

### Parámetros

* `-editor` (requerido): Editor a usar (`cursor` o `vsCode`)
* `-browser` (opcional): Navegador a usar (`chrome`, `edge`, `opera`, `firefox`)
* `-web` (opcional): Lista de URLs separadas por coma

## Funcionamiento

1. Abre el editor especificado.
2. Simula escritura y movimiento del mouse dentro del editor durante 3 minutos.
3. Si se especifican URLs, abre el navegador y navega por ellas, realizando clics aleatorios.
4. Regresa al editor y continúa la simulación en un bucle infinito hasta que el usuario detenga la ejecución manualmente.

## Detener el bot

Para finalizar el script, presiona `CTRL + C` en la terminal.

## Notas

* En Windows, puede ser necesario ejecutar la terminal como administrador para que `pyautogui` funcione correctamente.
* En macOS, puede requerir permisos adicionales de accesibilidad en `Preferencias del Sistema > Seguridad y privacidad > Accesibilidad`.
