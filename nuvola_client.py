import os
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_FILE = "/tmp/nuvola_cache.json"
SESSION_FILE = os.path.join(DATA_DIR, "nuvola_session.json")
ENV_FILE = os.path.join(BASE_DIR, ".env")

_CACHE_DATA = {
    "timestamp": 0,
    "compiti": []
}

def load_env_credentials():
    username = os.environ.get("NUVOLA_USERNAME")
    password = os.environ.get("NUVOLA_PASSWORD")
    if not username and os.path.exists(ENV_FILE):
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'").strip('"')
                    if k == "NUVOLA_USERNAME":
                        username = v
                    elif k == "NUVOLA_PASSWORD":
                        password = v
        except Exception:
            pass
    return username, password

def load_cached_compiti(allow_stale=False):
    global _CACHE_DATA
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                age = time.time() - d.get("timestamp", 0)
                if age < 1800 or allow_stale:
                    _CACHE_DATA = d
                    return d.get("compiti", [])
        except Exception:
            pass
    return _CACHE_DATA.get("compiti", [])

def get_valid_token():
    """
    Ottiene un token JWT valido per le API di Nuvola:
    1. Se presente in nuvola_session.json e non scaduto, lo usa direttamente.
    2. Se presente un refreshToken in nuvola_session.json, rinnova il token via API nativa mobile.
    3. Se scaduto o assente, effettua il login trasparente con le credenziali Nuvola (da .env)
       utilizzando l'endpoint nativo dell'app mobile (POST /api-studente/v1/login),
       senza richiedere SPID/CIE.
    """
    sess = {}
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                sess = json.load(f)
        except Exception:
            sess = {}

    cur_time = time.time()

    # 1. Token ancora valido (con 60s di margine di sicurezza)
    token = sess.get("token")
    expires_at = sess.get("expires_at", 0)
    if token and cur_time < (expires_at - 60):
        return token

    # 2. Tentativo di rinnovo con refresh_token
    refresh_token = sess.get("refreshToken")
    if refresh_token:
        try:
            payload = json.dumps({"refresh_token": refresh_token}).encode("utf-8")
            req = urllib.request.Request(
                "https://nuvola.madisoft.it/api-studente/v1/refresh-token",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "okhttp/4.9.2"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=7) as r:
                if r.status == 200:
                    d = json.loads(r.read().decode("utf-8"))
                    new_token = d.get("token")
                    new_refresh = d.get("refreshToken") or refresh_token
                    if new_token:
                        sess["token"] = new_token
                        sess["refreshToken"] = new_refresh
                        sess["expires_at"] = cur_time + 1700
                        sess["timestamp"] = cur_time
                        os.makedirs(DATA_DIR, exist_ok=True)
                        with open(SESSION_FILE, "w", encoding="utf-8") as f:
                            json.dump(sess, f, indent=2)
                        return new_token
        except Exception as e:
            print("Nuvola: refresh token non riuscito, fallback su login credenziali:", e)

    # 3. Login diretto tramite endpoint nativo mobile API
    username, password = load_env_credentials()
    if username and password and username not in ["YOUR_NUVOLA_USERNAME", "tua_username_o_email"] and not password.startswith("YOUR_"):
        try:
            payload = json.dumps({"username": username, "password": password}).encode("utf-8")
            req = urllib.request.Request(
                "https://nuvola.madisoft.it/api-studente/v1/login",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "okhttp/4.9.2"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=8) as r:
                if r.status == 200:
                    d = json.loads(r.read().decode("utf-8"))
                    new_token = d.get("token")
                    new_refresh = d.get("refreshToken")
                    if new_token:
                        sess["token"] = new_token
                        sess["refreshToken"] = new_refresh
                        sess["expires_at"] = cur_time + 1700
                        sess["timestamp"] = cur_time
                        os.makedirs(DATA_DIR, exist_ok=True)
                        with open(SESSION_FILE, "w", encoding="utf-8") as f:
                            json.dump(sess, f, indent=2)
                        print("Nuvola: login automatico mobile API completato con successo")
                        return new_token
        except Exception as e:
            print("Nuvola: errore login credenziali:", e)

    # 4. Fallback legacy (cookie session da login web se presenti)
    cookies = sess.get("cookies", [])
    if cookies:
        cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies if "nuvola" in c.get("domain", "")])
        try:
            req = urllib.request.Request(
                "https://nuvola.madisoft.it/api-studente/v1/login-from-web",
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                    "Cookie": cookie_header,
                    "Accept": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=6) as r:
                if r.status == 200:
                    ct = r.headers.get("Content-Type", "")
                    if "application/json" in ct:
                        d = json.loads(r.read().decode("utf-8"))
                        return d.get("token")
        except Exception:
            pass

    return None

def fetch_nuvola_agenda(force_refresh=False):
    global _CACHE_DATA
    now_ts = time.time()
    if not force_refresh and (now_ts - _CACHE_DATA.get("timestamp", 0) < 1800):
        if _CACHE_DATA.get("compiti"):
            return _CACHE_DATA["compiti"]

    cached = load_cached_compiti(allow_stale=False)
    if cached and not force_refresh:
        return cached

    token = get_valid_token()
    if not token:
        print("Nuvola: token non disponibile, uso cache su disco")
        return load_cached_compiti(allow_stale=True)

    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "okhttp/4.9.2",
        "Accept": "application/json"
    }

    try:
        # Recupera ID alunno attivo
        alunno_id = 73104
        try:
            req_alunni = urllib.request.Request("https://nuvola.madisoft.it/api-studente/v1/alunni", headers=headers)
            with urllib.request.urlopen(req_alunni, timeout=6) as resp_a:
                if resp_a.status == 200:
                    alunni_data = json.loads(resp_a.read().decode("utf-8"))
                    for a in alunni_data.get("valori", []):
                        if a.get("attivoInAnnoScolasticoCorrente"):
                            alunno_id = a.get("id", alunno_id)
                            break
        except Exception:
            pass

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

                            compiti_list.append({
                                "materia": materia.upper().strip(),
                                "docente": item.get("docente", "").strip(),
                                "data": target_d.strftime("%d/%m"),
                                "date_val": target_d.isoformat(),
                                "descrizione": desc.strip(),
                                "is_test": is_test
                            })
            except Exception:
                pass

        # Estrai eventi di classe / verifiche formali
        url_eventi = f"https://nuvola.madisoft.it/api-studente/v1/alunno/{alunno_id}/eventi-classe?contextAlunno={alunno_id}&limit=15"
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
                                compiti_list.append({
                                    "materia": (ev.get("nome") or "AVVISO").upper().strip(),
                                    "docente": ev.get("docente", "").strip(),
                                    "data": ev_d.strftime("%d/%m"),
                                    "date_val": ev_d.isoformat(),
                                    "descrizione": ev.get("descrizione", "").strip(),
                                    "is_test": True
                                })
        except Exception:
            pass

        # Ordina per data crescente (prima verifiche se stesso giorno)
        compiti_list.sort(key=lambda x: (x["date_val"], not x["is_test"]))

        if compiti_list:
            _CACHE_DATA = {
                "timestamp": now_ts,
                "compiti": compiti_list
            }
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(_CACHE_DATA, f, ensure_ascii=False, indent=2)
            return compiti_list
        else:
            return load_cached_compiti(allow_stale=True)

    except Exception as e:
        print("Errore fetch Nuvola agenda:", e)
        return load_cached_compiti(allow_stale=True)
