import asyncio
from datetime import date, timedelta
from pathlib import Path
import os
import sys

from icalendar import Calendar, Event
import pytz

# Lib Celcat
try:
    from celcat_scraper import CelcatConfig, CelcatScraperAsync
except Exception as e:
    print("ERREUR: celcat_scraper non dispo:", e)
    sys.exit(1)

CYU_URL = "https://services-web.cyu.fr/calendar"  # base CYU
OUTPUT = Path("docs/edt.ics")
TIMEZONE = pytz.timezone("Europe/Paris")

async def fetch_events(username: str, password: str):
    config = CelcatConfig(
        url=CYU_URL,
        username=username,
        password=password,
        include_holidays=True,
    )
    start = date.today()
    end = start + timedelta(days=365)
    async with CelcatScraperAsync(config) as scraper:
        events = await scraper.get_calendar_events(start, end)
    return events

def write_calendar(events):
    cal = Calendar()
    cal.add("prodid", "-//EDT CYU Auto//celcat-scraper//")
    cal.add("version", "2.0")

    if not events:
        # Met au moins un événement témoin pour prouver que l’ICS existe
        from datetime import datetime, timedelta, timezone
        dt = datetime.now(timezone.utc)
        ev = Event()
        ev.add("summary", "EDT vide (placeholder)")
        ev.add("dtstart", dt)
        ev.add("dtend", dt + timedelta(minutes=30))
        cal.add_component(ev)
    else:
        for ev in events:
            e = Event()
            title_parts = [ev.get("course") or "Cours"]
            if ev.get("category"):
                title_parts.append(f"[{ev['category']}]")
            e.add("summary", " ".join(title_parts))

            # horaires
            e.add("dtstart", TIMEZONE.localize(ev["start"]))
            e.add("dtend",   TIMEZONE.localize(ev["end"]))

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

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "wb") as f:
        f.write(cal.to_ical())
    print("OK: écrit", OUTPUT)

async def main():
    username = os.environ.get("CELCAT_USERNAME")
    password = os.environ.get("CELCAT_PASSWORD")
    if not username or not password:
        print("ERREUR: secrets CELCAT_USERNAME / CELCAT_PASSWORD manquants")
        sys.exit(1)

    try:
        events = await fetch_events(username, password)
        print(f"Événements récupérés: {len(events)}")
    except Exception as e:
        print("ATTENTION: échec de récupération Celcat → on écrit quand même un ICS placeholder.")
        print("Détails:", e)
        events = []

    write_calendar(events)

if __name__ == "__main__":
    asyncio.run(main())
