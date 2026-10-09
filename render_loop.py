import asyncio
import os
import subprocess
import time
from playwright.async_api import async_playwright

BASE_DIR = os.environ.get("KINDLE_BASE_DIR", os.path.dirname(os.path.abspath(__file__)))
RAW_IMG = os.path.join(BASE_DIR, "dashboard_kindle_raw.png")
ROT_TMP = os.path.join(BASE_DIR, "dashboard_kindle_tmp.png")
ROT_IMG = os.path.join(BASE_DIR, "dashboard_kindle.png")

K4_TMP = os.path.join(BASE_DIR, "dashboard_k4_tmp.png")
K4_IMG = os.path.join(BASE_DIR, "dashboard_k4.png")
PORT = os.environ.get("PORT", "5055")

async def render_for_timestamp(page_pw1, page_k4, target_ts):
    t0 = time.time()
    
    # 1. Render per Kindle Paperwhite 1 (1024x758 -> ruotato a 90° su 758x1024)
    url_pw1 = f"http://127.0.0.1:{PORT}/?ts={target_ts}"
    await page_pw1.goto(url_pw1, wait_until="networkidle")
    await page_pw1.screenshot(path=RAW_IMG, full_page=False)
    subprocess.run(["convert", RAW_IMG, "-rotate", "90", ROT_TMP], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.exists(ROT_TMP):
        os.replace(ROT_TMP, ROT_IMG)
        
    # 2. Render per Kindle 4 (800x600 nativo Landscape -> orientamento nativo K4)
    url_k4 = f"http://127.0.0.1:{PORT}/k4?ts={target_ts}"
    await page_k4.goto(url_k4, wait_until="networkidle")
    await page_k4.screenshot(path=K4_TMP, full_page=False)
    if os.path.exists(K4_TMP):
        os.replace(K4_TMP, K4_IMG)

    dt_str = time.strftime('%H:%M:%S', time.localtime(target_ts))
    elapsed = time.time() - t0
    print(f"[{time.strftime('%H:%M:%S')}] [DUAL-RENDER] Snapshot target {dt_str} completati in {elapsed:.2f}s (PW1 + K4)", flush=True)

async def main():
    print(f"=== KINDLE DUAL CALENDAR RENDERING ENGINE (PW1 + K4 on PORT {PORT}) ===", flush=True)
    while True:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page_pw1 = await browser.new_page(viewport={"width": 1024, "height": 758})
                page_k4 = await browser.new_page(viewport={"width": 800, "height": 600})
                
                # Rendering iniziale immediato
                cur_now = time.time()
                cur_sec = cur_now % 60.0
                if cur_sec >= 45.0:
                    init_target = ((int(cur_now) // 60) + 1) * 60
                else:
                    init_target = (int(cur_now) // 60) * 60
                await render_for_timestamp(page_pw1, page_k4, init_target)

                while True:
                    # Calcoliamo lo sleep per svegliarci esattamente al secondo :55.0 del minuto corrente
                    now = time.time()
                    sec = now % 60.0
                    if sec < 55.0:
                        sleep_time = 55.0 - sec
                    else:
                        sleep_time = (60.0 - sec) + 55.0
                    
                    await asyncio.sleep(sleep_time)
                    
                    now_trigger = time.time()
                    target_ts = ((int(now_trigger) // 60) + 1) * 60
                    await render_for_timestamp(page_pw1, page_k4, target_ts)
                    
                    await asyncio.sleep(2.0)

        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Errore nel dual render loop: {e}. Riavvio browser tra 2s...")
            await asyncio.sleep(2.0)

if __name__ == "__main__":
    asyncio.run(main())
