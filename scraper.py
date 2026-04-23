#!/usr/bin/env python3

# Bristol City FC Home Fixtures Scraper

# ======================================

# Fetches Bristol City home matches at Ashton Gate and returns CalendarEvent objects.

# 

# DATA SOURCE DECISION:

# PRIMARY:  BBC Sport - bbc.co.uk/sport/football/teams/bristol-city/fixtures

# Chosen because: public HTML, no login, no API key, stable for 10+ years,

# covers Championship, FA Cup, Carabao Cup and play-offs, real-time kick-off

# time updates.

# FALLBACK: Soccerway - uk.soccerway.com/teams/england/bristol-city-fc/660/matches/

# Independent aggregator, different code path = true redundancy.

# BASELINE: Hardcoded known home fixtures (researched April 2026).

# Guarantees calendar is never empty even if both scrapers fail.

# 

# Only …
[11:22, 23/04/2026] Jason: #!/usr/bin/env python3

# Bristol Bears & Ashton Gate Calendar Scraper

# ============================================

# Scrapes fixtures from Premiership Rugby website and events from

# Ashton Gate Stadium’s What’s On page, then generates a combined .ics file.

# 

# Data Source Decision:

# - Bristol Bears fixtures: Premiership Rugby official website (premiershiprugby.com)

# Chosen because: public HTML, stable structure, covers all Premiership matches,

# no login required, no API key needed.

# Fallback: Ultimate Rugby (ultimaterugby.com) for additional competitions.

# - Ashton Gate events: ashtongatestadium.co.uk/whatson/

# Chosen because: official source, WordPress CMS with stable event markup.

import json
import logging
import logging.handlers
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

# —————————————————————————

# Setup

# —————————————————————————

BASE_DIR = Path(*file*).resolve().parent
CONFIG_PATH = BASE_DIR / “config.json”

with open(CONFIG_PATH) as f:
CONFIG = json.load(f)

# Logging

log_cfg = CONFIG[“logging”]
log_dir = BASE_DIR / Path(log_cfg[“file”]).parent
log_dir.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(“bristol_calendar”)
logger.setLevel(getattr(logging, log_cfg[“level”]))

formatter = logging.Formatter(log_cfg[“format”])

# Console handler

ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(formatter)
logger.addHandler(ch)

# Rotating file handler

fh = logging.handlers.RotatingFileHandler(
BASE_DIR / log_cfg[“file”],
maxBytes=log_cfg[“max_bytes”],
backupCount=log_cfg[“backup_count”],
)
fh.setFormatter(formatter)
logger.addHandler(fh)

TZ = ZoneInfo(CONFIG[“timezone”])
HTTP_CFG = CONFIG[“http”]

# —————————————————————————

# Data model

# —————————————————————————

@dataclass
class CalendarEvent:
uid: str
title: str
start: datetime
end: datetime
location: str = “”
description: str = “”
categories: list = field(default_factory=list)
url: str = “”
status: str = “CONFIRMED”  # CONFIRMED, TENTATIVE, CANCELLED

# —————————————————————————

# HTTP helpers

# —————————————————————————

SESSION = requests.Session()
SESSION.headers.update({
“User-Agent”: HTTP_CFG[“user_agent”],
“Accept”: “text/html,application/xhtml+xml,application/xml;q=0.9,/;q=0.8”,
“Accept-Language”: “en-GB,en;q=0.9”,
})

def fetch_page(url: str, retries: int = None) -> Optional[BeautifulSoup]:
# Fetch a URL and return a BeautifulSoup object, with retries.


if retries is None:
    retries = HTTP_CFG["retry_attempts"]
for attempt in range(1, retries + 1):
    try:
        logger.info(f"Fetching [{attempt}/{retries}]: {url}")
        resp = SESSION.get(url, timeout=HTTP_CFG["timeout_seconds"])
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except requests.RequestException as e:
        logger.warning(f"Request failed (attempt {attempt}): {e}")
        if attempt < retries:
            time.sleep(HTTP_CFG["retry_delay_seconds"])
logger.error(f"All {retries} attempts failed for {url}")
return None


# —————————————————————————

# Date/time parsing

