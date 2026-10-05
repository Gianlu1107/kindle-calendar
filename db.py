"""
Kindle Calendar Dashboard - PostgreSQL Database Layer
Gestisce la persistenza e le query per:
- Orario scolastico (school_schedule)
- Libri di testo (school_books)
- Calendario scolastico, vacanze e ponti (school_calendar_config, school_holidays, school_bridges)
- Compiti delle vacanze e stato avanzamento (holiday_tasks)
"""

import os
import json
from datetime import datetime, date
import psycopg2
from psycopg2.extras import RealDictCursor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

def get_db_url():
    """Restituisce l'URL di connessione PostgreSQL da env o valori di default."""
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]

    user = os.environ.get("POSTGRES_USER", os.environ.get("USER", "postgres"))
    pwd = os.environ.get("POSTGRES_PASSWORD", "")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    dbname = os.environ.get("POSTGRES_DB", "kindle_calendar")

    auth = f"{user}:{pwd}" if pwd else user
    return f"postgresql://{auth}@{host}:{port}/{dbname}"

def get_connection():
    """Tenta la connessione al database PostgreSQL."""
    try:
        url = get_db_url()
        conn = psycopg2.connect(url, connect_timeout=3)
        return conn
    except Exception as e:
        return None

def init_db(conn=None):
    """Crea tutte le tabelle nel database se non esistono."""
    should_close = False
    if conn is None:
        conn = get_connection()
        if conn is None:
            return False
        should_close = True

    try:
        with conn.cursor() as cur:
            # 1. Tabella classi
            cur.execute("""
            CREATE TABLE IF NOT EXISTS classes (
                id SERIAL PRIMARY KEY,
                class_name VARCHAR(50) NOT NULL UNIQUE,
                school_name VARCHAR(255) NOT NULL,
                specialization VARCHAR(255)
            );
            """)

            # 2. Orario scolastico settimanale
            cur.execute("""
            CREATE TABLE IF NOT EXISTS school_schedule (
                id SERIAL PRIMARY KEY,
                class_name VARCHAR(50) NOT NULL,
                day_of_week VARCHAR(20) NOT NULL,
                period_label VARCHAR(30) NOT NULL,
                ore_num INTEGER[] DEFAULT '{}',
                start_time VARCHAR(5) NOT NULL,
                end_time VARCHAR(5) NOT NULL,
                subject VARCHAR(100) NOT NULL,
                detail TEXT,
                teachers TEXT[] DEFAULT '{}',
                room VARCHAR(50),
                sort_order INTEGER DEFAULT 0
            );
            """)

            # 3. Libri di testo adottati
            cur.execute("""
            CREATE TABLE IF NOT EXISTS school_books (
                id SERIAL PRIMARY KEY,
                class_name VARCHAR(50) NOT NULL,
                subject VARCHAR(100) NOT NULL,
                title VARCHAR(255) NOT NULL,
                subtitle VARCHAR(255),
                author VARCHAR(255),
                publisher VARCHAR(100),
                isbn VARCHAR(30),
                required BOOLEAN DEFAULT TRUE,
                sort_order INTEGER DEFAULT 0
            );
            """)

            # 4. Configurazione calendario scolastico (anno, inizio, fine)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS school_calendar_config (
                id SERIAL PRIMARY KEY,
                school_year VARCHAR(20) NOT NULL UNIQUE,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL
            );
            """)

            # 5. Vacanze scolastiche (natale, carnevale, pasqua con rientro)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS school_holidays (
                id SERIAL PRIMARY KEY,
                school_year VARCHAR(20) NOT NULL,
                holiday_type VARCHAR(50) NOT NULL,
                name VARCHAR(100) NOT NULL,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                resume_date DATE
            );
            """)

            # 6. Ponti e festività singole
            cur.execute("""
            CREATE TABLE IF NOT EXISTS school_bridges (
                id SERIAL PRIMARY KEY,
                school_year VARCHAR(20) NOT NULL,
                bridge_date DATE NOT NULL UNIQUE,
                name VARCHAR(150) NOT NULL
            );
            """)

            # 7. Compiti delle vacanze e relativo stato
            cur.execute("""
            CREATE TABLE IF NOT EXISTS holiday_tasks (
                id SERIAL PRIMARY KEY,
                holiday_type VARCHAR(50) NOT NULL,
                subject VARCHAR(100) NOT NULL,
                description TEXT NOT NULL,
                status VARCHAR(100) NOT NULL,
                progress_percent INTEGER,
                is_test BOOLEAN DEFAULT FALSE,
                due_date DATE,
                notes TEXT,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """)

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print("Errore inizializzazione schema PostgreSQL:", e)
        return False
    finally:
        if should_close:
            conn.close()

