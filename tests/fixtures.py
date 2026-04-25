"""
Shared test fixtures for the Bristol Bears Calendar test suite.

All synthetic events use year 2099 so they never expire.
FROZEN_NOW is used when tests need to control "now" for fallback-filter logic.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import CalendarEvent, make_uid

TZ = ZoneInfo("Europe/London")

# Fixed "now" used when patching datetime — before any hardcoded season data
FROZEN_NOW = datetime(2026, 3, 1, 12, 0, 0, tzinfo=TZ)

# Base datetime for synthetic events — far future, never expires
FUTURE_BASE = datetime(2099, 6, 15, 15, 0, 0, tzinfo=TZ)


def make_event(
    title="Test Event",
    days_offset=0,
    uid=None,
    categories=None,
    location="Ashton Gate Stadium, Ashton Road, Bristol, BS3 2EJ",
    duration_mins=110,
):
    """Return a synthetic CalendarEvent anchored to FUTURE_BASE."""
    start = FUTURE_BASE + timedelta(days=days_offset)
    end = start + timedelta(minutes=duration_mins)
    return CalendarEvent(
        uid=uid or make_uid("test", title, start),
        title=title,
        start=start,
        end=end,
        location=location,
        description=f"Test description for {title}",
        categories=categories or ["Test"],
        url="https://example.com",
    )


def make_mock_response(json_data):
    """Return a mock requests.Response whose .json() yields json_data."""
    from unittest.mock import MagicMock
    mock = MagicMock()
    mock.raise_for_status.return_value = None
    mock.json.return_value = json_data
    return mock


# ── BBC Sport internal API snapshots ─────────────────────────────────────────

# Future HOME fixture — Bristol City at home
BBC_JSON_HOME = {
    "eventGroups": [{
        "displayLabel": "Sunday 15th June 2099",
        "secondaryGroups": [{
            "displayLabel": "Championship",
            "events": [{
                "home": {"fullName": "Bristol City"},
                "away": {"fullName": "Stoke City"},
                "startDateTime": "2099-06-15T11:30:00Z",
            }],
        }],
    }],
}

# Future AWAY fixture — Bristol City away (should be ignored by scraper)
BBC_JSON_AWAY = {
    "eventGroups": [{
        "displayLabel": "Sunday 15th June 2099",
        "secondaryGroups": [{
            "displayLabel": "Championship",
            "events": [{
                "home": {"fullName": "Swansea City"},
                "away": {"fullName": "Bristol City"},
                "startDateTime": "2099-06-15T11:30:00Z",
            }],
        }],
    }],
}

# PAST fixture — should be filtered out by scraper
BBC_JSON_PAST = {
    "eventGroups": [{
        "displayLabel": "Saturday 1st August 2020",
        "secondaryGroups": [{
            "displayLabel": "Championship",
            "events": [{
                "home": {"fullName": "Bristol City"},
                "away": {"fullName": "Watford"},
                "startDateTime": "2020-08-01T14:00:00Z",
            }],
        }],
    }],
}

# Empty response — no fixtures this week
BBC_JSON_EMPTY = {"eventGroups": []}

# ── Ashton Gate HTML snapshots ────────────────────────────────────────────────

# A single major event (tattoo convention → matches 'tattoo' keyword)
AG_HTML_MAJOR = """\
<html><body>
<article class="tribe-event">
  <h3>Bristol Tattoo Convention 2099</h3>
  <p>15 Jun 2099 11:00</p>
</article>
</body></html>
"""

# A minor event (seminar → matches minor keyword, must be excluded)
AG_HTML_MINOR = """\
<html><body>
<article class="tribe-event">
  <h3>Digital Business Seminar</h3>
  <p>15 Jun 2099 09:00</p>
</article>
</body></html>
"""

# An event with no title element — must not crash the scraper
AG_HTML_NO_TITLE = """\
<html><body>
<article class="tribe-event">
  <p>15 Jun 2099 09:00</p>
</article>
</body></html>
"""