# —————————————————————————

def parse_uk_datetime(date_str: str, time_str: str = “”) -> Optional[datetime]:
# Parse a date string (and optional time) into a timezone-aware UK datetime.

# Handles formats like:

# ‘17 Apr 2026’, ‘Fri, Apr 17’, ‘17th April 2026’, ‘2026-04-17’

# Times like: ‘19:45’, ‘7:45pm’, ‘15:00’


date_str = date_str.strip()
time_str = time_str.strip() if time_str else ""

# Remove ordinal suffixes
date_str = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_str)

combined = f"{date_str} {time_str}".strip() if time_str else date_str

try:
    dt = dateutil_parser.parse(combined, dayfirst=True, fuzzy=True)
    # If no year was present, assume current or next year
    now = datetime.now(tz=TZ)
    if dt.year < now.year:
        dt = dt.replace(year=now.year)
    # Attach timezone
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt
except Exception as e:
    logger.debug(f"Date parse failed for '{combined}': {e}")
    return None


def make_uid(prefix: str, title: str, start: datetime) -> str:
# Generate a stable unique UID for an ICS event.


slug = re.sub(r"[^a-z0-9]", "-", title.lower())[:40]
stamp = start.strftime("%Y%m%dT%H%M%S")
return f"{prefix}-{slug}-{stamp}@bristol-bears-calendar"


# —————————————————————————

# Bristol Bears scraper — Primary: Premiership Rugby

# —————————————————————————

PREM_URL = CONFIG[“sources”][“bristol_bears”][“primary”][“url”]
PREM_FALLBACK_URL = CONFIG[“sources”][“bristol_bears”][“fallback”][“url”]

def scrape_prem_rugby_fixtures() -> list[CalendarEvent]:
# Scrape Bristol Bears fixtures from the Premiership Rugby website.

# The site renders fixture cards with date/time/teams/venue info.

# Falls back to Ultimate Rugby if Premiership Rugby fails.


events = []

soup = fetch_page(PREM_URL)
if soup:
    events = _parse_prem_rugby_page(soup)
    logger.info(f"Premiership Rugby: found {len(events)} fixtures")

if not events:
    logger.warning("Premiership Rugby scrape yielded 0 results — trying fallback")
    soup2 = fetch_page(PREM_FALLBACK_URL)
    if soup2:
        events = _parse_ultimate_rugby_page(soup2)
        logger.info(f"Ultimate Rugby fallback: found {len(events)} fixtures")

return events


def _parse_prem_rugby_page(soup: BeautifulSoup) -> list[CalendarEvent]:
# Parse fixtures from premiershiprugby.com club fixtures page.


events = []
seen = set()

# The Premiership Rugby site uses match cards with various class structures.
# We look for elements containing match data by scanning for date+team patterns.

# Try multiple selector strategies for resilience
match_cards = (
    soup.find_all("div", class_=re.compile(r"match|fixture|card", re.I)) or
    soup.find_all("article", class_=re.compile(r"match|fixture", re.I)) or
    soup.find_all("li", class_=re.compile(r"match|fixture", re.I))
)

logger.debug(f"Prem Rugby: found {len(match_cards)} potential match cards")

for card in match_cards:
    event = _extract_prem_match_card(card)
    if event and event.uid not in seen:
        seen.add(event.uid)
        events.append(event)

# If structured cards didn't work, try text-based extraction
if not events:
    events = _extract_prem_text_based(soup)

return events


def _extract_prem_match_card(card) -> Optional[CalendarEvent]:
# Extract a fixture from a Premiership Rugby match card element.


text = card.get_text(separator=" ", strip=True)

# Must contain 'Bristol Bears' or 'Bristol'
if not re.search(r"bristol", text, re.I):
    return None

# Extract date - look for date patterns
date_match = re.search(
    r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})",
    text, re.I
) or re.search(
    r"((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s+\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))",
    text, re.I
)
if not date_match:
    return None

date_str = date_match.group(1)

# Extract time
time_match = re.search(r"(\d{1,2}:\d{2}(?:\s*[ap]m)?)", text, re.I)
time_str = time_match.group(1) if time_match else "15:00"

