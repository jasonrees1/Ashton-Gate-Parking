# Bristol Bears & Ashton Gate Calendar

An automated system that scrapes Bristol Bears rugby fixtures and Ashton Gate Stadium events, then generates a combined `.ics` calendar file — updated daily via GitHub Actions.

## 📅 Subscribe to the Calendar

Once deployed, your calendar feed will be at:

```
https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/calendar/bristol_bears_and_ashton_gate.ics
```

Subscribe to this URL in:
- **Apple Calendar**: File → New Calendar Subscription → paste URL
- **Google Calendar**: Other Calendars → From URL → paste URL
- **Outlook**: Add calendar → From internet → paste URL

The calendar auto-refreshes every hour (or when GitHub Actions runs daily).

---

## 📂 Project Structure

```
bristol-bears-calendar/
├── .github/
│   └── workflows/
│       └── update.yml          # Daily GitHub Actions workflow
├── calendar/
│   └── bristol_bears_and_ashton_gate.ics   # Generated calendar (committed)
├── logs/
│   └── scraper.log             # Rotating log file (not committed)
├── config.json                 # All configuration: URLs, paths, logging
├── scraper.py                  # Data scraper (Premiership Rugby + Ashton Gate)
├── ics_generator.py            # Pure-Python RFC 5545 ICS generator
├── main.py                     # Entry point — runs scraper + generator
├── test_calendar.py            # 42-test test suite
├── requirements.txt            # Python dependencies
├── .gitignore
└── README.md
```

---

## 🔧 Setup

### 1. Fork / Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/bristol-bears-calendar.git
cd bristol-bears-calendar
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

**Dependencies:**
| Package | Purpose |
|---|---|
| `requests` | HTTP scraping |
| `beautifulsoup4` | HTML parsing |
| `lxml` | Fast HTML parser backend |
| `python-dateutil` | Robust date/time parsing |

> Note: `ics_generator.py` is a pure-Python RFC 5545 implementation — **no icalendar library needed**.

### 3. Run Locally

```bash
# Normal run — scrapes and generates ICS
python main.py

# Dry run — scrape only, don't write file
python main.py --dry-run

# Run + verify the output ICS
python main.py --verify

# Custom output path
python main.py --output /path/to/output.ics
```

### 4. Run Tests

```bash
python test_calendar.py
```

All 42 tests should pass. Tests cover:
- Date/time parsing (8 tests)
- UID generation (4 tests)
- Known Bristol Bears fixtures (6 tests)
- Known Ashton Gate events (3 tests)
- Deduplication logic (4 tests)
- ICS generation & RFC 5545 compliance (10 tests)
- Competition extraction (3 tests)
- Venue lookup (2 tests)
- End-to-end pipeline (1 test)

---

## ⚙️ GitHub Actions Workflow

The workflow (`.github/workflows/update.yml`) runs **every day at 06:00 UTC** (07:00 BST).

It also runs:
- On every push to `main` that changes a Python or config file
- Manually via the GitHub Actions UI ("Run workflow" button)

### What the workflow does:

1. Checks out the repository
2. Sets up Python 3.12 with pip caching
3. Installs dependencies
4. Creates `calendar/` and `logs/` directories
5. Runs `python main.py --verify`
6. Validates the ICS structure
7. Prints an event summary
8. Commits and pushes the updated `.ics` if it changed
9. Uploads the ICS as a workflow artifact (kept 30 days)

### Required Permissions

The workflow needs write access to push the calendar file. This is handled via `permissions: contents: write` in the workflow YAML — no secrets required.

### Manual Trigger

Go to **Actions → Update Bristol Bears Calendar → Run workflow**.

You can tick "Dry run" to test without committing.

---

## 📊 Data Sources

### Decision: Why these sources?

| Source | Decision | Reason |
|---|---|---|
| **Premiership Rugby** (premiershiprugby.com) | ✅ **Primary** | Official Premiership data, public HTML, no login, stable structure |
| **Ultimate Rugby** (ultimaterugby.com) | ✅ **Fallback** | Covers all competitions, link-based URL parsing is resilient |
| **Bristol Bears official** (bristolbearsrugby.com) | ❌ Rejected | Requires login to view full fixture list |
| **API-Football** | ❌ Rejected | Rugby Union / Premiership coverage is limited; JSON parsing adds fragility |
| **Ashton Gate Stadium** (ashtongatestadium.co.uk) | ✅ **Primary** | Official source, WordPress site, structured event markup |

### Resilience Strategy

The scraper uses a **3-layer fallback** for fixtures:

