#!/usr/bin/env python3
import os
import subprocess
import datetime
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APPLESCRIPT = os.path.join(BASE_DIR, "export_script.applescript")
ICS_OUTPUT = os.path.join(BASE_DIR, "calendar_feed.ics")

SERVER_HOST = os.environ.get("KINDLE_SERVER_HOST", "root@192.168.1.250")
SERVER_DEST = os.environ.get("KINDLE_SERVER_DEST", "/opt/kindleCalendar/calendar_feed.ics")
CONTAINER_ID = os.environ.get("LXC_CONTAINER_ID", "141")

def to_ical_dt(dt_str, is_allday):
    # Format: YYYY-MM-DDTHH:MM:SS
    clean = dt_str.replace("-", "").replace(":", "")
    if is_allday:
        return f"VALUE=DATE:{clean[:8]}"
    return clean

def generate_feed():
    print(f"[{datetime.datetime.now()}] Estrazione eventi da macOS Calendar...")
    p = subprocess.run(["osascript", APPLESCRIPT], capture_output=True, text=True)
    if p.returncode != 0:
        print("Errore osascript:", p.stderr)
        return False

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Kindle Calendar Syncer//IT//",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Mac Unified Feed",
        "X-WR-TIMEZONE:Europe/Rome"
    ]
    
    now_utc = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    count = 0

    seen_keys = set()
    for line in p.stdout.splitlines():
        line = line.strip()
        if not line or "|||" not in line:
            continue
        parts = line.split("|||")
        if len(parts) < 6:
            continue
        uid, sdate, edate, allday_str, cal_name, summary = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
        is_allday = (allday_str.lower() == "true")
        clean_summ = summary.replace("\n", " ").strip()

        # Deduplicazione basata su titolo e orario di inizio
        dedup_key = (clean_summ.lower(), sdate)
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        loc = parts[6].replace("\n", " ").strip() if len(parts) > 6 else ""
        desc = parts[7].replace("\n", " ").strip() if len(parts) > 7 else ""

        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{uid}")
        lines.append(f"DTSTAMP:{now_utc}")
        lines.append(f"DTSTART;{to_ical_dt(sdate, is_allday)}")
        lines.append(f"DTEND;{to_ical_dt(edate, is_allday)}")
        lines.append(f"SUMMARY:{clean_summ}")
        if loc:
            lines.append(f"LOCATION:{loc}")
        if desc:
            lines.append(f"DESCRIPTION:{desc}")
        lines.append(f"CATEGORIES:{cal_name}")
        lines.append("END:VEVENT")
        count += 1

    lines.append("END:VCALENDAR")

    with open(ICS_OUTPUT, "w", encoding="utf-8") as f:
        f.write("\r\n".join(lines) + "\r\n")

    print(f"[{datetime.datetime.now()}] Generato {ICS_OUTPUT} con {count} eventi unici.")
    return True

def push_to_server():
    tmp_dest = "/tmp/calendar_feed.ics"
    cmd_scp = ["scp", "-q", "-o", "ConnectTimeout=5", ICS_OUTPUT, f"{SERVER_HOST}:{tmp_dest}"]
    res = subprocess.run(cmd_scp)
    if res.returncode == 0:
        if CONTAINER_ID:
            cmd_push = ["ssh", "-o", "ConnectTimeout=5", SERVER_HOST, f"pct push {CONTAINER_ID} {tmp_dest} {SERVER_DEST}"]
            subprocess.run(cmd_push)
        print("Sincronizzazione completata con successo sul server.")
    else:
        print("Errore durante il caricamento SCP.")

if __name__ == "__main__":
    if generate_feed():
        push_to_server()
