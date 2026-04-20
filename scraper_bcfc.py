#!/usr/bin/env python3
"""
Bristol City FC Home Fixtures Scraper
======================================
Fetches Bristol City home matches at Ashton Gate and returns CalendarEvent objects.

DATA SOURCE DECISION:
  PRIMARY:  BBC Sport - bbc.co.uk/sport/football/teams/bristol-city/fixtures
            Chosen because: public HTML, no login, no API key, stable for 10+ years,
            covers Championship, FA Cup, Carabao Cup and play-offs, real-time kick-off
            time updates.
  FALLBACK: Soccerway - uk.soccerway.com/teams/england/bristol-city-fc/660/matches/
            Independent aggregator, different code path = true redundancy.
  BASELINE: Hardcoded known home fixtures (researched April 2026).
            Guarantees calendar is never empty even if both scrapers fail.

Only HOME fixtures at Ashton Gate are included.
Already-played matches are skipped automatically.
"""

import json
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

BASE_DIR = Path(__file__).resolve().parent
with open(BASE_DIR / "config.json") as f:
    CONFIG = json.load(f)

logger = logging.getLogger("bristol_calendar")
TZ = ZoneInfo(CONFIG["timezone"])
HTTP = CONFIG["http"]

# URLs
BBC_URL = "https://www.bbc.co.uk/sport/football/teams/bristol-city/fixtures"
SOCCERWAY_URL = "https://uk.soccerway.com/teams/england/bristol-city-fc/660/matches/"
BCFC_VENUE = "Ashton Gate Stadium, Ashton Road, Bristol, BS3 2EJ"
BCFC_TICKETS = "https://www.bcfc.co.uk/tickets/"
BCFC_FIXTURES = "https://www.bcfc.co.uk/fixtures/"

# Known home fixtures as a reliable hardcoded baseline.
# Format: (date_str, time_str, opponent, competition)
# Season ends 2 May 2026 (Stoke City, final home match of 2025-26).
# Future seasons: update this list each summer when fixtures are released.
KNOWN_HOME_FIXTURES = [
    # ── 2025-26 remaining home matches (from Apr 2026) ──────────────────
    ("25 Apr 2026", "15:00", "Stoke City",         "EFL Championship"),
    # Playoff fixtures (dates TBC – added as placeholders if City qualify)
    # ("TBC",         "15:00", "TBC",                "EFL Championship Play-Off"),
]

# Full 2025-26 home fixture list for reference / manual top-up
# Already played (before today) are automatically skipped by the filter.
FULL_SEASON_HOME_FIXTURES = [
    ("16 Aug 2025", "15:00", "Charlton Athletic",   "EFL Championship"),
    ("30 Aug 2025", "15:00", "Hull City",            "EFL Championship"),
    ("13 Sep 2025", "15:00", "Burnley",              "EFL Championship"),
    ("27 Sep 2025", "15:00", "Cardiff City",         "EFL Championship"),
    ("04 Oct 2025", "15:00", "Coventry City",        "EFL Championship"),
    ("18 Oct 2025", "15:00", "Sheffield United",     "EFL Championship"),
    ("01 Nov 2025", "15:00", "Stoke City",           "EFL Championship"),
    ("10 Dec 2025", "19:45", "Leicester City",       "EFL Championship"),
    ("20 Dec 2025", "15:00", "Middlesbrough",        "EFL Championship"),
    ("01 Jan 2026", "15:00", "Portsmouth",           "EFL Championship"),
    ("04 Jan 2026", "15:00", "Preston North End",    "EFL Championship"),
    ("10 Jan 2026", "15:00", "Watford",              "FA Cup"),
    ("24 Jan 2026", "15:00", "Sheffield Wednesday",  "EFL Championship"),
    ("30 Jan 2026", "19:45", "Derby County",         "EFL Championship"),
    ("13 Feb 2026", "19:45", "Wrexham",              "EFL Championship"),
    ("21 Feb 2026", "15:00", "Swansea City",         "EFL Championship"),
    ("07 Mar 2026", "15:00", "Luton Town",           "EFL Championship"),
    ("14 Mar 2026", "15:00", "West Bromwich Albion", "EFL Championship"),
    ("04 Apr 2026", "15:00", "QPR",                  "EFL Championship"),
    ("11 Apr 2026", "15:00", "Blackburn Rovers",     "EFL Championship"),
    ("18 Apr 2026", "15:00", "Oxford United",        "EFL Championship"),
    ("25 Apr 2026", "15:00", "Stoke City",           "EFL Championship"),
]


# ── HTTP helper ──────────────────────────────────────────────────────────────

