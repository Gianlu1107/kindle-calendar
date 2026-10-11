import os
import json
import re
import threading
import time as pytime
from datetime import datetime, timedelta, time, date
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.parse
import http.cookiejar

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")

_EMOJI_PATTERN = re.compile(
    r"[\U0001F600-\U0001F64F"
    r"\U0001F300-\U0001F5FF"
    r"\U0001F680-\U0001F6FF"
    r"\U0001F1E0-\U0001F1FF"
    r"\U00002702-\U000027B0"
    r"\U000024C2-\U0001F251"
    r"\U0001F900-\U0001F9FF"
    r"\U0001FA70-\U0001FAFF"
    r"\U00002600-\U000026FF]+",
    flags=re.UNICODE
)

def strip_emojis(text):
    if not text:
        return ""
    cleaned = _EMOJI_PATTERN.sub("", text)
    return " ".join(cleaned.split()).strip()

import db

# Carica orario e libri con supporto orario temporaneo speciale (fino al 21/10/2026)
def load_orario_data(target_date=None):
    if target_date is None:
        target_date = datetime.now().date()
    elif isinstance(target_date, datetime):
        target_date = target_date.date()

    # Orario provvisorio speciale (fino al 21/10/2026 incluso).
    # Dal 22/10/2026 torna automaticamente all'orario predefinito standard.
    if target_date <= date(2026, 10, 21):
        temp_path = os.path.join(DATA_DIR, "orario_3id_temp.json")
        if os.path.exists(temp_path):
            try:
                with open(temp_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

    try:
        data = db.get_schedule("3ID")
        if data and data.get("schedule"):
            return data
    except Exception:
        pass
    with open(os.path.join(DATA_DIR, "orario_3id.json"), "r", encoding="utf-8") as f:
        return json.load(f)

def load_libri_data():
    try:
        data = db.get_books("3ID")
        if data and data.get("books"):
            return data
    except Exception:
        pass
    with open(os.path.join(DATA_DIR, "libri_3id.json"), "r", encoding="utf-8") as f:
        return json.load(f)

ORARIO_DATA = load_orario_data()
LIBRI_DATA = load_libri_data()

GIORNI_MAP = {
    0: "lunedi",
    1: "martedi",
    2: "mercoledi",
    3: "giovedi",
    4: "venerdi",
    5: "sabato",
    6: "domenica"
}

GIORNI_NOMI_IT = {
    0: "Lunedì",
    1: "Martedì",
    2: "Mercoledì",
    3: "Giovedì",
    4: "Venerdì",
    5: "Sabato",
    6: "Domenica"
}

# Calendario Scolastico Regione Veneto 2026/2027 (DGR n. 239/2026 e DGR n. 712/2026)
# ITI Francesco Severi - Padova
SCHOOL_YEAR_START_2026_2027 = date(2026, 9, 10)  # Inizio ufficiale lezioni: 10 settembre 2026
SCHOOL_YEAR_END_2026_2027 = date(2027, 6, 8)    # Fine ufficiale lezioni: 8 giugno 2027

# Grandi Vacanze Scolastiche (categorizzate esplicitamente come 'holiday')
# Include: Vacanze Estive (pre/post anno scolastico), Vacanze Invernali/Natale, Carnevale, Pasqua
SCHOOL_HOLIDAYS_2026_2027 = [
    # Vacanze Natalizie / Invernali: 24 dicembre 2026 - 6 gennaio 2027
    {
        "type": "winter",
        "name": "Vacanze di Natale",
        "start": date(2026, 12, 24),
        "end": date(2027, 1, 6)
    },
    # Vacanze di Carnevale e Mercoledì delle Ceneri: 8 - 10 febbraio 2027
    {
        "type": "carnival",
        "name": "Vacanze di Carnevale",
        "start": date(2027, 2, 8),
        "end": date(2027, 2, 10)
    },
    # Vacanze Pasquali: 25 - 30 marzo 2027
    {
        "type": "easter",
        "name": "Vacanze di Pasqua",
        "start": date(2027, 3, 25),
        "end": date(2027, 3, 30)
    }
]

# Ponti e Festività Nazionali/Locali (categorizzati come 'bridge' o 'festivity', NON come 'holiday')
SCHOOL_BRIDGES_2026_2027 = {
    "2026-11-01": "Tutti i Santi",
    "2026-12-07": "Ponte dell'Immacolata",
    "2026-12-08": "Immacolata Concezione",
    "2027-04-25": "Festa della Liberazione",
    "2027-04-29": "Ponte 1° Maggio",
    "2027-04-30": "Ponte 1° Maggio",
    "2027-05-01": "Festa del Lavoro",
    "2027-05-31": "Ponte 2 Giugno",
    "2027-06-01": "Ponte 2 Giugno",
    "2027-06-02": "Festa della Repubblica",
    "2027-06-13": "Sant'Antonio (Patrono Padova)"
}

def load_school_calendar_config():
    global SCHOOL_YEAR_START_2026_2027, SCHOOL_YEAR_END_2026_2027, SCHOOL_HOLIDAYS_2026_2027, SCHOOL_BRIDGES_2026_2027
    try:
        c_conf = db.get_calendar_config()
        if c_conf:
            SCHOOL_YEAR_START_2026_2027 = c_conf["start_date"]
            SCHOOL_YEAR_END_2026_2027 = c_conf["end_date"]
            SCHOOL_HOLIDAYS_2026_2027 = c_conf["holidays"]
            SCHOOL_BRIDGES_2026_2027 = c_conf["bridges"]
            return
    except Exception:
        pass

    cfg_file = os.path.join(DATA_DIR, "vacanze_scolastiche.json")
    if os.path.exists(cfg_file):
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "school_year_start" in data:
                y, m, d = map(int, data["school_year_start"].split("-"))
                SCHOOL_YEAR_START_2026_2027 = date(y, m, d)
            if "school_year_end" in data:
                y, m, d = map(int, data["school_year_end"].split("-"))
                SCHOOL_YEAR_END_2026_2027 = date(y, m, d)
            if "holidays" in data:
                h_list = []
                for h in data["holidays"]:
                    sy, sm, sd = map(int, h["start"].split("-"))
                    ey, em, ed = map(int, h["end"].split("-"))
                    h_list.append({
                        "type": h["type"],
                        "name": h["name"],
                        "start": date(sy, sm, sd),
                        "end": date(ey, em, ed),
                        "resume_date": h.get("resume_date")
                    })
                SCHOOL_HOLIDAYS_2026_2027 = h_list
            if "bridges" in data:
                SCHOOL_BRIDGES_2026_2027 = data["bridges"]
        except Exception as e:
            print("Avviso caricamento vacanze_scolastiche.json:", e)

load_school_calendar_config()

def get_holiday_tasks(holiday_type, target_d_obj, env):
    """
    Carica i compiti per il periodo di vacanza ('summer', 'winter', 'carnival', 'easter').
    Interroga prioritariamente PostgreSQL (holiday_tasks); in caso di assenza o errore,
    utilizza il fallback su data/compiti_vacanze.json ed eventuale integrazione da ClasseViva.
    """
    tasks = []
    try:
        db_tasks = db.get_holiday_tasks_db(holiday_type)
        if db_tasks is not None and len(db_tasks) > 0:
            return db_tasks
    except Exception:
        pass

    vacanze_file = os.path.join(DATA_DIR, "compiti_vacanze.json")
    if os.path.exists(vacanze_file):
        try:
            with open(vacanze_file, "r", encoding="utf-8") as vf:
                raw_v = json.load(vf)
                if isinstance(raw_v, dict) and holiday_type in raw_v:
                    tasks = list(raw_v[holiday_type])
                elif isinstance(raw_v, list):
                    tasks = raw_v
        except Exception as e:
            print("Errore lettura compiti_vacanze.json:", e)

    return tasks

def get_school_day_info(target_d):
    """
    Classifica con precisione il giorno target rispetto al calendario scolastico.
    Ritorna:
      - category: 'school_day' | 'holiday' | 'bridge' | 'sunday'
      - is_holiday: True SOLO per grandi vacanze (estive, invernali, carnevale, pasqua)
      - holiday_type: 'summer' | 'winter' | 'carnival' | 'easter' | None
      - label: Denominazione testuale della vacanza, ponte o festività
      - has_school: True solo se è un giorno di scuola effettivo (Lun-Sab senza feste o vacanze)
    """
    if isinstance(target_d, datetime):
        d_val = target_d.date()
    else:
        d_val = target_d

    iso_str = d_val.strftime("%Y-%m-%d")

    # 1. Vacanze Estive (prima dell'inizio o dopo la fine delle lezioni)
    if d_val < SCHOOL_YEAR_START_2026_2027 or d_val > SCHOOL_YEAR_END_2026_2027:
        return {
            "category": "holiday",
            "is_holiday": True,
            "holiday_type": "summer",
            "label": "Vacanze Estive",
            "has_school": False
        }

    # 2. Grandi Vacanze Scolastiche (Invernali/Natale, Carnevale, Pasqua)
    for hol in SCHOOL_HOLIDAYS_2026_2027:
        if hol["start"] <= d_val <= hol["end"]:
            return {
                "category": "holiday",
                "is_holiday": True,
                "holiday_type": hol["type"],
                "label": hol["name"],
                "has_school": False
            }

    # 3. Ponti e Festività singole (NON vacanze grandi)
    if iso_str in SCHOOL_BRIDGES_2026_2027:
        return {
            "category": "bridge",
            "is_holiday": False,
            "holiday_type": None,
            "label": SCHOOL_BRIDGES_2026_2027[iso_str],
            "has_school": False
        }

    # 4. Domenica (giorno libero)
    if d_val.weekday() == 6:
        return {
            "category": "sunday",
            "is_holiday": False,
            "holiday_type": None,
            "label": "Domenica",
            "has_school": False
        }

    # 5. Giorno di Scuola effettivo (Lunedì - Sabato)
    return {
        "category": "school_day",
        "is_holiday": False,
        "holiday_type": None,
        "label": "Giorno di Scuola",
        "has_school": True
    }

def load_env():
    env_file = os.path.join(BASE_DIR, ".env")
    env = {}
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    return env

_WEATHER_CACHE = {"timestamp": None, "data": None}

def get_weather():
    global _WEATHER_CACHE
    now = datetime.now()
    if _WEATHER_CACHE["timestamp"] and (now - _WEATHER_CACHE["timestamp"]).total_seconds() < 900:
        return _WEATHER_CACHE["data"]
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=45.4064&longitude=11.8768&current_weather=true&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=auto"
        req = urllib.request.Request(url, headers={"User-Agent": "KindleServer/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())
            cur = data.get("current_weather", {})
            temp = round(cur.get("temperature", 18))
            code = cur.get("weathercode", 0)

            desc_map = {
                0: "Sereno", 1: "Poco Nuvoloso", 2: "Nuvoloso", 3: "Coperto",
                45: "Nebbia", 48: "Nebbia", 51: "Pioviggine", 53: "Pioviggine", 55: "Pioviggine",
                61: "Pioggia", 63: "Pioggia Moderata", 65: "Pioggia Forte",
                71: "Neve", 73: "Neve", 75: "Neve", 80: "Rovesci", 81: "Rovesci", 82: "Temporale",
                95: "Temporale", 96: "Temporale", 99: "Temporale"
            }
            desc = desc_map.get(code, "Sereno")

            def get_icon_svg(wcode):
                # Icone SVG minimaliste monocromatiche perfette per E-Ink
                if wcode == 0:
                    # Sole
                    return '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>'
                elif wcode in [1, 2]:
                    # Poco nuvoloso (sole + nuvola)
                    return '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/></svg>'
                elif wcode == 3:
                    # Coperto (nuvolone)
                    return '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/></svg>'
                elif wcode in [45, 48]:
                    # Nebbia
                    return '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="8" x2="20" y2="8"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="16" x2="20" y2="16"/></svg>'
                elif wcode in [51, 53, 55, 61, 63, 65, 80, 81]:
                    # Pioggia
                    return '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 13v6"/><path d="M8 13v6"/><path d="M12 15v6"/><path d="M20 16.58A5 5 0 0 0 18 7h-1.26A8 8 0 1 0 4 15.25"/></svg>'
                elif wcode in [71, 73, 75]:
                    # Neve
                    return '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 17.58A5 5 0 0 0 18 8h-1.26A8 8 0 1 0 4 16.25"/><line x1="8" y1="16" x2="8" y2="16.01"/><line x1="12" y1="18" x2="12" y2="18.01"/><line x1="16" y1="16" x2="16" y2="16.01"/></svg>'
                elif wcode in [82, 95, 96, 99]:
                    # Temporale
                    return '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 16.9A5 5 0 0 0 18 7h-1.26A8 8 0 1 0 4 15.25"/><polyline points="13 11 9 17 15 17 11 23"/></svg>'
                return '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/></svg>'

            # Previsioni per i prossimi 4 giorni
            daily = data.get("daily", {})
            forecast = []
            days_time = daily.get("time", [])
            max_temps = daily.get("temperature_2m_max", [])
            min_temps = daily.get("temperature_2m_min", [])
            codes = daily.get("weathercode", [])

            giorni_abbr = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
            for i in range(min(4, len(days_time))):
                dt = datetime.fromisoformat(days_time[i])
                label = "Oggi" if i == 0 else ("Domani" if i == 1 else giorni_abbr[dt.weekday()])
                w_c = codes[i] if i < len(codes) else 0
                f_desc = desc_map.get(w_c, "Sereno")
                f_max = round(max_temps[i]) if i < len(max_temps) else temp
                f_min = round(min_temps[i]) if i < len(min_temps) else temp
                forecast.append({
                    "giorno": label,
                    "desc": f_desc,
                    "max": f_max,
                    "min": f_min,
                    "code": w_c,
                    "icon": get_icon_svg(w_c)
                })

            res = {
                "temp": temp,
                "desc": desc,
                "code": code,
                "icon": get_icon_svg(code),
                "forecast": forecast
            }
            _WEATHER_CACHE["timestamp"] = now
            _WEATHER_CACHE["data"] = res
            return res
    except Exception as e:
        print("Weather fetch error:", e)
    return {
        "temp": "--",
        "desc": "Padova",
        "code": 0,
        "icon": '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/></svg>',
        "forecast": [
            {"giorno": "Oggi", "desc": "Sereno", "max": 22, "min": 12, "code": 0, "icon": ""},
            {"giorno": "Domani", "desc": "Nuvoloso", "max": 21, "min": 13, "code": 2, "icon": ""},
            {"giorno": "Mar", "desc": "Sereno", "max": 23, "min": 12, "code": 0, "icon": ""},
            {"giorno": "Mer", "desc": "Coperto", "max": 20, "min": 11, "code": 3, "icon": ""}
        ]
    }

_CALDAV_CLIENT = None
_CALDAV_CALENDARS = []
_CALDAV_CALENDARS_TS = None
_CALDAV_CACHE = {"timestamp": None, "date_str": None, "data": []}
_RAW_CALDAV_CACHE_BY_DATE = {}
_MERGED_CACHE_BY_DATE = {}
_CALDAV_CACHE_FILE = "/tmp/caldav_events_cache.json"

def get_caldav_client_and_calendars(username, password):
    global _CALDAV_CLIENT, _CALDAV_CALENDARS, _CALDAV_CALENDARS_TS
    now = datetime.now()
    if _CALDAV_CALENDARS and _CALDAV_CALENDARS_TS and (now - _CALDAV_CALENDARS_TS).total_seconds() < 14400:
        return _CALDAV_CLIENT, _CALDAV_CALENDARS
    try:
        import caldav
        client = caldav.DAVClient(url="https://caldav.icloud.com", username=username, password=password)
        principal = client.principal()
        cals = []
        for c in principal.calendars():
            try:
                name = c.get_display_name() if hasattr(c, "get_display_name") else getattr(c, "name", "")
                if "promemoria" in name.lower() or "reminder" in name.lower():
                    continue
                cals.append(c)
            except Exception:
                pass
        _CALDAV_CLIENT = client
        _CALDAV_CALENDARS = cals
        _CALDAV_CALENDARS_TS = now
        return _CALDAV_CLIENT, _CALDAV_CALENDARS
    except Exception as e:
        print("CalDAV discovery warning:", e)
        return _CALDAV_CLIENT, _CALDAV_CALENDARS

def fetch_caldav_events_direct(caldav_user, caldav_pwd, target_date):
    global _CALDAV_CACHE, _RAW_CALDAV_CACHE_BY_DATE
    now = datetime.now()
    date_str = target_date.strftime("%Y-%m-%d")
    _, calendars = get_caldav_client_and_calendars(caldav_user, caldav_pwd)
    if not calendars:
        return _RAW_CALDAV_CACHE_BY_DATE.get(date_str, {}).get("data", _CALDAV_CACHE["data"] if _CALDAV_CACHE["data"] else [])

    window_days = 4
    # Query CalDAV estesa a 14 giorni prima per intercettare conferenze ed eventi multi-giorno iniziati prima
    start_dt = datetime.combine(target_date - timedelta(days=14), datetime.min.time())
    end_dt = datetime.combine(target_date + timedelta(days=window_days), datetime.max.time())
    
    # Inizializza dizionario per ciascuna data della finestra
    events_by_date = {}
    for k in range(window_days + 1):
        cur_d_str = (target_date + timedelta(days=k)).strftime("%Y-%m-%d")
        events_by_date[cur_d_str] = []

    seen = set()

    for cal in calendars:
        try:
            cal_events = cal.search(start=start_dt, end=end_dt, event=True, expand=True)
            for ev in cal_events:
                comp = ev.icalendar_component
                s_dt = comp.get("dtstart").dt
                summ = strip_emojis(str(comp.get("summary", "") or ""))
                loc = strip_emojis(str(comp.get("location", "") or ""))
                desc = strip_emojis(str(comp.get("description", "") or ""))
                e_dt = comp.get("dtend").dt if comp.get("dtend") else None

                is_allday = not isinstance(s_dt, datetime)
                if is_allday:
                    s_date = s_dt
                    if e_dt is not None:
                        e_date = e_dt if not isinstance(e_dt, datetime) else e_dt.date()
                    else:
                        e_date = s_date + timedelta(days=1)

                    # Espandi l'evento per ogni giorno compreso nell'intervallo [s_date, e_date)
                    cur_d = s_date
                    while cur_d < e_date:
                        cur_d_str = cur_d.strftime("%Y-%m-%d")
                        if cur_d_str in events_by_date:
                            dedup_key = (cur_d_str, summ.lower(), "Tutto il giorno")
                            if dedup_key not in seen:
                                seen.add(dedup_key)
                                events_by_date[cur_d_str].append({
                                    "summary": summ,
                                    "location": loc,
                                    "desc": desc,
                                    "is_allday": True,
                                    "start_min": 0,
                                    "end_min": 24 * 60,
                                    "ora": "Tutto il giorno",
                                    "ora_fine": ""
                                })
                        cur_d += timedelta(days=1)
                else:
                    s_local = s_dt.astimezone() if getattr(s_dt, "tzinfo", None) else s_dt
                    if e_dt:
                        e_local = e_dt.astimezone() if getattr(e_dt, "tzinfo", None) else e_dt
                    else:
                        e_local = s_local + timedelta(hours=1)

                    s_date = s_local.date()
                    e_date = e_local.date()

                    cur_d = s_date
                    while cur_d <= e_date:
                        cur_d_str = cur_d.strftime("%Y-%m-%d")
                        if cur_d_str in events_by_date:
                            if cur_d == s_date:
                                start_min = s_local.hour * 60 + s_local.minute
                                ora_fmt = f"{s_local.hour:02d}:{s_local.minute:02d}"
                            else:
                                start_min = 0
                                ora_fmt = "00:00"

                            if cur_d == e_date:
                                end_min = e_local.hour * 60 + e_local.minute
                                ora_fine_fmt = f"{e_local.hour:02d}:{e_local.minute:02d}"
                            else:
                                end_min = 24 * 60
                                ora_fine_fmt = "24:00"

                            dedup_key = (cur_d_str, summ.lower(), ora_fmt)
                            if dedup_key not in seen:
                                seen.add(dedup_key)
                                events_by_date[cur_d_str].append({
                                    "summary": summ,
                                    "location": loc,
                                    "desc": desc,
                                    "is_allday": False,
                                    "start_min": start_min,
                                    "end_min": end_min,
                                    "ora": ora_fmt,
                                    "ora_fine": ora_fine_fmt
                                })
                        cur_d += timedelta(days=1)
        except Exception:
            pass

    def sort_key(ev):
        return (1, 0) if ev.get("is_allday") else (0, ev.get("start_min", 0))

    for d_k, ev_list in events_by_date.items():
        ev_list.sort(key=sort_key)
        _RAW_CALDAV_CACHE_BY_DATE[d_k] = {"timestamp": now, "data": ev_list}

    target_events = events_by_date.get(date_str, [])
    _CALDAV_CACHE["timestamp"] = now
    _CALDAV_CACHE["date_str"] = date_str
    _CALDAV_CACHE["data"] = target_events
    try:
        with open(_CALDAV_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"timestamp": now.isoformat(), "date_str": date_str, "data": target_events}, f, ensure_ascii=False)
    except Exception:
        pass
    return target_events

def clean_f1_summary(summ):
    if not summ:
        return ""
    if "FORMULA 1" in summ.upper() and " - " in summ:
        parts = summ.split(" - ")
        session = parts[-1].strip()
        gp_match = re.search(r"([A-Za-z\s]+)\s+GRAND PRIX", parts[0], re.IGNORECASE)
        gp_name = ""
        if gp_match:
            words = [w for w in gp_match.group(1).split() if w.upper() not in ["FORMULA", "1", "HEINEKEN", "AIRWAYS", "CRUISES", "GULF", "AIR", "AIRLINES", "MSC", "AIRLINE", "PETRONAS", "QATAR"]]
            if words:
                gp_name = " ".join(dict.fromkeys(words)).title()
        if gp_name:
            return f"F1 {gp_name} • {session}"
        return f"F1 • {session}"
    return summ

def extract_ical_dt(line):
    parts = line.split(":", 1)
    if len(parts) == 2:
        return parts[1].strip()
    parts = line.split(";", 1)
    if len(parts) == 2:
        return parts[1].strip()
    return line.strip()

def parse_ics_events(content, target_date):
    if not content:
        return []
    target_str = target_date.strftime("%Y%m%d")
    events = []
    seen = set()
    cur = {}
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("BEGIN:VEVENT"):
            cur = {}
        elif line.startswith("SUMMARY:"):
            cur["summary"] = line[8:].strip()
        elif line.startswith("DTSTART"):
            cur["start_raw"] = extract_ical_dt(line)
        elif line.startswith("DTEND"):
            cur["end_raw"] = extract_ical_dt(line)
        elif line.startswith("LOCATION:"):
            cur["location"] = line[9:].strip()
        elif line.startswith("DESCRIPTION:"):
            cur["desc"] = line[12:].strip()
        elif line.startswith("END:VEVENT"):
            start = cur.get("start_raw", "")
            end = cur.get("end_raw", "")
            raw_summ = strip_emojis(cur.get("summary", ""))
            summ = clean_f1_summary(raw_summ)
            loc = strip_emojis(cur.get("location", ""))
            desc = strip_emojis(cur.get("desc", ""))

            if start:
                is_allday = "T" not in start
                s_d_str = start[:8]
                e_d_str = end[:8] if end else s_d_str

                if is_allday:
                    if e_d_str > s_d_str:
                        matches = (s_d_str <= target_str < e_d_str)
                    else:
                        matches = (s_d_str == target_str)
                    if matches:
                        dedup_key = (raw_summ.lower(), "Tutto il giorno")
                        if dedup_key not in seen:
                            seen.add(dedup_key)
                            events.append({
                                "summary": summ,
                                "raw_summary": raw_summ,
                                "location": loc,
                                "desc": desc,
                                "is_allday": True,
                                "start_min": 0,
                                "end_min": 24 * 60,
                                "ora": "Tutto il giorno",
                                "ora_fine": ""
                            })
                else:
                    if s_d_str <= target_str <= e_d_str:
                        if s_d_str == target_str and len(start) >= 13:
                            sh, sm = int(start[9:11]), int(start[11:13])
                            start_min = sh * 60 + sm
                            ora_fmt = f"{sh:02d}:{sm:02d}"
                        else:
                            start_min = 0
                            ora_fmt = "00:00"

                        if e_d_str == target_str and len(end) >= 13:
                            eh, em = int(end[9:11]), int(end[11:13])
                            end_min = eh * 60 + em
                            ora_fine_fmt = f"{eh:02d}:{em:02d}"
                        else:
                            end_min = 24 * 60
                            ora_fine_fmt = "24:00"

                        dedup_key = (raw_summ.lower(), ora_fmt)
                        if dedup_key not in seen:
                            seen.add(dedup_key)
                            events.append({
                                "summary": summ,
                                "raw_summary": raw_summ,
                                "location": loc,
                                "desc": desc,
                                "is_allday": False,
                                "start_min": start_min,
                                "end_min": end_min,
                                "ora": ora_fmt,
                                "ora_fine": ora_fine_fmt
                            })
    return events

def get_icloud_events(env, target_date=None, force_refresh=False, mock_events=False):
    global _CALDAV_CACHE, _RAW_CALDAV_CACHE_BY_DATE, _MERGED_CACHE_BY_DATE
    now = datetime.now()
    if target_date is None:
        target_date = now.date()
    elif isinstance(target_date, datetime):
        target_date = target_date.date()

    date_str = target_date.strftime("%Y-%m-%d")

    if mock_events:
        mock_data = {
            "2026-07-16": [
                {"summary": "Allenamento Nuoto", "start_min": 17*60+30, "end_min": 19*60, "ora": "17:30", "ora_fine": "19:00", "location": "Padovanuoto", "is_allday": False}
            ],
            "2026-07-17": [
                {"summary": "Guida per patente", "start_min": 10*60, "end_min": 11*60+30, "ora": "10:00", "ora_fine": "11:30", "location": "Autoscuola Severi", "is_allday": False}
            ],
            "2026-12-27": [
                {"summary": "Pranzo in famiglia", "start_min": 12*60+30, "end_min": 15*60, "ora": "12:30", "ora_fine": "15:00", "location": "Casa Nonni", "is_allday": False}
            ],
            "2027-03-29": [
                {"summary": "Grigliata con amici", "start_min": 12*60, "end_min": 17*60, "ora": "12:00", "ora_fine": "17:00", "location": "Parco dei Colli", "is_allday": False}
            ]
        }
        return mock_data.get(date_str, [])

    # Cache di 45 secondi sui risultati unificati
    if not force_refresh and date_str in _MERGED_CACHE_BY_DATE:
        entry = _MERGED_CACHE_BY_DATE[date_str]
        if (now - entry["timestamp"]).total_seconds() < 45:
            return entry["data"]

    # 1. SINCRONIZZAZIONE DIRETTA CALDAV (REAL-TIME SERVER-TO-APPLE)
    caldav_events = []
    caldav_user = env.get("ICLOUD_APPLE_ID", "").strip()
    caldav_pwd = env.get("ICLOUD_APP_PASSWORD", "").strip()
    if caldav_user and caldav_pwd:
        if force_refresh:
            _CALDAV_CACHE["timestamp"] = None
            if date_str in _RAW_CALDAV_CACHE_BY_DATE:
                del _RAW_CALDAV_CACHE_BY_DATE[date_str]
            if date_str in _MERGED_CACHE_BY_DATE:
                del _MERGED_CACHE_BY_DATE[date_str]

        # Controlla cache CalDAV raw prima di risollecitare la rete
        if not force_refresh and date_str in _RAW_CALDAV_CACHE_BY_DATE:
            entry = _RAW_CALDAV_CACHE_BY_DATE[date_str]
            if (now - entry["timestamp"]).total_seconds() < 45:
                caldav_events = entry["data"]

        if not caldav_events:
            try:
                caldav_events = fetch_caldav_events_direct(caldav_user, caldav_pwd, target_date)
            except Exception as e:
                print("CalDAV fetch error (fallback to cache):", e)
                if date_str in _RAW_CALDAV_CACHE_BY_DATE:
                    caldav_events = _RAW_CALDAV_CACHE_BY_DATE[date_str].get("data", [])
                elif _CALDAV_CACHE.get("data"):
                    caldav_events = _CALDAV_CACHE["data"]

    # 2. FEED ICAL LOCALE O URL (PER SOTTOSCRIZIONI COME FORMULA 1 E FEED ESTERNI)
    ics_events = []
    local_ics = "/opt/kindleCalendar/calendar_feed.ics"
    if not os.path.exists(local_ics):
        local_ics = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calendar_feed.ics")
    url = env.get("ICLOUD_ICAL_URL", "").strip()
    content = ""

    if os.path.exists(local_ics):
        try:
            with open(local_ics, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            print("Local ics read error:", e)
    elif url.startswith("/") or url.startswith("file://"):
        local_path = url.replace("file://", "")
        if os.path.exists(local_path):
            try:
                with open(local_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception as e:
                print("Local ics read error:", e)
    elif url:
        if url.startswith("webcal://"):
            url = "https://" + url[9:]
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "KindleServer/1.0", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            print("iCloud sync error:", e)

    if content:
        ics_events = parse_ics_events(content, target_date)

    # 3. MERGE & DEDUPLICAZIONE (CALDAV PREVALE, ICS AGGIUNGE F1 E ALTRI SOTTOSCRITTI)
    merged = []
    seen = set()

    for ev in caldav_events:
        ev["summary"] = clean_f1_summary(ev.get("summary", ""))
        key = (ev["summary"].strip().lower(), ev.get("ora", ""))
        if key not in seen:
            seen.add(key)
            merged.append(ev)

    for ev in ics_events:
        key = (ev["summary"].strip().lower(), ev.get("ora", ""))
        raw_key = (ev.get("raw_summary", ev["summary"]).strip().lower(), ev.get("ora", ""))
        if key not in seen and raw_key not in seen:
            seen.add(key)
            merged.append(ev)

    def sort_key(ev):
        return (0, 0) if ev.get("is_allday") else (1, ev.get("start_min", 0))

    merged.sort(key=sort_key)
    _MERGED_CACHE_BY_DATE[date_str] = {"timestamp": now, "data": merged}
    try:
        with open(_CALDAV_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"timestamp": now.isoformat(), "date_str": date_str, "data": merged}, f, ensure_ascii=False)
    except Exception:
        pass
    return merged

_CV_CACHE = {"timestamp": None, "data": []}
_CV_CACHE_FILE = "/tmp/classeviva_cache.json"

def get_classeviva_agenda(env):
    global _CV_CACHE
    user = env.get("CLASSEVIVA_USERNAME", "").strip()
    pwd = env.get("CLASSEVIVA_PASSWORD", "").strip()
    if not user or user == "tua_username_o_email":
        return []

    now = datetime.now()
    # Cache 1 ora (3600 secondi) in memoria per evitare ban dell'account
    if _CV_CACHE["timestamp"] and (now - _CV_CACHE["timestamp"]).total_seconds() < 3600:
        return _CV_CACHE["data"]

    # Tentativo di recupero da cache su disco (persistente anche dopo riavvio server)
    if not _CV_CACHE["timestamp"] and os.path.exists(_CV_CACHE_FILE):
        try:
            with open(_CV_CACHE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                saved_ts = datetime.fromisoformat(saved.get("timestamp"))
                if (now - saved_ts).total_seconds() < 3600:
                    _CV_CACHE["timestamp"] = saved_ts
                    _CV_CACHE["data"] = saved.get("data", [])
                    print(f"ClasseViva: caricati dati validi da cache disco ({int((now - saved_ts).total_seconds())}s fa)")
                    return _CV_CACHE["data"]
        except Exception:
            pass

    try:
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

        login_url = "https://web.spaggiari.eu/auth-p7/app/default/AuthApi4.php?a=aLoginPwd"
        login_data = urllib.parse.urlencode({"cid": "", "uid": user, "pwd": pwd, "pin": "", "target": ""}).encode()
        login_req = urllib.request.Request(
            login_url,
            data=login_data,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )

        with opener.open(login_req, timeout=5) as resp:
            res = json.loads(resp.read().decode("utf-8", errors="ignore"))
            auth = res.get("data", {}).get("auth", {})
            if not auth.get("loggedIn"):
                print("ClasseViva login non riuscito")
                return []
            student_id = auth.get("accountInfo", {}).get("id") or user.lstrip("SGX").rstrip("I")

        da_str = now.strftime("%Y%m%d")
        a_str = (now + timedelta(days=14)).strftime("%Y%m%d")
        agenda_url = f"https://web.spaggiari.eu/rest/w1/students/{student_id}/agendav2/all/{da_str}/{a_str}"
        agenda_req = urllib.request.Request(
            agenda_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept": "application/json"
            }
        )

        compiti = []
        raw_items = []
        with opener.open(agenda_req, timeout=5) as resp_ag:
            ag_data = json.loads(resp_ag.read().decode("utf-8", errors="ignore"))
            for item in ag_data.get("agenda", []):
                raw_begin = item.get("evtDatetimeBegin", "")
                ev_date = None
                data_label = "Prossimamente"
                if raw_begin:
                    try:
                        ev_dt = datetime.fromisoformat(raw_begin)
                        ev_date = ev_dt.date()
                        if ev_date == now.date():
                            data_label = "Oggi"
                        elif ev_date == (now + timedelta(days=1)).date():
                            data_label = "Domani"
                        else:
                            data_label = ev_dt.strftime("%d/%m")
                    except Exception:
                        data_label = raw_begin[:10]

                # Filtra eventi già passati prima di oggi
                if ev_date and ev_date < now.date():
                    continue

                materia = item.get("subjectDesc") or item.get("authorName") or "Compito"
                note_testo = item.get("notes") or ""

                raw_items.append({
                    "date_val": ev_date or (now + timedelta(days=99)).date(),
                    "date_str": ev_date.isoformat() if ev_date else "",
                    "materia": materia,
                    "data": data_label,
                    "descrizione": note_testo,
                    "is_test": False
                })

        # --- FILTRO INTELLIGENTE LLM GROQ ---
        # Evita falsi positivi distinguendo tra vere verifiche e compiti per casa
        groq_api_key = env.get("GROQ_API_KEY", "").strip()
        if groq_api_key and raw_items:
            try:
                items_to_classify = [f"{it['materia']}: {it['descrizione']}" for it in raw_items]
                sys_prompt = (
                    "Sei un assistente scolastico esperto per il registro elettronico ClasseViva.\n"
                    "Analizza ciascun compito/nota e stabilisci se si tratta di una VERA prova valutata formale (verifica scritta, test, prova pratica, interrogazione, compito in classe, esame).\n"
                    "ATTENZIONE MASSIMA AI FALSI POSITIVI:\n"
                    "- 'studiare p. 308, rispondere sul quaderno tipo verifica alle domande' -> NON è una verifica (false), sono normali compiti per casa ('tipo verifica' indica solo la modalità).\n"
                    "- 'in preparazione alla verifica fare gli esercizi...' -> NON è una verifica (false).\n"
                    "- 'portare il materiale / libro' -> NON è una verifica (false).\n"
                    "- 'Interrogazione: valore assoluto' -> VERA interrogazione (true).\n"
                    "- 'Verifica scritta: valore assoluto' -> VERA verifica (true).\n"
                    "Restituisci ESCLUSIVAMENTE un JSON valido nel formato: {\"results\": [true/false, ...]} con un booleano per ciascun elemento in ordine."
                )
                payload = {
                    "model": "qwen/qwen3.8-27b",
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": json.dumps(items_to_classify, ensure_ascii=False)}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.0
                }
                g_req = urllib.request.Request(
                    "https://api.groq.com/openai/v1/chat/completions",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {groq_api_key}",
                        "Content-Type": "application/json",
                        "User-Agent": "Mozilla/5.0"
                    }
                )
                with urllib.request.urlopen(g_req, timeout=5) as g_resp:
                    g_json = json.loads(g_resp.read().decode("utf-8", errors="ignore"))
                    content_str = g_json.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                    parsed_res = json.loads(content_str)
                    bool_list = parsed_res.get("results", [])
                    for idx, val in enumerate(bool_list):
                        if idx < len(raw_items):
                            raw_items[idx]["is_test"] = bool(val)
            except Exception as ge:
                print("Groq LLM filter warning (fallback to rule-based):", ge)
                # Fallback euristico se Groq non risponde
                for it in raw_items:
                    txt = (it["materia"] + " " + it["descrizione"]).lower()
                    if "tipo verifica" in txt or "in preparazione" in txt:
                        it["is_test"] = False
                    elif any(k in txt for k in ["verifica", "interrogazione", "compito in classe", "test"]):
                        it["is_test"] = True

        # Ordina SEMPRE in ordine cronologico crescente di data (Oggi -> Domani -> Giorni successivi)
        raw_items.sort(key=lambda x: (x["date_val"], not x["is_test"]))

        for item in raw_items:
            compiti.append({
                "materia": strip_emojis(item["materia"]),
                "data": item["data"],
                "date_str": item.get("date_str", ""),
                "descrizione": strip_emojis(item["descrizione"]),
                "is_test": item["is_test"]
            })

        _CV_CACHE["timestamp"] = now
        _CV_CACHE["data"] = compiti
        try:
            with open(_CV_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({"timestamp": now.isoformat(), "data": compiti}, f, ensure_ascii=False)
        except Exception:
            pass
        return compiti
    except Exception as e:
        print("Errore fetch ClasseViva:", e)
        return _CV_CACHE["data"] if _CV_CACHE["data"] else []

def build_dashboard_html(query_params):
    env = load_env()
    ts_param = query_params.get("ts", [""])[0]
    time_param = query_params.get("time", [""])[0]
    date_param = query_params.get("date", [""])[0]

    if ts_param:
        try:
            now = datetime.fromtimestamp(float(ts_param))
        except Exception:
            now = datetime.now()
    else:
        now = datetime.now()
        # Se mancano meno di 15 secondi al minuto successivo, significa che stiamo
        # pre-renderizzando l'immagine che comparirà al minuto :00
        if now.second >= 45:
            now = (now + timedelta(seconds=(60 - now.second))).replace(microsecond=0)

    if date_param:
        try:
            p_date = datetime.fromisoformat(date_param).date()
            now = now.replace(year=p_date.year, month=p_date.month, day=p_date.day)
        except Exception:
            pass

    holiday_param = query_params.get("holiday", [""])[0].lower()
    if holiday_param:
        if holiday_param == "summer":
            now = now.replace(year=2026, month=7, day=16)
        elif holiday_param == "winter":
            now = now.replace(year=2026, month=12, day=27)
        elif holiday_param == "carnival":
            now = now.replace(year=2027, month=2, day=9)
        elif holiday_param == "easter":
            now = now.replace(year=2027, month=3, day=29)

    if time_param and ":" in time_param:
        try:
            th, tm = map(int, time_param.split(":"))
            now = now.replace(hour=th, minute=tm, second=0, microsecond=0)
        except Exception:
            pass

    cur_time = now.time()

    t_0630 = time(6, 30)
    t_0800 = time(8, 0)
    t_2130 = time(21, 30)

    mode_param = query_params.get("mode", [""])[0]
    if mode_param in ["morning", "day", "evening"]:
        current_phase = mode_param
    else:
        if t_0630 <= cur_time < t_0800:
            current_phase = "morning"
        elif t_0800 <= cur_time < t_2130:
            current_phase = "day"
        else:
            current_phase = "evening"

    # Giorno target
    if current_phase == "evening":
        target_date = now + timedelta(days=1)
        weekday = target_date.weekday()
        giorno_key = GIORNI_MAP.get(weekday, "lunedi")
        giorno_titolo = f"{GIORNI_NOMI_IT.get(weekday, '')} (Domani)"
    else:
        target_date = now
        weekday = now.weekday()
        if weekday == 6:
            # Domenica mostra il calendario impegni, non forziamo lunedì durante il giorno
            giorno_key = "domenica"
            giorno_titolo = "Domenica"
        else:
            giorno_key = GIORNI_MAP.get(weekday, "lunedi")
            giorno_titolo = GIORNI_NOMI_IT.get(weekday, "Oggi")

    override_day = query_params.get("day", [""])[0]
    if override_day:
        giorno_key = override_day
        giorno_titolo = override_day.capitalize()

    target_d_obj = target_date.date() if isinstance(target_date, datetime) else target_date

    global ORARIO_DATA, LIBRI_DATA
    ORARIO_DATA = load_orario_data(target_date=target_d_obj)
    LIBRI_DATA = load_libri_data()
    load_school_calendar_config()

    # Classificazione accurata giorno di scuola vs vacanza ('holiday') vs ponte ('bridge') vs domenica
    school_info = get_school_day_info(target_d_obj)

    lezioni = list(ORARIO_DATA["schedule"].get(giorno_key, []))
    # A scuola si va nei giorni classificati 'school_day' (Lun-Sab feriali non vacanze), salvo override_day
    has_school = (school_info["has_school"] and len(lezioni) > 0) or bool(override_day)

    # Calcolo orario di termine dell'ultima lezione del giorno odierno
    fine_scuola_min = 0
    for l in lezioni:
        f_str = l.get("fine", "")
        if ":" in f_str:
            try:
                fh, fm = map(int, f_str.split(":"))
                m_val = fh * 60 + fm
                if m_val > fine_scuola_min:
                    fine_scuola_min = m_val
            except Exception:
                pass

    # Dopo la fine delle lezioni (es. 13:50 o 13:00 o 12:05), aspetta 30 minuti prima di passare al calendario
    switch_timeline_min = fine_scuola_min + 30 if fine_scuola_min > 0 else 0
    now_min = now.hour * 60 + now.minute

    # Determina se visualizzare l'orario scolastico o la linea del tempo della giornata
    show_school_schedule = False
    if current_phase == "evening":
        show_school_schedule = has_school
    elif current_phase == "morning":
        show_school_schedule = has_school
    elif current_phase == "day":
        if has_school and (now_min < switch_timeline_min or switch_timeline_min == 0):
            show_school_schedule = True
        else:
            show_school_schedule = False

    # Evidenziazione lezione in corso
    ora_corrente_str = now.strftime("%H:%M")
    for l in lezioni:
        l["in_corso"] = (current_phase == "day" and show_school_schedule and (l["inizio"] <= ora_corrente_str <= l["fine"]))

    # Libri necessari
    materie_oggi = set(l["materia"] for l in lezioni)
    libri_list = []
    for b in LIBRI_DATA["books"]:
        if b["subject"] in materie_oggi:
            libri_list.append({
                "materia": b["subject"],
                "titolo": b["title"]
            })

    meteo = get_weather()
    compiti = get_classeviva_agenda(env)
    force_cal_refresh = query_params.get("refresh", [""])[0] in ["1", "true", "True"]
    mock_events = query_params.get("mock_events", [""])[0] in ["1", "true", "True"]
    icloud_events = get_icloud_events(env, target_date=target_date, force_refresh=force_cal_refresh, mock_events=mock_events)
    has_icloud = len(icloud_events) > 0

    # Lettura percentuale reale batteria Kindle e stato di carica
    battery = 100
    is_charging = False
    batt_file = "/tmp/kindle_battery.txt"
    charging_file = "/tmp/kindle_charging.txt"

    batt_param = query_params.get("batt", [""])[0]
    charging_param = query_params.get("charging", [""])[0]

    if batt_param and batt_param.isdigit():
        battery = int(batt_param)
    elif os.path.exists(batt_file):
        try:
            with open(batt_file, "r") as bf:
                val = bf.read().strip()
                if val.isdigit():
                    battery = int(val)
        except Exception:
            pass

    if charging_param in ["1", "true", "True"]:
        is_charging = True
    elif os.path.exists(charging_file):
        try:
            with open(charging_file, "r") as cf:
                cval = cf.read().strip()
                is_charging = (cval in ["1", "true", "True"])
        except Exception:
            pass

    # Icona fulmine SVG per la ricarica
    bolt_icon = '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" stroke="none" style="margin-right:2px;display:inline-block;vertical-align:-1px;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>'
    charging_prefix = bolt_icon if is_charging else ""
    battery_display = f"{charging_prefix}{battery}%"

    # Data formattata in italiano
    data_str = now.strftime("%A %d %B %Y")
    traduzioni_it = {
        "January": "Gennaio", "February": "Febbraio", "March": "Marzo", "April": "Aprile",
        "May": "Maggio", "June": "Giugno", "July": "Luglio", "August": "Agosto",
        "September": "Settembre", "October": "Ottobre", "November": "Novembre", "December": "Dicembre",
        "Monday": "Lunedì", "Tuesday": "Martedì", "Wednesday": "Mercoledì",
        "Thursday": "Giovedì", "Friday": "Venerdì", "Saturday": "Sabato", "Sunday": "Domenica"
    }
    for en, it in traduzioni_it.items():
        data_str = data_str.replace(en, it)

    ora_str = now.strftime("%H:%M")

    # Righe lezioni HTML
    lezioni_rows = ""
    for slot in lezioni:
        bg = "#000" if slot["in_corso"] else "#fff"
        color = "#fff" if slot["in_corso"] else "#000"
        border_r = "#fff" if slot["in_corso"] else "#000"
        docenti_str = ", ".join(slot.get("docenti", []))
        det = f'<span style="display:block;font-size:11px;font-weight:600;opacity:0.85;margin-top:2px;">{slot["dettaglio"]}</span>' if slot.get("dettaglio") else ""
        lezioni_rows += f'''
        <div style="display:flex;align-items:center;padding:14px 14px;border-radius:10px;border:2.5px solid #000;background:{bg};color:{color};">
          <div style="width:50px;text-align:center;font-weight:900;font-size:20px;border-right:2px solid {border_r};padding-right:8px;">
            {slot["ora"]}
          </div>
          <div style="padding:0 14px;font-size:13px;font-weight:900;width:110px;letter-spacing:-0.2px;">
            {slot["inizio"]} - {slot["fine"]}
          </div>
          <div style="flex:1;font-weight:900;font-size:18px;line-height:1.2;">
            {slot["materia"]}
            {det}
          </div>
          <div style="text-align:right;padding-left:10px;">
            <span style="display:block;font-weight:900;font-size:15px;">{slot["aula"]}</span>
            <span style="display:block;font-size:11px;font-weight:700;opacity:0.8;">{docenti_str}</span>
          </div>
        </div>
        '''

    # Colonna Sinistra (se non ci sono lezioni scolastiche o sono terminate da 30m)
    if not show_school_schedule:
        if school_info["category"] == "holiday":
            # MODALITÀ VACANZE (HOLIDAY SYSTEM): AGENDA A CARD GIORNALIERE CON ALL-DAY E MINI-TIMELINE
            holiday_type = school_info.get("holiday_type", "summer")
            holiday_badges_map = {
                "summer": "VACANZE ESTIVE",
                "winter": "VACANZE DI NATALE",
                "carnival": "CARNEVALE",
                "easter": "VACANZE DI PASQUA"
            }
            holiday_badge_label = holiday_badges_map.get(holiday_type, school_info.get("label", "VACANZE").upper())

            # 3 giorni a partire da target_date
            cards_html = ""
            for i in range(3):
                d_target = (target_date.date() if isinstance(target_date, datetime) else target_date) + timedelta(days=i)
                d_events = get_icloud_events(env, target_date=d_target, force_refresh=force_cal_refresh, mock_events=mock_events)
                d_allday = [e for e in d_events if e.get("is_allday")]
                d_timed = [e for e in d_events if not e.get("is_allday")]

                d_weekday = d_target.weekday()
                d_name_it = GIORNI_NOMI_IT.get(d_weekday, "")
                d_month_it = traduzioni_it.get(d_target.strftime("%B"), d_target.strftime("%B"))

                # Intestazione e badge per ciascuna card
                if i == 0:
                    c_title = f"OGGI • {d_name_it.upper()} {d_target.day} {d_month_it.upper()}"
                    c_badge = f"{len(d_timed)} IMPEGNI" if len(d_timed) > 0 else "OGGI"
                elif i == 1:
                    c_title = f"DOMANI • {d_name_it.upper()} {d_target.day} {d_month_it.upper()}"
                    c_badge = f"{len(d_timed)} IMPEGNI" if len(d_timed) > 0 else "PROSSIMO GIORNO"
                else:
                    c_title = f"{d_name_it.upper()} {d_target.day} {d_month_it.upper()}"
                    c_badge = f"{len(d_timed)} IMPEGNI" if len(d_timed) > 0 else ("WEEKEND" if d_weekday in [5, 6] else "GIORNATA LIBERA")

                # All-day banners (solo impegni di calendario reali)
                allday_banners = ""
                if d_allday:
                    chips = ""
                    for ev in d_allday:
                        clean_summ = strip_emojis(ev.get("summary", ""))
                        chips += f'''
                        <span style="display:inline-flex;align-items:center;border:1.5px solid #000;border-radius:4px;padding:2px 6px;background:#fff;font-size:11px;font-weight:900;margin-right:4px;margin-bottom:3px;">
                          {clean_summ}
                        </span>
                        '''
                    allday_banners = f'''
                    <div style="margin-bottom:6px;padding-bottom:5px;border-bottom:1.5px dashed #000;display:flex;flex-wrap:wrap;align-items:center;">
                      <span style="font-size:9.5px;font-weight:900;text-transform:uppercase;color:#444;letter-spacing:0.3px;margin-right:6px;">Tutto il giorno:</span>
                      <div style="display:flex;flex-wrap:wrap;align-items:center;">{chips}</div>
                    </div>
                    '''

                # Mini-timeline (struttura e stile speculari alla timeline principale dei giorni liberi)
                now_min = now.hour * 60 + now.minute
                if d_timed:
                    items_rows = ""
                    for ev in d_timed:
                        clean_summ = strip_emojis(ev.get("summary", ""))
                        s_min = ev.get("start_min", 0)
                        e_min = ev.get("end_min", s_min + 60)
                        ora_start = ev.get("ora", "")
                        ora_fine = ev.get("ora_fine", "")
                        time_label = ora_start
                        if ora_fine:
                            time_label += f" - {ora_fine}"

                        is_active = (i == 0 and s_min <= now_min <= e_min)
                        bg = "#000" if is_active else "#fff"
                        color = "#fff" if is_active else "#000"
                        badge_bg = "#fff" if is_active else "#000"
                        badge_color = "#000" if is_active else "#fff"
                        dot_bg = "#000" if is_active else "#000"

                        loc_line = ""
                        clean_loc = strip_emojis(ev.get("location", ""))
                        if clean_loc:
                            loc_line = f'''
                            <div style="font-size:10px;font-weight:700;opacity:0.85;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                              <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="display:inline-block;vertical-align:-1px;margin-right:3px;">
                                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
                                <circle cx="12" cy="10" r="3"></circle>
                              </svg>{clean_loc}
                            </div>
                            '''

                        desc_line = ""
                        clean_desc = strip_emojis(ev.get("desc", ""))
                        if clean_desc and not clean_desc.startswith("Calendario:"):
                            desc_line = f'<div style="font-size:9.5px;font-weight:600;opacity:0.75;margin-top:2px;line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{clean_desc}</div>'

                        items_rows += f'''
                        <div style="display:flex;align-items:stretch;gap:7px;">
                          <div style="width:36px;flex-shrink:0;text-align:right;padding-top:4px;">
                            <span style="font-size:10.5px;font-weight:900;color:#222;line-height:1;">{ora_start}</span>
                          </div>
                          <div style="position:relative;width:8px;flex-shrink:0;display:flex;justify-content:center;">
                            <div style="width:2px;background:#000;height:100%;"></div>
                            <div style="position:absolute;top:6px;width:7px;height:7px;background:{dot_bg};border:1.5px solid #000;border-radius:50%;"></div>
                          </div>
                          <div style="flex:1;border:1.5px solid #000;border-radius:6px;background:{bg};color:{color};padding:4px 8px;margin-bottom:4px;box-sizing:border-box;">
                            <div style="display:flex;justify-content:space-between;align-items:center;">
                              <span style="font-size:12px;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-right:6px;">{clean_summ}</span>
                              <span style="font-size:9.5px;font-weight:900;background:{badge_bg};color:{badge_color};padding:1px 5px;border-radius:3px;white-space:nowrap;">{time_label}</span>
                            </div>
                            {loc_line}
                            {desc_line}
                          </div>
                        </div>
                        '''
                    mini_timeline_html = f'''
                    <div style="display:flex;flex-direction:column;gap:3px;margin-top:2px;">
                      {items_rows}
                    </div>
                    '''
                else:
                    d_day_info = get_school_day_info(d_target)
                    if d_day_info["has_school"]:
                        mini_timeline_html = '''
                        <div style="display:flex;align-items:stretch;gap:7px;margin-top:2px;">
                          <div style="width:36px;flex-shrink:0;text-align:right;padding-top:4px;">
                            <span style="font-size:10.5px;font-weight:900;color:#222;line-height:1;">08:00</span>
                          </div>
                          <div style="position:relative;width:8px;flex-shrink:0;display:flex;justify-content:center;">
                            <div style="width:2px;background:#000;height:100%;"></div>
                            <div style="position:absolute;top:6px;width:7px;height:7px;background:#000;border-radius:50%;"></div>
                          </div>
                          <div style="flex:1;border:1.5px solid #000;border-radius:6px;background:#fff;color:#000;padding:4px 8px;box-sizing:border-box;">
                            <div style="display:flex;justify-content:space-between;align-items:center;">
                              <span style="font-size:12px;font-weight:900;">Lezioni ordinarie</span>
                              <span style="font-size:9.5px;font-weight:900;background:#000;color:#fff;padding:1px 5px;border-radius:3px;">08:00 - 13:50</span>
                            </div>
                          </div>
                        </div>
                        '''
                    else:
                        empty_lbl = "Nessun impegno a orario per oggi" if i == 0 else "Nessun impegno a orario programmato"
                        mini_timeline_html = f'''
                        <div style="border:1.5px dashed #000;border-radius:6px;padding:6px 8px;text-align:center;font-size:11px;font-weight:800;color:#555;background:#fff;margin-top:2px;">
                          {empty_lbl}
                        </div>
                        '''

                cards_html += f'''
                <div style="border:2px solid #000;border-radius:8px;padding:7px 9px;background:#fff;">
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;border-bottom:1.5px solid #000;padding-bottom:3px;">
                    <span style="font-size:12px;font-weight:900;text-transform:uppercase;letter-spacing:0.4px;">{c_title}</span>
                    <span style="font-size:10px;font-weight:800;color:#555;">{c_badge}</span>
                  </div>
                  {allday_banners}
                  {mini_timeline_html}
                </div>
                '''

            col_left_content = f'''
            <div style="display:flex;flex-direction:column;">
              <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #000;padding-bottom:5px;margin-bottom:8px;">
                <div style="font-size:13px;font-weight:900;text-transform:uppercase;letter-spacing:0.5px;">AGENDA &amp; IMPEGNI</div>
                <span style="font-size:11px;font-weight:900;color:#000;background:#eee;padding:2px 6px;border-radius:4px;border:1px solid #000;">{holiday_badge_label}</span>
              </div>
              <div style="display:flex;flex-direction:column;gap:8px;">
                {cards_html}
              </div>
            </div>
            '''
        else:
            # LINEA DEL TEMPO GIORNALIERA ORDINARIA (PER DOMENICHE, PONTI E POMERIGGI FERIALI)
            allday_events = [e for e in icloud_events if e.get("is_allday")]
            timed_events = [e for e in icloud_events if not e.get("is_allday")]

            # 1. Eventi tutta la giornata (mostrati in cima, compatti, senza occupare la timeline oraria)
            allday_html = ""
            if allday_events:
                chips = ""
                for ev in allday_events:
                    chips += f'''
                    <div style="display:inline-flex;align-items:center;border:1.5px solid #000;border-radius:6px;padding:3px 8px;background:#fff;margin-right:6px;margin-bottom:4px;font-size:11.5px;font-weight:900;">
                      <span>{ev.get("summary","")}</span>
                    </div>
                    '''
                allday_html = f'''
                <div style="margin-bottom:8px;padding-bottom:6px;border-bottom:1.5px dashed #000;">
                  <div style="font-size:10px;font-weight:900;text-transform:uppercase;color:#444;margin-bottom:4px;letter-spacing:0.3px;">Tutto il giorno</div>
                  <div style="display:flex;flex-wrap:wrap;">{chips}</div>
                </div>
                '''

            # 2. Linea del tempo della giornata (07:00 - 23:00)
            t_start = 7 * 60   # 07:00
            t_end = 23 * 60    # 23:00
            total_span = t_end - t_start

            hour_markers = ""
            for h in range(8, 23, 2):
                pos_pct = ((h * 60 - t_start) / total_span) * 100
                hour_markers += f'''
                <div style="position:absolute;top:{pos_pct:.2f}%;left:0;right:0;display:flex;align-items:center;pointer-events:none;z-index:1;">
                  <span style="font-size:10px;font-weight:900;width:38px;color:#444;background:#fff;line-height:1;">{h:02d}:00</span>
                  <div style="flex:1;border-bottom:1px dashed #ccc;height:1px;"></div>
                </div>
                '''

            timed_blocks = ""
            now_min = now.hour * 60 + now.minute
            now_line = ""
            if t_start <= now_min <= t_end:
                now_pos_pct = ((now_min - t_start) / total_span) * 100
                now_line = f'''
                <div id="timeline-now-line" style="position:absolute;top:{now_pos_pct:.2f}%;left:36px;right:0;border-bottom:2px solid #000;z-index:4;pointer-events:none;display:flex;align-items:center;">
                  <span id="timeline-now-badge" style="position:absolute;left:-36px;font-size:9.5px;font-weight:900;background:#000;color:#fff;padding:1px 3px;border-radius:2px;">{now.strftime('%H:%M')}</span>
                </div>
                '''

            if timed_events:
                # Partizionamento intervalli sovrapposti in colonne affiancate
                sorted_evs = sorted(
                    timed_events,
                    key=lambda ev: (
                        max(t_start, min(t_end, ev.get("start_min", t_start))),
                        -(max(t_start, min(t_end, ev.get("end_min", ev.get("start_min", t_start) + 45))) - max(t_start, min(t_end, ev.get("start_min", t_start))))
                    )
                )

                clusters = []
                current_cluster = []
                cluster_end = -1
                for ev in sorted_evs:
                    s = max(t_start, min(t_end, ev.get("start_min", t_start)))
                    e = max(s + 30, min(t_end, ev.get("end_min", s + 45)))
                    if not current_cluster:
                        current_cluster.append(ev)
                        cluster_end = e
                    else:
                        if s < cluster_end:
                            current_cluster.append(ev)
                            cluster_end = max(cluster_end, e)
                        else:
                            clusters.append(current_cluster)
                            current_cluster = [ev]
                            cluster_end = e
                if current_cluster:
                    clusters.append(current_cluster)

                for cluster in clusters:
                    cols_end = []
                    assignments = []
                    for ev in cluster:
                        s = max(t_start, min(t_end, ev.get("start_min", t_start)))
                        e = max(s + 30, min(t_end, ev.get("end_min", s + 45)))
                        placed = False
                        for c_idx in range(len(cols_end)):
                            if s >= cols_end[c_idx]:
                                cols_end[c_idx] = e
                                assignments.append((ev, c_idx))
                                placed = True
                                break
                        if not placed:
                            c_idx = len(cols_end)
                            cols_end.append(e)
                            assignments.append((ev, c_idx))

                    total_cols = len(cols_end)

                    for ev, col_idx in assignments:
                        s_min = max(t_start, min(t_end, ev.get("start_min", t_start)))
                        e_min = max(t_start, min(t_end, ev.get("end_min", s_min + 60)))
                        if e_min <= s_min:
                            e_min = s_min + 45

                        top_pct = ((s_min - t_start) / total_span) * 100
                        height_pct = max(9.0, ((e_min - s_min) / total_span) * 100)
                        if top_pct + height_pct > 100:
                            height_pct = 100 - top_pct

                        time_label = ev.get("ora", "")
                        if ev.get("ora_fine"):
                            time_label += f" - {ev.get('ora_fine')}"

                        extra_details_html = ""
                        loc_text = ev.get("location", "").strip()
                        desc_text = ev.get("desc", "").strip()
                        if desc_text.startswith("Calendario:"):
                            desc_text = ""

                        if height_pct >= 12.0 and loc_text:
                            clean_loc = strip_emojis(loc_text)
                            if clean_loc:
                                extra_details_html += f'<div style="font-size:9.5px;font-weight:700;opacity:0.85;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"><svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="display:inline-block;vertical-align:-1px;margin-right:2px;"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path><circle cx="12" cy="10" r="3"></circle></svg>{clean_loc}</div>'

                        if height_pct >= 18.0 and desc_text:
                            clean_desc = strip_emojis(desc_text)
                            if clean_desc:
                                extra_details_html += f'<div style="font-size:9px;font-weight:600;opacity:0.75;margin-top:2px;line-height:1.2;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;">{clean_desc}</div>'

                        is_active = (s_min <= now_min <= e_min)
                        bg = "#000" if is_active else "#fff"
                        color = "#fff" if is_active else "#000"
                        badge_bg = "#fff" if is_active else "#000"
                        badge_color = "#000" if is_active else "#fff"

                        if total_cols == 1:
                            col_pos_style = "left:45px;right:4px;"
                        else:
                            col_left_calc = f"calc(45px + (100% - 49px) * {col_idx / total_cols:.4f} + {2 if col_idx > 0 else 0}px)"
                            col_width_calc = f"calc((100% - 49px) * {1.0 / total_cols:.4f} - 3px)"
                            col_pos_style = f"left:{col_left_calc};width:{col_width_calc};"

                        timed_blocks += f'''
                        <div style="position:absolute;top:{top_pct:.2f}%;height:{height_pct:.2f}%;{col_pos_style}border:2px solid #000;border-radius:7px;background:{bg};color:{color};padding:5px 8px;box-sizing:border-box;z-index:2;display:flex;flex-direction:column;justify-content:flex-start;overflow:hidden;">
                          <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                            <span style="font-size:12px;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-right:4px;">{ev.get("summary","")}</span>
                            <span style="font-size:9px;font-weight:900;background:{badge_bg};color:{badge_color};padding:1px 4px;border-radius:3px;white-space:nowrap;">{time_label}</span>
                          </div>
                          {extra_details_html}
                        </div>
                        '''
            else:
                timed_blocks = '''
                <div style="position:absolute;top:40%;left:45px;right:10px;border:1.5px dashed #000;border-radius:8px;padding:12px;text-align:center;font-size:12px;font-weight:800;color:#555;background:#fff;">
                  Nessun impegno a orario per oggi
                </div>
                '''

            timeline_container = f'''
            <div style="flex:1;position:relative;width:100%;min-height:360px;margin-top:4px;">
              {hour_markers}
              {now_line}
              {timed_blocks}
            </div>
            '''

            if school_info["category"] == "bridge":
                sub_status = school_info["label"]
            elif weekday == 6 or school_info["category"] == "sunday":
                sub_status = "Domenica • Nessuna scuola"
            elif has_school and now_min >= switch_timeline_min:
                fine_h = fine_scuola_min // 60
                fine_m = fine_scuola_min % 60
                sub_status = f"Lezioni terminate ({fine_h:02d}:{fine_m:02d})"
            else:
                sub_status = "Oggi nessuna scuola"

            col_left_content = f'''
            <div style="display:flex;flex-direction:column;height:100%;">
              <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #000;padding-bottom:5px;margin-bottom:8px;">
                <div style="font-size:13px;font-weight:900;text-transform:uppercase;letter-spacing:0.5px;">LINEA DEL TEMPO • GIORNATA</div>
                <span style="font-size:11px;font-weight:900;color:#000;background:#eee;padding:2px 6px;border-radius:4px;border:1px solid #000;">{sub_status}</span>
              </div>
              {allday_html}
              {timeline_container}
            </div>
            '''
    else:
        col_left_content = f'''
        <div style="display:flex;flex-direction:column;height:100%;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <div style="font-size:13px;font-weight:900;text-transform:uppercase;letter-spacing:0.5px;">
              LEZIONI: {giorno_titolo}
            </div>
            <span style="font-size:11.5px;font-weight:800;color:#555;">32 Ore Settimanali</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:8px;">
            {lezioni_rows}
          </div>
        </div>
        '''

    # Colonna Destra Superiore:
    # Se Mattina/Sera -> Zaino & Libri
    # Se Giorno -> Se ci sono eventi iCloud mostra iCloud, altrimenti METEO FORECAST PADOVA (utile, pulito, zero AI slop)
    if current_phase in ["morning", "evening"] and has_school:
        libri_rows = ""
        for lb in libri_list:
            libri_rows += f'''
            <div style="border:1.5px solid #000;border-radius:8px;padding:9px 12px;background:#fff;">
              <div style="font-size:10.5px;font-weight:900;text-transform:uppercase;letter-spacing:0.4px;color:#444;">{lb["materia"]}</div>
              <div style="font-size:13px;font-weight:900;line-height:1.2;margin-top:2px;">{lb["titolo"]}</div>
            </div>
            '''
        sub_title = "ZAINO MATTINA • LIBRI DA PORTARE" if current_phase == "morning" else "PREPARAZIONE ZAINO PER DOMANI"
        col_right_top = f'''
        <div style="display:flex;flex-direction:column;">
          <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #000;padding-bottom:5px;margin-bottom:8px;">
            <div style="font-size:12px;font-weight:900;text-transform:uppercase;letter-spacing:0.5px;">{sub_title}</div>
            <span style="font-size:10px;font-weight:900;background:#000;color:#fff;padding:2px 6px;border-radius:3px;">CHECKLIST</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:6px;">
            {libri_rows}
          </div>
        </div>
        '''
    else:
        # Mostra SEMPRE il Meteo Forecast curato a destra (nessuna duplicazione di iCloud!)
        forecast_items = ""
        for f_item in meteo.get("forecast", []):
            forecast_items += f'''
            <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px;border:1.5px solid #000;border-radius:8px;background:#fff;">
              <div style="font-weight:900;font-size:13px;width:65px;">{f_item["giorno"]}</div>
              <div style="display:flex;align-items:center;gap:8px;flex:1;padding:0 8px;">
                <span style="display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;">{f_item.get("icon", "")}</span>
                <span style="font-weight:800;font-size:12px;text-transform:uppercase;color:#222;">{f_item["desc"]}</span>
              </div>
              <div style="font-weight:900;font-size:13.5px;text-align:right;white-space:nowrap;">
                {f_item["max"]}° <span style="font-size:11px;color:#555;font-weight:700;">/ {f_item["min"]}°</span>
              </div>
            </div>
            '''

        col_right_top = f'''
        <div style="display:flex;flex-direction:column;">
          <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #000;padding-bottom:5px;margin-bottom:8px;">
            <div style="font-size:12px;font-weight:900;text-transform:uppercase;letter-spacing:0.5px;">METEO & PREVISIONI • {meteo.get("temp", "--")}°C</div>
            <span style="font-size:10px;font-weight:900;border:1.5px solid #000;padding:1px 5px;border-radius:3px;">PADOVA</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:6px;">
            {forecast_items}
          </div>
        </div>
        '''

    if school_info["category"] == "holiday":
        holiday_type = school_info.get("holiday_type", "summer")
        h_tasks = get_holiday_tasks(holiday_type, target_d_obj, env)
        if holiday_type == "summer":
            compiti_header_title = "COMPITI & ATTIVITÀ ESTIVE"
            compiti_header_badge = "STATO AVANZAMENTO"
        elif holiday_type == "winter":
            compiti_header_title = "COMPITI PER IL RIENTRO (7 GENNAIO)"
            days_left = max(1, (date(2027, 1, 7) - target_d_obj).days) if target_d_obj < date(2027, 1, 7) else 0
            compiti_header_badge = f"{days_left} GIORNI AL RIENTRO" if days_left > 0 else "RIENTRO OGGI"
        elif holiday_type == "carnival":
            compiti_header_title = "VERIFICHE & COMPITI AL RIENTRO"
            compiti_header_badge = "RIENTRO GIOVEDÌ"
        elif holiday_type == "easter":
            compiti_header_title = "COMPITI PER IL RIENTRO (31 MARZO)"
            days_left = max(1, (date(2027, 3, 31) - target_d_obj).days) if target_d_obj < date(2027, 3, 31) else 0
            compiti_header_badge = f"{days_left} GIORNI AL RIENTRO" if days_left > 0 else "RIENTRO OGGI"
        else:
            compiti_header_title = "COMPITI & PROMEMORIA"
            compiti_header_badge = "ATTIVITÀ"

        compiti_items = ""
        if h_tasks:
            for c in h_tasks[:3]:
                is_test = c.get("is_test", False)
                bg = "#000" if is_test else "#fff"
                text_color = "#fff" if is_test else "#111"
                title_color = "#fff" if is_test else "#000"
                badge_bg = "#fff" if is_test else "#000"
                badge_color = "#000" if is_test else "#fff"

                compiti_items += f'''
                <div style="border:2px solid #000;border-radius:6px;padding:7px 9px;background:{bg};color:{text_color};">
                  <div style="display:flex;justify-content:space-between;align-items:center;font-weight:900;font-size:11.5px;color:{title_color};">
                    <span>{strip_emojis(c["materia"])}</span>
                    <span style="font-size:10px;font-weight:900;background:{badge_bg};color:{badge_color};padding:1px 6px;border-radius:3px;">{c["stato"]}</span>
                  </div>
                  <div style="font-size:11px;font-weight:600;color:{text_color};margin-top:3px;line-height:1.25;opacity:0.95;">{strip_emojis(c["descrizione"])}</div>
                </div>
                '''
        else:
            empty_compiti_msg = "Nessun compito o attività registrata" if holiday_type == "summer" else "Nessun compito registrato per il rientro"
            compiti_items = f'<div style="border:1.5px dashed #000;border-radius:6px;padding:10px;text-align:center;font-size:11px;font-weight:700;color:#555;">{empty_compiti_msg}</div>'
    else:
        compiti_header_title = "COMPITI & PROMEMORIA"
        compiti_header_badge = "SYNC LIVE"
        compiti_items = ""

        today_date = now.date()
        tomorrow_date = today_date + timedelta(days=1)
        hide_today_tasks = (cur_time >= time(19, 0))

        visible_compiti = []
        if compiti and len(compiti) > 0:
            for c in compiti:
                # Estrazione o ricostruzione data evento
                c_date = None
                if "date_str" in c and c["date_str"]:
                    try:
                        c_date = date.fromisoformat(c["date_str"])
                    except Exception:
                        pass
                if not c_date:
                    raw_d = c.get("data", "")
                    if raw_d == "Oggi":
                        c_date = today_date
                    elif raw_d == "Domani":
                        c_date = tomorrow_date
                    elif "/" in raw_d:
                        try:
                            g, m = map(int, raw_d.split("/"))
                            y = today_date.year if m >= today_date.month else today_date.year + 1
                            c_date = date(y, m, g)
                        except Exception:
                            pass
                if not c_date:
                    c_date = today_date + timedelta(days=99)

                # Filtra eventi già passati prima di oggi
                if c_date < today_date:
                    continue

                # Alle 19:00 spariscono i compiti della giornata stessa
                if hide_today_tasks and c_date == today_date:
                    continue

                # Ricalcola etichetta temporale dinamica rispetto alla data odierna
                if c_date == today_date:
                    display_data = "Oggi"
                elif c_date == tomorrow_date:
                    display_data = "Domani"
                else:
                    display_data = c_date.strftime("%d/%m")

                visible_compiti.append({
                    "materia": c["materia"],
                    "data": display_data,
                    "date_val": c_date,
                    "descrizione": c["descrizione"],
                    "is_test": c.get("is_test", False)
                })

            # Ordina SEMPRE rigorosamente in ordine di data crescente
            visible_compiti.sort(key=lambda x: (x["date_val"], not x["is_test"]))

        if visible_compiti and len(visible_compiti) > 0:
            for c in visible_compiti[:3]:
                is_test = c.get("is_test", False)
                bg = "#000" if is_test else "#fff"
                text_color = "#fff" if is_test else "#111"
                title_color = "#fff" if is_test else "#000"
                badge_bg = "#fff" if is_test else "#000"
                badge_color = "#000" if is_test else "#fff"

                compiti_items += f'''
                <div style="border:2px solid #000;border-radius:6px;padding:8px 10px;background:{bg};color:{text_color};">
                  <div style="display:flex;justify-content:space-between;align-items:center;font-weight:900;font-size:11.5px;color:{title_color};">
                    <span>{c["materia"]}</span>
                    <span style="font-size:10px;font-weight:900;background:{badge_bg};color:{badge_color};padding:1px 6px;border-radius:3px;">{c["data"]}</span>
                  </div>
                  <div style="font-size:11px;font-weight:600;color:{text_color};margin-top:4px;line-height:1.25;opacity:0.95;">{c["descrizione"]}</div>
                </div>
                '''
        else:
            compiti_items = '<div style="border:1.5px dashed #000;border-radius:6px;padding:10px;text-align:center;font-size:11px;font-weight:700;color:#555;">Nessun compito registrato</div>'

    # Anti-Burn-in & Anti-Ghosting Pixel Shifting:
    # Varia impercettibilmente il padding interno della dashboard di ±1 o ±2 pixel
    # in base all'ora e al minuto. Sposta le linee divisorie e i testi statici
    # evitando che le particelle elettroforetiche restino polarizzate negli stessi identici punti.
    # All'occhio umano e assolutamente invisibile (1 o 2 pixel su 1024x758).
    minute_idx = now.minute
    pad_top = 18 + (minute_idx % 3)            # 18px, 19px, 20px
    pad_bottom = 20 - (minute_idx % 3)         # 20px, 19px, 18px
    pad_left = 24 + ((minute_idx // 3) % 3)    # 24px, 25px, 26px
    pad_right = 26 - ((minute_idx // 3) % 3)   # 26px, 25px, 24px

    html = f'''<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=1024, height=758, initial-scale=1.0">
  <title>Dashboard 3ID</title>
  <!-- Auto-refresh ogni 2 minuti per browser Kindle -->
  <meta http-equiv="refresh" content="120">
  <style>
    * {{ box-sizing: border-box; -webkit-font-smoothing: antialiased; margin:0; padding:0; }}
    body {{
      width: 1024px;
      height: 758px;
      overflow: hidden;
      background: #ffffff;
      color: #000000;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      padding: {pad_top}px {pad_right}px {pad_bottom}px {pad_left}px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
  </style>
</head>
<body>

  <!-- ==================== HEADER ==================== -->
  <header style="display:flex;justify-content:space-between;align-items:flex-end;border-bottom:4px solid #000;padding-bottom:10px;">
    <div>
      <h1 style="font-size:28px;font-weight:900;text-transform:uppercase;letter-spacing:-0.5px;">{data_str}</h1>
      <div style="font-size:12px;font-weight:800;color:#333;margin-top:3px;letter-spacing:0.3px;">
        ITI F. SEVERI PADOVA • CLASSE 3ID • INFORMATICA E TELECOMUNICAZIONI
      </div>
    </div>
    <div style="display:flex;align-items:center;gap:14px;text-align:right;">
      <div>
        <div id="live-clock" style="font-size:48px;font-weight:900;line-height:0.9;letter-spacing:-1px;">{ora_str}</div>
        <div style="display:flex;align-items:center;justify-content:flex-end;gap:5px;font-size:11.5px;font-weight:900;text-transform:uppercase;color:#444;margin-top:4px;">
          <span style="display:inline-flex;align-items:center;width:16px;height:16px;">{meteo.get("icon","")}</span>
          <span>{meteo["desc"]} • {meteo["temp"]}°C</span>
        </div>
      </div>
      <div style="border:2.5px solid #000;border-radius:5px;padding:3px 7px;font-size:12px;font-weight:900;display:inline-flex;align-items:center;">
        {battery_display}
      </div>
    </div>
  </header>

  <!-- ==================== MAIN 2 COLONNE ==================== -->
  <main style="display:flex;gap:22px;flex:1;margin:14px 0;overflow:hidden;">
    
    <!-- COLONNA SINISTRA (ORARIO O CALENDARIO ICLOUD) -->
    <section style="flex:1.4;display:flex;flex-direction:column;justify-content:space-between;height:100%;">
      {col_left_content}
    </section>

    <!-- COLONNA DESTRA (ZAINO / METEO FORECAST / COMPITI) -->
    <section style="flex:1;display:flex;flex-direction:column;justify-content:space-between;height:100%;border-left:2.5px solid #000;padding-left:20px;">
      {col_right_top}

      <!-- COMPITI -->
      <div style="border-top:2px solid #000;padding-top:8px;margin-top:auto;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
          <div style="font-size:11.5px;font-weight:900;text-transform:uppercase;letter-spacing:0.4px;">{compiti_header_title}</div>
          <span style="font-size:9.5px;font-weight:800;color:#555;">{compiti_header_badge}</span>
        </div>
        <div style="display:flex;flex-direction:column;gap:5px;">
          {compiti_items}
        </div>
      </div>
    </section>

  </main>

  <!-- ==================== FOOTER ==================== -->
  <footer style="display:flex;justify-content:space-between;align-items:center;border-top:2px solid #000;padding-top:6px;font-size:10.5px;font-weight:800;color:#444;text-transform:uppercase;letter-spacing:0.5px;">
    <div>ITI F. SEVERI • 3ID INFORMATICA</div>
    <div>ULTIMO SYNC: {ora_str}</div>
  </footer>

  <!-- SCRIPT OROLOGIO DINAMICO IN TEMPO REALE -->
  <script>
    var serverTimestamp = {int(now.timestamp() * 1000)};
    function updateClock() {{
      try {{
        var d = new Date(serverTimestamp);
        var h = String(d.getHours()).padStart(2, '0');
        var m = String(d.getMinutes()).padStart(2, '0');
        var timeStr = h + ':' + m;

        // 1. Aggiorna orologio principale
        var el = document.getElementById('live-clock');
        if (el) {{
          el.innerText = timeStr;
        }}

        // 2. Aggiorna e sincronizza indicatore linea del tempo
        var tStart = 7 * 60;   // 07:00
        var tEnd = 23 * 60;    // 23:00
        var totalSpan = tEnd - tStart;
        var curMin = d.getHours() * 60 + d.getMinutes();

        var tlBadge = document.getElementById('timeline-now-badge');
        if (tlBadge) {{
          tlBadge.innerText = timeStr;
        }}
        var tlLine = document.getElementById('timeline-now-line');
        if (tlLine && curMin >= tStart && curMin <= tEnd) {{
          var pct = ((curMin - tStart) / totalSpan) * 100;
          tlLine.style.top = pct.toFixed(2) + '%';
        }}
      }} catch(e) {{}}
    }}
    // Aggiorna subito
    updateClock();
  </script>

</body>
</html>
'''
    return html

class KindleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        client_ip = self.client_address[0]
        device_param = query.get("device", [""])[0].lower()
        is_k4 = (device_param == "k4") or (client_ip == "192.168.1.29")

        if path in ["/", "/index.html"]:
            if is_k4:
                import dashboard_k4
                html_content = dashboard_k4.build_k4_dashboard_html(query, weather_getter=get_weather).encode("utf-8")
            else:
                html_content = build_dashboard_html(query).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_content)))
            self.end_headers()
            self.wfile.write(html_content)
        elif path == "/k4":
            import dashboard_k4
            html_content = dashboard_k4.build_k4_dashboard_html(query, weather_getter=get_weather).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_content)))
            self.end_headers()
            self.wfile.write(html_content)
        elif path == "/api/status":
            now_dt = datetime.now()
            res = json.dumps({
                "status": "running",
                "timestamp": now_dt.isoformat(),
                "school_info": get_school_day_info(now_dt.date())
            }, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(res)))
            self.end_headers()
            self.wfile.write(res)
        elif path == "/api/calendar":
            env = load_env()
            force_ref = query.get("refresh", [""])[0] in ["1", "true", "True"]
            events = get_icloud_events(env, force_refresh=force_ref)
            res = json.dumps({"status": "ok", "count": len(events), "events": events}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(res)))
            self.end_headers()
            self.wfile.write(res)
        elif path == "/api/image":
            batt_val = query.get("batt", [""])[0]
            batt_file = "/tmp/kindle_k4_battery.txt" if is_k4 else "/tmp/kindle_battery.txt"
            if batt_val and batt_val.isdigit():
                try:
                    with open(batt_file, "w") as bf:
                        bf.write(batt_val)
                except Exception:
                    pass
            chg_val = query.get("charging", [""])[0]
            chg_file = "/tmp/kindle_k4_charging.txt" if is_k4 else "/tmp/kindle_charging.txt"
            if chg_val in ["0", "1", "true", "false", "True", "False"]:
                try:
                    with open(chg_file, "w") as cf:
                        cf.write(chg_val)
                except Exception:
                    pass

            if is_k4:
                img_path = "/opt/kindleCalendar/dashboard_k4.png"
                if not os.path.exists(img_path):
                    img_path = "dashboard_k4.png"
            else:
                img_path = "/opt/kindleCalendar/dashboard_kindle.png"
                if not os.path.exists(img_path):
                    img_path = "dashboard_kindle.png"

            if os.path.exists(img_path):
                with open(img_path, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"No image rendered yet")
        else:
            self.send_response(404)
            self.end_headers()
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ["/api/calendar/refresh", "/api/calendar"]:
            env = load_env()
            events = get_icloud_events(env, force_refresh=True)
            res = json.dumps({"status": "refreshed", "count": len(events), "events": events}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(res)))
            self.end_headers()
            self.wfile.write(res)
        else:
            self.send_response(404)
            self.end_headers()

    def do_HEAD(self):
        self.do_GET()

    def log_message(self, format, *args):
        pass

def _caldav_background_loop():
    while True:
        try:
            env = load_env()
            user = env.get("ICLOUD_APPLE_ID", "").strip()
            pwd = env.get("ICLOUD_APP_PASSWORD", "").strip()
            if user and pwd:
                fetch_caldav_events_direct(user, pwd, datetime.now().date())
        except Exception:
            pass
        pytime.sleep(45)

def run_server(port=5055):
    # Avvia sincronizzazione continua CalDAV in background (ogni 45s)
    bg_thread = threading.Thread(target=_caldav_background_loop, daemon=True)
    bg_thread.start()

    server = HTTPServer(("0.0.0.0", port), KindleHandler)
    print(f"=== SERVER DASHBOARD 3ID ATTIVO ===")
    print(f"Locale: http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    env = load_env()
    port = int(env.get("PORT", 5055))
    run_server(port)
