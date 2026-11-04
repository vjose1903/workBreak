# Desarrollo y publicación de WorkBreak

La guía de instalación y uso está en el [README](../README.md). Aquí se documentan la ejecución desde código, los instaladores y las publicaciones.

## Ejecutar desde código

Requiere Python 3.12, Git y los [permisos de macOS](../README.md#permisos).

```bash
git clone https://github.com/vjose1903/workBreak.git
cd workBreak
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-mac.txt
python src/main.py
```

Sin argumentos, macOS abre la interfaz de la barra. `python src/main.py --terminal` abre el menú de terminal. Los argumentos de configuración inician directamente la sesión:

```bash
# Editor y navegador durante 60 minutos
python src/main.py -browser chrome -web "https://example.com,https://example.org" -tiempo 60

# Solo editor durante 30 minutos
python src/main.py --modo editor -editor vsCode -tiempo 30

# Solo navegador durante 15 minutos
python src/main.py --modo web -browser chrome -web "https://example.com" -tiempo 15
```

| Argumento | Valores |
| --- | --- |
| `--modo` | `ambos`, `editor`, `web`. |
| `-editor` | `vsCode`, `cursor`, `windsurf`, `vsCodeInsiders`. |
| `-browser` | `chrome`, `edge`, `opera`, `firefox`. |
| `-web` | Direcciones separadas por comas. Para URLs que contienen comas, utiliza la interfaz. |
| `-tiempo` | Minutos enteros positivos o `indefinido`. Sin límite configurado, la ejecución es indefinida. |

**Ctrl+C** solicita el cierre. Las notificaciones del sistema se habilitan en la app compilada; desde Python se usa el aviso interno. Windows conserva dependencias y ejecución por terminal para desarrollo, pero no tiene distribución terminada.

## Comprobaciones

Las pruebas de automatización usan dobles de teclado y mouse. Ejecuta las pruebas cuando corresponda al cambio:

```bash
python -m unittest discover -s tests
node --test tests/release.test.js
```

Las pruebas no sustituyen una corrida funcional en la app firmada. Valida por separado notificaciones, permisos, instalación con autorización, inicio de sesión y comportamiento en cada arquitectura y monitor.

## Compilar para macOS

Requiere macOS 15+, Python 3.12 y las herramientas de línea de comandos de Apple. Configura las identidades de firma descritas más abajo antes de compilar una distribución:

```bash
python3.12 -m venv .venv-build
.venv-build/bin/python -m pip install -r requirements-build-mac.lock
.venv-build/bin/python scripts/build_macos.py --no-migrate
```

Se generan `dist/WorkBreak-X.Y.Z-macos-ARQUITECTURA.dmg`, `.pkg` y `.sha256`. Los instaladores no son universales: la arquitectura depende del Python utilizado. Compila `arm64` e `x86_64` en sus entornos nativos.

El build verifica firma, equipo, identificador, entitlements, icono, recursos, certificados HTTPS e importación de la automatización en un proceso separado. La comprobación del ejecutable no envía teclado ni mouse ni conecta con la red.

Para desarrollo local sin certificados:

```bash
.venv-build/bin/python scripts/build_macos.py --no-migrate --allow-adhoc
```

`--allow-adhoc` se rechaza en CI. Una firma provisional puede requerir renovar permisos entre compilaciones. La notarización es opcional con `WORKBREAK_NOTARY_PROFILE` y un perfil de `notarytool` ya configurado; el workflow no la realiza.

### Firma estable

La distribución exige certificados **Developer ID Application** y **Developer ID Installer** del mismo equipo. Mantén `APP_ID` y el equipo Apple entre versiones; no uses certificados autofirmados como sustituto. El CI falla si faltan credenciales, sin recurrir a firma ad hoc.

Configura en GitHub Actions:

| Tipo | Nombre | Contenido |
| --- | --- | --- |
| Secret | `WORKBREAK_CERTIFICATE_P12_BASE64` | `.p12` codificado en base64 con ambos certificados y sus claves privadas. |
| Secret | `WORKBREAK_CERTIFICATE_PASSWORD` | Contraseña del `.p12`. |
| Variable | `WORKBREAK_CODESIGN_IDENTITY` | `Developer ID Application: Nombre (TEAMID)`. |
| Variable | `WORKBREAK_INSTALLER_IDENTITY` | `Developer ID Installer: Nombre (TEAMID)`. |
| Variable | `WORKBREAK_TEAM_ID` | Identificador de equipo Apple de 10 caracteres. |

En compilaciones locales, las tres variables de identidad se leen del entorno. En CI, los certificados se importan en un llavero temporal que se elimina al finalizar.

La firma conserva Hardened Runtime: `allow-jit` permite los callbacks de PyObjC y, en Intel, se agrega `allow-unsigned-executable-memory`. La firma Developer ID no equivale a notarización ni garantiza que macOS nunca solicite renovar permisos.

## Crear y publicar una versión

Requiere Node.js 18+ y Git con acceso de escritura al repositorio. El script no requiere GitHub CLI:

```bash
node scripts/release.js
```

Elige **Mayor**, **Versión**, **Parche** o **Actual** y describe el cambio. **Actual** publica el valor que ya contiene `VERSION` o permite reintentar un push interrumpido.

Antes de confirmar, el script muestra rama, versión, tag y archivos pendientes. Incluye **todos los cambios no ignorados**, crea commit y tag anotado y envía ambos mediante push atómico. No reemplaza tags ni fuerza el push.

El comando termina al subirlos; **GitHub Actions continúa en segundo plano**. Puedes cerrar la terminal y consultar el progreso en [Actions](https://github.com/vjose1903/workBreak/actions).

```bash
# Simular sin modificar archivos, staging, commits ni tags
node scripts/release.js --dry-run --kind parche --description "Corrección de escritura"
```

Para reintentar el push, elige **Actual** con el checkout limpio y el tag apuntando al commit actual. Esto no reinicia un workflow fallido: reejecútalo desde Actions.

`VERSION` es la única fuente de versión para la app y sus instaladores. `python scripts/version.py patch` solo modifica ese archivo; también admite `minor` y `major`.

### Workflow y artefactos

Un tag `vX.Y.Z` activa [release-macos.yml](../.github/workflows/release-macos.yml):

1. Comprueba la coincidencia con `VERSION` y prueba el flujo de publicación.
2. Ejecuta las pruebas Python y compila por separado Intel y Apple Silicon.
3. Genera DMG, PKG y sumas SHA-256.
4. Publica los DMG cuando validación, pruebas y ambas compilaciones finalizan correctamente.

Cada Release contiene DMG versionados y copias de nombre fijo para los enlaces del README. Los PKG separados y las sumas quedan como artefactos de Actions; el actualizador usa los DMG versionados y el SHA-256 anunciado por GitHub.

Una reejecución puede completar un borrador, pero no reemplaza archivos de una Release publicada. Cada corrección publicada necesita otra versión y tag.

Si el tag ya existe, inicia **Actions → Publicar WorkBreak para macOS → Run workflow**, selecciona `main` e indica el tag. Con GitHub CLI:

```bash
gh workflow run release-macos.yml --ref main -f tag=v1.4.2
```

El workflow compila el código de ese tag; no lo mueve. La descarga solo estará disponible cuando la publicación termine.

## Persistencia y límites

| Dato | App instalada | Código fuente |
| --- | --- | --- |
| Preferencias | `~/Library/Application Support/WorkBreak/preferences.json` | La misma ruta. |
| Historial | `~/Library/Application Support/WorkBreak/config_history.json` | `config_history.json` en la raíz del checkout. |
| Logs | `~/Library/Logs/WorkBreak/workbreak.log` | La interfaz usa esa ruta; el modo de terminal escribe en consola. |
| Instalador | `~/Library/Logs/WorkBreak/update.log` | No aplica fuera de la copia instalada. |

Sin `--no-migrate`, la compilación local puede copiar una vez el historial a Application Support si aún no existe. Los datos personales no se incluyen en el DMG.

- Preferencias e historial: hasta 2 MiB; se rechazan archivos no regulares y JSON excesivamente anidado.
- Fuentes: archivos regulares de hasta 2 MiB y de 20 a 400 líneas; el escaneo se puede cancelar.
- Duración total: de un segundo a `9999:59:59`, o indefinida. Los tiempos internos se definen en [timing_config.py](../src/timing_config.py).
- Consulta de actualizaciones: proceso cancelable con límite total de 30 segundos, incluido DNS. Descarga: 15 minutos.
- Instalación: requiere la app en `/Applications/WorkBreak.app`; comprueba HTTPS, tamaño, SHA-256 y los metadatos del paquete antes de entregarlo al instalador nativo.
- El proceso antirreposo queda ligado al PID del bot. Una interfaz y una sesión de automatización por usuario evitan ejecuciones simultáneas.
