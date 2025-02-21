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

Ejecutar el script con los parámetros requeridos:

```bash
python src/bot.py -editor vsCode -browser chrome -web "https://google.com,https://chat.openai.com" -tiempo 3600
```

### Parámetros

* `-editor` (requerido): Editor a usar (`cursor` o `vsCode`)
* `-browser` (opcional): Navegador a usar (`chrome`, `edge`, `opera`, `firefox`)
* `-web` (opcional): Lista de URLs separadas por coma
* `-tiempo` (opcional): Tiempo en segundos que el script debe ejecutarse. Si no se proporciona, el script se ejecutará indefinidamente.

## Funcionamiento

1. Abre el editor especificado.
2. Simula escritura y movimiento del mouse dentro del editor durante 3 minutos.
3. Si se especifican URLs, abre el navegador y navega por ellas, realizando clics aleatorios.
4. Regresa al editor y continúa la simulación en un bucle infinito o hasta que se haya alcanzado el tiempo especificado por el parámetro `-tiempo`.
5. El script se detendrá automáticamente una vez transcurrido el tiempo indicado (si se especificó `-tiempo`), o continuará indefinidamente hasta que el usuario lo detenga manualmente.

## Detener el bot

Para finalizar el script, presiona `CTRL + C` en la terminal.

## Notas

* En Windows, puede ser necesario ejecutar la terminal como administrador para que `pyautogui` funcione correctamente.
* En macOS, puede requerir permisos adicionales de accesibilidad en `Preferencias del Sistema > Seguridad y privacidad > Accesibilidad`.
