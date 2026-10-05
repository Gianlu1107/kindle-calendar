import unittest
import os
import db
from server import get_holiday_tasks

class TestPostgreSQLIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = db.get_connection()
        if cls.conn is not None:
            db.init_db(cls.conn)
            db.seed_from_json(cls.conn)

    def test_01_db_connection(self):
        if self.conn is None:
            self.skipTest("PostgreSQL non raggiungibile nell'ambiente di test")
        self.assertIsNotNone(self.conn)

    def test_02_get_schedule(self):
        if self.conn is None:
            self.skipTest("PostgreSQL non raggiungibile")
        sched = db.get_schedule("3ID")
        self.assertIsNotNone(sched)
        self.assertIn("schedule", sched)
        self.assertIn("lunedi", sched["schedule"])
        self.assertGreater(len(sched["schedule"]["lunedi"]), 0)

    def test_03_get_books(self):
        if self.conn is None:
            self.skipTest("PostgreSQL non raggiungibile")
        books_data = db.get_books("3ID")
        self.assertIsNotNone(books_data)
        self.assertIn("books", books_data)
        self.assertGreater(len(books_data["books"]), 0)

    def test_04_get_calendar_config(self):
        if self.conn is None:
            self.skipTest("PostgreSQL non raggiungibile")
        cal = db.get_calendar_config()
        self.assertIsNotNone(cal)
        self.assertIn("start_date", cal)
        self.assertIn("end_date", cal)
        self.assertIn("holidays", cal)
        self.assertIn("bridges", cal)

    def test_05_get_holiday_tasks_and_update_status(self):
        if self.conn is None:
            self.skipTest("PostgreSQL non raggiungibile")
        tasks = db.get_holiday_tasks_db("summer")
        self.assertIsNotNone(tasks)
        self.assertEqual(len(tasks), 0)

        # Inserimento compito di test
        t_id = db.add_holiday_task(
            holiday_type="summer",
            subject="Test Materia",
            description="Compito di test temporaneo",
            status="NON INIZIATO",
            progress_percent=0
        )
        self.assertIsNotNone(t_id)

        # Aggiornamento stato
        upd_ok = db.update_task_status(t_id, "COMPLETATO", progress_percent=100)
        self.assertTrue(upd_ok)

        # Verifica lettura dal server
        tasks_server = get_holiday_tasks("summer", None, {})
        found = [t for t in tasks_server if t.get("id") == t_id]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["stato"], "COMPLETATO")
        self.assertEqual(found[0]["progress_percent"], 100)

        # Cleanup
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM holiday_tasks WHERE id = %s;", (t_id,))
        self.conn.commit()

if __name__ == "__main__":
    unittest.main()
