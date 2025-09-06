import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import os, sys, traceback

from icalendar import Calendar, Event
import pytz

# ---------- LIB CELCAT ----------
try:
    from celcat_scraper import CelcatConfig, CelcatScraperAsync
except Exception as e:
    print("ERREUR: celcat_scraper introuvable:", e)
    sys.exit(1)
# --------------------------------

# ====== PARAMS ======
ENTITY_ID = "22304921"  # ton fid0 (vu dans l’URL Celcat)
ENTITY_TYPES = ["student", "group", "class", "program"]  # on teste plusieurs

# Certaines instances veulent la racine sans /calendar
CANDIDATE_BASE_URLS = [
    "https://services-web.cyu.fr",
    "https://services-web.cyu.fr/calendar",
]

OUTPUT = Path("docs/edt.ics")
TZ = pytz.timezone("Europe/Paris")

# Fenêtre glissante: -14 j → +180 j
today = date.today()
START = today - timedelta(days=14)
END   = today + timedelta(days=180)
# ====================


def write_ics(events):
    """Toujours écrire un ICS valide (placeholder si vide)."""
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

            start_dt = ev["start"]
            end_dt   = ev["end"]
            if start_dt.tzinfo is None:
                start_dt = TZ.localize(start_dt)
            if end_dt.tzinfo is None:
                end_dt = TZ.localize(end_dt)

            e = Event()
            e.add("summary", title)
            e.add("dtstart", start_dt)
            e.add("dtend",   end_dt)

            rooms = ", ".join(ev.get("rooms") or [])
            sites = ", ".join(ev.get("sites") or [])
            profs = ", ".join(ev.get("professors") or [])
            loc = ", ".join([p for p in (rooms, sites) if p])
            if loc:
                e.add("location", loc)

            desc = []
            if ev.get("department"): desc.append(f"Département: {ev['department']}")
            if profs: desc.append(f"Prof(s): {profs}")
            if desc:
                e.add("description", "\n".join(desc))

            cal.add_component(e)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "wb") as f:
        f.write(cal.to_ical())
    print("Écrit:", OUTPUT)


async def fetch_variant(base_url: str, etype: str, start: date, end: date, user: str, pwd: str):
    """Teste 2 stratégies selon la version de la lib; retourne (events, info)."""
    cfg = CelcatConfig(
        url=base_url,
        username=user,
        password=pwd,
        include_holidays=True,
    )
    async with CelcatScraperAsync(cfg) as s:
        # 1) méthode spécifique à l'entité si dispo
        if hasattr(s, "get_calendar_events_for_entity"):
            try:
                print(f"  -> try for_entity(type={etype}) @ {base_url}")
                evs = await s.get_calendar_events_for_entity(
                    entity_type=etype, entity_id=ENTITY_ID, start=start, end=end
                )
                return evs, f"for_entity:{etype} @ {base_url}"
            except Exception as e:
                print("     (échec for_entity)", repr(e))
                traceback.print_exc(limit=1)

        # 2) méthode générique avec params
        try:
            print(f"  -> try generic(entity_type={etype}) @ {base_url}")
            evs = await s.get_calendar_events(
                start=start, end=end, entity_type=etype, entity_id=ENTITY_ID
            )
            return evs, f"generic:{etype} @ {base_url}"
        except Exception as e:
            print("     (échec generic)", repr(e))
            traceback.print_exc(limit=1)

    return [], None


async def main():
    user = os.environ.get("CELCAT_USERNAME")
    pwd  = os.environ.get("CELCAT_PASSWORD")
    if not user or not pwd:
        print("ERREUR: secrets CELCAT_USERNAME / CELCAT_PASSWORD manquants")
        sys.exit(1)

    print(f"Fenêtre: {START} → {END}")
    print(f"ENTITY_ID: {ENTITY_ID}")

    best_events = []
    chosen_info = None

    for base in CANDIDATE_BASE_URLS:
        print(f"\n=== Base URL: {base}")
        try:
            for etype in ENTITY_TYPES:
                evs, info = await fetch_variant(base, etype, START, END, user, pwd)
                print(f"    {etype}: {len(evs)} évènement(s)")
                if len(evs) > len(best_events):
                    best_events = evs
                    chosen_info = info
            if best_events:
                break
        except Exception as e:
            print("  (échec global sur cette base)", repr(e))
            traceback.print_exc(limit=1)

    if best_events:
        print(f"\nOK ✅ {len(best_events)} évènement(s) via {chosen_info}")
    else:
        print("\nAucun évènement trouvé ❌ (auth/URL/type/ID). ICS placeholder généré.")

    write_ics(best_events)


if __name__ == "__main__":
    asyncio.run(main())
