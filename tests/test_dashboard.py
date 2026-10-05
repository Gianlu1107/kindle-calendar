import unittest
from server import build_dashboard_html

class TestDashboardScheduleSwitch(unittest.TestCase):
    def test_school_in_progress(self):
        # Lunedì ore 12:30 -> Lezioni ancora in corso
        html = build_dashboard_html({"day": ["lunedi"], "time": ["12:30"]})
        self.assertIn("LEZIONI: Lunedi", html)
        self.assertIn("METEO &amp; PREVISIONI", html.replace("&", "&amp;"))

    def test_school_ended_within_30_minutes(self):
        # Lunedì ore 14:05 -> Lezioni finite alle 13:50 (passati 15 minuti, deve mantenere orario)
        html = build_dashboard_html({"day": ["lunedi"], "time": ["14:05"]})
        self.assertIn("LEZIONI: Lunedi", html)

    def test_school_ended_after_30_minutes(self):
        # Lunedì ore 14:20 -> Esattamente 30 minuti dopo le 13:50: switch a calendario + meteo
        html = build_dashboard_html({"day": ["lunedi"], "time": ["14:20"]})
        self.assertIn("LINEA DEL TEMPO • GIORNATA", html)
        self.assertIn("Lezioni terminate (13:50)", html)
        self.assertIn("METEO &amp; PREVISIONI", html.replace("&", "&amp;"))

    def test_tuesday_early_dismissal(self):
        # Martedì finisce alle 13:00 -> Alle 13:15 mostra ancora lezioni
        html_before = build_dashboard_html({"day": ["martedi"], "time": ["13:15"]})
        self.assertIn("LEZIONI: Martedi", html_before)
        # Alle 13:31 (31m dopo) -> Passa a linea del tempo
        html_after = build_dashboard_html({"day": ["martedi"], "time": ["13:31"]})
        self.assertIn("LINEA DEL TEMPO • GIORNATA", html_after)
        self.assertIn("Lezioni terminate (13:00)", html_after)

    def test_saturday_dismissal(self):
        # Sabato finisce alle 12:05 -> Alle 12:36 (31m dopo) passa a linea del tempo
        html_sat = build_dashboard_html({"day": ["sabato"], "time": ["12:36"]})
        self.assertIn("LINEA DEL TEMPO • GIORNATA", html_sat)
        self.assertIn("Lezioni terminate (12:05)", html_sat)

    def test_morning_backpack(self):
        # Mattina 07:15 -> Mostra checklist zaino mattina
        html_morning = build_dashboard_html({"day": ["lunedi"], "time": ["07:15"]})
        self.assertIn("LEZIONI: Lunedi", html_morning)
        self.assertIn("ZAINO MATTINA • LIBRI DA PORTARE", html_morning)

    def test_evening_backpack_tomorrow_activation(self):
        # Alle 21:20 -> ancora fase pomeridiana/serale (linea del tempo)
        html_before_2130 = build_dashboard_html({"day": ["lunedi"], "time": ["21:20"]})
        self.assertIn("LINEA DEL TEMPO • GIORNATA", html_before_2130)

        # Alle 21:30 esatte -> scatta lo scenario sera (preparazione zaino domani)
        html_at_2130 = build_dashboard_html({"time": ["21:30"]})
        self.assertIn("PREPARAZIONE ZAINO PER DOMANI", html_at_2130)

        # Alle 23:15 -> scenario sera attivo
        html_evening = build_dashboard_html({"time": ["23:15"]})
        self.assertIn("PREPARAZIONE ZAINO PER DOMANI", html_evening)

if __name__ == "__main__":
    unittest.main()
