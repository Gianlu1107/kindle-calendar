import os
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright
import dashboard_k4
from server import get_weather

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "docs", "screenshots_k4")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SCENARIOS = [
    {
        "id": "scenario_1_morning_prep",
        "title": "Scenario 1: Preparazione Mattina (07:00 - 08:30)",
        "time": "07:45",
        "phase": "morning_prep",
        "file": "01_morning_prep_0745.png"
    },
    {
        "id": "scenario_2_school_progress",
        "title": "Scenario 2: Durante le Lezioni (08:30 - 13:00)",
        "time": "10:15",
        "phase": "school_progress",
        "file": "02_school_progress_1015.png"
    },
    {
        "id": "scenario_3_afternoon_homework",
        "title": "Scenario 3: Pomeriggio Compiti (13:00 - 20:30)",
        "time": "15:30",
        "phase": "afternoon_homework",
        "file": "03_afternoon_homework_1530.png"
    },
    {
        "id": "scenario_4_night_prep",
        "title": "Scenario 4: Sera e Notte Controllo Zaino (20:30 - 07:00)",
        "time": "21:15",
        "phase": "night_prep",
        "file": "04_night_prep_2115.png"
    }
]

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 800, "height": 600})

        for sc in SCENARIOS:
            params = {
                "time": [sc["time"]],
                "phase": [sc["phase"]]
            }
            html_content = dashboard_k4.build_k4_dashboard_html(params, weather_getter=get_weather)
            await page.set_content(html_content, wait_until="networkidle")
            
            out_path = os.path.join(OUTPUT_DIR, sc["file"])
            await page.screenshot(path=out_path)
            print(f"Salvato scenario: {out_path}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
