# Bot de Interacción con Editor y Navegador

<p style="background-color: #FFEB3B; color: #D32F2F; padding: 10px; font-weight: bold;"> ¡¡¡Advertencia!!! Si tienes múltiples monitores, asegúrate de mantener tanto el navegador como el editor en la misma pantalla donde se ejecuta el script para evitar problemas de interacción.</p>

Este bot permite interactuar automáticamente con un editor de código y un navegador web, simulando escritura, movimientos del mouse y clics.

## Requisitos

* Python 3.x
* Pip (administrador de paquetes de Python)

### Dependencias Generales

* `pyautogui`
* `argparse`
* `pygetwindow`
* `pyperclip`

### Dependencias en Windows

* `pywin32>=305; platform_system=="Windows"`
* `psutil; platform_system=="Windows"`

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/vjose1903/workBreak
cd workBreak
```

### 2. Instalar dependencias

#### En macOS/Linux

```bash
chmod +x setup.sh
./setup.sh
```

#### En Windows

```bash
setup.bat
```

## Uso

Ejecutar el script sin parámetros para que se muestre el **menú interactivo**:

```bash
python src/main.py
```

El menú permite configurar:

* Editor a usar (`vsCode` o `cursor`).
* Navegador a usar (`chrome`, `edge`, `opera`, `firefox`) o `ninguno`.
* Webs donde simular interacción (separadas por coma).
* Fuente del código a colocar en el editor:
  * **Código React/TypeScript aleatorio** (por defecto).
  * **Directorio real** con código React/TS del proyecto monitoreado: el bot escanea el directorio (ignorando `node_modules`, `dist`, `build`, etc.), elige archivos reales y los pega en el editor, para que las capturas muestren el código real del proyecto.
* Tiempo de ejecución en minutos (vacío o `0` = indefinido).

### Modo avanzado (parámetros CLI)

Si se pasa el parámetro `-editor`, el bot usa la configuración por línea de comandos y omite el menú:

```bash
python src/main.py -editor vsCode -browser chrome -web "https://google.com,https://chat.openai.com" -tiempo 60
```

### Parámetros

* `-editor` (opcional): Editor a usar (`cursor` o `vsCode`). Si no se pasa, se muestra el menú interactivo.
* `-browser` (opcional): Navegador a usar (`chrome`, `edge`, `opera`, `firefox`)
* `-web` (opcional): Lista de URLs separadas por coma
* `-tiempo` (opcional): Tiempo en minutos que el script debe ejecutarse. Acepta `indefinido` o un número positivo. Si no se proporciona, el script se ejecutará indefinidamente.

## Funcionamiento

1. Abre el editor especificado con un proyecto simulado temporal.
2. Inyecta bloques grandes de código (React/TypeScript aleatorio o archivos reales del proyecto) de forma instantánea (copiándolos al portapapeles y pegándolos en el editor) y después simula escritura y movimiento del mouse. Todo lo aleatorio se escribe y borra solo al final del archivo para no dañar el código visible en las capturas. Las fases de escritura y mouse tienen duraciones variables y distintas entre sí.
3. Si se especifican URLs, abre el navegador y navega por ellas, realizando clics aleatorios.
4. Regresa al editor y continúa la simulación en un bucle infinito o hasta que se haya alcanzado el tiempo especificado por el parámetro `-tiempo`.
5. El script se detendrá automáticamente una vez transcurrido el tiempo indicado (si se especificó `-tiempo`), o continuará indefinidamente hasta que el usuario lo detenga manualmente.

## Detener el bot

Para finalizar el script, presiona `CTRL + C` en la terminal.

## Notas

* En Windows, puede ser necesario ejecutar la terminal como administrador para que `pyautogui` funcione correctamente.
* En macOS, puede requerir permisos adicionales de accesibilidad en `Preferencias del Sistema > Seguridad y privacidad > Accesibilidad`.
