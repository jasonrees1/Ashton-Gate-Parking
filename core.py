#!/usr/bin/env python3
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from dateutil import parser as dateutil_parser

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / 'config.json'

with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

TZ = ZoneInfo(CONFIG['timezone'])
BEARS_VENUE = 'Ashton Gate Stadium, Ashton Road, Bristol, BS3 2EJ'

logger = logging.getLogger('bristol_calendar')


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
