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

MESI_NOMI_IT = {
    1: "GENNAIO",
    2: "FEBBRAIO",
    3: "MARZO",
    4: "APRILE",
    5: "MAGGIO",
    6: "GIUGNO",
    7: "LUGLIO",
    8: "AGOSTO",
    9: "SETTEMBRE",
    10: "OTTOBRE",
    11: "NOVEMBRE",
    12: "DICEMBRE"
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
    # 3. 13:00 - 20:30: "afternoon_homework" (Compiti domani a sinistra, Materie domani a destra, Meteo orizzontale sotto)
    # 4. 20:30 - 07:00: "night_prep" (Materie di domani per zaino a sinistra, Meteo + Compiti a destra)
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
    meteo = {"temp": 18, "desc": "Sereno", "icon": "", "forecast": []}
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
    mese_str = MESI_NOMI_IT.get(now.month, now.strftime('%B').upper())
    data_str = f"{today_name.upper()} {now.day} {mese_str} {now.year}"

    # Helper rendering lista lezioni
    def render_lessons_html(lessons, title, subtitle, highlight_current=False):
        items_html = ""
        now_hm = now.strftime("%H:%M")
        for l in lessons:
            is_active = highlight_current and (l["inizio"] <= now_hm <= l["fine"])
            bg = "#000" if is_active else "#fff"
            color = "#fff" if is_active else "#000"
            border = "2px solid #000" if is_active else "1.5px solid #000"
            badge = f'<span style="background:{"#fff" if is_active else "#000"};color:{"#000" if is_active else "#fff"};font-size:10px;font-weight:900;padding:2px 7px;border-radius:3px;">IN CORSO</span>' if is_active else f'<span style="font-size:11px;font-weight:800;color:{"#ccc" if is_active else "#555"};">{l["inizio"]} - {l["fine"]}</span>'

            items_html += f'''
            <div style="border:{border};border-radius:5px;padding:9px 12px;background:{bg};color:{color};display:flex;justify-content:space-between;align-items:center;">
              <div>
                <div style="font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.4px;color:{"#eee" if is_active else "#555"};">{l["ora"]}ª ORA</div>
                <div style="font-size:15px;font-weight:900;margin-top:2px;line-height:1.1;">{l["materia"]}</div>
              </div>
              {badge}
            </div>
            '''
        return f'''
        <div style="display:flex;flex-direction:column;height:100%;">
          <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:2.5px solid #000;padding-bottom:4px;margin-bottom:7px;">
            <div style="font-size:12.5px;font-weight:900;text-transform:uppercase;letter-spacing:0.4px;">{title}</div>
            <span style="font-size:9.5px;font-weight:900;background:#000;color:#fff;padding:2px 6px;border-radius:3px;">{subtitle}</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:6px;">
            {items_html or '<div style="border:1.5px dashed #000;border-radius:5px;padding:20px;text-align:center;font-size:12px;font-weight:800;">Nessuna lezione in programma</div>'}
          </div>
        </div>
        '''

    # Helper rendering compiti compatti
    def render_tasks_box_html(tasks, title, subtitle, max_items=4, show_full_desc=False):
        filtered = [t for t in tasks if t.get("data") in ["Domani"] or (t.get("date_val", "") >= today_date.isoformat())]
        if not filtered:
            filtered = [t for t in tasks if t.get("date_val", "") >= today_date.isoformat()]

        items_html = ""
        for t in filtered[:max_items]:
            is_test = t.get("is_test", False)
            border_style = "border:1.5px solid #000;border-left:5px solid #000;" if is_test else "border:1.5px solid #000;"
            badge_html = f'<span style="background:#000;color:#fff;font-size:9px;font-weight:900;padding:1px 5px;border-radius:3px;margin-right:4px;">VERIFICA</span>' if is_test else ''
            date_badge = f'<span style="border:1px solid #000;background:{"#000" if not is_test else "#fff"};color:{"#fff" if not is_test else "#000"};font-size:9.5px;font-weight:900;padding:1px 5px;border-radius:3px;">{t["data"]}</span>'
            clamp_css = "" if show_full_desc else "display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;"

            items_html += f'''
            <div style="{border_style}border-radius:5px;padding:7px 10px;background:#fff;color:#000;">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="font-size:12.5px;font-weight:900;">{t["materia"]}</span>
                <div style="display:flex;align-items:center;">
                  {badge_html}
                  {date_badge}
                </div>
              </div>
              <div style="font-size:11px;font-weight:600;line-height:1.22;margin-top:2px;{clamp_css}">{t["descrizione"]}</div>
            </div>
            '''
        return f'''
        <div style="display:flex;flex-direction:column;">
          <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #000;padding-bottom:4px;margin-bottom:6px;">
            <div style="font-size:12px;font-weight:900;text-transform:uppercase;letter-spacing:0.4px;">{title}</div>
            <span style="font-size:9.5px;font-weight:900;background:#000;color:#fff;padding:2px 5px;border-radius:3px;">{subtitle}</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:5px;">
            {items_html or '<div style="border:1.5px dashed #000;border-radius:5px;padding:14px;text-align:center;font-size:11px;font-weight:800;">Nessun compito registrato</div>'}
          </div>
        </div>
        '''

    # Helper box meteo verticale stile PW1 (usato nella colonna destra in fasi 1, 2, 4)
    def render_vertical_weather_box_html(meteo_dict):
        forecast = meteo_dict.get("forecast", [])
        if not forecast:
            forecast = [
                {"giorno": "Oggi", "desc": meteo_dict.get("desc", "Sereno"), "max": meteo_dict.get("temp", 18), "min": 11, "icon": meteo_dict.get("icon", "")},
                {"giorno": "Domani", "desc": "Sereno", "max": 19, "min": 12, "icon": meteo_dict.get("icon", "")},
                {"giorno": "+2 gg", "desc": "Poco nuvoloso", "max": 20, "min": 10, "icon": meteo_dict.get("icon", "")},
                {"giorno": "+3 gg", "desc": "Coperto", "max": 18, "min": 11, "icon": meteo_dict.get("icon", "")},
            ]

        rows_html = ""
        for f in forecast[:4]:
            giorno = f.get("giorno", "")
            desc = f.get("desc", "")
            t_max = f.get("max", "--")
            t_min = f.get("min", "--")
            icon_svg = f.get("icon", "").replace('width="24" height="24"', 'width="18" height="18"')

            rows_html += f'''
            <div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid #ddd;">
              <span style="font-size:11.5px;font-weight:900;width:55px;">{giorno}</span>
              <div style="display:flex;align-items:center;gap:6px;flex:1;">
                <div style="display:flex;align-items:center;width:18px;height:18px;">{icon_svg}</div>
                <span style="font-size:10.5px;font-weight:700;color:#333;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:130px;">{desc}</span>
              </div>
              <span style="font-size:11.5px;font-weight:900;text-align:right;">{t_max}° <span style="font-size:10px;font-weight:700;color:#666;">{t_min}°</span></span>
            </div>
            '''

        return f'''
        <div style="border:2px solid #000;border-radius:6px;padding:7px 10px;background:#fff;margin-bottom:8px;">
          <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1.5px solid #000;padding-bottom:3px;margin-bottom:4px;">
            <span style="font-size:11px;font-weight:900;text-transform:uppercase;letter-spacing:0.4px;">METEO &amp; PREVISIONI • {meteo_dict.get("temp", 18)}°C</span>
            <span style="font-size:9px;font-weight:800;color:#555;">PADOVA</span>
          </div>
          <div style="display:flex;flex-direction:column;">
            {rows_html}
          </div>
        </div>
        '''

    # Helper meteo orizzontale a tutta larghezza (usato in Scenario 3 per riempire lo spazio sotto)
    def render_horizontal_weather_bar_html(meteo_dict):
        forecast = meteo_dict.get("forecast", [])
        if not forecast:
            forecast = [
                {"giorno": "Oggi", "desc": meteo_dict.get("desc", "Sereno"), "max": meteo_dict.get("temp", 18), "min": 11, "icon": meteo_dict.get("icon", "")},
                {"giorno": "Domani", "desc": "Sereno", "max": 19, "min": 12, "icon": meteo_dict.get("icon", "")},
                {"giorno": "+2 gg", "desc": "Poco nuvoloso", "max": 20, "min": 10, "icon": meteo_dict.get("icon", "")},
                {"giorno": "+3 gg", "desc": "Coperto", "max": 18, "min": 11, "icon": meteo_dict.get("icon", "")},
            ]

        cards_html = ""
        for f in forecast[:4]:
            giorno = f.get("giorno", "")
            desc = f.get("desc", "")
            t_max = f.get("max", "--")
            t_min = f.get("min", "--")
            icon_svg = f.get("icon", "").replace('width="24" height="24"', 'width="22" height="22"')

            cards_html += f'''
            <div style="flex:1;border:1.5px solid #000;border-radius:5px;padding:5px 8px;display:flex;align-items:center;gap:7px;background:#fff;min-width:0;">
              <div style="display:flex;align-items:center;justify-content:center;width:24px;height:24px;flex-shrink:0;">
                {icon_svg}
              </div>
              <div style="flex:1;min-width:0;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                  <span style="font-size:11px;font-weight:900;text-transform:uppercase;">{giorno}</span>
                  <span style="font-size:11px;font-weight:900;">{t_max}° <span style="font-size:9.5px;font-weight:700;color:#555;">{t_min}°</span></span>
                </div>
                <div style="font-size:9.5px;font-weight:700;color:#444;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{desc}</div>
              </div>
            </div>
            '''

        return f'''
        <section style="border-top:2px solid #000;padding-top:6px;margin-top:8px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
            <span style="font-size:10px;font-weight:900;text-transform:uppercase;letter-spacing:0.5px;">PREVISIONI METEO PADOVA</span>
            <span style="font-size:9px;font-weight:800;color:#555;">OPEN-METEO 4 GIORNI</span>
          </div>
          <div style="display:flex;gap:7px;">
            {cards_html}
          </div>
        </section>
        '''

    bottom_weather_html = ""

    # Layout delle due colonne in base alla fase oraria
    if phase == "morning_prep":
        # 07:00 - 08:30: Materie di oggi (SX), Meteo in alto a DX + Compiti in basso a DX
        col_left = render_lessons_html(today_lessons, f"MATERIE DI OGGI • {today_name.upper()}", "ORARIO LEZIONI")
        col_right = f'''
        <div style="display:flex;flex-direction:column;height:100%;">
          {render_vertical_weather_box_html(meteo)}
          {render_tasks_box_html(nuvola_tasks, "COMPITI & VERIFICHE", "NUVOLA", max_items=3)}
        </div>
        '''
    elif phase == "school_progress":
        # 08:30 - 13:00: Avanzamento progressivo lezioni (SX), Meteo + Compiti a DX
        col_left = render_lessons_html(today_lessons, f"LEZIONI IN CORSO • {today_name.upper()}", "IN DIRETTA", highlight_current=True)
        col_right = f'''
        <div style="display:flex;flex-direction:column;height:100%;">
          {render_vertical_weather_box_html(meteo)}
          {render_tasks_box_html(nuvola_tasks, "COMPITI & PROMEMORIA", "PROSSIMI", max_items=3)}
        </div>
        '''
    elif phase == "afternoon_homework":
        # 13:00 - 20:30: Compiti domani a tutta colonna a sinistra (compatti!), Materie domani a destra, Meteo orizzontale sotto!
        col_left = render_tasks_box_html(nuvola_tasks, "COMPITI PER CASA &amp; VERIFICHE", "DOMANI", max_items=4, show_full_desc=False)
        col_right = render_lessons_html(tomorrow_lessons, f"LEZIONI DI DOMANI • {tomorrow_name.upper()}", "ZAINO", highlight_current=False)
        bottom_weather_html = render_horizontal_weather_bar_html(meteo)
    else:
        # 20:30 - 07:00: Materie per domani per controllo zaino (SX), Meteo + Compiti a DX
        col_left = render_lessons_html(tomorrow_lessons, f"MATERIE PER DOMANI • {tomorrow_name.upper()}", "SERA/NOTTE")
        col_right = f'''
        <div style="display:flex;flex-direction:column;height:100%;">
          {render_vertical_weather_box_html(meteo)}
          {render_tasks_box_html(nuvola_tasks, "COMPITI IN ARRIVO", "NUVOLA", max_items=3)}
        </div>
        '''

    # Pixel Shifting K4 impercettibile (±1px su 800x600)
    minute_idx = now.minute
    pad_top = 10 + (minute_idx % 3)
    pad_bottom = 12 - (minute_idx % 3)
    pad_left = 12 + ((minute_idx // 3) % 3)
    pad_right = 14 - ((minute_idx // 3) % 3)

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
  <header style="display:flex;justify-content:space-between;align-items:flex-end;border-bottom:3px solid #000;padding-bottom:5px;">
    <div>
      <h1 style="font-size:22px;font-weight:900;text-transform:uppercase;letter-spacing:-0.5px;line-height:1.1;">{data_str}</h1>
      <div style="font-size:10.5px;font-weight:800;color:#333;margin-top:2px;">
        SCUOLA SECONDARIA • CLASSE 3A • NUVOLA REGISTRO
      </div>
    </div>
    <div style="display:flex;align-items:center;gap:12px;text-align:right;">
      <div>
        <div style="font-size:36px;font-weight:900;line-height:0.9;letter-spacing:-1px;">{ora_str}</div>
        <div style="font-size:10px;font-weight:800;text-transform:uppercase;color:#555;margin-top:2px;">
          {meteo.get("desc","Sereno")} • {meteo.get("temp",18)}°C
        </div>
      </div>
      <div style="border:2px solid #000;border-radius:4px;padding:3px 6px;font-size:11px;font-weight:900;">
        {batt_str}
      </div>
    </div>
  </header>

  <!-- MAIN 2 COLONNE -->
  <main style="display:flex;gap:14px;flex:1;margin-top:8px;overflow:hidden;">
    <section style="flex:1.15;height:100%;overflow:hidden;">
      {col_left}
    </section>
    <section style="flex:1;height:100%;border-left:2px solid #000;padding-left:12px;overflow:hidden;">
      {col_right}
    </section>
  </main>

  <!-- METEO ORIZZONTALE SOTTO (SE PRESENTE) -->
  {bottom_weather_html}

  <!-- FOOTER -->
  <footer style="display:flex;justify-content:space-between;align-items:center;border-top:1.5px solid #000;padding-top:3px;margin-top:5px;font-size:9.5px;font-weight:800;color:#555;text-transform:uppercase;">
    <div>KINDLE K4 SMART KIOSK • NUVOLA 3A</div>
    <div>SYNC: {ora_str}</div>
  </footer>

</body>
</html>
'''
    return html
