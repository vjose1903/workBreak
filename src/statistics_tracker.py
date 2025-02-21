import time
from collections import defaultdict

class StatisticsTracker:
    def __init__(self):
        self.start_time = time.time()
        self.editor_times = []
        self.web_times = defaultdict(lambda: (0, 0))  # Guardamos tupla (tiempo_total, visitas)
        self.total_web_time = 0
        
    def register_editor_session(self, duration_seconds: float):
        """Registra una sesión de interacción con el editor"""
        self.editor_times.append(duration_seconds)
        
    def register_web_session(self, url: str, duration_seconds: float):
        """Registra una sesión de interacción con una página web"""
        current_time, visit_count = self.web_times[url]
        self.web_times[url] = (current_time + duration_seconds, visit_count + 1)
        self.total_web_time += duration_seconds
        
    def get_total_runtime(self) -> float:
        """Retorna el tiempo total de ejecución del script en segundos"""
        return time.time() - self.start_time
        
    def get_total_editor_time(self) -> float:
        """Retorna el tiempo total en el editor en segundos"""
        return sum(self.editor_times)
        
    def get_total_web_time(self) -> float:
        """Retorna el tiempo total en páginas web en segundos"""
        return self.total_web_time
        
    def get_per_website_stats(self) -> dict:
        """Retorna estadísticas por sitio web: (número de visitas, tiempo total)"""
        return {url: (visits, time_spent) for url, (time_spent, visits) in self.web_times.items()}
    
    def _calculate_percentage(self, part: float, total: float) -> float:
        """Calcula el porcentaje de una parte respecto al total"""
        return (part / total) * 100 if total > 0 else 0
        
    def print_statistics(self):
        """Imprime un resumen estadístico de toda la ejecución"""
        total_runtime = self.get_total_runtime()
        total_editor_time = self.get_total_editor_time()
        total_web_time = self.get_total_web_time()
        website_stats = self.get_per_website_stats()
        
        # Convertir segundos a minutos
        total_runtime_min = total_runtime / 60
        total_editor_min = total_editor_time / 60
        total_web_min = total_web_time / 60
        
        # Imprimir estadísticas
        print("\n" + "="*90)
        print("ESTADÍSTICAS DE EJECUCIÓN")
        print("="*90)
        print(f"Tiempo total de ejecución: {total_runtime_min:.2f} minutos")
        print(f"Tiempo total en editor: {total_editor_min:.2f} minutos ({self._calculate_percentage(total_editor_time, total_runtime):.1f}% del total)")
        print(f"Tiempo total en navegación web: {total_web_min:.2f} minutos ({self._calculate_percentage(total_web_time, total_runtime):.1f}% del total)")
        
        if website_stats:
            print("\nESTADÍSTICAS POR SITIO WEB:")
            print("-"*90)
            print(f"{'URL':<30} {'Visitas':<10} {'Tiempo (min)':<15} {'% del tiempo web':<20}")
            print("-"*90)
            
            for url, (visits, time_spent) in sorted(website_stats.items(), key=lambda x: x[1][1], reverse=True):
                print(f"{url:<30} {visits:<10} {time_spent/60:<15.2f} {self._calculate_percentage(time_spent, total_web_time):<20.1f}%")
        
        print("="*90)