1. **Live scrape** — Premiership Rugby website (structured HTML cards)
2. **Fallback scrape** — Ultimate Rugby (URL-based parsing)
3. **Hardcoded baseline** — Known fixtures compiled from official sources

For Ashton Gate events:

1. **Live scrape** — WordPress event articles (tribe events or generic)
2. **Text fallback** — Parse the page's text content by date headers
3. **Hardcoded baseline** — Known events compiled from official sources

This means **the calendar never goes empty** even if all scraping fails.

---

## 🗓️ What's in the Calendar

### Bristol Bears Fixtures
- All Gallagher Premiership matches
- Premiership Rugby Cup fixtures
- Investec Champions Cup fixtures
- Home matches marked with 🏠 in description
- Full venue addresses for away matches
- 110-minute duration (80min + warm-up + half-time)
- Categories: `Rugby`, `Bristol Bears`, `<Competition Name>`

### Ashton Gate Events
- Concerts and entertainment
- Sports events (non-rugby)
- Community and corporate events
- All prefixed with `[Ashton Gate]` in title
- Categories: `Ashton Gate`, `Stadium Event`, `<Type>`

---

## 🔍 Configuration

Edit `config.json` to customise behaviour:

```json
{
  "sources": {
    "bristol_bears": {
      "primary": { "url": "https://www.premiershiprugby.com/clubs/bristol-bears/fixtures-results" },
      "fallback": { "url": "https://www.ultimaterugby.com/bristol/matches" }
    },
    "ashton_gate": {
      "primary": { "url": "https://www.ashtongatestadium.co.uk/whatson/" }
    }
  },
  "output": {
    "ics_file": "calendar/bristol_bears_and_ashton_gate.ics",
    "calendar_name": "Bristol Bears & Ashton Gate Events"
  },
  "timezone": "Europe/London",
  "default_match_duration_minutes": 110,
  "default_event_duration_minutes": 120,
  "logging": {
    "level": "INFO",
    "file": "logs/scraper.log"
  },
  "http": {
    "timeout_seconds": 30,
    "retry_attempts": 3,
    "retry_delay_seconds": 5
  }
}
```

---

## 🛠️ Updating Hardcoded Fixtures

When new fixtures are announced, update `KNOWN_FIXTURES` in `scraper.py`:

```python
KNOWN_FIXTURES = [
    # (date_str, time_str, home_team, away_team, competition)
    ("17 Apr 2026", "19:45", "Bristol Bears", "Gloucester Rugby", "Gallagher Premiership"),
    # Add new rows here ...
]
```

Similarly for Ashton Gate events, update `KNOWN_ASHTON_GATE_EVENTS`.

---

## 🐛 Troubleshooting

**Calendar not updating?**
- Check the Actions tab for failed runs
- The workflow only commits if the calendar changed
- Manual trigger: Actions → Run workflow

**ICS not loading in my calendar app?**
- Ensure you're using the raw GitHub URL (with `/raw/` in it)
- Apple Calendar needs `webcal://` — replace `https://` with `webcal://`

**Scraper getting blocked?**
- The scraper uses a real browser `User-Agent`
- Retry logic is built in (3 attempts with 5s delay)
- If sites block GitHub Actions IPs, the hardcoded baseline will hold

**Want to add more events?**
- Ashton Gate events: update `KNOWN_ASHTON_GATE_EVENTS` in `scraper.py`
- Bristol Bears: update `KNOWN_FIXTURES`

---

## 📄 ICS Format Reference

The generated `.ics` is fully RFC 5545 compliant:

```
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Bristol Bears Calendar//Bristol Bears & Ashton Gate//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
X-WR-CALNAME:Bristol Bears & Ashton Gate Events
X-WR-TIMEZONE:Europe/London
BEGIN:VTIMEZONE
  TZID:Europe/London
  ... (BST/GMT rules)
END:VTIMEZONE
BEGIN:VEVENT
  UID:known-bristol-bears-vs-saracens-20260509T150000@bristol-bears-calendar
  DTSTART;TZID=Europe/London:20260509T150000
  DTEND;TZID=Europe/London:20260509T171000
  SUMMARY:Bristol Bears vs Saracens
  LOCATION:Ashton Gate Stadium\, Ashton Road\, Bristol\, BS3 2EJ
  DESCRIPTION:🏉 Gallagher Premiership\n\nBristol Bears vs Saracens ...
  CATEGORIES:Rugby,Bristol Bears,Gallagher Premiership
  STATUS:CONFIRMED
END:VEVENT
...
END:VCALENDAR
```

---

## 📝 Licence

MIT — free to use, modify, and share.