start = parse_uk_datetime(date_str, time_str)
if not start:
    return None

duration = CONFIG["default_match_duration_minutes"]
end = start + timedelta(minutes=duration)

# Extract teams - look for vs / v pattern
vs_match = re.search(r"([A-Za-z][A-Za-z\s]+?)\s+(?:v|vs\.?)\s+([A-Za-z][A-Za-z\s]+)", text, re.I)
home_team = "Bristol Bears"
away_team = "TBC"
is_home = True

if vs_match:
    t1 = vs_match.group(1).strip()
    t2 = vs_match.group(2).strip()
    if re.search(r"bristol", t1, re.I):
        home_team = "Bristol Bears"
        away_team = t2
    elif re.search(r"bristol", t2, re.I):
        home_team = t1
        away_team = "Bristol Bears"
        is_home = False
    else:
        home_team = t1
        away_team = t2

if is_home:
    title = f"Bristol Bears vs {away_team}"
    location = "Ashton Gate Stadium, Ashton Road, Bristol, BS3 2EJ"
else:
    title = f"{home_team} vs Bristol Bears"
    location = _guess_venue(home_team)

# Competition from card text
competition = _extract_competition(text)

description = _build_rugby_description(
    home_team=home_team if not is_home else "Bristol Bears",
    away_team=away_team if is_home else "Bristol Bears",
    competition=competition,
    kickoff=start.strftime("%A %d %B %Y, %H:%M"),
    is_home=is_home,
)

uid = make_uid("prem", title, start)

return CalendarEvent(
    uid=uid,
    title=title,
    start=start,
    end=end,
    location=location,
    description=description,
    categories=["Rugby", "Bristol Bears", competition],
    url=PREM_URL,
)


def _extract_prem_text_based(soup: BeautifulSoup) -> list[CalendarEvent]:
# Text-based fallback: find all text nodes containing Bristol Bears match info.

# Scans the full page text for fixture patterns.


events = []
seen = set()
page_text = soup.get_text(separator="\n")

# Pattern: date line followed by team line
# e.g. "Fri, Apr 17\n19:45\nBristol Bears v Gloucester"
lines = [l.strip() for l in page_text.splitlines() if l.strip()]

i = 0
while i < len(lines):
    line = lines[i]
    # Check if this line looks like a date
    if re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", line, re.I):
        # Collect next few lines to find match info
        window = " ".join(lines[i:i+6])
        if re.search(r"bristol", window, re.I):
            event = _parse_fixture_from_text_window(window)
            if event and event.uid not in seen:
                seen.add(event.uid)
                events.append(event)
    i += 1

return events


def _parse_fixture_from_text_window(text: str) -> Optional[CalendarEvent]:
# Parse a fixture from a multi-line text window.


# Extract date
date_match = re.search(
    r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*(?:\s+\d{4})?)",
    text, re.I
) or re.search(
    r"((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:\s+\d{4})?)",
    text, re.I
)
if not date_match:
    return None

date_str = date_match.group(1)
time_match = re.search(r"(\d{1,2}:\d{2}(?:\s*[ap]m)?)", text, re.I)
time_str = time_match.group(1) if time_match else "15:00"

start = parse_uk_datetime(date_str, time_str)
if not start:
    return None

# Look for vs pattern containing Bristol
vs_match = re.search(
    r"(Bristol Bears|Bristol)\s+(?:v|vs\.?)\s+([A-Za-z][A-Za-z\s&']+?)(?:\s+\d|\s*$|\n|[|])",
    text, re.I
) or re.search(
    r"([A-Za-z][A-Za-z\s&']+?)\s+(?:v|vs\.?)\s+(Bristol Bears|Bristol)(?:\s|\n|$)",
    text, re.I
)

is_home = True
home_team = "Bristol Bears"
away_team = "TBC"

if vs_match:
    t1 = vs_match.group(1).strip()
    t2 = vs_match.group(2).strip()
    if re.search(r"bristol", t1, re.I):
        away_team = t2
    else:
        home_team = t1
        away_team = "Bristol Bears"
        is_home = False

