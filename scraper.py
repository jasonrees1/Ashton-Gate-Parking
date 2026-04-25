#!/usr/bin/env python3
import json
import logging
import logging.handlers
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

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / 'config.json'

with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

TZ = ZoneInfo(CONFIG['timezone'])
HTTP = CONFIG['http']

log_cfg = CONFIG['logging']
log_dir = BASE_DIR / Path(log_cfg['file']).parent
log_dir.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger('bristol_calendar')
logger.setLevel(getattr(logging, log_cfg['level']))
fmt = logging.Formatter(log_cfg['format'])
ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(fmt)
logger.addHandler(ch)
fh = logging.handlers.RotatingFileHandler(
    BASE_DIR / log_cfg['file'],
    maxBytes=log_cfg['max_bytes'],
    backupCount=log_cfg['backup_count'],
)
fh.setFormatter(fmt)
logger.addHandler(fh)


@dataclass
class CalendarEvent:
    uid: str
    title: str
    start: datetime
    end: datetime
    location: str = ''
    description: str = ''
    categories: list = field(default_factory=list)
    url: str = ''
    status: str = 'CONFIRMED'


SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': HTTP['user_agent'],
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'en-GB,en;q=0.9',
})


def fetch(url):
    for attempt in range(1, HTTP['retry_attempts'] + 1):
        try:
            logger.info('Fetching [%d/%d]: %s', attempt, HTTP['retry_attempts'], url)
            r = SESSION.get(url, timeout=HTTP['timeout_seconds'])
            r.raise_for_status()
            return BeautifulSoup(r.text, 'lxml')
        except requests.RequestException as e:
            logger.warning('Fetch failed attempt %d: %s', attempt, e)
            if attempt < HTTP['retry_attempts']:
                time.sleep(HTTP['retry_delay_seconds'])
    logger.error('All attempts failed for %s', url)
    return None


def parse_dt(date_str, time_str='15:00'):
    date_str = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str.strip())
    has_year = bool(re.search(r'\b20\d{2}\b', date_str))
    combined = (date_str + ' ' + time_str).strip()
    try:
        dt = dateutil_parser.parse(combined, dayfirst=True, fuzzy=True)
        now = datetime.now(tz=TZ)
        if not has_year and dt.year < now.year:
            dt = dt.replace(year=now.year)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt
    except Exception as e:
        logger.debug('Date parse failed %r: %s', combined, e)
        return None


def make_uid(prefix, title, start):
    slug = re.sub(r'[^a-z0-9]', '-', title.lower())[:40]
    return '%s-%s-%s@bristol-bears-calendar' % (prefix, slug, start.strftime('%Y%m%dT%H%M%S'))


BEARS_VENUE = 'Ashton Gate Stadium, Ashton Road, Bristol, BS3 2EJ'
AG_URL = CONFIG['sources']['ashton_gate']['primary']['url']
PREM_URL = CONFIG['sources']['bristol_bears']['primary']['url']
BBC_URL = CONFIG['sources']['bristol_city']['primary']['url']

KNOWN_VENUES = {
    'Newcastle Red Bulls': 'Kingston Park, Brunton Road, Newcastle, NE13 8AF',
    'Northampton Saints': 'cinch Stadium, Weedon Road, Northampton, NN5 5BG',
    'Bath Rugby': 'The Rec, Pulteney Mews, Bath, BA2 4DS',
    'Sale Sharks': 'Salford Community Stadium, Eccles, Salford, M30 7EY',
    'Exeter Chiefs': 'Sandy Park, Exeter, EX2 7NN',
    'Gloucester Rugby': 'Kingsholm Stadium, Gloucester, GL1 3AX',
    'Harlequins': 'The Stoop, Twickenham, TW2 7SX',
    'Leicester Tigers': 'Welford Road Stadium, Leicester, LE2 7TR',
    'Saracens': 'StoneX Stadium, London, NW4 1RL',
}

