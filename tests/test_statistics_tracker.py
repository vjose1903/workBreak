import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from statistics_tracker import StatisticsTracker


class StatisticsTrackerTest(unittest.TestCase):
    def setUp(self):
        self.tracker = StatisticsTracker()

    def test_inicialmente_ceros(self):
        self.assertEqual(self.tracker.get_total_editor_time(), 0.0)
        self.assertEqual(self.tracker.get_editor_sessions(), 0)
        self.assertEqual(self.tracker.get_total_web_time(), 0.0)
        self.assertEqual(self.tracker.get_per_website_stats(), {})

    def test_editor_sessions_acumulan(self):
        self.tracker.register_editor_session(120.5)
        self.tracker.register_editor_session(60.25)
        self.assertAlmostEqual(self.tracker.get_total_editor_time(), 180.75)
        self.assertEqual(self.tracker.get_editor_sessions(), 2)

    def test_web_sessions_acumulan_por_url(self):
        self.tracker.register_web_session('https://example.com', 30.0)
        self.tracker.register_web_session('https://example.com', 45.0)
        self.tracker.register_web_session('https://otro.org', 10.0)
        self.assertAlmostEqual(self.tracker.get_total_web_time(), 85.0)
        stats = self.tracker.get_per_website_stats()
        visitas, tiempo = stats['https://example.com']
        self.assertEqual(visitas, 2)
        self.assertAlmostEqual(tiempo, 75.0)
        visitas, tiempo = stats['https://otro.org']
        self.assertEqual(visitas, 1)
        self.assertAlmostEqual(tiempo, 10.0)

    def test_editor_y_web_son_independientes(self):
        self.tracker.register_editor_session(50.0)
        self.tracker.register_web_session('https://a.com', 20.0)
        self.assertAlmostEqual(self.tracker.get_total_editor_time(), 50.0)
        self.assertAlmostEqual(self.tracker.get_total_web_time(), 20.0)
        self.assertEqual(self.tracker.get_editor_sessions(), 1)

    def test_get_total_runtime_no_negativo(self):
        self.assertGreaterEqual(self.tracker.get_total_runtime(), 0.0)

    def test_print_statistics(self):
        self.tracker.register_editor_session(60.0)
        self.tracker.register_editor_session(30.0)
        self.tracker.register_web_session('https://a.com', 30.0)
        self.tracker.register_web_session('https://b.com', 15.0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.tracker.print_statistics()
        salida = buf.getvalue()
        self.assertIn('ESTADÍSTICAS DE EJECUCIÓN', salida)
        self.assertIn('Sesiones de editor registradas: 2', salida)
        self.assertIn('Tiempo total en editor', salida)
        self.assertIn('Tiempo total en navegación web', salida)
        self.assertIn('https://a.com', salida)
        self.assertIn('https://b.com', salida)


if __name__ == '__main__':
    unittest.main()