_session = requests.Session()
_session.headers.update({
    "User-Agent": HTTP["user_agent"],
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
})


def _fetch(url: str) -> Optional[BeautifulSoup]:
    for attempt in range(1, HTTP["retry_attempts"] + 1):
        try:
            logger.info(f"BCFC fetch [{attempt}/{HTTP['retry_attempts']}]: {url}")
            r = _session.get(url, timeout=HTTP["timeout_seconds"])
            r.raise_for_status()
            return BeautifulSoup(r.text, "lxml")
        except requests.RequestException as e:
            logger.warning(f"BCFC fetch failed (attempt {attempt}): {e}")
            if attempt < HTTP["retry_attempts"]:
                time.sleep(HTTP["retry_delay_seconds"])
    logger.error(f"BCFC: all attempts failed for {url}")
    return None


# ── Datetime helpers ─────────────────────────────────────────────────────────

def _parse_dt(date_str: str, time_str: str = "15:00") -> Optional[datetime]:
    """Parse UK date + time into a timezone-aware datetime."""
    date_str_clean = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_str.strip())
    combined = f"{date_str_clean} {time_str}".strip()
    # Check whether an explicit 4-digit year is present in the original string
    has_explicit_year = bool(re.search(r"\b20\d{2}\b", date_str))
    try:
        dt = dateutil_parser.parse(combined, dayfirst=True, fuzzy=True)
        now = datetime.now(tz=TZ)
        # Only bump year when no explicit year given AND result is in the past
        if not has_explicit_year and dt.year < now.year:
            dt = dt.replace(year=now.year)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt
    except Exception as e:
        logger.debug(f"BCFC date parse failed '{combined}': {e}")
        return None


def _is_future(dt: datetime) -> bool:
    """Return True if the match hasn't kicked off yet."""
    return dt > datetime.now(tz=TZ)


def _make_uid(opponent: str, start: datetime) -> str:
    slug = re.sub(r"[^a-z0-9]", "-", opponent.lower())[:30]
    return f"bcfc-home-{slug}-{start.strftime('%Y%m%dT%H%M%S')}@bristol-bears-calendar"


def _make_event(opponent: str, competition: str, start: datetime):
    """Build a CalendarEvent for a Bristol City home match."""
    from scraper import CalendarEvent
    end = start + timedelta(minutes=115)  # 90min + warm-up + half-time
    title = f"Bristol City vs {opponent}"
    description = (
        f"⚽ {competition}\n\n"
        f"Bristol City vs {opponent}\n"
        f"Kick-off: {start.strftime('%A %d %B %Y, %H:%M')} 🏠\n\n"
        f"Venue: Ashton Gate Stadium, Bristol\n"
        f"Tickets: {BCFC_TICKETS}\n"
        f"Fixtures: {BCFC_FIXTURES}"
    )
    return CalendarEvent(
        uid=_make_uid(opponent, start),
        title=title,
        start=start,
        end=end,
        location=BCFC_VENUE,
        description=description,
        categories=["Football", "Bristol City", competition],
        url=BCFC_FIXTURES,
    )


def _extract_competition(text: str) -> str:
    t = text.lower()
    if "fa cup" in t:
        return "FA Cup"
    if "carabao" in t or "league cup" in t or "efl cup" in t:
        return "Carabao Cup (EFL Cup)"
    if "play-off" in t or "playoff" in t:
        return "EFL Championship Play-Off"
    return "EFL Championship"


# ── Primary scraper: BBC Sport ───────────────────────────────────────────────

def _scrape_bbc() -> list:
    """
    Parse BBC Sport's Bristol City fixtures page.

    BBC Sport fixture pages render each match inside a list/article with:
      - Date (in a heading or time element)
      - Home team v Away team
      - Competition label
      - Score (only if played)

    We look for upcoming (no score) fixtures where Bristol City is home.
    BBC's stable CSS classes include 'sp-c-fixture' and 'gs-o-list-ui__item'.
    We use text-pattern matching as a universal fallback when classes change.
    """
    from scraper import CalendarEvent

    soup = _fetch(BBC_URL)
    if not soup:
        return []

    events = []
    seen = set()

    # ── Strategy 1: structured fixture elements ──────────────────────────
    containers = (
        soup.find_all(class_=re.compile(r"sp-c-fixture", re.I)) or
        soup.find_all("li",  class_=re.compile(r"fixture|match", re.I)) or
        soup.find_all("article", class_=re.compile(r"fixture|match", re.I))
    )

    for el in containers:
        text = el.get_text(separator=" ", strip=True)
        ev = _parse_bbc_element(el, text)
        if ev and ev.uid not in seen:
            seen.add(ev.uid)
            events.append(ev)

    # ── Strategy 2: full-page text scan ─────────────────────────────────
    if not events:
        logger.debug("BBC Sport: structured elements empty, falling back to text scan")
        events = _bbc_text_scan(soup)

    logger.info(f"BBC Sport: {len(events)} upcoming home fixtures")
    return events