# HOME FIXTURES ONLY - Bristol Bears at Ashton Gate
KNOWN_BEARS_FIXTURES = [
    ('17 Apr 2026', '19:45', 'Bristol Bears', 'Gloucester Rugby', 'Gallagher Premiership'),
    ('09 May 2026', '15:00', 'Bristol Bears', 'Saracens', 'Gallagher Premiership'),
    ('30 May 2026', '15:00', 'Bristol Bears', 'Bath Rugby', 'Gallagher Premiership'),
]

# MAJOR EVENTS ONLY - events likely to cause parking disruption around Ashton Gate
# Includes: international sport, concerts, large public shows, conventions, festivals
# Excludes: corporate seminars, training days, small business events, educational days
KNOWN_AG_EVENTS = [
    ('25 Apr 2026', '14:15', 'Red Roses vs Wales - Womens Six Nations', 'Sport'),
    ('04 Jul 2026', '11:00', 'Bristol Tattoo Convention 2026', 'Convention'),
    ('26 Jul 2026', '08:00', 'Break The Cycle 2026', 'Charity Event'),
]

# Keywords that indicate a MAJOR event worth including (parking impact likely)
MAJOR_EVENT_KEYWORDS = [
    'concert', 'live', 'tour', 'festival', 'gig',
    'international', 'nations', 'world cup', 'cup final', 'championship final',
    'convention', 'tattoo', 'comic con', 'expo',
    'show', 'exhibition',
    'rugby', 'football', 'cricket', 'boxing', 'ufc', 'mma',
    'marathon', 'run', 'cycle', 'triathlon', 'race',
    'graduation', 'ceremony',
    'red roses', 'england', 'wales', 'scotland', 'ireland',
]

# Keywords that indicate a MINOR event to exclude (parking impact unlikely)
MINOR_EVENT_KEYWORDS = [
    'conference', 'seminar', 'workshop', 'training', 'networking',
    'apprenticeship', 'education', 'learning', 'skills',
    'digital', 'tech', 'itshowcase', 'nrg',
    'dinner', 'gala', 'awards', 'lunch',
    'market', 'card market', 'craft',
    'pitch', 'play on the pitch',
    'guitar show',
]


def is_major_event(title):
    title_lower = title.lower()
    for kw in MINOR_EVENT_KEYWORDS:
        if kw in title_lower:
            return False
    for kw in MAJOR_EVENT_KEYWORDS:
        if kw in title_lower:
            return True
    return False

KNOWN_BCFC_FIXTURES = [
    ('02 May 2026', '12:30', 'Stoke City', 'EFL Championship'),
]


def bears_event(home, away, competition, start, end):
    is_home = home == 'Bristol Bears'
    title = '%s vs %s' % (home, away)
    loc = BEARS_VENUE if is_home else KNOWN_VENUES.get(home, home + ' home ground')
    desc = ('Rugby - %s\n%s vs %s\nKick-off: %s\nTickets: '
            'https://www.bristolbearsrugby.com/tickets/') % (
        competition, home, away, start.strftime('%A %d %B %Y %H:%M'))
    return CalendarEvent(
        uid=make_uid('bears', title, start),
        title=title, start=start, end=end,
        location=loc, description=desc,
        categories=['Rugby', 'Bristol Bears', competition],
        url='https://www.bristolbearsrugby.com/bears-men/first-team/fixtures-results/',
    )


def get_known_fixtures():
    events = []
    for date_str, time_str, home, away, comp in KNOWN_BEARS_FIXTURES:
        start = parse_dt(date_str, time_str)
        if not start:
            continue
        end = start + timedelta(minutes=CONFIG['default_match_duration_minutes'])
        events.append(bears_event(home, away, comp, start, end))
    return events