if is_home:
    title = f"Bristol Bears vs {away_team}"
    location = "Ashton Gate Stadium, Ashton Road, Bristol, BS3 2EJ"
else:
    title = f"{home_team} vs Bristol Bears"
    location = _guess_venue(home_team)

competition = _extract_competition(text)
duration = CONFIG["default_match_duration_minutes"]
end = start + timedelta(minutes=duration)
uid = make_uid("bb", title, start)

description = _build_rugby_description(
    home_team="Bristol Bears" if is_home else home_team,
    away_team=away_team if is_home else "Bristol Bears",
    competition=competition,
    kickoff=start.strftime("%A %d %B %Y, %H:%M"),
    is_home=is_home,
)

return CalendarEvent(
    uid=uid,
    title=title,
    start=start,
    end=end,
    location=location,
    description=description,
    categories=["Rugby", "Bristol Bears", competition],
    url=PREM_URL,
)


def _parse_ultimate_rugby_page(soup: BeautifulSoup) -> list[CalendarEvent]:
# Parse fixtures from ultimaterugby.com.


events = []
seen = set()

# Ultimate Rugby lists matches with team names and dates
match_links = soup.find_all("a", href=re.compile(r"/match/bristol", re.I))

for link in match_links:
    href = link.get("href", "")
    full_url = f"https://www.ultimaterugby.com{href}" if href.startswith("/") else href
    text = link.get_text(separator=" ", strip=True)

    if not text:
        continue

    # Extract date from URL or text
    date_match = re.search(
        r"(\d{1,2}(?:st|nd|rd|th)?-(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*-(\d{4}))",
        href, re.I
    )
    date_str = ""
    if date_match:
        date_str = date_match.group(1).replace("-", " ")
    else:
        # Try page text around the link
        parent_text = ""
        parent = link.parent
        for _ in range(3):
            if parent:
                parent_text = parent.get_text(separator=" ", strip=True)
                dm = re.search(
                    r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})",
                    parent_text, re.I
                )
                if dm:
                    date_str = dm.group(1)
                    break
                parent = getattr(parent, "parent", None)

    if not date_str:
        continue

    time_match = re.search(r"(\d{1,2}:\d{2}(?:\s*[ap]m)?)", text, re.I)
    time_str = time_match.group(1) if time_match else "15:00"

    start = parse_uk_datetime(date_str, time_str)
    if not start:
        continue

    # Extract teams from link text or href
    # URL format: /match/bristol-bears-vs-gloucester-rugby-at-ashton-gate-17th-apr-2026/
    vs_url_match = re.search(
        r"match/(.+?)-vs-(.+?)-at-(.+?)-\d",
        href, re.I
    )
    home_team = "Bristol Bears"
    away_team = "TBC"
    venue_slug = ""
    is_home = True

    if vs_url_match:
        t1_slug = vs_url_match.group(1).replace("-", " ").title()
        t2_slug = vs_url_match.group(2).replace("-", " ").title()
        venue_slug = vs_url_match.group(3).replace("-", " ").title()
        if re.search(r"bristol", t1_slug, re.I):
            away_team = t2_slug
        else:
            home_team = t1_slug
            away_team = "Bristol Bears"
            is_home = False

    if is_home:
        title = f"Bristol Bears vs {away_team}"
        location = "Ashton Gate Stadium, Ashton Road, Bristol, BS3 2EJ"
    else:
        title = f"{home_team} vs Bristol Bears"
        location = venue_slug if venue_slug else _guess_venue(home_team)

    duration = CONFIG["default_match_duration_minutes"]
    end = start + timedelta(minutes=duration)
    uid = make_uid("ur", title, start)

    if uid in seen:
        continue
    seen.add(uid)

    competition = _extract_competition(text + " " + href)
    description = _build_rugby_description(
        home_team="Bristol Bears" if is_home else home_team,
        away_team=away_team if is_home else "Bristol Bears",
        competition=competition,
        kickoff=start.strftime("%A %d %B %Y, %H:%M"),
        is_home=is_home,
    )

    events.append(CalendarEvent(
        uid=uid,
        title=title,
        start=start,
        end=end,
        location=location,
        description=description,
        categories=["Rugby", "Bristol Bears", competition],
        url=full_url,
    ))