def seed_from_json(conn=None, force=False):
    """Popola il database dai file JSON se le tabelle sono vuote (o force=True)."""
    should_close = False
    if conn is None:
        conn = get_connection()
        if conn is None:
            return False
        should_close = True

    try:
        with conn.cursor() as cur:
            # 1. Seed orario e classe
            cur.execute("SELECT COUNT(*) FROM school_schedule;")
            count_sched = cur.fetchone()[0]
            orario_path = os.path.join(DATA_DIR, "orario_3id.json")
            if (count_sched == 0 or force) and os.path.exists(orario_path):
                if force:
                    cur.execute("TRUNCATE TABLE school_schedule, classes CASCADE;")
                with open(orario_path, "r", encoding="utf-8") as f:
                    o_data = json.load(f)
                class_name = o_data.get("class", "3ID")
                school_name = o_data.get("school", "ITI Francesco Severi - Padova")
                cur.execute("""
                INSERT INTO classes (class_name, school_name, specialization)
                VALUES (%s, %s, %s)
                ON CONFLICT (class_name) DO UPDATE SET school_name = EXCLUDED.school_name;
                """, (class_name, school_name, "Informatica e Telecomunicazioni"))

                order = 0
                for day, lessons in o_data.get("schedule", {}).items():
                    for les in lessons:
                        cur.execute("""
                        INSERT INTO school_schedule (
                            class_name, day_of_week, period_label, ore_num,
                            start_time, end_time, subject, detail, teachers, room, sort_order
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                        """, (
                            class_name, day, les.get("ora", ""), les.get("ore_num", []),
                            les.get("inizio", ""), les.get("fine", ""), les.get("materia", ""),
                            les.get("dettaglio", ""), les.get("docenti", []), les.get("aula", ""), order
                        ))
                        order += 1

            # 2. Seed libri
            cur.execute("SELECT COUNT(*) FROM school_books;")
            count_books = cur.fetchone()[0]
            libri_path = os.path.join(DATA_DIR, "libri_3id.json")
            if (count_books == 0 or force) and os.path.exists(libri_path):
                if force:
                    cur.execute("TRUNCATE TABLE school_books CASCADE;")
                with open(libri_path, "r", encoding="utf-8") as f:
                    l_data = json.load(f)
                class_name = l_data.get("class", "3ID")
                for idx, b in enumerate(l_data.get("books", [])):
                    cur.execute("""
                    INSERT INTO school_books (
                        class_name, subject, title, subtitle, author, publisher, isbn, required, sort_order
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """, (
                        class_name, b.get("subject", ""), b.get("title", ""), b.get("subtitle", ""),
                        b.get("author", ""), b.get("publisher", ""), b.get("isbn", ""),
                        b.get("required", True), idx
                    ))

            # 3. Seed calendario scolastico, vacanze e ponti
            cur.execute("SELECT COUNT(*) FROM school_calendar_config;")
            count_cal = cur.fetchone()[0]
            vacanze_path = os.path.join(DATA_DIR, "vacanze_scolastiche.json")
            if (count_cal == 0 or force) and os.path.exists(vacanze_path):
                if force:
                    cur.execute("TRUNCATE TABLE school_calendar_config, school_holidays, school_bridges CASCADE;")
                with open(vacanze_path, "r", encoding="utf-8") as f:
                    v_data = json.load(f)

                school_year = v_data.get("school_year", "2026/2027")
                sy_start = v_data.get("school_year_start", "2026-09-10")
                sy_end = v_data.get("school_year_end", "2027-06-08")
                cur.execute("""
                INSERT INTO school_calendar_config (school_year, start_date, end_date)
                VALUES (%s, %s, %s)
                ON CONFLICT (school_year) DO UPDATE SET start_date = EXCLUDED.start_date, end_date = EXCLUDED.end_date;
                """, (school_year, sy_start, sy_end))

                for h in v_data.get("holidays", []):
                    res_date = h.get("resume_date")
                    cur.execute("""
                    INSERT INTO school_holidays (school_year, holiday_type, name, start_date, end_date, resume_date)
                    VALUES (%s, %s, %s, %s, %s, %s);
                    """, (school_year, h["type"], h["name"], h["start"], h["end"], res_date))

                for b_date, b_name in v_data.get("bridges", {}).items():
                    cur.execute("""
                    INSERT INTO school_bridges (school_year, bridge_date, name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (bridge_date) DO UPDATE SET name = EXCLUDED.name;
                    """, (school_year, b_date, b_name))

            # 4. Seed compiti vacanze con stato
            cur.execute("SELECT COUNT(*) FROM holiday_tasks;")
            count_tasks = cur.fetchone()[0]
            compiti_path = os.path.join(DATA_DIR, "compiti_vacanze.json")
            if (count_tasks == 0 or force) and os.path.exists(compiti_path):
                if force:
                    cur.execute("TRUNCATE TABLE holiday_tasks CASCADE;")
                with open(compiti_path, "r", encoding="utf-8") as f:
                    c_data = json.load(f)

                for h_type, tasks in c_data.items():
                    for idx, t in enumerate(tasks):
                        # Calcola progress_percent se presente nella stringa di stato (es. "IN CORSO • 57%")
                        prog = None
                        st = t.get("stato", "")
                        if "%" in st:
                            try:
                                prog = int(st.split("%")[0].split()[-1].replace("•", "").strip())
                            except Exception:
                                pass
                        elif st.upper() == "COMPLETATO":
                            prog = 100

                        cur.execute("""
                        INSERT INTO holiday_tasks (
                            holiday_type, subject, description, status, progress_percent, is_test, sort_order
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s);
                        """, (
                            h_type, t.get("materia", ""), t.get("descrizione", ""),
                            st, prog, t.get("is_test", False), idx
                        ))

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print("Errore durante il seeding da JSON a PostgreSQL:", e)
        return False
    finally:
        if should_close:
            conn.close()

