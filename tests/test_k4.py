import unittest
import dashboard_k4
import nuvola_client

class TestK4Dashboard(unittest.TestCase):
    def test_k4_phases_rendering(self):
        phases = {
            "morning_prep": "ORARIO LEZIONI",
            "school_progress": "IN DIRETTA",
            "afternoon_homework": "ZAINO",
            "night_prep": "SERA/NOTTE"
        }
        for ph, badge in phases.items():
            params = {
                "phase": [ph],
                "time": ["10:00"],
                "batt": ["85"],
                "charging": ["0"]
            }
            html = dashboard_k4.build_k4_dashboard_html(params)
            self.assertIn("<!DOCTYPE html>", html)
            self.assertIn("85%", html)
            self.assertIn(badge, html)

    def test_k4_charging_icon(self):
        params = {
            "phase": ["school_progress"],
            "batt": ["92"],
            "charging": ["1"]
        }
        html = dashboard_k4.build_k4_dashboard_html(params)
        self.assertIn("92%", html)
        self.assertIn("<svg", html)  # Charging bolt svg

    def test_k4_time_and_day_override(self):
        params = {
            "day": ["mercoledi"],
            "time": ["11:30"]
        }
        html = dashboard_k4.build_k4_dashboard_html(params)
        self.assertIn("11:30", html)

    def test_nuvola_client_safe_defaults(self):
        # Assicura che la chiamata con credenziali assenti o placeholder gestisca l'errore senza crash
        cached = nuvola_client.load_cached_compiti(allow_stale=True)
        self.assertIsInstance(cached, list)

if __name__ == "__main__":
    unittest.main()
