import sys


def main(argv=None):
    parametros = list(sys.argv[1:] if argv is None else argv)
    terminal = '--terminal' in parametros
    if terminal:
        parametros.remove('--terminal')
    if sys.platform == 'darwin' and not parametros and not terminal:
        try:
            from mac_menu import ejecutar_interfaz
        except ImportError as error:
            print('No se pudo cargar la interfaz de macOS. Instala requirements-mac.txt '
                  'o utiliza --terminal. Detalle: ' + str(error), file=sys.stderr)
            return 1
        return ejecutar_interfaz()
    from automation_bot import AutomationBot
    return AutomationBot().ejecutar(parametros)

if __name__ == "__main__":
    sys.exit(main())