def get_known_ashton_gate_events():
    events = []
    for date_str, time_str, title, category in KNOWN_AG_EVENTS:
        start = parse_dt(date_str, time_str)
        if not start:
            continue
        end = start + timedelta(minutes=CONFIG['default_event_duration_minutes'])
        full_title = '[Ashton Gate] ' + title
        desc = 'Ashton Gate Stadium Event\n%s\nDate: %s\nMore info: %s' % (
            title, date_str, AG_URL)
        events.append(CalendarEvent(
            uid=make_uid('ag', title, start),
            title=full_title, start=start, end=end,
            location=BEARS_VENUE, description=desc,
            categories=['Ashton Gate', 'Stadium Event', category],
            url=AG_URL,
        ))
    return events


def get_known_bcfc_fixtures():
    events = []
    now = datetime.now(tz=TZ)
    for date_str, time_str, opponent, competition in KNOWN_BCFC_FIXTURES:
        start = parse_dt(date_str, time_str)
        if not start or start <= now:
            continue
        end = start + timedelta(minutes=115)
        title = 'Bristol City vs ' + opponent
        desc = ('Football - %s\nBristol City vs %s\nKick-off: %s\n'
                'Tickets: https://www.bcfc.co.uk/tickets/') % (
            competition, opponent, start.strftime('%A %d %B %Y %H:%M'))
        events.append(CalendarEvent(
            uid=make_uid('bcfc', title, start),
            title=title, start=start, end=end,
            location=BEARS_VENUE, description=desc,
            categories=['Football', 'Bristol City', competition],
            url='https://www.bcfc.co.uk/fixtures/',
        ))
    return events


def scrape_ashton_gate():
    soup = fetch(AG_URL)
    if not soup:
        return []
    events = []
    seen = set()
    containers = (
        soup.find_all('article', class_=re.compile(r'tribe|event', re.I)) or
        soup.find_all(['article', 'div'], class_=re.compile(r'event|card', re.I))
    )
    for el in containers:
        text = el.get_text(separator=' ', strip=True)
        title_el = el.find(['h1', 'h2', 'h3', 'h4'])
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue
        date_m = re.search(
            r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*(?:\s+\d{4})?)',
            text, re.I)
        if not date_m:
            continue
        date_str = date_m.group(1)
        if not re.search(r'\d{4}', date_str):
            date_str = date_str + ' ' + str(datetime.now(tz=TZ).year)
        time_m = re.search(r'(\d{1,2}:\d{2})', text)
        time_str = time_m.group(1) if time_m else ''
        start = parse_dt(date_str, time_str)
        if not start:
            continue
        end = start + timedelta(minutes=CONFIG['default_event_duration_minutes'])
        uid = make_uid('ag-live', title, start)
        if uid in seen:
            continue
        seen.add(uid)
        desc = 'Ashton Gate Stadium Event\n%s\nMore info: %s' % (title, AG_URL)
        if not is_major_event(title):
            logger.debug('Skipping minor event: %s', title)
            continue
        events.append(CalendarEvent(
            uid=uid, title='[Ashton Gate] ' + title,
            start=start, end=end, location=BEARS_VENUE,
            description=desc,
            categories=['Ashton Gate', 'Stadium Event'],
            url=AG_URL,
        ))
    logger.info('Ashton Gate live scrape: %d major events', len(events))
    return events


def scrape_bears():
    soup = fetch(PREM_URL)
    if not soup:
        return []
    events = []
    seen = set()
    text_blocks = soup.get_text(separator='\n').splitlines()
    current_date = ''
    for line in text_blocks:
        line = line.strip()
        date_m = re.search(
            r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*(?:\s+\d{4})?)',
            line, re.I)
        if date_m and not re.search(r'bristol', line, re.I):
            current_date = date_m.group(1)
            continue
        vs_m = re.search(r'(Bristol Bears)\s+v\s+([\w\s]+?)(?:\s{2,}|$)', line, re.I)
        if vs_m and current_date:
            # HOME ONLY - Bristol Bears listed first means home
            start = parse_dt(current_date)
            if not start:
                continue
            end = start + timedelta(minutes=CONFIG['default_match_duration_minutes'])
            away = vs_m.group(2).strip()
            ev = bears_event('Bristol Bears', away, 'Gallagher Premiership', start, end)
            if ev.uid not in seen:
                seen.add(ev.uid)
                events.append(ev)
    logger.info('Bears live scrape: %d fixtures', len(events))
    return events


