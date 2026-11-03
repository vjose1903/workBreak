# Bot de Interacción con Editor y Navegador

<p style="background-color: #FFEB3B; color: #D32F2F; padding: 10px; font-weight: bold;"> ¡¡¡Advertencia!!! Si tienes múltiples monitores, asegúrate de mantener tanto el navegador como el editor en la misma pantalla donde se ejecuta el script para evitar problemas de interacción.</p>

Este bot permite interactuar automáticamente con un editor de código y un navegador web, simulando escritura, movimientos del mouse y clics.

## Requisitos

Las fases de mouse detectan los monitores conectados y utilizan el área visible de la ventana del editor o navegador, aunque esté fuera del monitor principal. En macOS se utilizan coordenadas globales en puntos para admitir pantallas Retina y monitores a la izquierda o encima del principal. Si una ventana ocupa varias pantallas, se elige la mayor área de interacción continua dentro de una pantalla. La posición de las ventanas y las pantallas se vuelve a consultar durante la fase de mouse; no hace falta seleccionar un monitor en el menú.

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

### Aplicación de macOS: instalar y actualizar sin Terminal

Los instaladores versionados se publican en [GitHub Releases](https://github.com/vjose1903/workBreak/releases).
Descarga el DMG correspondiente a tu Mac: `arm64` para Apple Silicon o `x86_64` para Intel. Esta distribución requiere macOS 15 o posterior.

1. Abre el DMG y ejecuta el archivo `.pkg` que contiene.
2. El instalador coloca **WorkBreak.app** en **Aplicaciones**. Ábrelo desde allí: aparecerá su W en la barra superior, sin ventana de Terminal ni una instalación adicional de Python.
3. Al iniciar el bot por primera vez, concede a WorkBreak los permisos de **Accesibilidad**, **Monitorización de entrada** y **Automatización** que macOS solicite para el editor y el navegador. Los permisos de Terminal no sustituyen los de esta aplicación.

Para actualizar, utiliza **Buscar actualizaciones…** en el menú de WorkBreak. La aplicación consulta la última Release estable de este repositorio y ofrece descargar el DMG compatible. Cierra WorkBreak y ejecuta el nuevo `.pkg`: actualizará la aplicación existente, sin borrarla manualmente. El instalador rechaza la instalación mientras la aplicación empaquetada está abierta y comprueba las versiones para evitar sobrescribir una más reciente con otra antigua.

La configuración instalada se conserva en `~/Library/Application Support/WorkBreak/config_history.json`; los registros están en `~/Library/Logs/WorkBreak/`. Ambos quedan fuera de la aplicación y sobreviven a su sustitución. El build local migra una vez el historial del checkout a Application Support si allí todavía no existe uno. Nunca incluye configuraciones personales en el DMG ni reemplaza las ya instaladas.

La distribución actual utiliza firma local ad hoc, **sin Developer ID ni notarización de Apple**. macOS puede bloquear la primera apertura de un archivo descargado; la autorización se gestiona en **Ajustes del Sistema → Privacidad y seguridad**. Tras actualizar puede ser necesario renovar los permisos de automatización. No se desactiva Gatekeeper. La descarga es explícita y la instalación la realiza el instalador nativo; no hay reemplazos silenciosos ni un actualizador con privilegios propios.

### Compilar una distribución

Requiere macOS 15+, Python 3.12 y las herramientas de línea de comandos de Apple. Las dependencias del build están fijadas en `requirements-build-mac.lock`; se instalan en un entorno independiente del Python habitual:

```bash
python3.12 -m venv .venv-build
.venv-build/bin/python -m pip install -r requirements-build-mac.lock
.venv-build/bin/python scripts/build_macos.py
```

Se generan `dist/WorkBreak-X.Y.Z-macos-ARQUITECTURA.dmg`, `.pkg` y `.sha256`. Cada build verifica la firma estructural y ejecuta una comprobación del binario: interfaz nativa, recursos, certificados HTTPS e importación de la automatización en un proceso separado, sin enviar entradas ni conectar con la red. `--no-migrate` omite la migración del historial local. Los artefactos se construyen para la arquitectura del Python usado, no son universales.

`VERSION` es la única fuente de versión de la aplicación, el paquete y las descargas. Para incrementarla:

```bash
python scripts/version.py patch
```

Usa `patch` para correcciones, `minor` para funcionalidades y `major` para cambios incompatibles. El comando modifica `VERSION` y muestra el tag correspondiente; no confirma cambios ni publica nada.

### Publicar actualizaciones mediante tags de GitHub

El comando de publicación es similar al `release.js` de Novac y solo necesita Node.js 18 o posterior y Git:

```bash
node scripts/release.js
```

Elige **mayor**, **versión** o **parche** y describe los cambios. Para publicar la primera `1.0.0`, o si ya incrementaste `VERSION` por separado, elige **Actual**. El script muestra la rama, la versión, el tag y los archivos pendientes antes de pedir la confirmación final. Incluye todos los cambios del proyecto que no estén ignorados por Git, crea el commit y un tag anotado con la descripción, y envía rama y tag juntos mediante un push atómico. No es necesario ejecutar los comandos Git manualmente ni compilar el DMG en tu Mac.

Para revisar el flujo sin modificar archivos, staging, commits ni tags:

```bash
node scripts/release.js --dry-run --kind parche --description "Corrección de escritura"
```

El script comprueba tags locales y remotos, límites de versión de macOS, conflictos, rama separada y sincronización con origin. No reemplaza tags existentes ni hace push forzado. Si el envío falla, conserva los cambios y muestra cómo reintentar el push sin crear otra versión.

Al llegar un tag `vX.Y.Z`, el workflow `.github/workflows/release-macos.yml`:

1. Comprueba que el tag coincida exactamente con `VERSION` y prueba el publicador con repositorios temporales.
2. Ejecuta las pruebas de Python y compila instaladores separados para Intel y Apple Silicon.
3. Verifica los ejecutables y genera DMG, PKG y sumas SHA-256.
4. Prepara una Release en borrador con la descripción del tag y solo la publica cuando ambos instaladores están disponibles. Las reejecuciones pueden completar un borrador, pero no sustituyen archivos de una Release ya publicada.

La implementación y el workflow deben formar parte del commit publicado; el script los incluirá si están pendientes. No se deben mover tags publicados: cualquier corrección lleva un nuevo número y un nuevo tag. **Buscar actualizaciones…** compara versiones numéricamente y consulta únicamente Releases estables con instalador para la arquitectura actual. Los tags sin Release o sin instaladores no se ofrecen como actualizaciones instalables.

Si en el futuro dispones de certificados de distribución, el build admite `WORKBREAK_CODESIGN_IDENTITY`, `WORKBREAK_INSTALLER_IDENTITY` y `WORKBREAK_NOTARY_PROFILE` (perfil guardado en Keychain para `notarytool`). No se incluyen certificados ni contraseñas en el repositorio. La firma y notarización con Developer ID requieren configurar esas credenciales en el entorno de compilación; el workflow actual usa firma local.

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

En **macOS**, ejecutar el script sin parámetros abre una **W en la barra de menús superior**:

```bash
python src/main.py
```

Haz clic en la **W** para configurar navegador, webs, fuente de código, tiempo, fases y configuraciones recientes. El bot no empieza hasta pulsar **Iniciar bot**. Mientras trabaja, las opciones de configuración quedan bloqueadas; **Detener bot**, **Estado y estadísticas**, **Ver registro** y **Salir de WorkBreak** permanecen disponibles.

El menú muestra la fase actual, las pausas por actividad y su cuenta atrás. **Detener bot** interrumpe también el debounce. **Salir** solicita una detención ordenada y espera la limpieza antes de cerrar. Solo se admite una interfaz por checkout y una sesión de automatización a la vez, compartiendo el bloqueo con Terminal y los argumentos CLI. El código real se escanea en el proceso del bot, para mantener disponible el menú durante la carga.

La automatización se ejecuta en un proceso separado creado con `spawn`. La interfaz permanece en el hilo principal de AppKit. El registro se guarda en `~/Library/Logs/WorkBreak/workbreak.log`, con rotación. La configuración se sigue guardando en el historial existente al iniciar una sesión válida.

Para utilizar el menú anterior en Terminal:

```bash
python src/main.py --terminal
```

En Windows el menú de terminal continúa siendo el predeterminado. Los parámetros CLI conservan su funcionamiento en ambos sistemas. Al ejecutar desde el checkout se utiliza Python; la distribución DMG incluye su propia aplicación y runtime. Las dependencias de macOS están declaradas en `requirements-mac.txt`.

El editor es siempre **Visual Studio Code**, sin selección adicional.

El menú permite configurar:

* Navegador a usar (`chrome`, `edge`, `opera`, `firefox`) o `ninguno`.
* Webs donde simular interacción (separadas por coma).
* Fuente del código a colocar en el editor:
  * **Código React/TypeScript aleatorio** (por defecto).
  * **Directorio real** con código React/TS del proyecto monitoreado: el bot escanea el directorio (ignorando `node_modules`, `dist`, `build`, etc.), solo considera archivos de **más de 20 y menos de 400 líneas**, elige archivos reales y los pega en el editor, para que las capturas muestren el código real del proyecto.
* Tiempo de ejecución en minutos (vacío o `0` = indefinido).
* **Interacción**: editor y navegador (por defecto), solo editor o solo navegador. El modo solo navegador exige un navegador y al menos una web, y no abre VS Code ni carga la fuente de código. Se conserva en el historial; también está disponible en la opción 9 del menú de terminal y mediante `--modo web`, `--modo editor` o `--modo ambos`.
* **Fases del editor** (opción 6 del menú de terminal): escritura y mouse (por defecto), solo escritura o solo mouse. La elección se muestra en el resumen y se conserva en el historial. Las configuraciones antiguas usan ambas fases.
* **Usar configuración previa**: carga una de las configuraciones de las últimas 5 sesiones (guardadas localmente en `config_history.json`). Se auto-selecciona la más reciente; también puedes elegir otra por número.

El archivo `config_history.json` se crea al guardar la primera sesión en la raíz del proyecto y conserva las últimas 5 configuraciones usadas. Las actualizaciones reemplazan el archivo de forma atómica para conservar la versión anterior si falla la escritura.

En los tres modos se pega inicialmente el código completo. En solo mouse se conserva ese contenido y se realizan movimientos y scroll sin reescribir fragmentos. En solo escritura se omiten las fases de mouse. Esta selección se aplica al editor; la navegación web conserva su configuración independiente. Para iniciar, pulsa **Iniciar bot** en la W, o usa la opción 7 en el menú de terminal.

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
2. Inyecta código (React/TypeScript aleatorio o archivos reales del proyecto) una vez, copiándolo al portapapeles y pegándolo en el editor. Después elige bloques y **reescribe su contenido carácter a carácter, línea por línea, conservando los saltos de línea**. Cada carácter se inserta mediante un pegado individual para evitar que el editor añada automáticamente comillas, paréntesis o sangría. La escritura conserva sus pausas variables:
   * Si una fase de escritura termina a mitad de una línea, el bot **recuerda dónde quedó** (`bloque`, `indice_linea`, `desplazamiento`) y en la siguiente sesión de teclado **continúa exactamente desde ahí**, sin volver a borrar.
   * Al pasar a la fase de clics, guarda el estado; al volver a escribir, se reposiciona en la línea pendiente. En macOS usa `Option+G`, comprueba por portapapeles el contenido del panel antes de enviar las coordenadas y compara la línea de destino con el código cargado antes de continuar. Si no puede confirmarlo, se detiene sin editar. En Windows usa `Ctrl+G`.
   * La **fase de mouse** sube al inicio del archivo (`Ctrl+Home` en Windows, `Cmd+↑` en macOS), hace clic sobre el editor para enfocarlo y hace scroll arriba/abajo sobre el código. La vuelta a la línea pendiente se hace una sola vez, cuando se reanuda la escritura.
   * Cuando termina de reescribir un bloque completo, **toma otro bloque o línea** del código.
   * El tamaño del bloque se adapta al tamaño del archivo. Navega una sola vez a cada línea y verifica que la selección coincida exactamente con su contenido antes de reemplazarla, sin incluir el salto de línea. Al terminar comprueba el resultado; no realiza un segundo reemplazo para restaurar la sangría. Para continuar una línea parcial, verifica el texto y avanza exactamente su longitud desde la columna 1, independientemente del ajuste visual.
   * Solo elige líneas con caracteres ASCII imprimibles. Los atajos de macOS se envían mediante Quartz con modificadores explícitos, sin `Fn`. El texto de las líneas se inserta por portapapeles. En Windows libera Ctrl/Shift/Alt tras las secuencias de edición.
   Al completar cada bloque, el archivo queda exactamente igual al original para las capturas. Las fases de escritura y mouse tienen duraciones variables y distintas entre sí.
3. Si se especifican URLs, abre el navegador y navega por ellas, realizando clics aleatorios dentro de una zona interior de la ventana. Si hay webs configuradas, las fases del editor y del navegador se **alternan en turnos acotados** (editor ~30-90s, navegador ~30-60s). El recorrido conserva las páginas pendientes entre turnos, aunque la lista no quepa en uno solo. Los movimientos del editor también se limitan a una zona interior; si no se puede confirmar una zona visible suficiente, se cancela la interacción.
4. Regresa al editor y continúa la simulación en un bucle infinito o hasta que se haya alcanzado el tiempo especificado por el parámetro `-tiempo`.
5. Al agotarse el tiempo indicado por `-tiempo`, no inicia nuevas páginas ni interacciones web. La limpieza puede terminar después del límite. Las pestañas se conservan abiertas: el bot no envía un cierre a la pestaña activa sin poder demostrar que es la que creó. Esto también protege las pestañas o ventanas abiertas por enlaces durante una visita. Sin límite configurado, continúa hasta que el usuario lo detenga manualmente.

## Detener el bot

Durante los primeros **5 segundos del inicio**, el bot ignora la actividad del usuario para que el Enter utilizado para arrancarlo no provoque una pausa. El bot comienza a trabajar durante ese margen, sin esperar a que termine. Los eventos ignorados no se acumulan ni disparan una pausa posterior.

Después de ese margen, el bot se pausa automáticamente cuando detecta actividad del usuario en el teclado o el mouse, en cualquier aplicación y en cualquier fase. Cada tecla, movimiento, clic o scroll reinicia una espera de **10 segundos desde la última actividad**. Tras ese intervalo sin intervención, recupera su archivo y continúa; sus propios eventos no reinician la espera. Los movimientos animados se comprueban en pasos de unos 10 ms y cada carácter se comprueba antes de enviarlo.

La terminal informa el inicio de la pausa, los reinicios del debounce, los segundos restantes y la reanudación. La cuenta se actualiza por segundo y los eventos continuos se agrupan para no saturar la consola. Si mantienes una tecla o un botón pulsado, indica que la cuenta comenzará cuando lo sueltes.

El límite total de ejecución continúa contando durante la pausa. Las estadísticas conservan el tiempo trabajado antes de cada interrupción y excluyen la espera de reanudación. El bot conserva el contenido nuevo que copies durante una pausa para restaurarlo al finalizar, y no reemplaza un portapapeles que haya cambiado externamente.

Si intervienes durante una visita web, el bot conserva la página, el índice del recorrido y el tiempo restante del turno; al reanudar no vuelve primero al editor. Conserva la pestaña anterior y continúa en una nueva: dos pestañas pueden tener la misma URL, por lo que no utiliza esa dirección como prueba de identidad. Si modificas el contenido del archivo temporal del editor, las comprobaciones exactas de línea detienen la edición para no sobrescribir tus cambios, incluso si conservaste el prefijo que había escrito el bot.

Esto también se aplica si la navegación estaba pendiente de confirmar o redirigió a otra URL. Pueden quedar pestañas adicionales abiertas después de cada pausa durante la navegación.

En macOS las aperturas se solicitan en segundo plano y los procesos auxiliares de activación y consulta del editor se cancelan al detectar actividad. Una acción que el sistema operativo ya haya ejecutado no puede deshacerse con la pausa. Si el monitor pierde una liberación de tecla o botón, consulta el estado físico para evitar una pausa permanente.

En macOS la detección global requiere permiso de **Monitorización de entrada** y **Accesibilidad** para la aplicación desde la que ejecutas Python (por ejemplo, Terminal). Si no puede iniciar el monitor, el bot termina con un mensaje en lugar de ejecutarse sin esta protección. Windows utiliza los hooks nativos de teclado y mouse. No se requieren dependencias nuevas.

Para finalizar el script, presiona `CTRL + C` en la terminal.

También puedes activar la parada de emergencia de PyAutoGUI llevando el mouse a una esquina de la pantalla principal. Al detectarla, el bot no envía teclas para cerrar pestañas; puede quedar abierta la pestaña de esa interacción.

La parada de emergencia se comprueba también durante el debounce, aproximadamente una vez por segundo. El límite total se revisa antes de cada acción; al agotarse solo se permiten tareas de limpieza, siempre respetando la actividad del usuario. Las operaciones nativas del portapapeles tienen un máximo de cinco segundos y se interrumpen al detectar actividad. Un error de lectura conserva el estado anterior y detiene el flujo, sin confundirlo con un portapapeles vacío. Si una copia quedó interrumpida antes de confirmar su contenido y no coincide con un valor conocido del bot, la ejecución se detiene sin sobrescribir el portapapeles actual ni el valor guardado. No se deduce la autoría mediante el contador de cambios.

El historial descarta registros con tipos o valores inválidos. Los instaladores devuelven un error si falla pip. La demostración manual se ejecuta únicamente con `python test_pyautogui.py --mover-mouse`: mueve el puntero, sin hacer clic, escribir ni borrar contenido, y no se descubre como prueba automática.

## Notas

* Al cambiar de fase, el bot conserva el contenido exacto de la línea que acaba de escribir, aunque haya quedado incompleta. Cada carácter insertado actualiza ese estado antes de comprobar una nueva pausa. Al regresar selecciona la línea lógica completa, incluso cuando ocupa varias filas visuales, y exige igualdad completa con el estado esperado. Si la comprobación falla, registra el número de línea, las longitudes y si existía captura previa, sin imprimir el código fuente.

* En Windows, puede ser necesario ejecutar la terminal como administrador para que `pyautogui` funcione correctamente.
* En macOS, puede requerir permisos adicionales de accesibilidad en `Preferencias del Sistema > Seguridad y privacidad > Accesibilidad`.