# --------------------------------------------------------------------------
# Funzioni di Query per il Server e la Dashboard
# --------------------------------------------------------------------------

def get_schedule(class_name="3ID"):
    """Recupera l'orario scolastico strutturato da PostgreSQL."""
    conn = get_connection()
    if conn is None:
        return None

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
            SELECT s.day_of_week, s.period_label, s.ore_num, s.start_time, s.end_time,
                   s.subject, s.detail, s.teachers, s.room, c.school_name, c.class_name
            FROM school_schedule s
            LEFT JOIN classes c ON c.class_name = s.class_name
            WHERE s.class_name = %s
            ORDER BY s.sort_order, s.id;
            """, (class_name,))
            rows = cur.fetchall()

        if not rows:
            return None

        sched = {}
        school_name = "ITI Francesco Severi - Padova"
        for r in rows:
            day = r["day_of_week"]
            if day not in sched:
                sched[day] = []
            school_name = r.get("school_name") or school_name
            les = {
                "ora": r["period_label"],
                "ore_num": r["ore_num"] or [],
                "inizio": r["start_time"],
                "fine": r["end_time"],
                "materia": r["subject"],
                "aula": r["room"] or "",
                "docenti": r["teachers"] or []
            }
            if r.get("detail"):
                les["dettaglio"] = r["detail"]
            sched[day].append(les)

        return {
            "class": class_name,
            "school": school_name,
            "schedule": sched
        }
    except Exception as e:
        print("Errore query get_schedule:", e)
        return None
    finally:
        conn.close()

def get_books(class_name="3ID"):
    """Recupera l'elenco dei libri di testo da PostgreSQL."""
    conn = get_connection()
    if conn is None:
        return None

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
            SELECT subject, title, subtitle, author, publisher, isbn, required
            FROM school_books
            WHERE class_name = %s
            ORDER BY sort_order, id;
            """, (class_name,))
            rows = cur.fetchall()

        if not rows:
            return None

        return {
            "class": class_name,
            "books": [
                {
                    "subject": r["subject"],
                    "title": r["title"],
                    "subtitle": r["subtitle"] or "",
                    "author": r["author"] or "",
                    "publisher": r["publisher"] or "",
                    "isbn": r["isbn"] or "",
                    "required": r["required"]
                }
                for r in rows
            ]
        }
    except Exception as e:
        print("Errore query get_books:", e)
        return None
    finally:
        conn.close()

def get_calendar_config(school_year="2026/2027"):
    """Recupera le date di inizio/fine anno, vacanze e ponti da PostgreSQL."""
    conn = get_connection()
    if conn is None:
        return None

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Anno scolastico
            cur.execute("SELECT start_date, end_date FROM school_calendar_config WHERE school_year = %s;", (school_year,))
            conf = cur.fetchone()
            if not conf:
                # Fallback al più recente
                cur.execute("SELECT start_date, end_date, school_year FROM school_calendar_config ORDER BY id DESC LIMIT 1;")
                conf = cur.fetchone()

            if not conf:
                return None

            start_d = conf["start_date"]
            end_d = conf["end_date"]

            # Vacanze
            cur.execute("""
            SELECT holiday_type, name, start_date, end_date, resume_date
            FROM school_holidays
            ORDER BY start_date;
            """)
            holidays = [
                {
                    "type": r["holiday_type"],
                    "name": r["name"],
                    "start": r["start_date"],
                    "end": r["end_date"],
                    "resume_date": r["resume_date"].strftime("%Y-%m-%d") if r["resume_date"] else None
                }
                for r in cur.fetchall()
            ]

            # Ponti
            cur.execute("SELECT bridge_date, name FROM school_bridges ORDER BY bridge_date;")
            bridges = {r["bridge_date"].strftime("%Y-%m-%d"): r["name"] for r in cur.fetchall()}

        return {
            "start_date": start_d,
            "end_date": end_d,
            "holidays": holidays,
            "bridges": bridges
        }
    except Exception as e:
        print("Errore query get_calendar_config:", e)
        return None
    finally:
        conn.close()

def get_holiday_tasks_db(holiday_type):
    """Recupera i compiti e lo stato avanzamento per il tipo di vacanza specificato."""
    conn = get_connection()
    if conn is None:
        return None

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
            SELECT id, holiday_type, subject, description, status, progress_percent, is_test, due_date
            FROM holiday_tasks
            WHERE holiday_type = %s
            ORDER BY sort_order, id;
            """, (holiday_type,))
            rows = cur.fetchall()

        return [
            {
                "id": r["id"],
                "materia": r["subject"],
                "descrizione": r["description"],
                "stato": r["status"],
                "progress_percent": r["progress_percent"],
                "is_test": r["is_test"],
                "due_date": r["due_date"].strftime("%Y-%m-%d") if r["due_date"] else None
            }
            for r in rows
        ]
    except Exception as e:
        print(f"Errore query get_holiday_tasks_db ({holiday_type}):", e)
        return None
    finally:
        conn.close()

