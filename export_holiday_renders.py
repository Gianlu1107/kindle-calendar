import asyncio
import os
import shutil
from playwright.async_api import async_playwright
from server import build_dashboard_html

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARTIFACT_DIR = os.environ.get("ARTIFACT_DIR")

SCENARIOS = [
    {
        "name": "estate",
        "params": {"date": ["2026-07-16"], "time": ["16:45"], "holiday": ["summer"], "mock_events": ["1"]},
        "filename": "mockup_estate.png"
    },
    {
        "name": "natale",
        "params": {"date": ["2026-12-27"], "time": ["11:30"], "holiday": ["winter"], "mock_events": ["1"]},
        "filename": "mockup_natale.png"
    },
    {
        "name": "carnevale",
        "params": {"date": ["2027-02-09"], "time": ["10:15"], "holiday": ["carnival"], "mock_events": ["1"]},
        "filename": "mockup_carnevale.png"
    },
    {
        "name": "pasqua",
        "params": {"date": ["2027-03-29"], "time": ["09:30"], "holiday": ["easter"], "mock_events": ["1"]},
        "filename": "mockup_pasqua.png"
    }
]

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1024, "height": 758})

        for sc in SCENARIOS:
            print(f"Elaborazione scenario {sc['name']}...", flush=True)
            html = build_dashboard_html(sc["params"])
            await page.set_content(html, wait_until="load")
            await page.wait_for_timeout(400)
            out_path = os.path.join(BASE_DIR, sc["filename"])
            await page.screenshot(path=out_path)
            print(f"Esportata immagine: {out_path}", flush=True)
            
            # Copia facoltativa negli artifacts se impostata la variabile
            if ARTIFACT_DIR and os.path.isdir(ARTIFACT_DIR):
                art_path = os.path.join(ARTIFACT_DIR, sc["filename"])
                shutil.copyfile(out_path, art_path)
                print(f"Copiata in artifact: {art_path}", flush=True)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
