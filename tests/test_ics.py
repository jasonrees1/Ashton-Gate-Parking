"""
Step 5: Tests for generate_ics(), _escape(), _fold(), and _fmt_dt().
Includes regression test for the UTC→local timezone conversion bug.
"""

import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ics_generator import generate_ics, _escape, _fold, _fmt_dt
from tests.fixtures import make_event, FUTURE_BASE

TZ = ZoneInfo("Europe/London")


class TestEscape(unittest.TestCase):

    def test_comma_escaped(self):
        self.assertIn("\\,", _escape("hello, world"))

    def test_semicolon_escaped(self):
        self.assertIn("\\;", _escape("a;b"))

    def test_backslash_escaped(self):
        self.assertIn("\\\\", _escape("a\\b"))

    def test_newline_escaped(self):
        result = _escape("line1\nline2")
        self.assertIn("\\n", result)
        self.assertNotIn("\n", result)

    def test_plain_text_unchanged(self):
        self.assertEqual(_escape("Hello World"), "Hello World")


class TestFold(unittest.TestCase):

    def test_short_line_not_folded(self):
        line = "A" * 50
        result = _fold(line)
        self.assertEqual(result, line + "\r\n")

    def test_long_line_folded(self):
        line = "X" * 100
        result = _fold(line)
        self.assertIn("\r\n ", result)  # folded continuation starts with space

    def test_all_output_lines_within_75_bytes(self):
        line = "DESCRIPTION:" + "A" * 200
        result = _fold(line)
        for raw_line in result.split("\r\n"):
            if raw_line:
                self.assertLessEqual(len(raw_line.encode("utf-8")), 75)

    def test_folded_output_ends_with_crlf(self):
        result = _fold("Hello")
        self.assertTrue(result.endswith("\r\n"))


class TestFmtDt(unittest.TestCase):
    """
    Regression tests for the UTC→local timezone conversion bug.
    _fmt_dt must convert UTC datetimes to Europe/London local time,
    not naively format the UTC hour as if it were local.
    """

    def test_naive_datetime_gets_local_tz(self):
        naive = datetime(2099, 6, 15, 15, 0, 0)  # no tzinfo
        result = _fmt_dt(naive)
        self.assertEqual(result, "20990615T150000")

    def test_utc_datetime_converted_to_bst(self):
        # 11:30 UTC in June (BST = UTC+1) → must render as 12:30
        utc_dt = datetime(2099, 6, 15, 11, 30, 0, tzinfo=timezone.utc)
        result = _fmt_dt(utc_dt)
        self.assertEqual(result, "20990615T123000")

    def test_utc_datetime_converted_to_gmt(self):
        # 14:00 UTC in January (GMT = UTC+0) → stays 14:00
        utc_dt = datetime(2099, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        result = _fmt_dt(utc_dt)
        self.assertEqual(result, "20990115T140000")

    def test_already_local_datetime_unchanged(self):
        # A datetime already in Europe/London stays as-is
        local_dt = datetime(2099, 6, 15, 15, 0, 0, tzinfo=TZ)
        result = _fmt_dt(local_dt)
        self.assertEqual(result, "20990615T150000")


class TestGenerateIcs(unittest.TestCase):

    def _events(self, n=2):
        return [make_event(f"Event {i}", days_offset=i * 10) for i in range(n)]

    # ── Structure ──────────────────────────────────────────────────────────

    def test_contains_vcalendar_wrapper(self):
        ics = generate_ics(self._events())
        self.assertIn("BEGIN:VCALENDAR", ics)
        self.assertIn("END:VCALENDAR", ics)

    def test_contains_version(self):
        self.assertIn("VERSION:2.0", generate_ics(self._events()))

    def test_contains_vtimezone(self):
        self.assertIn("BEGIN:VTIMEZONE", generate_ics(self._events()))

    def test_contains_europe_london(self):
        self.assertIn("Europe/London", generate_ics(self._events()))

    def test_empty_list_raises(self):
        with self.assertRaises(ValueError):
            generate_ics([])

    # ── Event count ────────────────────────────────────────────────────────

    def test_correct_vevent_count(self):
        events = self._events(3)
        ics = generate_ics(events)
        self.assertEqual(ics.count("BEGIN:VEVENT"), 3)

    def test_uid_count_matches_events(self):
        events = self._events(3)
        ics = generate_ics(events)
        self.assertEqual(len(re.findall(r"^UID:", ics, re.MULTILINE)), 3)

    def test_dtstart_count_events_plus_vtimezone(self):
        # VTIMEZONE block has 2 DTSTART lines (DAYLIGHT + STANDARD)
        events = self._events(3)
        ics = generate_ics(events)
        self.assertEqual(ics.count("DTSTART"), 3 + 2)

    # ── Content ────────────────────────────────────────────────────────────

    def test_summary_present(self):
        ev = make_event("Bristol Bears vs Saracens")
        ics = generate_ics([ev])
        self.assertIn("Bristol Bears vs Saracens", ics)

    def test_location_present(self):
        ev = make_event(location="Ashton Gate Stadium, Bristol")
        ics = generate_ics([ev])
        self.assertIn("Ashton Gate", ics)

    def test_dtstart_uses_london_tzid(self):
        ev = make_event()
        ics = generate_ics([ev])
        self.assertIn("DTSTART;TZID=Europe/London:", ics)

    def test_dtstart_is_local_time_not_utc(self):
        # Event at 15:00 BST (local) — DTSTART must be T150000, not UTC
        ev = make_event()  # FUTURE_BASE is 15:00 BST
        ics = generate_ics([ev])
        self.assertIn("T150000", ics)

    def test_utc_source_time_localised_in_dtstart(self):
        # Simulate a BCFC event whose datetime came from BBC API in UTC
        # 11:30 UTC in June = 12:30 BST → DTSTART must be T123000
        from scraper import CalendarEvent, make_uid
        utc_start = datetime(2099, 6, 15, 11, 30, 0, tzinfo=timezone.utc)
        ev = CalendarEvent(
            uid=make_uid("test", "UTC Test", utc_start),
            title="UTC Test Event",
            start=utc_start,
            end=datetime(2099, 6, 15, 13, 25, 0, tzinfo=timezone.utc),
            location="Ashton Gate",
            categories=["Test"],
        )
        ics = generate_ics([ev])
        self.assertIn("DTSTART;TZID=Europe/London:20990615T123000", ics)

    # ── File output ────────────────────────────────────────────────────────

    def test_writes_to_file(self):
        events = self._events(1)
        with tempfile.NamedTemporaryFile(suffix=".ics", delete=False) as f:
            tmp = f.name
        try:
            generate_ics(events, tmp)
            content = Path(tmp).read_text(encoding="utf-8")
            self.assertIn("BEGIN:VCALENDAR", content)
        finally:
            Path(tmp).unlink(missing_ok=True)

    def test_returns_string_without_path(self):
        result = generate_ics(self._events(1))
        self.assertIsInstance(result, str)


if __name__ == "__main__":
    unittest.main()
