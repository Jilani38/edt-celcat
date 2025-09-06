import asyncio
from datetime import date, timedelta
from pathlib import Path
from icalendar import Calendar, Event
import pytz

from celcat_scraper import CelcatConfig, CelcatScraperAsync  # pip install celcat-scraper

CYU_URL = "https://services-web.cyu.fr/calendar"  # base Celcat CYU
OUTPUT = Path("docs/edt.ics")
TIMEZONE = pytz.timezone("Europe/Paris")

async def main():
    # Identifiants ENT récupérés via variables d'env (GitHub Actions)
    import os
    username = os.environ["CELCAT_USERNAME"]
    password = os.environ["CELCAT_PASSWORD"]

    # 1) Config Celcat (la lib gère la session et l’authent)
    config = CelcatConfig(
        url=CYU_URL,
        username=username,
        password=password,
        include_holidays=True,
    )

    # 2) Fenêtre de récupération (aujourd'hui → +365 jours)
    start = date.today()
    end = start + timedelta(days=365)

    # 3) Récupérer les événements
    async with CelcatScraperAsync(config) as scraper:
        previous = None
        events = await scraper.get_calendar_events(start, end, previous_events=previous)

    # 4) Construire l'ICS
    cal = Calendar()
    cal.add("prodid", "-//EDT CYU Auto//celcat-scraper//")
    cal.add("version", "2.0")

    for ev in events:
        e = Event()
        # Titre = cours [catégorie] (ajuste selon tes goûts)
        title_parts = [ev.get("course") or "Cours"]
        if ev.get("category"):
            title_parts.append(f"[{ev['category']}]")
        e.add("summary", " ".join(title_parts))

        # Horaires
        e.add("dtstart", TIMEZONE.localize(ev["start"]))
        e.add("dtend",   TIMEZONE.localize(ev["end"]))

        # Lieu / profs (si présents)
        rooms = ", ".join(ev.get("rooms") or [])
        sites = ", ".join(ev.get("sites") or [])
        profs = ", ".join(ev.get("professors") or [])
        location = ", ".join([p for p in [rooms, sites] if p])
        if location:
            e.add("location", location)

        desc_lines = []
        if ev.get("department"): desc_lines.append(f"Département: {ev['department']}")
        if profs: desc_lines.append(f"Prof(s): {profs}")
        if desc_lines:
            e.add("description", "\n".join(desc_lines))

        cal.add_component(e)

    # 5) Écrire dans docs/ (pour GitHub Pages)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "wb") as f:
        f.write(cal.to_ical())

if __name__ == "__main__":
    asyncio.run(main())
