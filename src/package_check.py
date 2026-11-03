"""Comprobación del ejecutable distribuido sin enviar teclado, mouse ni red."""
import json
import multiprocessing
from pathlib import Path


def _comprobar_hijo(resultados):
    import automation_bot
    import certifi
    import ssl
    from app_version import VERSION
    certificados = ssl.create_default_context(cafile=certifi.where()).cert_store_stats()['x509_ca']
    resultados.put({'version': VERSION, 'automatizacion_importada': hasattr(automation_bot, 'AutomationBot'),
                    'certificados_https': certificados > 0})


def comprobar(destino):
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory, NSStatusBar
    from app_paths import recurso, ruta_historial
    from app_version import VERSION
    from mac_menu import MenuWorkBreak
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    menu = MenuWorkBreak.alloc().init()
    menu.preparar()
    try:
        contexto = multiprocessing.get_context('spawn')
        resultados = contexto.Queue()
        proceso = contexto.Process(target=_comprobar_hijo, args=(resultados,))
        try:
            proceso.start()
            hijo = resultados.get(timeout=30)
            proceso.join(timeout=10)
            if proceso.is_alive() or proceso.exitcode != 0:
                raise RuntimeError('El proceso separado no terminó correctamente')
            reporte = {'version': VERSION, 'hijo': hijo,
                       'icono': menu.item_barra.button().image() is not None,
                       'actualizaciones': menu.actualizar_item.title(),
                       'historial': str(ruta_historial()), 'recursos': recurso('assets/icon.svg').is_file()}
            Path(destino).write_text(json.dumps(reporte, ensure_ascii=False), encoding='utf-8')
            return 0
        finally:
            if proceso.is_alive():
                proceso.terminate()
                proceso.join(timeout=5)
            proceso.close()
            resultados.close()
            resultados.join_thread()
    finally:
        menu.timer.invalidate()
        NSStatusBar.systemStatusBar().removeStatusItem_(menu.item_barra)
        menu.controlador.cerrar()