return events


# —————————————————————————

# Bristol Bears scraper — Additional: hardcoded known fixtures from research

# —————————————————————————

KNOWN_FIXTURES = [
# Compiled from research of official sources (April 2026 onwards)
# Format: (date_str, time_str, home, away, competition)
(“17 Apr 2026”, “19:45”, “Bristol Bears”, “Gloucester Rugby”, “Gallagher Premiership”),
(“25 Apr 2026”, “15:00”, “Newcastle Red Bulls”, “Bristol Bears”, “Gallagher Premiership”),
(“09 May 2026”, “15:00”, “Bristol Bears”, “Saracens”, “Gallagher Premiership”),
(“16 May 2026”, “15:00”, “Northampton Saints”, “Bristol Bears”, “Gallagher Premiership”),
(“30 May 2026”, “15:00”, “Bristol Bears”, “Bath Rugby”, “Gallagher Premiership”),
(“06 Jun 2026”, “14:00”, “Sale Sharks”, “Bristol Bears”, “Gallagher Premiership”),
]

KNOWN_VENUES = {
“Newcastle Red Bulls”: “Kingston Park, Brunton Road, Kenton Bank Foot, Newcastle, NE13 8AF”,
“Northampton Saints”: “cinch Stadium at Franklin’s Gardens, Weedon Road, Northampton, NN5 5BG”,
“Bath Rugby”: “The Rec, Pulteney Mews, Bath, BA2 4DS”,
“Sale Sharks”: “Salford Community Stadium, 1 Stadium Way, Eccles, Salford, M30 7EY”,
“Exeter Chiefs”: “Sandy Park, Exeter, EX2 7NN”,
“Gloucester Rugby”: “Kingsholm Stadium, Kingsholm Road, Gloucester, GL1 3AX”,
“Harlequins”: “The Stoop, Langhorn Drive, Twickenham, TW2 7SX”,
“Leicester Tigers”: “Welford Road Stadium, Aylestone Road, Leicester, LE2 7TR”,
“Saracens”: “StoneX Stadium, Greenlands Lane, London, NW4 1RL”,
}

def get_known_fixtures() -> list[CalendarEvent]:
# Return hardcoded known fixtures as a reliable baseline.


events = []
for date_str, time_str, home, away, competition in KNOWN_FIXTURES:
    start = parse_uk_datetime(date_str, time_str)
    if not start:
        continue
    end = start + timedelta(minutes=CONFIG["default_match_duration_minutes"])

    is_home = home == "Bristol Bears"
    if is_home:
        title = f"Bristol Bears vs {away}"
        location = "Ashton Gate Stadium, Ashton Road, Bristol, BS3 2EJ"
    else:
        title = f"{home} vs Bristol Bears"
        location = KNOWN_VENUES.get(home, _guess_venue(home))

    description = _build_rugby_description(
        home_team=home,
        away_team=away,
        competition=competition,
        kickoff=start.strftime("%A %d %B %Y, %H:%M"),
        is_home=is_home,
    )

    events.append(CalendarEvent(
        uid=make_uid("known", title, start),
        title=title,
        start=start,
        end=end,
        location=location,
        description=description,
        categories=["Rugby", "Bristol Bears", competition],
        url="https://www.bristolbearsrugby.com/bears-men/first-team/fixtures-results/",
    ))
return events


# —————————————————————————

# Ashton Gate events scraper

# —————————————————————————

ASHTON_GATE_URL = CONFIG[“sources”][“ashton_gate”][“primary”][“url”]

def scrape_ashton_gate_events() -> list[CalendarEvent]:
# Scrape events from Ashton Gate Stadium What’s On page.

# The page is a WordPress site with event articles structured as:

# <article class="tribe-events-calendar-list__event-article">

# or similar event markup.


events = []
seen = set()

soup = fetch_page(ASHTON_GATE_URL)
if not soup:
    logger.error("Failed to fetch Ashton Gate events page")
    return events

# Strategy 1: WordPress tribe events
tribe_events = soup.find_all("article", class_=re.compile(r"tribe-events|event", re.I))
logger.debug(f"Ashton Gate: tribe events found: {len(tribe_events)}")

