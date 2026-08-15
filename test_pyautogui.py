#!/usr/bin/env python3
import pyautogui
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_pyautogui():
    """Prueba básica de funcionalidad de pyautogui"""
    print("Iniciando prueba de pyautogui...")
    print("Mueve el mouse a la esquina superior izquierda para activar failsafe si es necesario")
    print("Presiona Ctrl+C para cancelar")
    
    try:
        # Configurar pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.5
        
        # Obtener tamaño de pantalla
        screen_width, screen_height = pyautogui.size()
        print(f"Resolución de pantalla: {screen_width}x{screen_height}")
        
        # Mover al centro
        center_x = screen_width // 2
        center_y = screen_height // 2
        print(f"Moviendo al centro: ({center_x}, {center_y})")
        pyautogui.moveTo(center_x, center_y, duration=1)
        time.sleep(1)
        
        # Hacer clic
        print("Haciendo clic...")
        pyautogui.click()
        time.sleep(1)
        
        # Escribir texto
        print("Escribiendo texto de prueba...")
        pyautogui.write("Hola mundo - prueba de pyautogui", interval=0.1)
        time.sleep(2)
        
        # Seleccionar todo y borrar
        print("Seleccionando todo y borrando...")
        pyautogui.hotkey('cmd', 'a')  # En Mac es cmd, en Windows sería ctrl
        time.sleep(0.5)
        pyautogui.press('backspace')
        time.sleep(1)
        
        # Mover mouse aleatoriamente
        print("Moviendo mouse aleatoriamente...")
        for i in range(5):
            x_offset = pyautogui.randint(-50, 50)
            y_offset = pyautogui.randint(-50, 50)
            pyautogui.moveRel(x_offset, y_offset, duration=0.3)
            time.sleep(0.5)
        
        print("Prueba completada exitosamente!")
        
    except pyautogui.FailSafeException:
        print("Failsafe activado - mouse en esquina superior izquierda")
    except Exception as e:
        print(f"Error durante la prueba: {e}")

if __name__ == "__main__":
    test_pyautogui()

