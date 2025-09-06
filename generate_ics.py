import asyncio
from datetime import date, timedelta
from pathlib import Path
import os
import sys
from icalendar import Calendar, Event
import pytz

try:
    # pip install celcat-scraper
    from celcat_scraper import CelcatConfig, CelcatScraperAsync
except Exception as e:
    print("ERREUR: celcat_scraper introuvable:", e)
    sys.exit(1)

BASE_URL = "https://services-web.cyu.fr/calendar"   # Celcat CYU
ENTITY_TYPE = "student"                              # <- important
ENTITY_ID = "22304921"                               # <- ton fid0
OUTPUT = Path("docs/edt.ics")
TZ = pytz.timezone("Europe/Paris")

async def main():
    user = os.environ.get("CELCAT_USERNAME")
    pwd  = os.environ.get("CELCAT_PASSWORD")
    if not user or not pwd:
        print("ERREUR: secrets CELCAT_USERNAME / CELCAT_PASSWORD manquants")
        sys.exit(1)

    # Fenêtre: aujourd'hui → +365j
    start = date.today()
    end   = start + timedelta(days=365)

    print(f"Connexion à Celcat: {BASE_URL}")
    print(f"Entité: {ENTITY_TYPE} / {ENTITY_ID} | Période: {start} → {end}")

    try:
        cfg = CelcatConfig(url=BASE_URL, username=user, password=pwd, include_holidays=True)
        async with CelcatScraperAsync(cfg) as s:
            # 👉 certaines versions exposent get_calendar_events_for_entity ; d'autres filtrent via params
            # Essai 1: méthode dédiée à l'entité
            if hasattr(s, "get_calendar_events_for_entity"):
                events = await s.get_calendar_events_for_entity(
                    entity_type=ENTITY_TYPE,
                    entity_id=ENTITY_ID,
                    start=start,
                    end=end
                )
            else:
                # Essai 2: méthode générique + paramètres (selon la lib)
                events = await s.get_calendar_events(
                    start=start,
                    end=end,
                    entity_type=ENTITY_TYPE,
                    entity_id=ENTITY_ID
                )
    except Exception as e:
        print("ATTENTION: échec de récupération Celcat → on génère un ICS placeholder.")
        print("Détail:", repr(e))
        events = []

    print(f"Événements récupérés: {len(events)}")

    cal = Calendar()
    cal.add("prodid", "-//EDT CYU Auto//celcat-scraper//")
    cal.add("version", "2.0")

    if not events:
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        e = Event()
        e.add("summary", "EDT vide (placeholder)")
        e.add("dtstart", now)
        e.add("dtend",   now + timedelta(minutes=30))
        cal.add_component(e)
    else:
        for ev in events:
            title = ev.get("course") or "Cours"
            if ev.get("category"):
                title += f" [{ev['category']}]"
            e = Event()
            e.add("summary", title)
            e.add("dtstart", TZ.localize(ev["start"]))
            e.add("dtend",   TZ.localize(ev["end"]))
            rooms = ", ".join(ev.get("rooms") or [])
            sites = ", ".join(ev.get("sites") or [])
            profs = ", ".join(ev.get("professors") or [])
            loc = ", ".join([p for p in [rooms, sites] if p])
            if loc: e.add("location", loc)
            desc = []
            if ev.get("department"): desc.append(f"Département: {ev['department']}")
            if profs: desc.append(f"Prof(s): {profs}")
            if desc: e.add("description", "\n".join(desc))
            cal.add_component(e)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "wb") as f:
        f.write(cal.to_ical())
    print("Écrit:", OUTPUT)

if __name__ == "__main__":
    asyncio.run(main())