# Strategy 2: Generic event/article elements
if not tribe_events:
    tribe_events = soup.find_all(
        ["article", "div", "li"],
        class_=re.compile(r"event|card|post", re.I)
    )

for article in tribe_events:
    event = _parse_ashton_gate_article(article)
    if event and event.uid not in seen:
        seen.add(event.uid)
        events.append(event)

# Strategy 3: Text-based fallback from the page
if not events:
    events = _parse_ashton_gate_text(soup)

# Strategy 4: Parse hardcoded known events from research
if not events:
    logger.warning("Ashton Gate scrape yielded 0 results — using research baseline")
    events = get_known_ashton_gate_events()

logger.info(f"Ashton Gate: found {len(events)} events total")

# Deduplicate by UID
final = []
seen2 = set()
for e in events:
    if e.uid not in seen2:
        seen2.add(e.uid)
        final.append(e)

return final


def _parse_ashton_gate_article(article) -> Optional[CalendarEvent]:
# Parse a single event article from the Ashton Gate What’s On page.


# Title
title_el = (
    article.find(["h1", "h2", "h3", "h4"], class_=re.compile(r"title|name|heading", re.I)) or
    article.find(["h1", "h2", "h3", "h4"])
)
if not title_el:
    return None
title = title_el.get_text(strip=True)
if not title:
    return None

text = article.get_text(separator=" ", strip=True)

# Date - Ashton Gate page shows dates like "25 April" or "25 April - 25 April"
date_match = re.search(
    r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s*(?:\d{4})?)",
    text, re.I
)
if not date_match:
    return None

date_str = date_match.group(1).strip()
# If no year, try to get from page context or use current/next year
if not re.search(r"\d{4}", date_str):
    now = datetime.now(tz=TZ)
    date_str = f"{date_str} {now.year}"

# Time
time_match = re.search(r"(\d{1,2}:\d{2}(?:\s*[ap]m)?)", text, re.I)
time_str = time_match.group(1) if time_match else ""

start = parse_uk_datetime(date_str, time_str)
if not start:
    return None

# Duration: for events without end time, use config default
duration = CONFIG["default_event_duration_minutes"]
end = start + timedelta(minutes=duration)

# URL
link = article.find("a", href=re.compile(r"ashtongatestadium|event", re.I))
url = link.get("href", ASHTON_GATE_URL) if link else ASHTON_GATE_URL

# Description
desc_el = article.find(["p", "div"], class_=re.compile(r"desc|excerpt|content|summary", re.I))
raw_desc = desc_el.get_text(strip=True)[:500] if desc_el else ""
description = _build_event_description(title=title, date_str=date_str, raw_desc=raw_desc)

# Category
cat_el = article.find(class_=re.compile(r"categ|tag|type", re.I))
category = cat_el.get_text(strip=True) if cat_el else "Event"
if not category:
    category = "Event"

uid = make_uid("ag", title, start)

return CalendarEvent(
    uid=uid,
    title=title,
    start=start,
    end=end,
    location="Ashton Gate Stadium, Ashton Road, Bristol, BS3 2EJ",
    description=description,
    categories=["Ashton Gate", "Stadium Event", category],
    url=url,
)


def _parse_ashton_gate_text(soup: BeautifulSoup) -> list[CalendarEvent]:
# Text-based fallback parser for Ashton Gate What’s On page.


events = []
seen = set()

# The page has month headers like "## APRIL 2026" and event blocks below
text = soup.get_text(separator="\n")
lines = [l.strip() for l in text.splitlines() if l.strip()]

