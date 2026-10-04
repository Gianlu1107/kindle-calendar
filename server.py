import os
import json
import re
from datetime import datetime, timedelta, time
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

# Carica orario corretto (32 ore settimanali e blocchi 2 ore) e libri
with open(os.path.join(DATA_DIR, "orario_3id.json"), "r", encoding="utf-8") as f:
    ORARIO_DATA = json.load(f)

with open(os.path.join(DATA_DIR, "libri_3id.json"), "r", encoding="utf-8") as f:
    LIBRI_DATA = json.load(f)

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

# Calendario Scolastico Veneto 2026/2027 (DGR Veneto n. 239/2026 e s.m.i.)
# Festività, vacanze e ponti deliberati per le scuole del Veneto
PONTI_FESTIVITA_2026_2027 = {
    "2026-11-01": "Tutti i Santi",
    "2026-12-07": "Ponte dell'Immacolata",
    "2026-12-08": "Immacolata Concezione",
    # Vacanze di Natale: 24 dicembre 2026 - 6 gennaio 2027
    "2026-12-24": "Vacanze di Natale",
    "2026-12-25": "Natale",
    "2026-12-26": "Santo Stefano",
    "2026-12-27": "Vacanze di Natale",
    "2026-12-28": "Vacanze di Natale",
    "2026-12-29": "Vacanze di Natale",
    "2026-12-30": "Vacanze di Natale",
    "2026-12-31": "Vacanze di Natale",
    "2027-01-01": "Capodanno",
    "2027-01-02": "Vacanze di Natale",
    "2027-01-03": "Vacanze di Natale",
    "2027-01-04": "Vacanze di Natale",
    "2027-01-05": "Vacanze di Natale",
    "2027-01-06": "Epifania",
    # Carnevale e Mercoledì delle Ceneri: 8 - 10 febbraio 2027
    "2027-02-08": "Vacanze di Carnevale",
    "2027-02-09": "Martedì Grasso",
    "2027-02-10": "Mercoledì delle Ceneri",
    # Vacanze di Pasqua: 25 - 30 marzo 2027
    "2027-03-25": "Vacanze di Pasqua",
    "2027-03-26": "Venerdì Santo",
    "2027-03-27": "Vacanze di Pasqua",
    "2027-03-28": "Pasqua",
    "2027-03-29": "Lunedì dell'Angelo",
    "2027-03-30": "Vacanze di Pasqua",
    # Anniversario della Liberazione
    "2027-04-25": "Festa della Liberazione",
    # Ponte Festa del Lavoro: 29 e 30 aprile 2027 + 1 maggio
    "2027-04-29": "Ponte 1° Maggio",
    "2027-04-30": "Ponte 1° Maggio",
    "2027-05-01": "Festa del Lavoro",
    # Ponte Festa della Repubblica: 31 maggio e 1 giugno 2027 + 2 giugno
    "2027-05-31": "Ponte 2 Giugno",
    "2027-06-01": "Ponte 2 Giugno",
    "2027-06-02": "Festa della Repubblica",
    # Santo Patrono di Padova (Sant'Antonio)
    "2027-06-13": "Sant'Antonio (Patrono Padova)"
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

def get_icloud_events(env):
    url = env.get("ICLOUD_ICAL_URL", "").strip()
    content = ""
    # Se non c'è URL o punta a un file locale
    local_ics = "/opt/kindleCalendar/calendar_feed.ics"
    if not url and os.path.exists(local_ics):
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
            req = urllib.request.Request(url, headers={"User-Agent": "KindleServer/1.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            print("iCloud sync error:", e)
            return []

    if not content:
        return []

    try:
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
                cur["start_raw"] = line.split(":")[-1].strip()
            elif line.startswith("DTEND"):
                cur["end_raw"] = line.split(":")[-1].strip()
            elif line.startswith("LOCATION:"):
                cur["location"] = line[9:].strip()
            elif line.startswith("DESCRIPTION:"):
                cur["desc"] = line[12:].strip()
            elif line.startswith("END:VEVENT"):
                now_str = datetime.now().strftime("%Y%m%d")
                start = cur.get("start_raw", "")
                end = cur.get("end_raw", "")
                summ = strip_emojis(cur.get("summary", ""))
                cur["summary"] = summ
                cur["location"] = strip_emojis(cur.get("location", ""))
                cur["desc"] = strip_emojis(cur.get("desc", ""))
                if start.startswith(now_str) or not start:
                    is_allday = True
                    start_min = 0
                    end_min = 24 * 60
                    ora_fmt = "Tutto il giorno"
                    ora_fine_fmt = ""

                    if "T" in start and len(start) >= 13:
                        is_allday = False
                        sh = int(start[9:11])
                        sm = int(start[11:13])
                        start_min = sh * 60 + sm
                        ora_fmt = f"{start[9:11]}:{start[11:13]}"
                        if "T" in end and len(end) >= 13:
                            eh = int(end[9:11])
                            em = int(end[11:13])
                            end_min = eh * 60 + em
                            ora_fine_fmt = f"{end[9:11]}:{end[11:13]}"
                        else:
                            end_min = start_min + 60
                            ora_fine_fmt = f"{(sh+1)%24:02d}:{sm:02d}"

                    cur["is_allday"] = is_allday
                    cur["start_min"] = start_min
                    cur["end_min"] = end_min
                    cur["ora"] = ora_fmt
                    cur["ora_fine"] = ora_fine_fmt
                    dedup_key = (summ.lower(), cur["ora"])
                    if dedup_key not in seen:
                        seen.add(dedup_key)
                        events.append(cur)

        # Ordina: prima per start_min se a orario, altrimenti in fondo
        def sort_key(ev):
            return (1, 0) if ev.get("is_allday") else (0, ev.get("start_min", 0))
        events.sort(key=sort_key)
        return events
    except Exception as e:
        print("iCloud sync error:", e)
        return []

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

                # Priorità base temporale: Domani (0), Oggi (1), Date future (2)
                tomorrow_date = (now + timedelta(days=1)).date()
                if ev_date == tomorrow_date:
                    priority = 0
                elif ev_date == now.date():
                    priority = 1
                else:
                    priority = 2

                raw_items.append({
                    "priority": priority,
                    "date_val": ev_date or (now + timedelta(days=99)).date(),
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

        # Ordina CRONOLOGICAMENTE: prima domani, poi i giorni a seguire in ordine di data crescente.
        # Così si vedono tutti i compiti del giorno successivo (normali e verifiche) e non solo verifiche future!
        raw_items.sort(key=lambda x: (x["priority"], x["date_val"]))

        for item in raw_items:
            compiti.append({
                "materia": strip_emojis(item["materia"]),
                "data": item["data"],
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
    cur_time = now.time()

    t_0630 = time(6, 30)
    t_0800 = time(8, 0)
    t_2300 = time(23, 0)

    mode_param = query_params.get("mode", [""])[0]
    if mode_param in ["morning", "day", "evening"]:
        current_phase = mode_param
    else:
        if t_0630 <= cur_time < t_0800:
            current_phase = "morning"
        elif t_0800 <= cur_time < t_2300:
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

    # Controllo Ponti e Festività Scolastiche Veneto 2026/2027
    target_iso = target_date.strftime("%Y-%m-%d")
    ponte_nome = PONTI_FESTIVITA_2026_2027.get(target_iso, "")

    lezioni = list(ORARIO_DATA["schedule"].get(giorno_key, []))
    # A scuola si va dal lunedì al sabato (weekday 0..5), salvo che non ci sia ponte/festa
    is_holiday = bool(ponte_nome)
    has_school = len(lezioni) > 0 and (weekday != 6 or override_day) and (not is_holiday or bool(override_day))

    # Evidenziazione lezione in corso
    ora_corrente_str = now.strftime("%H:%M")
    for l in lezioni:
        l["in_corso"] = (current_phase == "day" and has_school and (l["inizio"] <= ora_corrente_str <= l["fine"]))

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
    icloud_events = get_icloud_events(env)
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

    # Colonna Sinistra (se non ci sono lezioni scolastiche) -> LINEA DEL TEMPO GIORNALIERA
    if not has_school:
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
        # 16 ore = 960 minuti totali, altezza timeline proporzionata
        t_start = 7 * 60   # 07:00
        t_end = 23 * 60    # 23:00
        total_span = t_end - t_start

        # Marker delle ore principali (ogni 2 ore: 08:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00, 22:00)
        hour_markers = ""
        for h in range(8, 23, 2):
            pos_pct = ((h * 60 - t_start) / total_span) * 100
            hour_markers += f'''
            <div style="position:absolute;top:{pos_pct:.2f}%;left:0;right:0;display:flex;align-items:center;pointer-events:none;z-index:1;">
              <span style="font-size:10px;font-weight:900;width:38px;color:#444;background:#fff;line-height:1;">{h:02d}:00</span>
              <div style="flex:1;border-bottom:1px dashed #ccc;height:1px;"></div>
            </div>
            '''

        # Blocchi grafici degli impegni posizionati esattamente sulla linea del tempo
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
            for ev in timed_events:
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

                # Mostra dettagli extra (luogo, descrizione) SE E SOLO SE c'è abbastanza spazio verticale nel blocco
                extra_details_html = ""
                loc_text = ev.get("location", "").strip()
                desc_text = ev.get("desc", "").strip()
                # Rimuovi prefissi generici
                if desc_text.startswith("Calendario:"):
                    desc_text = ""

                # Se il blocco è alto almeno il 13% (circa 1 ora e mezza / 2 ore), c'è spazio per il luogo
                if height_pct >= 12.0 and loc_text:
                    clean_loc = strip_emojis(loc_text)
                    if clean_loc:
                        extra_details_html += f'<div style="font-size:10px;font-weight:700;opacity:0.85;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"><svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="display:inline-block;vertical-align:-1px;margin-right:3px;"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path><circle cx="12" cy="10" r="3"></circle></svg>{clean_loc}</div>'

                # Se il blocco è ancora più alto (oltre 18%, cioè 3+ ore), mostra anche la descrizione/note
                if height_pct >= 18.0 and desc_text:
                    clean_desc = strip_emojis(desc_text)
                    if clean_desc:
                        extra_details_html += f'<div style="font-size:9.5px;font-weight:600;opacity:0.75;margin-top:2px;line-height:1.2;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;">{clean_desc}</div>'

                # Evidenzia se l'impegno è in corso adesso
                is_active = (s_min <= now_min <= e_min)
                bg = "#000" if is_active else "#fff"
                color = "#fff" if is_active else "#000"
                badge_bg = "#fff" if is_active else "#000"
                badge_color = "#000" if is_active else "#fff"

                timed_blocks += f'''
                <div style="position:absolute;top:{top_pct:.2f}%;height:{height_pct:.2f}%;left:45px;right:4px;border:2px solid #000;border-radius:7px;background:{bg};color:{color};padding:5px 9px;box-sizing:border-box;z-index:2;display:flex;flex-direction:column;justify-content:center;overflow:hidden;">
                  <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="font-size:13px;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-right:6px;">{ev.get("summary","")}</span>
                    <span style="font-size:10px;font-weight:900;background:{badge_bg};color:{badge_color};padding:1px 5px;border-radius:3px;white-space:nowrap;">{time_label}</span>
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

        sub_status = ponte_nome if ponte_nome else ("Domenica • Nessuna scuola" if weekday == 6 else "Oggi nessuna scuola")
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

    compiti_items = ""
    if compiti and len(compiti) > 0:
        for c in compiti[:3]:
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
      padding: 18px 24px;
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

    <!-- COLONNA DESTRA (ZAINO / METEO FORECAST / COMPITI CLASSEVIVA) -->
    <section style="flex:1;display:flex;flex-direction:column;justify-content:space-between;height:100%;border-left:2.5px solid #000;padding-left:20px;">
      {col_right_top}

      <!-- COMPITI CLASSEVIVA -->
      <div style="border-top:2px solid #000;padding-top:8px;margin-top:auto;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
          <div style="font-size:11.5px;font-weight:900;text-transform:uppercase;letter-spacing:0.4px;">COMPITI & PROMEMORIA (CLASSEVIVA)</div>
          <span style="font-size:9.5px;font-weight:800;color:#555;">SYNC LIVE</span>
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

        if path in ["/", "/index.html"]:
            html_content = build_dashboard_html(query).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_content)))
            self.end_headers()
            self.wfile.write(html_content)
        elif path == "/api/status":
            res = json.dumps({"status": "running", "timestamp": datetime.now().isoformat()}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(res)))
            self.end_headers()
            self.wfile.write(res)
        elif path == "/api/image":
            batt_val = query.get("batt", [""])[0]
            if batt_val and batt_val.isdigit():
                try:
                    with open("/tmp/kindle_battery.txt", "w") as bf:
                        bf.write(batt_val)
                except Exception:
                    pass
            chg_val = query.get("charging", [""])[0]
            if chg_val in ["0", "1", "true", "false", "True", "False"]:
                try:
                    with open("/tmp/kindle_charging.txt", "w") as cf:
                        cf.write(chg_val)
                except Exception:
                    pass
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
    def do_HEAD(self):
        self.do_GET()

    def log_message(self, format, *args):
        pass

def run_server(port=5055):
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
