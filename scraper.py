#!/usr/bin/env python3
import logging
import logging.handlers
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

from core import CalendarEvent, parse_dt, make_uid, TZ, CONFIG, BEARS_VENUE

BASE_DIR = Path(__file__).resolve().parent

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


SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': HTTP['user_agent'],
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'en-GB,en;q=0.9',
})

# Populated during run(); read back to build the diagnostic report.
_source_details: dict = {}


def fetch(url, _diag_key=None):
    last_exc = None
    for attempt in range(1, HTTP['retry_attempts'] + 1):
        try:
            logger.info('Fetching [%d/%d]: %s', attempt, HTTP['retry_attempts'], url)
            r = SESSION.get(url, timeout=HTTP['timeout_seconds'])
            r.raise_for_status()
            if _diag_key:
                _source_details[_diag_key] = {'http_status': r.status_code}
            return BeautifulSoup(r.text, 'lxml')
        except requests.RequestException as e:
            last_exc = e
            logger.warning('Fetch failed attempt %d: %s', attempt, e)
            if attempt < HTTP['retry_attempts']:
                time.sleep(HTTP['retry_delay_seconds'])
    if _diag_key and last_exc is not None:
        resp = getattr(last_exc, 'response', None)
        _source_details[_diag_key] = {
            'http_status': resp.status_code if resp else None,
            'error': str(last_exc),
            'response_preview': resp.text[:500] if resp else None,
        }
    logger.error('All attempts failed for %s', url)
    return None


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
    ('09 May 2026', '17:30', 'Bristol Bears', 'Saracens', 'Gallagher Premiership'),
    ('29 May 2026', '19:45', 'Bristol Bears', 'Bath Rugby', 'Gallagher Premiership'),
]

# MAJOR EVENTS ONLY - events likely to cause parking disruption around Ashton Gate
KNOWN_AG_EVENTS = [
    ('25 Apr 2026', '14:15', 'Red Roses vs Wales - Womens Six Nations', 'Sport'),
    ('04 Jul 2026', '11:00', 'Bristol Tattoo Convention 2026', 'Convention'),
]

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

MINOR_EVENT_KEYWORDS = [
    'conference', 'seminar', 'workshop', 'training', 'networking',
    'apprenticeship', 'education', 'learning', 'skills',
    'digital', 'tech', 'itshowcase', 'nrg',
    'dinner', 'gala', 'awards', 'lunch',
    'market', 'card market', 'craft',
    'pitch', 'play on the pitch',
    'guitar show',
]

KNOWN_BCFC_FIXTURES = [
    # 2025/26 season ended. Add 2026/27 fixtures here when announced (typically June).
]

_TEAM_NAME_MAP = {
    'west brom': 'West Bromwich Albion',
    'west bromwich': 'West Bromwich Albion',
    'sheff utd': 'Sheffield United',
    'sheff wed': 'Sheffield Wednesday',
    'sheff wednesday': 'Sheffield Wednesday',
    'pne': 'Preston North End',
    'qpr': 'QPR',
    'man city': 'Manchester City',
    'man utd': 'Manchester United',
}


def _clean_team_name(name):
    name = re.sub(r'\s*(TBC|TBA|\d+[-–]\d+)\s*$', '', name.strip(), flags=re.I)
    return _TEAM_NAME_MAP.get(name.lower(), name)


def _extract_competition(text):
    t = text.lower()
    if 'fa cup' in t:
        return 'FA Cup'
    if 'carabao' in t or 'league cup' in t or 'efl cup' in t:
        return 'Carabao Cup (EFL Cup)'
    if 'play-off' in t or 'playoff' in t:
        return 'EFL Championship Play-Off'
    return 'EFL Championship'


def is_major_event(title):
    title_lower = title.lower()
    for kw in MINOR_EVENT_KEYWORDS:
        if kw in title_lower:
            return False
    for kw in MAJOR_EVENT_KEYWORDS:
        if kw in title_lower:
            return True
    return False


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
    now = datetime.now(tz=TZ)
    for date_str, time_str, home, away, comp in KNOWN_BEARS_FIXTURES:
        start = parse_dt(date_str, time_str)
        if not start or start <= now:
            continue
        end = start + timedelta(minutes=CONFIG['default_match_duration_minutes'])
        events.append(bears_event(home, away, comp, start, end))
    return events


def get_known_ashton_gate_events():
    events = []
    now = datetime.now(tz=TZ)
    for date_str, time_str, title, category in KNOWN_AG_EVENTS:
        start = parse_dt(date_str, time_str)
        if not start or start <= now:
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
    soup = fetch(AG_URL, _diag_key='ag_live')
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
    soup = fetch(PREM_URL, _diag_key='bears_live')
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


BBC_API_URL = (
    'https://www.bbc.co.uk/wc-data/container/sport-data-scores-fixtures'
    '?selectedEndDate={end}&selectedStartDate={start}'
    '&todayDate={today}&urn=urn%3Abbc%3Asportsdata%3Afootball%3Ateam%3Abristol-city'
    '&dataVars=selectedEndDate%3D{end}%26selectedStartDate%3D{start}'
)