# Find event blocks: a date marker followed by title and location
i = 0
while i < len(lines):
    line = lines[i]
    # Look for date pattern (day of month at start of line, or month name)
    date_match = re.match(
        r"^(\d{1,2})\s+((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*)\s*(\d{4})?$",
        line, re.I
    )
    if date_match:
        day = date_match.group(1)
        month = date_match.group(2)
        year = date_match.group(3)

        if not year:
            # Look backwards for a month/year header
            for j in range(max(0, i-10), i):
                m = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})", lines[j], re.I)
                if m:
                    year = m.group(2)
                    break
            if not year:
                year = str(datetime.now(tz=TZ).year)

        date_str = f"{day} {month} {year}"

        # Next lines should contain: event title, then description/location
        # Look ahead for title (non-date, non-location line)
        title = ""
        time_str = ""
        for k in range(i+1, min(i+5, len(lines))):
            candidate = lines[k]
            if re.search(r"ashton gate|location|find out more|bristol", candidate, re.I):
                continue
            time_m = re.search(r"(\d{1,2}:\d{2}(?:\s*[ap]m)?)", candidate)
            if time_m and not title:
                time_str = time_m.group(1)
                continue
            if len(candidate) > 5 and not re.match(r"^\d", candidate):
                title = candidate
                break

        if not title:
            i += 1
            continue

        start = parse_uk_datetime(date_str, time_str)
        if not start:
            i += 1
            continue

        duration = CONFIG["default_event_duration_minutes"]
        end = start + timedelta(minutes=duration)
        uid = make_uid("ag-txt", title, start)

        if uid not in seen:
            seen.add(uid)
            description = _build_event_description(title=title, date_str=date_str)
            events.append(CalendarEvent(
                uid=uid,
                title=title,
                start=start,
                end=end,
                location="Ashton Gate Stadium, Ashton Road, Bristol, BS3 2EJ",
                description=description,
                categories=["Ashton Gate", "Stadium Event"],
                url=ASHTON_GATE_URL,
            ))
    i += 1

return events


# —————————————————————————

# Hardcoded baseline events from research (April 2026 onwards)

# —————————————————————————

KNOWN_ASHTON_GATE_EVENTS = [
# From research of ashtongatestadium.co.uk/whatson/ on 2026-04-19
(“25 Apr 2026”, “14:15”, “Red Roses vs Wales | Women’s Six Nations”, “Sport”),
(“27 Apr 2026”, “09:00”, “National Apprenticeship & Education Event – Skills Show Southwest”, “Event”),
(“03 May 2026”, “10:00”, “Card Market Bristol”, “Event”),
(“14 May 2026”, “10:00”, “Play on the Pitch”, “Event”),
(“21 May 2026”, “09:00”, “Digital NRG: How to Grow & Scale a Brand in 2026”, “Event”),
(“21 May 2026”, “18:30”, “Gala Dinner 2026”, “Event”),
(“14 Jun 2026”, “09:00”, “Bristol Guitar Show”, “Event”),
(“04 Jul 2026”, “11:00”, “Bristol Tattoo Convention 2026”, “Event”),
(“26 Jul 2026”, “08:00”, “Break The Cycle 2026”, “Event”),
(“20 Oct 2026”, “10:00”, “itSHOWCASE Bristol”, “Event”),
]

def get_known_ashton_gate_events() -> list[CalendarEvent]:
# Return hardcoded known Ashton Gate events as reliable baseline.


events = []
for date_str, time_str, title, category in KNOWN_ASHTON_GATE_EVENTS:
    start = parse_uk_datetime(date_str, time_str)
    if not start:
        continue
    end = start + timedelta(minutes=CONFIG["default_event_duration_minutes"])
    uid = make_uid("ag-known", title, start)
    description = _build_event_description(title=title, date_str=date_str)
    events.append(CalendarEvent(
        uid=uid,
        title=f"[Ashton Gate] {title}",
        start=start,
        end=end,
        location="Ashton Gate Stadium, Ashton Road, Bristol, BS3 2EJ",
        description=description,
        categories=["Ashton Gate", "Stadium Event", category],
        url=ASHTON_GATE_URL,
    ))
return events


# —————————————————————————

# Helpers

# —————————————————————————

def _guess_venue(team: str) -> str:
# Return a known venue for a Premiership Rugby team.


return KNOWN_VENUES.get(team, f"{team} home ground")


def _extract_competition(text: str) -> str:
# Guess the competition from surrounding text.


text_lower = text.lower()
if "champions cup" in text_lower or "investec" in text_lower or "epcr" in text_lower:
    return "Investec Champions Cup"
