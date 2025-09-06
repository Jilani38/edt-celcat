import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import os
import sys

from icalendar import Calendar, Event
import pytz

try:
    from celcat_scraper import CelcatConfig, CelcatScraperAsync
except Exception as e:
    print("ERREUR: celcat_scraper introuvable:", e)
    sys.exit(1)

OUTPUT = Path("docs/edt.ics")
TZ = pytz.timezone("Europe/Paris")

# ➜ TON ID (vu dans l’URL fid0=22304921)
ENTITY_ID = "22304921"

# ➜ On teste plusieurs types courants (selon la version Celcat/lib)
ENTITY_TYPES = ["student", "group", "class", "program"]

# ➜ On teste plusieurs bases (certaines instances veulent la racine sans /calendar)
CANDIDATE_BASE_URLS = [
    "https://services-web.cyu.fr",
    "https://services-web.cyu.fr/calendar",
]

def build_calendar(events):
    cal = Calendar()
    cal.add("prodid", "-//EDT CYU Auto//celcat-scraper//")
    cal.add("version", "2.0")

    if not events:
        now = datetime.now(timezone.utc)
        e = Event()
        e.add("summary", "EDT vide (placeholder)")
        e.add("dtstart", now)
        e.add("dtend", now + timedelta(minutes=30))
        cal.add_component(e)
    else:
        for ev in events:
            title = ev.get("course") or "Cours"
            if ev.get("category"):
                title += f" [{ev['category']}]"

            e = Event()

            # dates
            start_dt = ev["start"]
            end_dt = ev["end"]
            if start_dt.tzinfo is None:
                start_dt = TZ.localize(start_dt)
            if end_dt.tzinfo is None:
                end_dt = TZ.localize(end_dt)

            e.add("summary", title)
            e.add("dtstart", start_dt)
            e.add("dtend", end_dt)

            rooms = ", ".join(ev.get("rooms") or [])
            sites = ", ".join(ev.get("sites") or [])
            profs = ", ".join(ev.get("professors") or [])
            loc = ", ".join([p for p in (rooms, sites) if p])
            if loc:
                e.add("location", loc)

            desc = []
            if ev.get("department"):
                desc.append(f"Département: {ev['department']}")
            if profs:
                desc.append(f"Prof(s): {profs}")
            if desc:
                e.add("description", "\n".join(desc))

            cal.add_component(e)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "wb") as f:
        f.write(cal.to_ical())
    print("Écrit:", OUTPUT)

async def fetch_with(scraper, entity_type, start, end):
    # Stratégie 1 : méthode dédiée à l’entité (si dispo)
    if hasattr(scraper, "get_calendar_events_for_entity"):
        try:
            print(f"  -> get_calendar_events_for_entity(type={entity_type})")
            evs = await scraper.get_calendar_events_for_entity(
                entity_type=entity_type, entity_id=ENTITY_ID, start=start, end=end
            )
            return evs, f"for_entity:{entity_type}"
        except Exception as e:
            print("     (échec stratégie for_entity)", repr(e))

    # Stratégie 2 : méthode générique avec params
    try:
        print(f"  -> get_calendar_events(entity_type={entity_type})")
        evs = await scraper.get_calendar_events(
            start=start, end=end, entity_type=entity_type, entity_id=ENTITY_ID
        )
        return evs, f"generic:{entity_type}"
    except Exception as e:
        print("     (échec stratégie generic)", repr(e))

    return [], None

async def main():
    user = os.environ.get("CELCAT_USERNAME")
    pwd  = os.environ.get("CELCAT_PASSWORD")
    if not user or not pwd:
        print("ERREUR: secrets CELCAT_USERNAME / CELCAT_PASSWORD manquants")
        sys.exit(1)

    # Fenêtre glissante : -14j → +180j
    today = date.today()
    start = today - timedelta(days=14)
    end   = today + timedelta(days=180)
    print(f"Fenêtre demandée: {start} → {end}")
    print(f"ID: {ENTITY_ID}")

    best = []
    chosen = None

    for base in CANDIDATE_BASE_URLS:
        print(f"\n=== Tentative base_url: {base}")
        try:
            cfg = CelcatConfig(url=base, username=user, password=pwd, include_holidays=True)
            async with CelcatScraperAsync(cfg) as s:
                for etype in ENTITY_TYPES:
                    evs, info = await fetch_with(s, etype, start, end)
                    print(f"    {etype}: {len(evs)} évènement(s)")
                    if len(evs) > len(best):
                        best = evs
                        chosen = f"{info} @ {base}"
                if best:
                    break  # on a trouvé quelque chose, on s'arrête
        except Exception as e:
            print("  (échec connexion/essai sur cette base)", repr(e))

    if best:
        print(f"OK, retenu: {len(best)} évènement(s) via {chosen}")
    else:
        print("Aucun évènement trouvé (auth/ID/url ?) → ICS placeholder.")

    build_calendar(best)

if __name__ == "__main__":
    asyncio.run(main())
