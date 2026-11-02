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

El editor es siempre **Visual Studio Code**, sin selección adicional.

El menú permite configurar:

* Navegador a usar (`chrome`, `edge`, `opera`, `firefox`) o `ninguno`.
* Webs donde simular interacción (separadas por coma).
* Fuente del código a colocar en el editor:
  * **Código React/TypeScript aleatorio** (por defecto).
  * **Directorio real** con código React/TS del proyecto monitoreado: el bot escanea el directorio (ignorando `node_modules`, `dist`, `build`, etc.), solo considera archivos de **más de 20 y menos de 400 líneas**, elige archivos reales y los pega en el editor, para que las capturas muestren el código real del proyecto.
* Tiempo de ejecución en minutos (vacío o `0` = indefinido).
* **Fases del editor** (opción 6): escritura y mouse (por defecto), solo escritura o solo mouse. La elección se muestra en el resumen y se conserva en el historial. Las configuraciones antiguas usan ambas fases.
* **Usar configuración previa**: carga una de las configuraciones de las últimas 5 sesiones (guardadas localmente en `config_history.json`). Se auto-selecciona la más reciente; también puedes elegir otra por número.

El archivo `config_history.json` se crea automáticamente en la raíz del proyecto si no existe y conserva las últimas 5 configuraciones usadas.

En los tres modos se pega inicialmente el código completo. En solo mouse se conserva ese contenido y se realizan movimientos y scroll sin reescribir fragmentos. En solo escritura se omiten las fases de mouse. Esta selección se aplica al editor; la navegación web conserva su configuración independiente. Para iniciar, usa la opción 7.

### Modo avanzado (parámetros CLI)

Si se pasan parámetros de configuración, el bot omite el menú y utiliza siempre VS Code:

```bash
python src/main.py -browser chrome -web "https://google.com,https://chat.openai.com" -tiempo 60
```

### Parámetros

* Los comandos antiguos con `-editor vsCode` siguen siendo compatibles. No se admiten otros editores.
* `-browser` (opcional): Navegador a usar (`chrome`, `edge`, `opera`, `firefox`)
* `-web` (opcional): Lista de URLs separadas por coma
* `-tiempo` (opcional): Tiempo en minutos que el script debe ejecutarse. Acepta `indefinido` o un número positivo. Si no se proporciona, el script se ejecutará indefinidamente.

## Funcionamiento

1. Abre Visual Studio Code con una pestaña vacía respaldada por un archivo temporal con nombre único por sesión. No crea un proyecto React ni carga una plantilla inicial; el primer contenido se pega desde la fuente configurada. Lanza el editor por nombre de aplicación (`open -a` en macOS / binario en Windows) y reintenta activar su ventana. Antes de la inyección y de cada paso de edición, comprueba la activación y el título del archivo temporal; si no puede confirmarlos, detiene el bot. El título de ventana debe incluir el nombre del archivo. Si Visual Studio Code no se puede abrir, termina con un error claro.
2. Inyecta código (React/TypeScript aleatorio o archivos reales del proyecto) una vez, copiándolo al portapapeles y pegándolo en el editor. Después elige bloques y **reescribe su contenido carácter a carácter, línea por línea, conservando los saltos de línea**. La escritura es continua y realista:
   * Si una fase de escritura termina a mitad de una línea, el bot **recuerda dónde quedó** (`bloque`, `indice_linea`, `desplazamiento`) y en la siguiente sesión de teclado **continúa exactamente desde ahí**, sin volver a borrar.
   * Al pasar a la fase de clics, guarda el estado; al volver a escribir, se reposiciona en la línea pendiente. En macOS usa `Option+G`, comprueba por portapapeles el contenido del panel antes de enviar las coordenadas y compara la línea de destino con el código cargado antes de continuar. Si no puede confirmarlo, se detiene sin editar. En Windows usa `Ctrl+G`.
   * La **fase de mouse** sube al inicio del archivo (`Ctrl+Home` en Windows, `Cmd+↑` en macOS), hace clic sobre el editor para enfocarlo y hace scroll arriba/abajo sobre el código. La vuelta a la línea pendiente se hace una sola vez, cuando se reanuda la escritura.
   * Cuando termina de reescribir un bloque completo, **toma otro bloque o línea** del código.
   * El tamaño del bloque se adapta al tamaño del archivo. Navega una sola vez a cada línea antes de reescribirla. Al terminarla, repone su texto exacto por portapapeles desde el inicio completo de la línea, incluyendo la sangría, sin volver a abrir Ir a línea. Así corrige posibles inserciones del autocompletado sin duplicar los espacios iniciales.
   * Solo elige líneas con caracteres ASCII imprimibles. En macOS envía el texto como Unicode mediante Quartz, con modificadores explícitamente vacíos; los atajos llevan únicamente sus modificadores necesarios y nunca `Fn`. Así evita que las letras se interpreten como atajos del selector de emojis. En Windows libera Ctrl/Shift/Alt tras las secuencias de edición.
   Al completar cada bloque, el archivo queda exactamente igual al original para las capturas. Las fases de escritura y mouse tienen duraciones variables y distintas entre sí.
3. Si se especifican URLs, abre el navegador y navega por ellas, realizando clics aleatorios. Si hay webs configuradas, las fases del editor y del navegador se **alternan en turnos acotados** (editor ~30-90s, navegador ~30-60s), de modo que ambas arrancan apenas su aplicación está abierta y no se espera a que termine toda la fase del editor.
4. Regresa al editor y continúa la simulación en un bucle infinito o hasta que se haya alcanzado el tiempo especificado por el parámetro `-tiempo`.
5. Al agotarse el tiempo indicado por `-tiempo`, no inicia nuevas páginas ni interacciones web. El cierre de la pestaña creada y la limpieza pueden terminar después del límite. Sin límite configurado, continúa hasta que el usuario lo detenga manualmente.

## Detener el bot

Para finalizar el script, presiona `CTRL + C` en la terminal.

También puedes activar la parada de emergencia de PyAutoGUI llevando el mouse a una esquina de la pantalla principal. Al detectarla, el bot no envía teclas para cerrar pestañas; puede quedar abierta la pestaña de esa interacción.

## Notas

* En Windows, puede ser necesario ejecutar la terminal como administrador para que `pyautogui` funcione correctamente.
* En macOS, puede requerir permisos adicionales de accesibilidad en `Preferencias del Sistema > Seguridad y privacidad > Accesibilidad`.