def _parse_bbc_element(el, text: str):
    """Try to extract a home fixture from a BBC Sport fixture element."""
    # Must mention Bristol City
    if not re.search(r"bristol city", text, re.I):
        return None

    # Skip if it looks like a result (has a scoreline like '2 - 1')
    if re.search(r"\b\d\s*[-–]\s*\d\b", text):
        return None

    # Determine home/away — BBC puts home team first
    # Pattern: "Bristol City v Opponent" = home; "Opponent v Bristol City" = away
    vs_match = re.search(
        r"(Bristol City)\s+v\s+([\w\s&'-]+?)(?:\s{2,}|\s*$)|"
        r"([\w\s&'-]+?)\s+v\s+(Bristol City)",
        text, re.I
    )
    if not vs_match:
        return None

    if vs_match.group(1):  # Bristol City is home
        opponent = vs_match.group(2).strip()
    else:
        return None  # away match — skip

    if not opponent or len(opponent) < 2:
        return None

    # Date — look for <time> element first, then text pattern
    time_el = el.find("time")
    date_str = ""
    time_str = "15:00"

    if time_el:
        dt_attr = time_el.get("datetime", "")
        # BBC uses ISO format: 2026-04-25T15:00:00+01:00
        if dt_attr:
            try:
                dt = dateutil_parser.parse(dt_attr)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=TZ)
                if not _is_future(dt):
                    return None
                opponent = _clean_team_name(opponent)
                return _make_event(opponent, _extract_competition(text), dt)
            except Exception:
                pass
        date_str = time_el.get_text(strip=True)

    if not date_str:
        date_match = re.search(
            r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*(?:\s+\d{4})?)",
            text, re.I
        )
        if date_match:
            date_str = date_match.group(1)

    if not date_str:
        return None

    time_match = re.search(r"(\d{1,2}:\d{2})", text)
    if time_match:
        time_str = time_match.group(1)

    start = _parse_dt(date_str, time_str)
    if not start or not _is_future(start):
        return None

    opponent = _clean_team_name(opponent)
    competition = _extract_competition(text)
    return _make_event(opponent, competition, start)


def _bbc_text_scan(soup: BeautifulSoup) -> list:
    """
    Text-based scan of the full BBC Sport page.
    Finds date headers followed by fixture lines with "Bristol City v <Opponent>".
    """
    events = []
    seen = set()
    lines = [l.strip() for l in soup.get_text(separator="\n").splitlines() if l.strip()]

    current_date = ""
    for i, line in enumerate(lines):
        # Date header: "Saturday 25 April", "Tue 28 Apr 2026" etc.
        date_m = re.match(
            r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+"
            r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*(?:\s+\d{4})?)\s*$",
            line, re.I
        )
        if date_m:
            current_date = date_m.group(1)
            continue

        # Home fixture line: "Bristol City v Opponent"
        fix_m = re.match(r"^(Bristol City)\s+v\s+([\w\s&'.-]+)$", line, re.I)
        if fix_m and current_date:
            opponent = _clean_team_name(fix_m.group(2).strip())

            # Look ahead for time
            time_str = "15:00"
            for lookahead in lines[i+1:i+4]:
                t = re.search(r"(\d{1,2}:\d{2})", lookahead)
                if t:
                    time_str = t.group(1)
                    break

            # Look ahead/behind for competition
            context = " ".join(lines[max(0,i-2):i+4])
            competition = _extract_competition(context)

            start = _parse_dt(current_date, time_str)
            if start and _is_future(start):
                uid = _make_uid(opponent, start)
                if uid not in seen:
                    seen.add(uid)
                    events.append(_make_event(opponent, competition, start))

    return events


# ── Fallback scraper: Soccerway ──────────────────────────────────────────────