def update_task_status(task_id, new_status, progress_percent=None):
    """Aggiorna lo stato e la percentuale di completamento di un compito."""
    conn = get_connection()
    if conn is None:
        return False

    try:
        with conn.cursor() as cur:
            if progress_percent is not None:
                cur.execute("""
                UPDATE holiday_tasks
                SET status = %s, progress_percent = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
                """, (new_status, progress_percent, task_id))
            else:
                cur.execute("""
                UPDATE holiday_tasks
                SET status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s;
                """, (new_status, task_id))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print("Errore update_task_status:", e)
        return False
    finally:
        conn.close()

def add_holiday_task(holiday_type, subject, description, status, progress_percent=None, is_test=False, due_date=None):
    """Inserisce un nuovo compito nel database."""
    conn = get_connection()
    if conn is None:
        return None

    try:
        with conn.cursor() as cur:
            cur.execute("""
            INSERT INTO holiday_tasks (holiday_type, subject, description, status, progress_percent, is_test, due_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
            """, (holiday_type, subject, description, status, progress_percent, is_test, due_date))
            task_id = cur.fetchone()[0]
        conn.commit()
        return task_id
    except Exception as e:
        conn.rollback()
        print("Errore add_holiday_task:", e)
        return None
    finally:
        conn.close()

if __name__ == "__main__":
    print("Inizializzazione database PostgreSQL...")
    ok = init_db()
    if ok:
        print("Schema tabelle verificato/creato con successo.")
        seeded = seed_from_json()
        print(f"Seeding da file JSON completato: {seeded}")
    else:
        print("Impossibile connettersi al database PostgreSQL.")
