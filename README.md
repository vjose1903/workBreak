<p align="center">
  <img src="assets/icon.svg" alt="Logo de WorkBreak" width="88" />
</p>

<h1 align="center">WorkBreak</h1>

<p align="center">
  Automatización de escritura y navegación, desde la barra de menús de tu Mac.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/versi%C3%B3n_del_c%C3%B3digo-1.0.0-536DFE" alt="Versión del código: 1.0.0" />
  <img src="https://img.shields.io/badge/macOS-15%2B-black?logo=apple" alt="macOS 15 o posterior" />
  <img src="https://img.shields.io/badge/arquitecturas-Intel_%7C_Apple_Silicon-00A6CB" alt="Intel y Apple Silicon" />
  <a href="https://github.com/vjose1903/workBreak/actions/workflows/release-macos.yml"><img src="https://github.com/vjose1903/workBreak/actions/workflows/release-macos.yml/badge.svg" alt="Estado de publicación de macOS" /></a>
</p>

<p align="center">
  <a href="#-descargas">Descargar</a> ·
  <a href="#-primeros-pasos">Primeros pasos</a> ·
  <a href="#-interfaz-y-configuración">Interfaz</a> ·
  <a href="#-actualizaciones">Actualizar</a> ·
  <a href="#-desarrollo-y-publicación">Desarrollo</a>
</p>

WorkBreak simula escritura en **Visual Studio Code** y movimientos, clics y scroll en un navegador. Puedes utilizar solo el editor, solo la web o alternar ambos, elegir las fases y definir una duración. Se controla desde su **W en la barra de menús**, sin mantener una terminal abierta cuando utilizas la aplicación instalada.

## 📥 Descargas

### 🍎 macOS · Intel y Apple Silicon

**Requisito: macOS 15 o posterior.** El instalador incluye Python y las dependencias; no necesitas instalarlos por separado.