def scrape_bcfc():
    events = []
    seen = set()
    now = datetime.now(tz=TZ)
    today_str = now.strftime('%Y-%m-%d')
    weeks_fetched = 0
    weeks_failed = 0
    last_error = None

    for week in range(16):
        start_dt = now + timedelta(weeks=week)
        end_dt = start_dt + timedelta(days=6)
        url = BBC_API_URL.format(
            start=start_dt.strftime('%Y-%m-%d'),
            end=end_dt.strftime('%Y-%m-%d'),
            today=today_str,
        )
        try:
            r = SESSION.get(url, timeout=HTTP['timeout_seconds'])
            r.raise_for_status()
            data = r.json()
            weeks_fetched += 1
        except Exception as e:
            resp = getattr(e, 'response', None)
            last_error = {
                'error': str(e),
                'http_status': getattr(resp, 'status_code', None),
                'response_preview': resp.text[:500] if resp else None,
            }
            weeks_failed += 1
            logger.warning('BBC API fetch failed (week %d): %s', week, e)
            continue

        for group in data.get('eventGroups', []):
            for sg in group.get('secondaryGroups', []):
                competition = _extract_competition(sg.get('displayLabel', ''))
                for ev in sg.get('events', []):
                    home = _clean_team_name(ev.get('home', {}).get('fullName', ''))
                    away = _clean_team_name(ev.get('away', {}).get('fullName', ''))
                    if home != 'Bristol City':
                        continue
                    start_iso = ev.get('startDateTime', '')
                    try:
                        dt = dateutil_parser.parse(start_iso)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=TZ)
                    except Exception:
                        continue
                    if dt <= now:
                        continue
                    title = 'Bristol City vs ' + away
                    uid = make_uid('bcfc-live', title, dt)
                    if uid in seen:
                        continue
                    seen.add(uid)
                    end = dt + timedelta(minutes=115)
                    local_dt = dt.astimezone(TZ)
                    desc = 'Football - %s\nBristol City vs %s\nKick-off: %s' % (
                        competition, away, local_dt.strftime('%A %d %B %Y %H:%M'))
                    events.append(CalendarEvent(
                        uid=uid, title=title, start=dt, end=end,
                        location=BEARS_VENUE, description=desc,
                        categories=['Football', 'Bristol City', competition],
                        url='https://www.bcfc.co.uk/fixtures/',
                    ))

    bcfc_diag = {'weeks_fetched': weeks_fetched, 'weeks_failed': weeks_failed}
    if last_error:
        bcfc_diag.update(last_error)
    _source_details['bcfc_live'] = bcfc_diag

    logger.info('BCFC live scrape: %d fixtures', len(events))
    return events


def _check_staleness():
    warnings = []
    now = datetime.now(tz=TZ)
    checks = [
        ('bears_known', KNOWN_BEARS_FIXTURES),
        ('ag_known', KNOWN_AG_EVENTS),
        ('bcfc_known', KNOWN_BCFC_FIXTURES),
    ]
    for key, fixtures in checks:
        future = [dt for row in fixtures if (dt := parse_dt(row[0])) and dt > now]
        if not future:
            warnings.append(
                f'{key}: all hardcoded entries have expired — update KNOWN_* list for new season'
            )
        elif (max(future) - now).days <= 30:
            days = (max(future) - now).days
            warnings.append(
                f'{key}: last entry expires in {days} day(s) — update list soon'
            )
    return warnings


PHANTOM_TITLES = re.compile(
    r'(?i)^(\[Ashton Gate\]\s+)?(january|february|march|april|may|june|july|august'
    r'|september|october|november|december)\s*[0-9]{4}$'
)


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
    global _source_details
    _source_details = {}

    logger.info('=' * 60)
    logger.info('Bristol Bears, Bristol City and Ashton Gate Calendar')
    logger.info('=' * 60)

    bears_live = scrape_bears()
    bears_known = get_known_fixtures()
    ag_live = scrape_ashton_gate()
    ag_known = get_known_ashton_gate_events()
    bcfc_live = scrape_bcfc()
    bcfc_known = get_known_bcfc_fixtures()

    sources = {
        'bears_live': {'events': len(bears_live), **_source_details.get('bears_live', {})},
        'bears_known': {'events': len(bears_known)},
        'ag_live': {'events': len(ag_live), **_source_details.get('ag_live', {})},
        'ag_known': {'events': len(ag_known)},
        'bcfc_live': {'events': len(bcfc_live), **_source_details.get('bcfc_live', {})},
        'bcfc_known': {'events': len(bcfc_known)},
    }

    warnings = []
    for key in ('bears_live', 'ag_live', 'bcfc_live'):
        if sources[key]['events'] == 0:
            warnings.append(f'{key} returned 0 events — possible scraper failure or end of season')
        if sources[key].get('error'):
            warnings.append(f'{key} HTTP error: {sources[key]["error"]}')

    stale_warnings = _check_staleness()

    all_events = merge([bears_live, bears_known, ag_live, ag_known, bcfc_live, bcfc_known])
    for ev in all_events:
        logger.info('[%s] %s', ev.start.strftime('%Y-%m-%d %H:%M'), ev.title)

    live_zeros = sum(1 for k in ('bears_live', 'ag_live', 'bcfc_live') if sources[k]['events'] == 0)
    if live_zeros == 3:
        status = 'failed'
    elif warnings or stale_warnings:
        status = 'degraded'
    else:
        status = 'ok'

    diag = {
        'sources': sources,
        'warnings': warnings,
        'stale_warnings': stale_warnings,
        'status': status,
        'total_events': len(all_events),
    }

    return all_events, diag


if __name__ == '__main__':
    events, _ = run()
    print('Scraper complete. %d events found.' % len(events))