if "premiership cup" in text_lower or "prem cup" in text_lower:
    return "Premiership Rugby Cup"
if "gallagher" in text_lower or "premiership" in text_lower or "prem rugby" in text_lower:
    return "Gallagher Premiership"
return "Rugby"


def _build_rugby_description(home_team: str, away_team: str, competition: str,
kickoff: str, is_home: bool) -> str:
# Build a rich description string for a rugby fixture.


home_flag = " 🏠" if is_home else ""
return (
    f"🏉 {competition}\n\n"
    f"{home_team} vs {away_team}\n"
    f"Kick-off: {kickoff}{home_flag}\n\n"
    f"Bristol Bears — Gallagher Premiership\n"
    f"Tickets: https://www.bristolbearsrugby.com/tickets/\n"
    f"Fixtures: https://www.bristolbearsrugby.com/bears-men/first-team/fixtures-results/"
)


def _build_event_description(title: str, date_str: str, raw_desc: str = “”) -> str:
# Build a description for an Ashton Gate event.


desc = f"🏟️ Ashton Gate Stadium Event\n\n{title}\nDate: {date_str}\n"
if raw_desc:
    desc += f"\n{raw_desc}\n"
desc += f"\nMore info: {ASHTON_GATE_URL}"
return desc


# —————————————————————————

# Deduplication and merging

# —————————————————————————

def merge_and_deduplicate(event_lists: list[list[CalendarEvent]]) -> list[CalendarEvent]:
# Merge multiple event lists, deduplicating by approximate date+title match.

# Prefer events with more complete data (location, description).


all_events = []
for lst in event_lists:
    all_events.extend(lst)

# Sort by start time
all_events.sort(key=lambda e: e.start)

# Deduplicate: two events are duplicates if same date and similar title
final = []
for event in all_events:
    is_dup = False
    for existing in final:
        if existing.start.date() == event.start.date():
            # Check title similarity (simple: normalised overlap)
            e_words = set(re.sub(r"[^a-z0-9]", " ", event.title.lower()).split())
            x_words = set(re.sub(r"[^a-z0-9]", " ", existing.title.lower()).split())
            overlap = e_words & x_words
            if len(overlap) >= 2 and len(overlap) / max(len(e_words), len(x_words)) > 0.5:
                # Keep whichever has more info
                if len(event.location) > len(existing.location):
                    final.remove(existing)
                    final.append(event)
                is_dup = True
                break
    if not is_dup:
        final.append(event)

final.sort(key=lambda e: e.start)
logger.info(f"After deduplication: {len(final)} events total")
return final


# —————————————————————————

# Main orchestration

# —————————————————————————

def run() -> list[CalendarEvent]:
# Run all scrapers and return merged, deduplicated event list.


logger.info("=" * 60)
logger.info("Bristol Bears, Bristol City & Ashton Gate Calendar Scraper")
logger.info("=" * 60)

# --- Bristol Bears fixtures ---
logger.info("Scraping Bristol Bears fixtures...")
bears_events = scrape_prem_rugby_fixtures()
known_bears = get_known_fixtures()
logger.info(f"Bristol Bears baseline: {len(known_bears)} fixtures")

# --- Ashton Gate events ---
logger.info("Scraping Ashton Gate Stadium events...")
ag_events = scrape_ashton_gate_events()
known_ag = get_known_ashton_gate_events()

# --- Bristol City FC home fixtures ---
logger.info("Scraping Bristol City FC home fixtures...")
try:
    from scraper_bcfc import scrape_bristol_city_home_fixtures
    bcfc_events = scrape_bristol_city_home_fixtures()
except Exception as e:
    logger.error(f"Bristol City scraper failed: {e}")
    bcfc_events = []

# Merge all sources
all_events = merge_and_deduplicate([
    bears_events, known_bears,
    ag_events, known_ag,
    bcfc_events,
])

logger.info(f"Total events in calendar: {len(all_events)}")
for ev in all_events:
    logger.info(f"  [{ev.start.strftime('%Y-%m-%d %H:%M')}] {ev.title}")

return all_events


if *name* == “*main*”:
events = run()
print(f”\n✅ Scraper complete. {len(events)} events found.”)
