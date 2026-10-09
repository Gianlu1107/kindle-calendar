import os
import json
from datetime import datetime, timedelta, time, date
import nuvola_client

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

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

def load_orario_k4():
    p = os.path.join(DATA_DIR, "orario_k4.json")
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"schedule": {}}

def build_k4_dashboard_html(query_params, weather_getter=None):
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
        if now.second >= 45:
            now = (now + timedelta(seconds=(60 - now.second))).replace(microsecond=0)

    if date_param:
        try:
            p_date = datetime.fromisoformat(date_param).date()
            now = now.replace(year=p_date.year, month=p_date.month, day=p_date.day)
        except Exception:
            pass

    if time_param and ":" in time_param:
        try:
            th, tm = map(int, time_param.split(":"))
            now = now.replace(hour=th, minute=tm, second=0, microsecond=0)
        except Exception:
            pass

    cur_time = now.time()
    t_0700 = time(7, 0)
    t_0830 = time(8, 30)
    t_1300 = time(13, 0)
    t_2030 = time(20, 30)

    # Identificazione fase oraria K4:
    # 1. 07:00 - 08:30: "morning_prep" (Materie di Oggi a sinistra, Meteo + Compiti a destra)
    # 2. 08:30 - 13:00: "school_progress" (Avanzamento lezioni a sinistra, Meteo + Compiti a destra)
    # 3. 13:00 - 20:30: "afternoon_homework" (Compiti domani in GRANDE a tutta altezza a sinistra, Materie domani a destra)
    # 4. 20:30 - 07:00: "night_prep" (Materie di domani a sinistra, Meteo + Compiti a destra)
    override_phase = query_params.get("phase", [""])[0]
    if override_phase in ["morning_prep", "school_progress", "afternoon_homework", "night_prep"]:
        phase = override_phase
    else:
        if t_0700 <= cur_time < t_0830:
            phase = "morning_prep"
        elif t_0830 <= cur_time < t_1300:
            phase = "school_progress"
        elif t_1300 <= cur_time < t_2030:
            phase = "afternoon_homework"
        else:
            phase = "night_prep"

    # Dati meteo e batteria
    meteo = {"temp": 18, "desc": "Sereno", "icon": ""}
    if weather_getter:
        try:
            m = weather_getter()
            if m: meteo = m
        except Exception:
            pass

    batt_str = "100%"
    try:
        if os.path.exists("/tmp/kindle_k4_battery.txt"):
            with open("/tmp/kindle_k4_battery.txt") as bf:
                b = bf.read().strip()
                if b: batt_str = f"{b}%"
    except Exception:
        pass

    orario_data = load_orario_k4()
    sched = orario_data.get("schedule", {})

    today_date = now.date()
    today_weekday = today_date.weekday()
    today_key = GIORNI_MAP.get(today_weekday, "lunedi")
    today_name = GIORNI_NOMI_IT.get(today_weekday, "Oggi")

    tomorrow_date = today_date + timedelta(days=1)
    tomorrow_weekday = tomorrow_date.weekday()
    tomorrow_key = GIORNI_MAP.get(tomorrow_weekday, "martedi")
    tomorrow_name = GIORNI_NOMI_IT.get(tomorrow_weekday, "Domani")

    today_lessons = sched.get(today_key, [])
    tomorrow_lessons = sched.get(tomorrow_key, [])

    # Compiti Nuvola
    nuvola_tasks = nuvola_client.fetch_nuvola_agenda()

    ora_str = now.strftime("%H:%M")
    data_str = f"{today_name.upper()} {now.day} {now.strftime('%B').upper()}"

    # Helper rendering lista lezioni
    def render_lessons_html(lessons, title, subtitle, highlight_current=False):
        items_html = ""
        now_hm = now.strftime("%H:%M")
        for l in lessons:
            is_active = highlight_current and (l["inizio"] <= now_hm <= l["fine"])
            bg = "#000" if is_active else "#fff"
            color = "#fff" if is_active else "#000"
            border = "2px solid #000"
            badge = f'<span style="background:{"#fff" if is_active else "#000"};color:{"#000" if is_active else "#fff"};font-size:10px;font-weight:900;padding:2px 6px;border-radius:4px;">IN CORSO</span>' if is_active else f'<span style="font-size:11px;font-weight:800;color:{"#ccc" if is_active else "#555"};">{l["inizio"]} - {l["fine"]}</span>'

            items_html += f'''
            <div style="border:{border};border-radius:6px;padding:9px 12px;background:{bg};color:{color};margin-bottom:7px;display:flex;justify-content:space-between;align-items:center;">
              <div>
                <div style="font-size:10.5px;font-weight:800;text-transform:uppercase;letter-spacing:0.4px;color:{"#eee" if is_active else "#555"};">{l["ora"]}ª ORA</div>
                <div style="font-size:15px;font-weight:900;margin-top:1px;">{l["materia"]}</div>
              </div>
              {badge}
            </div>
            '''
        return f'''
        <div style="display:flex;flex-direction:column;height:100%;">
          <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:2.5px solid #000;padding-bottom:5px;margin-bottom:10px;">
            <div style="font-size:13px;font-weight:900;text-transform:uppercase;letter-spacing:0.5px;">{title}</div>
            <span style="font-size:10px;font-weight:900;background:#000;color:#fff;padding:2px 6px;border-radius:3px;">{subtitle}</span>
          </div>
          <div style="display:flex;flex-direction:column;justify-content:space-between;flex:1;">
            {items_html or '<div style="text-align:center;padding:20px;font-size:13px;font-weight:800;">Nessuna lezione in programma</div>'}
          </div>
        </div>
        '''

    # Helper rendering compiti grandi per domani
    def render_large_tasks_html(tasks):
        # Filtra compiti per domani e giorni a seguire
        filtered = [t for t in tasks if t.get("data") in ["Domani"] or (t.get("date_val", "") > today_date.isoformat())]
        if not filtered:
            filtered = [t for t in tasks if t.get("date_val", "") >= today_date.isoformat()]

        items_html = ""
        for t in filtered[:4]:
            is_test = t.get("is_test", False)
            bg = "#000" if is_test else "#fff"
            color = "#fff" if is_test else "#000"
            badge_bg = "#fff" if is_test else "#000"
            badge_col = "#000" if is_test else "#fff"
            items_html += f'''
            <div style="border:2px solid #000;border-radius:6px;padding:10px 12px;background:{bg};color:{color};margin-bottom:8px;">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px;">
                <span style="font-size:13px;font-weight:900;">{t["materia"]}</span>
                <span style="background:{badge_bg};color:{badge_col};font-size:10px;font-weight:900;padding:2px 6px;border-radius:4px;">{t["data"]}</span>
              </div>
              <div style="font-size:12px;font-weight:600;line-height:1.25;margin-top:2px;">{t["descrizione"]}</div>
            </div>
            '''
        return f'''
        <div style="display:flex;flex-direction:column;height:100%;">
          <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:2.5px solid #000;padding-bottom:5px;margin-bottom:10px;">
            <div style="font-size:13px;font-weight:900;text-transform:uppercase;letter-spacing:0.5px;">COMPITI PER CASA &amp; VERIFICHE</div>
            <span style="font-size:10px;font-weight:900;background:#000;color:#fff;padding:2px 6px;border-radius:3px;">DOMANI</span>
          </div>
          <div style="display:flex;flex-direction:column;justify-content:space-between;flex:1;">
            {items_html or '<div style="border:1.5px dashed #000;border-radius:6px;padding:20px;text-align:center;font-size:12px;font-weight:800;">Nessun compito registrato per domani</div>'}
          </div>
        </div>
        '''

    # Helper rendering compiti compatti per colonna destra
    def render_compact_tasks_html(tasks):
        filtered = [t for t in tasks if t.get("date_val", "") >= today_date.isoformat()]
        items_html = ""
        for t in filtered[:2]:
            is_test = t.get("is_test", False)
            bg = "#000" if is_test else "#fff"
            color = "#fff" if is_test else "#000"
            badge_bg = "#fff" if is_test else "#000"
            badge_col = "#000" if is_test else "#fff"
            items_html += f'''
            <div style="border:1.5px solid #000;border-radius:5px;padding:6px 8px;background:{bg};color:{color};margin-bottom:5px;">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="font-size:11px;font-weight:900;">{t["materia"]}</span>
                <span style="background:{badge_bg};color:{badge_col};font-size:9.5px;font-weight:900;padding:1px 5px;border-radius:3px;">{t["data"]}</span>
              </div>
              <div style="font-size:10.5px;font-weight:600;margin-top:2px;line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{t["descrizione"]}</div>
            </div>
            '''
        return f'''
        <div style="border-top:2px solid #000;padding-top:6px;margin-top:auto;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;">
            <div style="font-size:11px;font-weight:900;text-transform:uppercase;letter-spacing:0.4px;">COMPITI PROSSIMI GIORNI</div>
            <span style="font-size:9px;font-weight:800;color:#555;">NUVOLA</span>
          </div>
          {items_html or '<div style="font-size:10px;font-weight:700;color:#555;text-align:center;padding:5px;">Nessun compito registrato</div>'}
        </div>
        '''

    # Layout delle due colonne in base alla fase oraria richiesta
    if phase == "morning_prep":
        # 07:00 - 08:30: Materie di oggi (SX), Meteo + Compiti compatti (DX)
        col_left = render_lessons_html(today_lessons, f"MATERIE DI OGGI • {today_name.upper()}", "ORARIO LEZIONI")
        col_right = f'''
        <div style="display:flex;flex-direction:column;height:100%;justify-content:space-between;">
          <div style="border:2px solid #000;border-radius:6px;padding:10px;text-align:center;">
            <div style="font-size:11px;font-weight:900;text-transform:uppercase;">METEO OGGI</div>
            <div style="font-size:28px;font-weight:900;margin:4px 0;">{meteo.get("temp", 18)}°C</div>
            <div style="font-size:12px;font-weight:800;color:#333;">{meteo.get("desc", "Sereno")}</div>
          </div>
          {render_compact_tasks_html(nuvola_tasks)}
        </div>
        '''
    elif phase == "school_progress":
        # 08:30 - 13:00: Avanzamento progressivo lezioni (SX), Meteo + Compiti (DX)
        col_left = render_lessons_html(today_lessons, f"LEZIONI IN CORSO • {today_name.upper()}", "IN DIRETTA", highlight_current=True)
        col_right = f'''
        <div style="display:flex;flex-direction:column;height:100%;justify-content:space-between;">
          <div style="border:2px solid #000;border-radius:6px;padding:10px;text-align:center;">
            <div style="font-size:11px;font-weight:900;text-transform:uppercase;">METEO &amp; PREVISIONI</div>
            <div style="font-size:28px;font-weight:900;margin:4px 0;">{meteo.get("temp", 18)}°C</div>
            <div style="font-size:12px;font-weight:800;color:#333;">{meteo.get("desc", "Sereno")}</div>
          </div>
          {render_compact_tasks_html(nuvola_tasks)}
        </div>
        '''
    elif phase == "afternoon_homework":
        # 13:00 - 20:30: Compiti domani in GRANDE a tutta altezza (SX), Materie domani (DX)
        col_left = render_large_tasks_html(nuvola_tasks)
        col_right = render_lessons_html(tomorrow_lessons, f"LEZIONI DI DOMANI • {tomorrow_name.upper()}", "ORARIO", highlight_current=False)
    else:
        # 20:30 - 07:00: Materie di domani (SX), Meteo + Compiti compatti (DX)
        col_left = render_lessons_html(tomorrow_lessons, f"MATERIE PER DOMANI • {tomorrow_name.upper()}", "SERA/NOTTE")
        col_right = f'''
        <div style="display:flex;flex-direction:column;height:100%;justify-content:space-between;">
          <div style="border:2px solid #000;border-radius:6px;padding:10px;text-align:center;">
            <div style="font-size:11px;font-weight:900;text-transform:uppercase;">METEO PREVISIONI</div>
            <div style="font-size:28px;font-weight:900;margin:4px 0;">{meteo.get("temp", 18)}°C</div>
            <div style="font-size:12px;font-weight:800;color:#333;">{meteo.get("desc", "Sereno")}</div>
          </div>
          {render_compact_tasks_html(nuvola_tasks)}
        </div>
        '''

    # Pixel Shifting K4 impercettibile (±1px su 800x600)
    minute_idx = now.minute
    pad_top = 12 + (minute_idx % 3)
    pad_bottom = 14 - (minute_idx % 3)
    pad_left = 14 + ((minute_idx // 3) % 3)
    pad_right = 16 - ((minute_idx // 3) % 3)

    html = f'''<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=800, height=600, initial-scale=1.0">
  <title>Dashboard K4</title>
  <meta http-equiv="refresh" content="120">
  <style>
    * {{ box-sizing: border-box; -webkit-font-smoothing: antialiased; margin:0; padding:0; }}
    body {{
      width: 800px;
      height: 600px;
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

  <!-- HEADER -->
  <header style="display:flex;justify-content:space-between;align-items:flex-end;border-bottom:3.5px solid #000;padding-bottom:6px;">
    <div>
      <h1 style="font-size:23px;font-weight:900;text-transform:uppercase;letter-spacing:-0.5px;">{data_str}</h1>
      <div style="font-size:11px;font-weight:800;color:#444;margin-top:2px;">
        SCUOLA SECONDARIA • CLASSE 3A • NUVOLA REGISTRO
      </div>
    </div>
    <div style="display:flex;align-items:center;gap:10px;text-align:right;">
      <div>
        <div style="font-size:38px;font-weight:900;line-height:0.9;letter-spacing:-1px;">{ora_str}</div>
        <div style="font-size:10.5px;font-weight:900;text-transform:uppercase;color:#555;margin-top:2px;">
          {meteo.get("desc","Sereno")} • {meteo.get("temp",18)}°C
        </div>
      </div>
      <div style="border:2px solid #000;border-radius:4px;padding:3px 6px;font-size:11px;font-weight:900;">
        {batt_str}
      </div>
    </div>
  </header>

  <!-- MAIN 2 COLONNE -->
  <main style="display:flex;gap:16px;flex:1;margin:10px 0;overflow:hidden;">
    <section style="flex:1.2;height:100%;display:flex;flex-direction:column;">
      {col_left}
    </section>
    <section style="flex:1;height:100%;border-left:2px solid #000;padding-left:14px;display:flex;flex-direction:column;">
      {col_right}
    </section>
  </main>

  <!-- FOOTER -->
  <footer style="display:flex;justify-content:space-between;align-items:center;border-top:2px solid #000;padding-top:4px;font-size:10px;font-weight:800;color:#555;text-transform:uppercase;">
    <div>KINDLE K4 SMART KIOSK • PROFILO 2</div>
    <div>SYNC: {ora_str}</div>
  </footer>

</body>
</html>
'''
    return html
