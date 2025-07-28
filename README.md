# Bot de Interacción con Editor y Navegador

<p style="background-color: #FFEB3B; color: #D32F2F; padding: 10px; font-weight: bold;"> ¡¡¡Advertencia!!! Si tienes múltiples monitores, asegúrate de mantener tanto el navegador como el editor en la misma pantalla donde se ejecuta el script para evitar problemas de interacción.</p>

Este bot permite interactuar automáticamente con un editor de código y un navegador web, simulando escritura, movimientos del mouse y clics. **Incluye optimización automática de código usando Ollama (IA gratuita y local).**

## 🚀 Inicio Rápido

```bash
# 1. Clonar e instalar dependencias
git clone https://github.com/vjose1903/workBreak
cd workBreak
./setup.sh  # o setup.bat en Windows

# 2. Configurar (opcional)
cp env.example .env

# 3. Ejecutar
python src/bot.py -editor cursor -tiempo 3600
```

## Requisitos

* Python 3.x
* Pip (administrador de paquetes de Python)
* Ollama (para optimización de código con IA)

### Requisitos del sistema para Ollama

**Mínimos:**

* 4GB RAM
* 4GB espacio en disco
* CPU compatible con AVX2

**Recomendados:**

* 8GB RAM
* 8GB espacio en disco
* GPU compatible (opcional, mejora el rendimiento)

### Dependencias Generales

* `pyautogui`
* `argparse`
* `pygetwindow`

* `pyperclip`
* `python-dotenv`

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

## Configuración de IA (Opcional)

El bot usa Ollama para optimizar código automáticamente. Ollama es completamente gratuito y funciona localmente en tu computadora.

### 1. Instalar Ollama

**En macOS:**

```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

**En Windows:**

1. Descarga desde [ollama.ai](https://ollama.ai/download)
2. Ejecuta el instalador descargado
3. Ollama se ejecutará automáticamente en segundo plano

**En Linux:**

```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

**En Docker:**

```bash
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama
```

### 2. Verificar instalación

```bash
ollama --version
```

### 3. Descargar modelo de código

```bash
# Modelo recomendado para optimización de código
ollama pull codellama:7b

# Modelo más potente (mayor calidad pero más lento)
ollama pull codellama:13b
```

### 4. Verificar que Ollama esté funcionando

```bash
# Ver modelos disponibles
ollama list

# Probar que funciona
ollama run codellama:7b "console.log('Hello World')"
```

### 5. Configurar el archivo .env

1. Copia el archivo de ejemplo:

```bash
cp env.example .env
```

2. El archivo `.env` ya está configurado por defecto para usar Ollama:

```bash
# Ollama (completamente gratuito)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=codellama:7b
OLLAMA_TIMEOUT=15
```

**Nota**: El archivo `.env` ya está incluido en `.gitignore` para mantener tu configuración segura.

### Solución de problemas con Ollama

**Ollama no responde:**

```bash
# Reiniciar Ollama
ollama serve

# Verificar que esté ejecutándose
ps aux | grep ollama
```

**Modelo no encontrado:**

```bash
# Ver modelos disponibles
ollama list

# Descargar modelo específico
ollama pull codellama:7b
```

**Puerto ocupado:**

```bash
# Cambiar puerto en .env
OLLAMA_URL=http://localhost:11435
```

**Memoria insuficiente:**

```bash
# Usar modelo más pequeño
ollama pull codellama:1b
```

**Timeout al optimizar código:**

```bash
# Reducir timeout en .env
OLLAMA_TIMEOUT=10

# O usar modelo más rápido
OLLAMA_MODEL=codellama:1b
```

**Modelo no responde:**

```bash
# Verificar que el modelo esté descargado
ollama list

# Re-descargar el modelo
ollama pull codellama:7b
```



## Uso

Ejecutar el script con los parámetros requeridos:

```bash
python src/bot.py -editor vsCode -browser chrome -web "https://google.com,https://github.com" -tiempo 3600
```

### Parámetros

* `-editor` (requerido): Editor a usar (`cursor` o `vsCode`)
* `-browser` (opcional): Navegador a usar (`chrome`, `edge`, `opera`, `firefox`)
* `-web` (opcional): Lista de URLs separadas por coma
* `-tiempo` (opcional): Tiempo en segundos que el script debe ejecutarse. Si no se proporciona, el script se ejecutará indefinidamente.

## Funcionamiento

1. Abre el editor especificado.
2. **Selecciona aleatoriamente un archivo de código** de la carpeta `src/boilerplate/` (archivos `.ts`, `.tsx`, `.js`, `.jsx`).
3. **Escribe el código completo** del archivo seleccionado en el editor.
4. **Interacciones adicionales**:
   - Hace clics aleatorios en la ventana
   - Mueve el scroll arriba y abajo
   - Cierra la pestaña actual
   - Abre una nueva pestaña para el siguiente archivo
5. Si se especifican URLs, abre el navegador y navega por ellas, realizando clics aleatorios.
6. Regresa al editor y continúa la simulación en un bucle infinito o hasta que se haya alcanzado el tiempo especificado por el parámetro `-tiempo`.
7. El script se detendrá automáticamente una vez transcurrido el tiempo indicado (si se especificó `-tiempo`), o continuará indefinidamente hasta que el usuario lo detenga manualmente.

## Detener el bot

Para finalizar el script, presiona `CTRL + C` en la terminal.

## Notas

* En Windows, puede ser necesario ejecutar la terminal como administrador para que `pyautogui` funcione correctamente.
* En macOS, puede requerir permisos adicionales de accesibilidad en `Preferencias del Sistema > Seguridad y privacidad > Accesibilidad`.
* **Escritura rápida**: El bot escribe código súper rápido con intervalo configurable.
* **Interacciones realistas**: Simula clics, scroll y navegación entre pestañas.
* **Archivos de boilerplate**: Lee archivos de la carpeta `src/boilerplate/` de forma aleatoria.
* **Archivos de boilerplate**: El bot lee archivos de la carpeta `src/boilerplate/`. Puedes agregar tus propios archivos de código (`.ts`, `.tsx`, `.js`, `.jsx`) para que el bot los use durante la simulación.
