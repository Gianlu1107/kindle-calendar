import asyncio
import os
import subprocess
import time
from playwright.async_api import async_playwright

BASE_DIR = os.environ.get("KINDLE_BASE_DIR", os.path.dirname(os.path.abspath(__file__)))
RAW_IMG = os.path.join(BASE_DIR, "dashboard_kindle_raw.png")
ROT_TMP = os.path.join(BASE_DIR, "dashboard_kindle_tmp.png")
ROT_IMG = os.path.join(BASE_DIR, "dashboard_kindle.png")
PORT = os.environ.get("PORT", "5055")

async def render_for_timestamp(page, target_ts):
    t0 = time.time()
    url = f"http://127.0.0.1:{PORT}/?ts={target_ts}"
    await page.goto(url, wait_until="networkidle")
    await page.screenshot(path=RAW_IMG, full_page=False)
    # Ruota di 90 gradi per il Paperwhite in un file temporaneo, poi rename atomico
    subprocess.run(["convert", RAW_IMG, "-rotate", "90", ROT_TMP], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.exists(ROT_TMP):
        os.replace(ROT_TMP, ROT_IMG)
    dt_str = time.strftime('%H:%M:%S', time.localtime(target_ts))
    elapsed = time.time() - t0
    print(f"[{time.strftime('%H:%M:%S')}] 📸 Snapshot target {dt_str} completato in {elapsed:.2f}s e pronto su /api/image!")

async def main():
    print(f"=== KINDLE CALENDAR RENDERING ENGINE AD ALTA PRECISIONE (PORT {PORT}) ===")
    while True:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page(viewport={"width": 1024, "height": 758})
                
                # Rendering iniziale immediato
                cur_now = time.time()
                cur_sec = cur_now % 60.0
                if cur_sec >= 45.0:
                    init_target = ((int(cur_now) // 60) + 1) * 60
                else:
                    init_target = (int(cur_now) // 60) * 60
                await render_for_timestamp(page, init_target)

                while True:
                    # Calcoliamo lo sleep per svegliarci esattamente al secondo :55.0 del minuto corrente
                    now = time.time()
                    sec = now % 60.0
                    if sec < 55.0:
                        sleep_time = 55.0 - sec
                    else:
                        sleep_time = (60.0 - sec) + 55.0
                    
                    # Sleep preciso
                    await asyncio.sleep(sleep_time)
                    
                    # Target: il minuto :00 successivo che sta per iniziare tra 5 secondi
                    now_trigger = time.time()
                    target_ts = ((int(now_trigger) // 60) + 1) * 60
                    await render_for_timestamp(page, target_ts)
                    
                    # Pausa di 2 secondi per evitare doppi trigger sullo stesso secondo :55
                    await asyncio.sleep(2.0)

        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Errore nel render loop: {e}. Riavvio browser tra 2s...")
            await asyncio.sleep(2.0)

if __name__ == "__main__":
    asyncio.run(main())
