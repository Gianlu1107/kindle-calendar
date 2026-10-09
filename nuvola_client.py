import os
import json
import time
import urllib.request
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_FILE = "/tmp/nuvola_cache.json"
SESSION_FILE = os.path.join(DATA_DIR, "nuvola_session.json")

_CACHE_DATA = {
    "timestamp": 0,
    "compiti": []
}

def load_cached_compiti():
    global _CACHE_DATA
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                if time.time() - d.get("timestamp", 0) < 1800:
                    _CACHE_DATA = d
                    return d.get("compiti", [])
        except Exception:
            pass
    return _CACHE_DATA.get("compiti", [])

def get_bearer_token(cookies_header):
    req = urllib.request.Request(
        "https://nuvola.madisoft.it/api-studente/v1/login-from-web",
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Cookie": cookies_header,
            "Accept": "application/json"
        }
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        if r.status == 200:
            d = json.loads(r.read().decode("utf-8"))
            return d.get("token")
    return None

def fetch_nuvola_agenda(force_refresh=False):
    global _CACHE_DATA
    now_ts = time.time()
    if not force_refresh and (now_ts - _CACHE_DATA["timestamp"] < 1800):
        if _CACHE_DATA["compiti"]:
            return _CACHE_DATA["compiti"]

    cached = load_cached_compiti()
    if cached and not force_refresh:
        return cached

    if not os.path.exists(SESSION_FILE):
        return cached or []

    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            sess = json.load(f)

        cookies = sess.get("cookies", [])
        cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies if "nuvola" in c.get("domain", "")])
        
        token = get_bearer_token(cookie_header)
        if not token:
            print("Nuvola: Impossibile rinnovare Bearer token con la sessione attuale")
            return cached or []

        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Accept": "application/json"
        }

        alunno_id = "73104"
        compiti_list = []
        today = datetime.now().date()

        # Interroga le date da oggi ai prossimi 7 giorni
        for i in range(7):
            target_d = today + timedelta(days=i)
            d_str = target_d.strftime("%d-%m-%Y")
            url = f"https://nuvola.madisoft.it/api-studente/v1/alunno/{alunno_id}/compito/elenco/{d_str}?contextAlunno={alunno_id}"
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=6) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        for item in data.get("valori", []):
                            materia = item.get("materia") or "Compito"
                            desc_raw = item.get("descrizioneCompito", [])
                            if isinstance(desc_raw, list):
                                desc = " ".join(desc_raw)
                            else:
                                desc = str(desc_raw or "")
                            
                            is_test = False
                            low = desc.lower()
                            if any(k in low for k in ["verifica", "interrogazione", "test", "compito in classe"]):
                                is_test = True

                            if target_d == today:
                                d_label = "Oggi"
                            elif target_d == today + timedelta(days=1):
                                d_label = "Domani"
                            else:
                                d_label = target_d.strftime("%d/%m")

                            compiti_list.append({
                                "materia": materia.upper().strip(),
                                "docente": item.get("docente", "").strip(),
                                "data": d_label,
                                "date_val": target_d.isoformat(),
                                "descrizione": desc.strip(),
                                "is_test": is_test
                            })
            except Exception:
                pass

        # Estrai eventi di classe / verifiche formali
        url_eventi = f"https://nuvola.madisoft.it/api-studente/v1/alunno/{alunno_id}/eventi-classe?contextAlunno={alunno_id}&limit=10"
        req_ev = urllib.request.Request(url_eventi, headers=headers)
        try:
            with urllib.request.urlopen(req_ev, timeout=6) as resp:
                if resp.status == 200:
                    ev_data = json.loads(resp.read().decode("utf-8"))
                    for ev in ev_data.get("valori", []):
                        ev_d_str = ev.get("dataInizio", "")[:10]
                        if ev_d_str:
                            ev_d = datetime.fromisoformat(ev_d_str).date()
                            if ev_d >= today:
                                if ev_d == today:
                                    d_label = "Oggi"
                                elif ev_d == today + timedelta(days=1):
                                    d_label = "Domani"
                                else:
                                    d_label = ev_d.strftime("%d/%m")

                                compiti_list.append({
                                    "materia": (ev.get("nome") or "AVVISO").upper().strip(),
                                    "docente": ev.get("docente", "").strip(),
                                    "data": d_label,
                                    "date_val": ev_d.isoformat(),
                                    "descrizione": ev.get("descrizione", "").strip(),
                                    "is_test": True
                                })
        except Exception:
            pass

        # Ordina per data crescente (prima verifiche se stesso giorno)
        compiti_list.sort(key=lambda x: (x["date_val"], not x["is_test"]))

        _CACHE_DATA = {
            "timestamp": now_ts,
            "compiti": compiti_list
        }
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_CACHE_DATA, f, ensure_ascii=False, indent=2)

        return compiti_list

    except Exception as e:
        print("Errore fetch Nuvola agenda:", e)
        return cached or []