| Tu Mac | Arquitectura | Última versión estable |
| --- | --- | --- |
| Apple Silicon · familia M1, M2, M3, M4 o M5 | `arm64` | [⬇ Descargar DMG para Apple Silicon](https://github.com/vjose1903/workBreak/releases/latest/download/WorkBreak-macos-arm64.dmg) |
| Procesador Intel | `x86_64` | [⬇ Descargar DMG para Intel](https://github.com/vjose1903/workBreak/releases/latest/download/WorkBreak-macos-x86_64.dmg) |

> **Disponibilidad:** los enlaces dinámicos requieren una Release estable publicada con los archivos de nombre fijo `WorkBreak-macos-arm64.dmg` y `WorkBreak-macos-x86_64.dmg`. El workflow los adjunta a las nuevas publicaciones. Hasta publicar una versión con este cambio, los enlaces pueden devolver 404. La ejecución nativa en Apple Silicon requiere además validación funcional en ARM.

Los botones de la tabla descargan directamente el **DMG**, sin pasar por una descarga del código fuente. Cada DMG contiene su instalador `.pkg`. El workflow adjunta a la Release únicamente los DMG de Intel y Apple Silicon; los PKG separados y las sumas SHA-256 se conservan como artefactos de compilación en Actions.

Los botones utilizan `/releases/latest/download/` y apuntan automáticamente a la **última Release estable**, sin editar el README con cada versión. También puedes consultar **[la última Release](https://github.com/vjose1903/workBreak/releases/latest)** o **[todas las versiones y sus cambios](https://github.com/vjose1903/workBreak/releases)**.

**¿Cuál necesitas?** En el menú  → **Acerca de este Mac**, si aparece «Chip Apple M…», elige Apple Silicon. Si aparece «Procesador Intel», elige Intel.

### 🪟 Windows · En construcción

🚧 **La aplicación y el instalador para Windows están en construcción.** Todavía no hay un ejecutable Windows publicado ni una interfaz equivalente a la de macOS. El repositorio conserva el modo de terminal y las dependencias de Windows para desarrollo; esto no equivale a una distribución terminada.

## 🚀 Primeros pasos

1. **Descarga** el DMG correspondiente a tu procesador.
2. **Abre el DMG** y ejecuta el archivo `.pkg` que contiene.
3. **Abre WorkBreak** desde Aplicaciones. Busca su W en la barra superior.
4. **Configura** la interacción, navegador, webs, fuente de código y tiempo.
5. Pulsa **Iniciar bot**. Para finalizar, abre la W y selecciona **Detener bot**.

El bot comienza únicamente cuando pulsas **Iniciar bot**. En los modos que usan el editor necesitas tener **Visual Studio Code instalado**; para la interacción web, el navegador elegido debe estar instalado.

### 🔐 Permisos y primera apertura

Concede los permisos que solicite macOS en **Ajustes del Sistema → Privacidad y seguridad**:

| Permiso | Para qué se utiliza |
| --- | --- |
| **Accesibilidad** | Enviar las interacciones de teclado y mouse y verificar las ventanas. |
| **Monitorización de entrada** | Detectar tu actividad y pausar la automatización. |
| **Automatización** | Activar y consultar el editor y el navegador. |

La distribución utiliza **firma local ad hoc, sin Developer ID ni notarización de Apple**. macOS puede bloquear la primera apertura de una descarga: revisa la autorización en **Privacidad y seguridad**. No es necesario desactivar Gatekeeper. Después de actualizar, macOS puede pedir renovar permisos.

Los permisos pertenecen a la aplicación desde la que ejecutas el bot: los de Terminal o Python no sustituyen los de **WorkBreak.app**.

## 🖥️ Interfaz y configuración

Las siguientes son **capturas reales de la interfaz del proyecto**, con direcciones de ejemplo. No se inició la automatización para obtenerlas.

### El menú de WorkBreak

<p align="center">
  <img src="docs/images/menu.png" alt="Menú de WorkBreak: interacción, navegador, webs, fuente, tiempo, fases y controles de ejecución" width="340" />
</p>

| Opción | Qué puedes configurar |
| --- | --- |
| **Interacción** | Editor y navegador, solo editor o solo navegador. |
| **Navegador** | Chrome, Edge, Opera, Firefox o ninguno. |
| **Webs…** | Una lista de direcciones identificadas por nombre. |
| **Fuente de código** | Código React/TypeScript aleatorio o archivos de un directorio real. |
| **Tiempo…** | Horas, minutos y segundos, o una ejecución indefinida. |
| **Fases del editor** | Escritura y mouse, solo escritura o solo mouse. |
| **Configuraciones recientes** | Recuperar una de las últimas cinco configuraciones utilizadas. |
| **Estado y estadísticas…** | Consultar el estado y los tiempos registrados. |
| **Ver registro…** | Abrir el registro para revisar el funcionamiento o un error. |
| **Buscar actualizaciones…** | Consultar la última versión estable compatible con tu arquitectura. |

Durante la ejecución se bloquean las opciones de configuración. Puedes consultar el estado, abrir el registro, detener el bot o solicitar la salida; la aplicación espera la limpieza antes de cerrarse.

### 🌐 Agregar y quitar webs

<p align="center">
  <img src="docs/images/webs.png" alt="Panel de webs con campos obligatorios de nombre y dirección, botón Agregar y tabla de direcciones configuradas" width="790" />
</p>

1. Escribe un **nombre** para identificar la web y su **dirección**. Ambos son obligatorios.
2. Pulsa **Agregar** para incorporarla a la lista. Puedes pegar con **⌘V**.
3. Para eliminar una entrada, selecciona su fila y pulsa **Quitar seleccionada**.
4. Pulsa **Guardar** para aplicar los cambios o **Cancelar** para descartarlos.

En **Solo editor**, las opciones Navegador y Webs se deshabilitan y muestran «Configurado solo editor». El modo **Solo navegador** requiere un navegador y al menos una web; no abre VS Code ni carga código.

### ⏱️ Elegir el tiempo de ejecución

<p align="center">
  <img src="docs/images/tiempo.png" alt="Selector de tiempo con horas, minutos y segundos; ejemplo de una hora y treinta minutos" width="470" />
</p>

Desactiva **Tiempo indefinido** para introducir una duración en horas, minutos y segundos. Puedes escribir los valores o usar los controles de incremento. La duración debe ser mayor que cero; minutos y segundos admiten de `00` a `59`.

<p align="center">
  <img src="docs/images/tiempo-indefinido.png" alt="Tiempo indefinido activado: horas, minutos y segundos quedan en cero y deshabilitados" width="470" />
</p>

Al activar **Tiempo indefinido**, los campos se restablecen a `00` y quedan deshabilitados. El bot continuará hasta que lo detengas. Si hay un límite, el tiempo sigue contando durante las pausas por actividad; la limpieza puede terminar después de ese límite.

### 📝 Fuente de código y fases del editor

El editor es siempre **Visual Studio Code**. WorkBreak abre un archivo temporal vacío; después coloca el código completo de la fuente seleccionada. Los archivos originales del directorio no se editan.

- **Código aleatorio:** genera contenido React/TypeScript.
- **Directorio real:** busca archivos `.tsx`, `.jsx`, `.ts` y `.js` de **20 a 400 líneas**, excluyendo carpetas como `node_modules`, `dist` y `build`. El directorio elegido aparece marcado en el menú. Cada tres fases de escritura intenta cargar otro archivo, evitando repetir el anterior cuando hay alternativas válidas.

| Fase | Comportamiento |
| --- | --- |
| **Escritura y mouse** | Alterna la reescritura de fragmentos con movimientos y scroll. |
| **Solo escritura** | Conserva el archivo completo y reescribe fragmentos línea por línea. |
| **Solo mouse** | Carga el código completo y realiza movimientos y scroll sin reescribirlo. |

La reescritura verifica el contenido antes de reemplazar una línea y conserva sus saltos y sangría. Si una fase termina con una línea incompleta, guarda el progreso para continuar después. Solo selecciona líneas no vacías con caracteres ASCII imprimibles para la reescritura.

En macOS utiliza **Option+G** para ir a la línea; los atajos se envían con modificadores explícitos y sin `Fn`. Si no puede confirmar el archivo temporal o el contenido esperado, detiene la edición para evitar sobrescribir cambios externos.

### 🖱️ Varios monitores

Puedes colocar el editor y el navegador en **monitores diferentes**. La fase de mouse consulta la posición de la ventana y elige un área visible dentro de la pantalla correspondiente, sin seleccionar un monitor manualmente.

Se contemplan coordenadas negativas, pantallas Retina y monitores situados a la izquierda o encima del principal. Si una ventana ocupa varias pantallas, se utiliza la mayor área continua de interacción en una de ellas. La posición se vuelve a consultar durante la fase de mouse.

La detección nativa reconoció cuatro monitores en el entorno de desarrollo. El flujo completo de clics y scroll en ventanas situadas en pantallas secundarias todavía requiere comprobación funcional.

## ⏸️ Pausas y detención

**Al usar tu teclado o mouse, el bot cede el control.** Después del margen inicial, cualquier tecla, movimiento, clic o scroll reinicia una pausa de **10 segundos desde la última actividad**. Si sigues utilizando la PC, la cuenta vuelve a empezar; si mantienes una tecla o botón pulsado, la espera comienza cuando lo sueltas.

- **Primeros 5 segundos:** ignora la actividad para evitar que el Enter o clic de inicio provoque una pausa inmediata. El bot puede trabajar durante ese margen.
- **Durante la pausa:** el menú muestra el estado y la cuenta atrás; el registro informa los reinicios y la reanudación. Sus propios eventos no reinician la espera.
- **Al reanudar:** recupera el trabajo pendiente. Si el archivo temporal cambió externamente, puede detener la edición para proteger esos cambios.
- **Detener bot:** finaliza la sesión también durante una pausa. **Salir de WorkBreak** solicita la detención y espera la limpieza.
- **Emergencia:** llevar el mouse a una esquina de la pantalla principal activa la parada de PyAutoGUI. Si ejecutas desde Terminal, también puedes usar **Ctrl+C**.

El portapapeles se guarda y se restaura respetando cambios externos. Las estadísticas excluyen las esperas de reanudación. Solo se permite una sesión de automatización a la vez.

Las pestañas del navegador pueden permanecer abiertas al terminar o después de una pausa. El bot evita cerrar una pestaña cuya identidad no puede confirmar; también comprueba la ventana y la dirección antes de interactuar.

## 🔄 Actualizaciones

1. Abre la W y selecciona **Buscar actualizaciones…** con el bot detenido.
2. Si existe una Release estable más reciente para tu arquitectura, acepta la descarga.
3. **Cierra WorkBreak** y abre el `.pkg` dentro del nuevo DMG.
4. El instalador actualiza la aplicación en **Aplicaciones**. No tienes que borrar la versión anterior.

El instalador rechaza la actualización mientras WorkBreak está abierto y comprueba la versión para evitar reemplazar una más reciente por otra antigua. La descarga requiere tu intervención y la instalación se realiza con el instalador nativo de macOS.

| Datos | Ubicación de la aplicación instalada |
| --- | --- |
| Configuraciones recientes | `~/Library/Application Support/WorkBreak/config_history.json` |
| Registro con rotación | `~/Library/Logs/WorkBreak/workbreak.log` |

Estos datos están fuera de la aplicación y se conservan al actualizar. Al ejecutar desde el código fuente, el historial se guarda en `config_history.json` en la raíz del proyecto. La compilación local puede migrarlo una vez a Application Support si aún no existe; nunca se incluye en el DMG.

## 🛠️ Desarrollo y publicación

### Ejecutar desde el código fuente en macOS

Necesitas **Python 3.12**, Git y los permisos de macOS indicados anteriormente.

```bash
git clone https://github.com/vjose1903/workBreak.git
cd workBreak
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-mac.txt
python src/main.py
```

Sin argumentos, macOS abre la interfaz de la barra de menús. Para usar el menú de terminal:

```bash
python src/main.py --terminal
```

### Modo avanzado por terminal

Los argumentos de configuración omiten el menú e inician la sesión:

```bash
# Alternar editor y navegador durante 60 minutos
python src/main.py -browser chrome -web "https://example.com,https://example.org" -tiempo 60

# Solo editor durante 30 minutos
python src/main.py --modo editor -tiempo 30

# Solo navegador durante 15 minutos
python src/main.py --modo web -browser chrome -web "https://example.com" -tiempo 15
```

| Parámetro | Valores |
| --- | --- |
| `--modo` | `ambos`, `editor` o `web`. |
| `-browser` | `chrome`, `edge`, `opera` o `firefox`. |
| `-web` | Direcciones separadas por comas. |
| `-tiempo` | Minutos positivos o `indefinido`; sin valor configurado, la ejecución es indefinida. |
| `-editor vsCode` | Compatibilidad con comandos antiguos; no permite otros editores. |

### Compilar el DMG

Requiere macOS 15+, Python 3.12 y las herramientas de línea de comandos de Apple.

```bash
python3.12 -m venv .venv-build
.venv-build/bin/python -m pip install -r requirements-build-mac.lock
.venv-build/bin/python scripts/build_macos.py
```

Se generan archivos `dist/WorkBreak-X.Y.Z-macos-ARQUITECTURA.dmg`, `.pkg` y `.sha256`. La arquitectura depende del Python utilizado: **los instaladores no son universales**. Usa un entorno nativo ARM para Apple Silicon y uno Intel para `x86_64`.

El build verifica la firma estructural y ejecuta una comprobación del binario: interfaz, icono, recursos, certificados HTTPS e importación de la automatización en un proceso separado, sin enviar teclado, mouse ni conectar con la red. `--no-migrate` omite la migración del historial local.

### 🏷️ Crear una versión y publicarla

Necesitas **Node.js 18 o posterior**, Git y acceso de escritura al repositorio. Desde la raíz:

```bash
node scripts/release.js
```

Elige **mayor**, **versión** o **parche** y describe los cambios. Para publicar la primera `1.0.0`, o si ya modificaste `VERSION`, elige **Actual**.

El script muestra la rama, versión, tag y archivos pendientes antes de pedir confirmación. **Incluye todos los cambios no ignorados del proyecto**, crea el commit y el tag anotado y envía rama y tag juntos mediante un push atómico. No reemplaza tags ni hace push forzado.

Para simularlo sin modificar archivos, staging, commits ni tags:

```bash
node scripts/release.js --dry-run --kind parche --description "Corrección de escritura"
```

`VERSION` es la fuente de versión de la aplicación y los instaladores. Como alternativa, `python scripts/version.py patch` solo incrementa ese archivo; también admite `minor` y `major`. No crea commits ni publica nada.

### ⚙️ CI/CD con GitHub Actions

Un tag **`vX.Y.Z`** activa [el workflow de publicación](.github/workflows/release-macos.yml):

1. Verifica que el tag coincida exactamente con `VERSION` y prueba el script de publicación.
2. Ejecuta las pruebas Python y compila por separado **Intel** y **Apple Silicon**.
3. Comprueba los ejecutables y genera DMG, PKG y sumas SHA-256.
4. Adjunta únicamente archivos DMG a una Release en borrador: los instaladores versionados y una copia de cada arquitectura con nombre fijo para los enlaces dinámicos. La publica cuando ambas arquitecturas están disponibles. El actualizador de la aplicación sigue utilizando los nombres versionados.

Una reejecución puede completar un borrador, pero no sustituye archivos de una Release ya publicada. Cada corrección requiere una nueva versión y un nuevo tag. Los tags sin Release o sin instaladores no se ofrecen como actualizaciones instalables.

Los enlaces de descarga no requieren cambios con cada versión. La insignia de versión del código puede actualizarse al preparar una nueva versión.

Si se incorporan certificados de Apple, el build admite `WORKBREAK_CODESIGN_IDENTITY`, `WORKBREAK_INSTALLER_IDENTITY` y `WORKBREAK_NOTARY_PROFILE`. El workflow actual utiliza firma local; no incluye credenciales de distribución ni realiza notarización.

## 🩺 Solución de problemas

| Situación | Qué revisar |
| --- | --- |
| La descarga devuelve 404 | La versión aún no está publicada o el build no terminó. Consulta [Releases](https://github.com/vjose1903/workBreak/releases) y [Actions](https://github.com/vjose1903/workBreak/actions). |
| macOS bloquea la apertura | Revisa **Privacidad y seguridad**. La distribución no está notarizada. |
| No puede detectar tu actividad o controlar ventanas | Concede los permisos a WorkBreak; si ejecutas desde fuente, a la aplicación que lanza Python. |
| No encuentra código en un directorio | Comprueba las extensiones admitidas y el rango de 20 a 400 líneas. |
| Se detiene durante una reescritura | Abre **Ver registro…**. Si la línea o el archivo cambió, la detención evita sobrescribir contenido externo. |
| No permite instalar una actualización | Cierra WorkBreak desde su menú antes de abrir el instalador. |
| No ofrece una actualización | Debe existir una Release estable más reciente con DMG para tu arquitectura. |

Para investigar un problema, comparte la versión, arquitectura, modo de interacción y el fragmento pertinente del registro. Revisa antes si contiene rutas o direcciones privadas.