def _scrape_soccerway() -> list:
    """
    Parse Bristol City fixtures from Soccerway.
    Soccerway uses a table with columns: date, home, score, away, competition.
    Home fixtures are where Bristol City appears in the home column.
    Future matches have no score (shown as '-' or empty).
    """
    soup = _fetch(SOCCERWAY_URL)
    if not soup:
        return []

    events = []
    seen = set()

    rows = soup.find_all("tr", class_=re.compile(r"match|fixture|future", re.I))
    if not rows:
        # Try any table rows on the page
        rows = soup.find_all("tr")

    for row in rows:
        text = row.get_text(separator="|", strip=True)
        if not re.search(r"bristol city", text, re.I):
            continue

        # Skip played matches (have a numeric score)
        if re.search(r"\|\s*\d+\s*-\s*\d+\s*\|", text):
            continue

        # Parse cells
        cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
        if len(cells) < 4:
            continue

        # Find date cell
        date_str = ""
        for cell in cells:
            if re.search(r"\d{2}/\d{2}/\d{4}|\d{1,2}\s+\w+\s+\d{4}", cell):
                date_str = cell
                break

        if not date_str:
            continue

        # Check home team column — Soccerway: col 1=date, col2=home, col3=score, col4=away
        home_team = cells[1] if len(cells) > 1 else ""
        away_team = cells[3] if len(cells) > 3 else ""

        if not re.search(r"bristol city", home_team, re.I):
            continue  # away match

        opponent = _clean_team_name(away_team)
        time_match = re.search(r"(\d{1,2}:\d{2})", text)
        time_str = time_match.group(1) if time_match else "15:00"

        competition = _extract_competition(text)
        start = _parse_dt(date_str, time_str)
        if not start or not _is_future(start):
            continue

        uid = _make_uid(opponent, start)
        if uid not in seen:
            seen.add(uid)
            events.append(_make_event(opponent, competition, start))

    logger.info(f"Soccerway: {len(events)} upcoming home fixtures")
    return events


# ── Hardcoded baseline ───────────────────────────────────────────────────────

def get_known_bcfc_fixtures() -> list:
    """
    Return hardcoded Bristol City home fixtures as a guaranteed baseline.
    Uses FULL_SEASON_HOME_FIXTURES and filters to future-only automatically.
    Update each summer when the new season's fixtures are released.
    """
    events = []
    seen = set()
    now = datetime.now(tz=TZ)

    for date_str, time_str, opponent, competition in FULL_SEASON_HOME_FIXTURES:
        start = _parse_dt(date_str, time_str)
        if not start:
            continue
        if start <= now:
            continue  # skip already-played matches
        uid = _make_uid(opponent, start)
        if uid not in seen:
            seen.add(uid)
            events.append(_make_event(opponent, competition, start))

    logger.info(f"BCFC baseline: {len(events)} upcoming home fixtures")
    return events


# ── Team name cleaner ────────────────────────────────────────────────────────

_NAME_MAP = {
    "west brom": "West Bromwich Albion",
    "west bromwich": "West Bromwich Albion",
    "sheff utd": "Sheffield United",
    "sheff wed": "Sheffield Wednesday",
    "sheff wednesday": "Sheffield Wednesday",
    "pne": "Preston North End",
    "qpr": "QPR",
    "man city": "Manchester City",
    "man utd": "Manchester United",
}


def _clean_team_name(name: str) -> str:
    """Normalise team names from various sources."""
    name = name.strip()
    # Remove trailing junk like score or TBC
    name = re.sub(r"\s*(TBC|TBA|\d+[-–]\d+)\s*$", "", name, flags=re.I).strip()
    lower = name.lower()
    return _NAME_MAP.get(lower, name)


# ── Main entry point ─────────────────────────────────────────────────────────

def scrape_bristol_city_home_fixtures() -> list:
    """
    Run all scrapers in order and return merged, deduplicated home fixtures.
    Always supplements with the hardcoded baseline for reliability.
    """
    logger.info("--- Bristol City FC home fixtures ---")

    # Layer 1: BBC Sport (primary)
    live_events = _scrape_bbc()

    # Layer 2: Soccerway fallback
    if not live_events:
        logger.warning("BBC Sport: no results — trying Soccerway fallback")
        live_events = _scrape_soccerway()

    # Layer 3: Hardcoded baseline (always merge)
    baseline = get_known_bcfc_fixtures()

    # Merge: combine live + baseline, deduplicate by uid
    all_events = {ev.uid: ev for ev in baseline}
    for ev in live_events:
        all_events[ev.uid] = ev  # live data wins over baseline

    result = sorted(all_events.values(), key=lambda e: e.start)
    logger.info(f"Bristol City: {len(result)} total upcoming home fixtures")
    return result


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    fixtures = scrape_bristol_city_home_fixtures()
    print(f"\nBristol City home fixtures: {len(fixtures)}")
    for f in fixtures:
        print(f"  {f.start.strftime('%Y-%m-%d %H:%M')} | {f.title} | {f.categories[-1]}")
