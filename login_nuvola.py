#!/usr/bin/env python3
"""
Script per il rinnovo automatico della sessione di Nuvola Registro Elettronico.
Apre una finestra di Google Chrome per permettere all'utente di autenticarsi con CIE o SPID.
Una volta completato l'accesso, cattura i cookie, aggiorna i compiti e sincronizza automaticamente il server Kindle (CT 141).
"""

import asyncio
import json
import os
import subprocess
import time
from playwright.async_api import async_playwright
import nuvola_client

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_FILE = os.path.join(BASE_DIR, "data", "nuvola_session.json")
CACHE_FILE = "/tmp/nuvola_cache.json"

async def main():
    print("=" * 65)
    print("   RINNOVO SESSIONE REGISTRO ELETTRONICO NUVOLA PER KINDLE")
    print("=" * 65)
    print("Si sta aprendo una finestra di Google Chrome con la pagina di Nuvola.")
    print("Effettua l'accesso tramite CIE, SPID o credenziali.")
    print("Non appena entrerai nel registro, la sessione verrà catturata")
    print("e i compiti aggiornati verranno sincronizzati direttamente sul Kindle!")
    print("=" * 65)

    async with async_playwright() as p:
        chrome_mac = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        launch_kwargs = {"headless": False}
        if os.path.exists(chrome_mac):
            launch_kwargs["executable_path"] = chrome_mac
        try:
            browser = await p.chromium.launch(**launch_kwargs)
        except Exception:
            browser = await p.chromium.launch(headless=False)

        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://nuvola.madisoft.it/login")

        logged_in = False
        start_t = time.time()
        while time.time() - start_t < 300:  # Timeout 5 minuti
            cur_url = page.url
            if ("nuvola.madisoft.it" in cur_url and
                "login" not in cur_url.lower() and
                "auth.nuvola" not in cur_url.lower() and
                "check" not in cur_url.lower()):

                await asyncio.sleep(2)
                cookies = await context.cookies()
                nuvola_cookie_names = [c["name"] for c in cookies if "nuvola" in c.get("domain", "")]
                if any("nuvola" in name.lower() or "session" in name.lower() for name in nuvola_cookie_names):
                    logged_in = True
                    print("\n[SUCCESS] Accesso a Nuvola rilevato con successo!")
                    print(f"URL: {cur_url}")

                    os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
                    with open(SESSION_FILE, "w", encoding="utf-8") as f:
                        json.dump({
                            "url": cur_url,
                            "cookies": cookies,
                            "timestamp": time.time()
                        }, f, indent=2)
                    print(f"[OK] Sessione salvata in: {SESSION_FILE}")

                    # Effettua subito il fetch e rigenera la cache locale
                    print("\n[INFO] Aggiornamento compiti e verifiche via API Nuvola...")
                    compiti = nuvola_client.fetch_nuvola_agenda(force_refresh=True)
                    print(f"[OK] Scaricati {len(compiti)} compiti ed eventi futuri.")

                    # Deploy facoltativo su server remoto Proxmox LXC se configurato
                    remote_host = os.environ.get("PROXMOX_HOST", os.environ.get("KINDLE_SERVER_HOST", ""))
                    ct_id = os.environ.get("PROXMOX_CT_ID", os.environ.get("LXC_CONTAINER_ID", ""))
                    if remote_host and ct_id:
                        print(f"\n[INFO] Sincronizzazione con il server del Kindle ({remote_host}, CT {ct_id})...")
                        try:
                            subprocess.run(
                                ["scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
                                 SESSION_FILE, f"{remote_host}:/tmp/nuvola_session.json"],
                                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                            )
                            if os.path.exists(CACHE_FILE):
                                subprocess.run(
                                    ["scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
                                     CACHE_FILE, f"{remote_host}:/tmp/nuvola_cache.json"],
                                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                                )

                            push_cmd = (
                                f"pct push {ct_id} /tmp/nuvola_session.json /opt/kindleCalendar/data/nuvola_session.json && "
                                f"pct push {ct_id} /tmp/nuvola_cache.json /tmp/nuvola_cache.json && "
                                f"pct exec {ct_id} -- chown root:root /opt/kindleCalendar/data/nuvola_session.json && "
                                f"pct exec {ct_id} -- systemctl restart kindle-server"
                            )
                            subprocess.run(
                                ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
                                 remote_host, push_cmd],
                                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                            )
                            print("[SUCCESS] Server e cache sincronizzati con successo!")
                        except Exception as e:
                            print(f"[AVVISO] Sincronizzazione automatica su server remoto non riuscita: {e}")
                    else:
                        print("\n[INFO] Sessione salvata in locale. (Opzionale: configura PROXMOX_HOST e PROXMOX_CT_ID per sync remoto)")

                    break

            await asyncio.sleep(1)

        if not logged_in:
            print("\n[TIMEOUT] Nessun accesso completato entro 5 minuti.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
