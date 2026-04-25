#!/usr/bin/env python3
"""
ICS Calendar Generator — Pure Python RFC 5545 Implementation
============================================================
No external dependencies beyond stdlib. Fully RFC 5545 compliant.
"""

import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from core import TZ, CONFIG

logger = logging.getLogger("bristol_calendar")

PRODID = "-//Bristol Bears Calendar//Bristol Bears & Ashton Gate//EN"

VTIMEZONE_EUROPE_LONDON = (
    "BEGIN:VTIMEZONE\r\n"
    "TZID:Europe/London\r\n"
    "X-LIC-LOCATION:Europe/London\r\n"
    "BEGIN:DAYLIGHT\r\n"
    "TZOFFSETFROM:+0000\r\n"
    "TZOFFSETTO:+0100\r\n"
    "TZNAME:BST\r\n"
    "DTSTART:19700329T010000\r\n"
    "RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=3\r\n"
    "END:DAYLIGHT\r\n"
    "BEGIN:STANDARD\r\n"
    "TZOFFSETFROM:+0100\r\n"
    "TZOFFSETTO:+0000\r\n"
    "TZNAME:GMT\r\n"
    "DTSTART:19701025T020000\r\n"
    "RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10\r\n"
    "END:STANDARD\r\n"
    "END:VTIMEZONE\r\n"
)


def _escape(text: str) -> str:
    """Escape special chars per RFC 5545 §3.3.11."""
    text = str(text)
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
    return text


def _fold(line: str) -> str:
    """RFC 5545 §3.1 line folding at 75 octets."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line + "\r\n"
    result = []
    buf = b""
    for char in line:
        cb = char.encode("utf-8")
        if len(buf) + len(cb) > 75:
            result.append(buf.decode("utf-8") + "\r\n")
            buf = b" " + cb
        else:
            buf += cb
    if buf:
        result.append(buf.decode("utf-8") + "\r\n")
    return "".join(result)


def _prop(name: str, value: str, params: dict = None) -> str:
    if params:
        pstr = ";".join(f"{k}={v}" for k, v in params.items())
        return _fold(f"{name};{pstr}:{value}")
    return _fold(f"{name}:{value}")


def _fmt_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    else:
        dt = dt.astimezone(TZ)
    return dt.strftime("%Y%m%dT%H%M%S")


def _fmt_utc(dt: datetime) -> str:
    utc = dt.astimezone(timezone.utc)
    return utc.strftime("%Y%m%dT%H%M%SZ")


def generate_ics(events: list, output_path: str = None) -> str:
    """Generate a valid RFC 5545 ICS string from CalendarEvent objects."""
    if not events:
        raise ValueError("Cannot generate ICS with zero events")

    now_utc = datetime.now(timezone.utc)
    dtstamp = _fmt_utc(now_utc)

    out = []
    out.append("BEGIN:VCALENDAR\r\n")
    out.append(_prop("VERSION", "2.0"))
    out.append(_prop("PRODID", PRODID))
    out.append(_prop("CALSCALE", "GREGORIAN"))
    out.append(_prop("METHOD", "PUBLISH"))
    out.append(_prop("X-WR-CALNAME", _escape(CONFIG["output"]["calendar_name"])))
    out.append(_prop("X-WR-CALDESC", _escape(CONFIG["output"]["calendar_description"])))
    out.append(_prop("X-WR-TIMEZONE", "Europe/London"))
    out.append(_prop("X-PUBLISHED-TTL", "PT1H"))
    out.append(VTIMEZONE_EUROPE_LONDON)

    for ev in events:
        out.append("BEGIN:VEVENT\r\n")
        out.append(_prop("UID", ev.uid))
        out.append(_prop("DTSTAMP", dtstamp))
        out.append(_prop("DTSTART", _fmt_dt(ev.start), {"TZID": "Europe/London"}))
        out.append(_prop("DTEND",   _fmt_dt(ev.end),   {"TZID": "Europe/London"}))
        out.append(_prop("SUMMARY", _escape(ev.title)))
        if ev.description:
            out.append(_prop("DESCRIPTION", _escape(ev.description)))
        if ev.location:
            out.append(_prop("LOCATION", _escape(ev.location)))
        if ev.url:
            out.append(_prop("URL", ev.url))
        if ev.categories:
            cats = [c for c in ev.categories if c]
            if cats:
                out.append(_prop("CATEGORIES", ",".join(_escape(c) for c in cats)))
        status = ev.status if ev.status in ("CONFIRMED", "TENTATIVE", "CANCELLED") else "CONFIRMED"
        out.append(_prop("STATUS", status))
        out.append(_prop("SEQUENCE", "0"))
        out.append("END:VEVENT\r\n")

    out.append("END:VCALENDAR\r\n")
    ics_str = "".join(out)

    _validate_ics(ics_str, len(events))

    if output_path:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(ics_str, encoding="utf-8")
        logger.info(f"ICS written: {p} ({p.stat().st_size} bytes, {len(events)} events)")

    return ics_str


def _validate_ics(ics: str, expected: int):
    errors = []
    for tag in ("BEGIN:VCALENDAR", "END:VCALENDAR", "VERSION:2.0", "PRODID:", "BEGIN:VTIMEZONE"):
        if tag not in ics:
            errors.append(f"Missing {tag}")
    n_events = ics.count("BEGIN:VEVENT")
    if n_events != expected:
        errors.append(f"Event count: expected {expected}, got {n_events}")
    # VTIMEZONE block contains 2 DTSTART lines (DAYLIGHT + STANDARD)
    if ics.count("DTSTART") != expected + 2:
        errors.append(f"DTSTART count mismatch: got {ics.count('DTSTART')}, expected {expected + 2} (events + 2 from VTIMEZONE)")
    if errors:
        for e in errors:
            logger.error(f"ICS validation: {e}")
        raise ValueError(f"ICS invalid: {'; '.join(errors)}")
    logger.info(f"ICS validation passed ✓ ({n_events} events)")