def scrape_bcfc():
    soup = fetch(BBC_URL)
    if not soup:
        return []
    events = []
    seen = set()
    now = datetime.now(tz=TZ)
    time_el_list = soup.find_all('time')
    for t in time_el_list:
        dt_attr = t.get('datetime', '')
        if not dt_attr:
            continue
        try:
            dt = dateutil_parser.parse(dt_attr)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)
        except Exception:
            continue
        if dt <= now:
            continue
        parent = t.parent
        for _ in range(5):
            if parent is None:
                break
            text = parent.get_text(separator=' ', strip=True)
            vs_m = re.search(r'(Bristol City)\s+v\s+([\w\s]+?)(?:\s{2,}|\d|$)', text, re.I)
            if vs_m:
                opponent = vs_m.group(2).strip()
                end = dt + timedelta(minutes=115)
                title = 'Bristol City vs ' + opponent
                uid = make_uid('bcfc-live', title, dt)
                if uid not in seen:
                    seen.add(uid)
                    desc = 'Football - EFL Championship\nBristol City vs %s\nKick-off: %s' % (
                        opponent, dt.strftime('%A %d %B %Y %H:%M'))
                    events.append(CalendarEvent(
                        uid=uid, title=title, start=dt, end=end,
                        location=BEARS_VENUE, description=desc,
                        categories=['Football', 'Bristol City', 'EFL Championship'],
                        url='https://www.bcfc.co.uk/fixtures/',
                    ))
                break
            parent = getattr(parent, 'parent', None)
    logger.info('BCFC live scrape: %d fixtures', len(events))
    return events


PHANTOM_TITLES = re.compile(r'(?i)^(\[Ashton Gate\]\s+)?(january|february|march|april|may|june|july|august|september|october|november|december)\s*[0-9]{4}$')


def merge(event_lists):
    all_events = []
    for lst in event_lists:
        all_events.extend(lst)
    all_events.sort(key=lambda e: e.start)
    all_events = [e for e in all_events if not PHANTOM_TITLES.match(e.title.strip())]
    final = []
    seen = set()
    for ev in all_events:
        if ev.uid not in seen:
            seen.add(ev.uid)
            dup = False
            for ex in final:
                if ex.start.date() == ev.start.date():
                    ew = set(re.sub(r'[^a-z0-9]', ' ', ev.title.lower()).split())
                    xw = set(re.sub(r'[^a-z0-9]', ' ', ex.title.lower()).split())
                    overlap = ew & xw
                    if len(overlap) >= 2 and len(overlap) / max(len(ew), len(xw)) > 0.5:
                        dup = True
                        break
            if not dup:
                final.append(ev)
    final.sort(key=lambda e: e.start)
    logger.info('After dedup: %d events', len(final))
    return final


def run():
    logger.info('=' * 60)
    logger.info('Bristol Bears, Bristol City and Ashton Gate Calendar')
    logger.info('=' * 60)
    bears_live = scrape_bears()
    bears_known = get_known_fixtures()
    ag_live = scrape_ashton_gate()
    ag_known = get_known_ashton_gate_events()
    bcfc_live = scrape_bcfc()
    bcfc_known = get_known_bcfc_fixtures()
    all_events = merge([bears_live, bears_known, ag_live, ag_known, bcfc_live, bcfc_known])
    for ev in all_events:
        logger.info('[%s] %s', ev.start.strftime('%Y-%m-%d %H:%M'), ev.title)
    return all_events


if __name__ == '__main__':
    events = run()
    print('Scraper complete. %d events found.' % len(events))
