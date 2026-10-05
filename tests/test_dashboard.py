import unittest
from datetime import date
from server import build_dashboard_html, get_school_day_info

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

    def test_school_day_info_classification(self):
        # Giorno di scuola ordinario (Lunedì 5 Ottobre 2026)
        info_school = get_school_day_info(date(2026, 10, 5))
        self.assertEqual(info_school["category"], "school_day")
        self.assertFalse(info_school["is_holiday"])
        self.assertTrue(info_school["has_school"])

        # Domenica (11 Ottobre 2026)
        info_sun = get_school_day_info(date(2026, 10, 11))
        self.assertEqual(info_sun["category"], "sunday")
        self.assertFalse(info_sun["is_holiday"])
        self.assertFalse(info_sun["has_school"])

        # Vacanze di Natale (28 Dicembre 2026) -> HOLIDAY (winter)
        info_natale = get_school_day_info(date(2026, 12, 28))
        self.assertEqual(info_natale["category"], "holiday")
        self.assertTrue(info_natale["is_holiday"])
        self.assertEqual(info_natale["holiday_type"], "winter")
        self.assertFalse(info_natale["has_school"])

        # Vacanze di Carnevale (9 Febbraio 2027) -> HOLIDAY (carnival)
        info_carnevale = get_school_day_info(date(2027, 2, 9))
        self.assertEqual(info_carnevale["category"], "holiday")
        self.assertTrue(info_carnevale["is_holiday"])
        self.assertEqual(info_carnevale["holiday_type"], "carnival")
        self.assertFalse(info_carnevale["has_school"])

        # Vacanze di Pasqua (27 Marzo 2027) -> HOLIDAY (easter)
        info_pasqua = get_school_day_info(date(2027, 3, 27))
        self.assertEqual(info_pasqua["category"], "holiday")
        self.assertTrue(info_pasqua["is_holiday"])
        self.assertEqual(info_pasqua["holiday_type"], "easter")
        self.assertFalse(info_pasqua["has_school"])

        # Vacanze Estive (15 Luglio 2027) -> HOLIDAY (summer)
        info_estate = get_school_day_info(date(2027, 7, 15))
        self.assertEqual(info_estate["category"], "holiday")
        self.assertTrue(info_estate["is_holiday"])
        self.assertEqual(info_estate["holiday_type"], "summer")
        self.assertFalse(info_estate["has_school"])

        # Ponte dell'Immacolata (7 Dicembre 2026) -> BRIDGE (non holiday grande)
        info_ponte = get_school_day_info(date(2026, 12, 7))
        self.assertEqual(info_ponte["category"], "bridge")
        self.assertFalse(info_ponte["is_holiday"])
        self.assertFalse(info_ponte["has_school"])

    def test_holiday_dashboard_rendering(self):
        # Durante le vacanze di Natale (28 Dicembre 2026):
        # Mostra la linea del tempo (free day come domenica), e NON l'orario delle lezioni
        html_xmas = build_dashboard_html({"date": ["2026-12-28"], "time": ["10:00"]})
        self.assertIn("LINEA DEL TEMPO • GIORNATA", html_xmas)
        self.assertIn("Vacanze • Vacanze di Natale", html_xmas)
        self.assertNotIn("LEZIONI:", html_xmas)

        # Durante le vacanze estive (15 Luglio 2027):
        html_summer = build_dashboard_html({"date": ["2027-07-15"], "time": ["10:00"]})
        self.assertIn("LINEA DEL TEMPO • GIORNATA", html_summer)
        self.assertIn("Vacanze • Vacanze Estive", html_summer)
        self.assertNotIn("LEZIONI:", html_summer)

if __name__ == "__main__":
    unittest.main()
