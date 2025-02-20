import argparse
import time
import random
import pyautogui
import webbrowser
import subprocess
import os

def validar_editor(value):
    if value not in ["cursor", "vsCode"]:
        raise argparse.ArgumentTypeError("El editor debe ser 'cursor' o 'vsCode'")
    return value

def validar_browser(value):
    navegadores = ["chrome", "edge", "opera", "firefox"]
    if value not in navegadores:
        raise argparse.ArgumentTypeError(f"El navegador debe ser uno de {navegadores}")
    return value

def abrir_editor(editor):
    if editor == "cursor":
        subprocess.Popen(["code", "--disable-extensions"], shell=True if os.name == "nt" else False)
    elif editor == "vsCode":
        subprocess.Popen(["code"], shell=True if os.name == "nt" else False)
    time.sleep(5)  # Esperar a que el editor abra completamente

def interactuar_editor():
    for _ in range(10):  # Simula 10 interacciones dentro del editor
        texto = "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=10))
        pyautogui.write(texto, interval=0.1)
        time.sleep(1)
        pyautogui.hotkey("ctrl" if os.name == "nt" else "command", "a")
        pyautogui.press("backspace")
        time.sleep(1)
        pyautogui.moveRel(random.randint(-50, 50), random.randint(-50, 50), duration=0.5)
        pyautogui.click()

def abrir_paginas(browser, paginas):
    if browser:
        webbrowser.get(browser).open(paginas[0])  # Abre la primera web en el navegador especificado
        for pagina in paginas[1:]:
            time.sleep(2)
            webbrowser.open_new_tab(pagina)
    else:
        for pagina in paginas:
            webbrowser.open(pagina)
    time.sleep(5)

def interactuar_web():
    for _ in range(10):  # Simula clics aleatorios en la web
        pyautogui.moveRel(random.randint(-100, 100), random.randint(-100, 100), duration=0.5)
        pyautogui.click()
        time.sleep(random.uniform(1, 3))

def main():
    parser = argparse.ArgumentParser(description="Bot de interacción con editor y navegador")
    parser.add_argument("-editor", type=validar_editor, required=True, help="Editor a usar: cursor o vsCode")
    parser.add_argument("-browser", type=validar_browser, required=False, help="Navegador a usar")
    parser.add_argument("-web", type=str, required=False, help="Lista de webs separadas por coma")
    
    args = parser.parse_args()
    paginas = args.web.split(",") if args.web else []
    
    abrir_editor(args.editor)
    
    while True:
        interactuar_editor()
        
        if paginas:
            abrir_paginas(args.browser, paginas)
            interactuar_web()
        
        interactuar_editor()

if __name__ == "__main__":
    main()
