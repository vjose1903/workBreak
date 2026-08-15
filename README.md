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
  * **Directorio real** con código React/TS del proyecto monitoreado: el bot escanea el directorio (ignorando `node_modules`, `dist`, `build`, etc.), solo considera archivos de **más de 20 y menos de 400 líneas**, elige archivos reales y los pega en el editor, para que las capturas muestren el código real del proyecto.
* Tiempo de ejecución en minutos (vacío o `0` = indefinido).
* **Usar configuración previa**: carga una de las configuraciones de las últimas 5 sesiones (guardadas localmente en `config_history.json`). Se auto-selecciona la más reciente; también puedes elegir otra por número.

El archivo `config_history.json` se crea automáticamente en la raíz del proyecto si no existe y conserva las últimas 5 configuraciones usadas.

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

1. Abre el editor especificado con un proyecto simulado temporal. El arranque es adaptativo: lanza el editor por nombre de aplicación (`open -a` en macOS / binario en Windows), reintenta activar su ventana hasta que está disponible (sin esperas fijas largas) y omite activaciones redundantes de aplicaciones, por lo que las fases de simulación arrancan apenas el editor queda listo. Si el editor elegido **no está instalado**, intenta automáticamente con el otro editor disponible y avisa en el log; si ninguno se puede abrir, termina con un error claro (no se queda reintentando).
2. Inyecta bloques grandes de código (React/TypeScript aleatorio o archivos reales del proyecto) de forma instantánea (copiándolos al portapapeles y pegándolos en el editor) y después simula trabajo real: elige un bloque de líneas del código visible, lo borra y lo **reescribe tal cual, carácter a carácter**. La escritura es continua y realista:
   * Si una fase de escritura termina a mitad de una línea, el bot **recuerda dónde quedó** (`bloque`, `indice_linea`, `desplazamiento`) y en la siguiente sesión de teclado **continúa exactamente desde ahí**, sin volver a borrar.
   * Al pasar a la fase de clics, guarda el estado; al volver a escribir, se reposiciona en la línea que estaba tecleando (`Ctrl+G` + `End`) y sigue.
   * La **fase de mouse** sube al inicio del archivo (`Ctrl+Home`), hace clic sobre el editor para enfocarlo y hace scroll arriba/abajo sobre el código (volviendo periódicamente al inicio) para que las capturas de pantalla muestren todo el contenido. Al terminar la fase, vuelve a la línea pendiente de escritura.
   * Cuando termina de reescribir un bloque completo, **toma otro bloque o línea** del código.
   * El tamaño del bloque se adapta al tamaño del archivo (archivos pequeños → bloques pequeños) para no borrar el archivo entero.
   * Solo escribe caracteres ASCII imprimibles y **suelta explícitamente los modificadores** (Ctrl/Cmd/Shift/Alt) tras cada secuencia de teclas, para evitar que macOS abra el panel de emojis por sí solo (`fn+E` o `Ctrl+Cmd+Space`).
   Al completar cada bloque, el archivo queda exactamente igual al original para las capturas. Las fases de escritura y mouse tienen duraciones variables y distintas entre sí.
3. Si se especifican URLs, abre el navegador y navega por ellas, realizando clics aleatorios. Si hay webs configuradas, las fases del editor y del navegador se **alternan en turnos acotados** (editor ~30-90s, navegador ~30-60s), de modo que ambas arrancan apenas su aplicación está abierta y no se espera a que termine toda la fase del editor.
4. Regresa al editor y continúa la simulación en un bucle infinito o hasta que se haya alcanzado el tiempo especificado por el parámetro `-tiempo`.
5. El script se detendrá automáticamente una vez transcurrido el tiempo indicado (si se especificó `-tiempo`), o continuará indefinidamente hasta que el usuario lo detenga manualmente.

## Detener el bot

Para finalizar el script, presiona `CTRL + C` en la terminal.

## Notas

* En Windows, puede ser necesario ejecutar la terminal como administrador para que `pyautogui` funcione correctamente.
* En macOS, puede requerir permisos adicionales de accesibilidad en `Preferencias del Sistema > Seguridad y privacidad > Accesibilidad`.
