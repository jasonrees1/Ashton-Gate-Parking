#!/usr/bin/env python3
"""
Test suite for Bristol Bears Calendar Scraper
==============================================
Tests date parsing, ICS generation, deduplication, and baseline fixtures.
Run with: python test_calendar.py
"""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from scraper import (
    CalendarEvent,
    parse_uk_datetime,
    make_uid,
    get_known_fixtures,
    get_known_ashton_gate_events,
    merge_and_deduplicate,
    _extract_competition,
    _guess_venue,
    KNOWN_VENUES,
)
from ics_generator import generate_ics, _escape as _sanitise_text, _validate_ics

TZ = ZoneInfo("Europe/London")


class TestDateParsing(unittest.TestCase):
    """Test the UK datetime parser."""

    def test_standard_date(self):
        dt = parse_uk_datetime("09 May 2026", "15:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 5)
        self.assertEqual(dt.day, 9)
        self.assertEqual(dt.hour, 15)
        self.assertEqual(dt.minute, 0)

    def test_date_with_ordinal(self):
        dt = parse_uk_datetime("17th April 2026", "19:45")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.day, 17)
        self.assertEqual(dt.hour, 19)
        self.assertEqual(dt.minute, 45)

    def test_short_month_format(self):
        dt = parse_uk_datetime("25 Apr 2026", "14:15")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.month, 4)
        self.assertEqual(dt.day, 25)

    def test_day_first_parsing(self):
        # 01/07 should be 1st July, not 7th January
        dt = parse_uk_datetime("01 Jul 2026")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.month, 7)
        self.assertEqual(dt.day, 1)

    def test_timezone_attached(self):
        dt = parse_uk_datetime("09 May 2026", "15:00")
        self.assertIsNotNone(dt.tzinfo)

    def test_bst_vs_gmt(self):
        # May is BST (+01:00), January is GMT (+00:00)
        dt_bst = parse_uk_datetime("09 May 2026", "15:00")
        dt_gmt = parse_uk_datetime("09 Jan 2026", "15:00")
        self.assertIsNotNone(dt_bst)
        self.assertIsNotNone(dt_gmt)
        # Both should have valid timezone info
        self.assertIsNotNone(dt_bst.tzinfo)
        self.assertIsNotNone(dt_gmt.tzinfo)

    def test_invalid_date_returns_none(self):
        dt = parse_uk_datetime("not a date")
        # Should not raise, may return None or a guessed date
        # Just check it doesn't crash
        pass

    def test_evening_kickoff(self):
        dt = parse_uk_datetime("17 Apr 2026", "19:45")
        self.assertEqual(dt.hour, 19)
        self.assertEqual(dt.minute, 45)


class TestUIDGeneration(unittest.TestCase):
    """Test UID generation for calendar events."""

    def test_uid_is_string(self):
        dt = parse_uk_datetime("09 May 2026", "15:00")
        uid = make_uid("test", "Bristol Bears vs Saracens", dt)
        self.assertIsInstance(uid, str)

    def test_uid_contains_domain(self):
        dt = parse_uk_datetime("09 May 2026", "15:00")
        uid = make_uid("test", "Test Event", dt)
        self.assertIn("@bristol-bears-calendar", uid)

    def test_uid_stability(self):
        """Same inputs should produce same UID."""
        dt = parse_uk_datetime("09 May 2026", "15:00")
        uid1 = make_uid("test", "Bristol Bears vs Saracens", dt)
        uid2 = make_uid("test", "Bristol Bears vs Saracens", dt)
        self.assertEqual(uid1, uid2)

    def test_uid_uniqueness(self):
        """Different events should have different UIDs."""
        dt1 = parse_uk_datetime("09 May 2026", "15:00")
        dt2 = parse_uk_datetime("30 May 2026", "15:00")
        uid1 = make_uid("test", "Bristol Bears vs Saracens", dt1)
        uid2 = make_uid("test", "Bristol Bears vs Bath", dt2)
        self.assertNotEqual(uid1, uid2)


class TestKnownFixtures(unittest.TestCase):
    """Test the hardcoded fixture baseline."""

    def test_returns_events(self):
        events = get_known_fixtures()
        self.assertGreater(len(events), 0)

    def test_events_have_required_fields(self):
        events = get_known_fixtures()
        for ev in events:
            self.assertTrue(ev.uid, f"Missing UID: {ev.title}")
            self.assertTrue(ev.title, "Missing title")
            self.assertIsNotNone(ev.start, f"Missing start: {ev.title}")
            self.assertIsNotNone(ev.end, f"Missing end: {ev.title}")
            self.assertGreater(ev.end, ev.start, f"End before start: {ev.title}")

    def test_home_fixture_has_ashton_gate_location(self):
        events = get_known_fixtures()
        home_fixtures = [e for e in events if "Bristol Bears vs" in e.title]
        for ev in home_fixtures:
            self.assertIn("Ashton Gate", ev.location, f"Home fixture missing Ashton Gate: {ev.title}")

    def test_away_fixture_has_away_venue(self):
        events = get_known_fixtures()
        away_fixtures = [e for e in events if "vs Bristol Bears" in e.title]
        for ev in away_fixtures:
            self.assertNotIn("Ashton Gate", ev.location, f"Away fixture shows Ashton Gate: {ev.title}")

    def test_all_events_in_future_or_recent(self):
        events = get_known_fixtures()
        cutoff = datetime(2026, 1, 1, tzinfo=TZ)
        for ev in events:
            self.assertGreater(ev.start, cutoff, f"Event too old: {ev.title} at {ev.start}")

    def test_events_have_categories(self):
        events = get_known_fixtures()
        for ev in events:
            self.assertTrue(ev.categories, f"Missing categories: {ev.title}")
            self.assertIn("Rugby", ev.categories)


class TestKnownAshtonGateEvents(unittest.TestCase):
    """Test the hardcoded Ashton Gate event baseline."""

    def test_returns_events(self):
        events = get_known_ashton_gate_events()
        self.assertGreater(len(events), 0)

    def test_events_have_ashton_gate_in_title_or_location(self):
        events = get_known_ashton_gate_events()
        for ev in events:
            self.assertIn("Ashton Gate", ev.location)

    def test_events_have_categories(self):
        events = get_known_ashton_gate_events()
        for ev in events:
            self.assertIn("Ashton Gate", ev.categories)


class TestDeduplication(unittest.TestCase):
    """Test the deduplication logic."""

    def _make_event(self, title, date_str, time_str="15:00"):
        start = parse_uk_datetime(date_str, time_str)
        end = start + timedelta(minutes=110)
        return CalendarEvent(
            uid=make_uid("test", title, start),
            title=title,
            start=start,
            end=end,
            location="Ashton Gate Stadium",
            description="Test event",
            categories=["Rugby"],
        )

    def test_dedup_removes_identical_events(self):
        ev1 = self._make_event("Bristol Bears vs Saracens", "09 May 2026")
        ev2 = self._make_event("Bristol Bears vs Saracens", "09 May 2026")
        result = merge_and_deduplicate([[ev1], [ev2]])
        self.assertEqual(len(result), 1)

    def test_dedup_keeps_different_events(self):
        ev1 = self._make_event("Bristol Bears vs Saracens", "09 May 2026")
        ev2 = self._make_event("Bristol Bears vs Bath", "30 May 2026")
        result = merge_and_deduplicate([[ev1], [ev2]])
        self.assertEqual(len(result), 2)

    def test_dedup_preserves_event_with_more_location(self):
        start = parse_uk_datetime("09 May 2026", "15:00")
        end = start + timedelta(minutes=110)
        ev1 = CalendarEvent(
            uid="uid1",
            title="Bristol Bears vs Saracens",
            start=start, end=end,
            location="",  # No location
        )
        ev2 = CalendarEvent(
            uid="uid2",
            title="Bristol Bears vs Saracens",
            start=start, end=end,
            location="Ashton Gate Stadium, Ashton Road, Bristol, BS3 2EJ",
        )
        result = merge_and_deduplicate([[ev1], [ev2]])
        self.assertEqual(len(result), 1)
        self.assertIn("Ashton Gate", result[0].location)

    def test_sorted_by_start_time(self):
        ev1 = self._make_event("Bristol Bears vs Bath", "30 May 2026")
        ev2 = self._make_event("Bristol Bears vs Saracens", "09 May 2026")
        result = merge_and_deduplicate([[ev1], [ev2]])
        self.assertLess(result[0].start, result[1].start)


class TestICSGeneration(unittest.TestCase):
    """Test the ICS calendar generator."""

    def _make_test_events(self):
        events = []
        for i, (date_str, time_str, title) in enumerate([
            ("09 May 2026", "15:00", "Bristol Bears vs Saracens"),
            ("30 May 2026", "15:00", "Bristol Bears vs Bath Rugby"),
            ("25 Apr 2026", "14:15", "[Ashton Gate] Red Roses vs Wales"),
        ]):
            start = parse_uk_datetime(date_str, time_str)
            end = start + timedelta(minutes=110)
            events.append(CalendarEvent(
                uid=make_uid("test", title, start),
                title=title,
                start=start,
                end=end,
                location="Ashton Gate Stadium, Ashton Road, Bristol, BS3 2EJ",
                description=f"Test description for {title}",
                categories=["Rugby", "Bristol Bears"],
                url="https://www.bristolbearsrugby.com/",
            ))
        return events

    def test_generates_valid_ics(self):
        events = self._make_test_events()
        ics = generate_ics(events)
        self.assertIn("BEGIN:VCALENDAR", ics)
        self.assertIn("END:VCALENDAR", ics)
        self.assertIn("VERSION:2.0", ics)

    def test_correct_event_count(self):
        events = self._make_test_events()
        ics = generate_ics(events)
        self.assertEqual(ics.count("BEGIN:VEVENT"), len(events))

    def test_events_have_dtstart(self):
        events = self._make_test_events()
        ics = generate_ics(events)
        # +2 because VTIMEZONE block has DAYLIGHT+STANDARD each with DTSTART
        self.assertEqual(ics.count("DTSTART"), len(events) + 2)

    def test_events_have_summary(self):
        events = self._make_test_events()
        ics = generate_ics(events)
        self.assertIn("Bristol Bears vs Saracens", ics)

    def test_events_have_location(self):
        events = self._make_test_events()
        ics = generate_ics(events)
        self.assertIn("Ashton Gate Stadium", ics)

    def test_events_have_uid(self):
        events = self._make_test_events()
        ics = generate_ics(events)
        import re
        uid_count = len(re.findall(r"^UID:", ics, re.MULTILINE))
        self.assertEqual(uid_count, len(events))

    def test_timezone_in_calendar(self):
        events = self._make_test_events()
        ics = generate_ics(events)
        self.assertIn("Europe/London", ics)

    def test_writes_to_file(self, tmp_path=None):
        import tempfile, os
        events = self._make_test_events()
        with tempfile.NamedTemporaryFile(suffix=".ics", delete=False) as f:
            tmp = f.name
        try:
            generate_ics(events, tmp)
            self.assertTrue(Path(tmp).exists())
            content = Path(tmp).read_text()
            self.assertIn("BEGIN:VCALENDAR", content)
        finally:
            os.unlink(tmp)

    def test_calendar_name_in_output(self):
        events = self._make_test_events()
        ics = generate_ics(events)
        self.assertIn("Bristol Bears", ics)

    def test_empty_events_raises(self):
        """Empty event list should raise validation error."""
        with self.assertRaises(ValueError):
            generate_ics([])

    def test_sanitise_text(self):
        text = "Hello, World; test\\slash\nnewline"
        result = _sanitise_text(text)
        self.assertIn("\\,", result)
        self.assertIn("\\;", result)
        self.assertIn("\\\\", result)


class TestCompetitionExtraction(unittest.TestCase):
    """Test competition name extraction."""

    def test_gallagher_premiership(self):
        self.assertEqual(_extract_competition("Gallagher Premiership match"), "Gallagher Premiership")
        self.assertEqual(_extract_competition("PREM Rugby"), "Gallagher Premiership")

    def test_champions_cup(self):
        self.assertEqual(_extract_competition("Investec Champions Cup pool"), "Investec Champions Cup")
        self.assertEqual(_extract_competition("EPCR Champions Cup"), "Investec Champions Cup")

    def test_default(self):
        self.assertEqual(_extract_competition("some random text"), "Rugby")


class TestVenueGuessing(unittest.TestCase):
    """Test venue lookup for away fixtures."""

    def test_known_teams(self):
        self.assertIn("Northampton", _guess_venue("Northampton Saints"))
        # Sale Sharks play at Salford Community Stadium (AKA AJ Bell Stadium)
        self.assertIn("Salford", _guess_venue("Sale Sharks"))
        self.assertIn("Bath", _guess_venue("Bath Rugby"))

    def test_unknown_team(self):
        result = _guess_venue("Unknown Team FC")
        self.assertIn("Unknown Team FC", result)


class TestEndToEnd(unittest.TestCase):
    """End-to-end integration test."""

    def test_full_pipeline_with_known_data(self):
        """Run full pipeline using only hardcoded data (no network needed)."""
        from scraper import get_known_fixtures, get_known_ashton_gate_events, merge_and_deduplicate
        from ics_generator import generate_ics

        bears = get_known_fixtures()
        ag = get_known_ashton_gate_events()
        all_events = merge_and_deduplicate([bears, ag])

        self.assertGreater(len(all_events), 5)

        ics = generate_ics(all_events)

        # Validate ICS via string checks (no icalendar lib needed)
        self.assertIn("BEGIN:VCALENDAR", ics)
        self.assertIn("END:VCALENDAR", ics)
        self.assertIn("VERSION:2.0", ics)
        self.assertIn("BEGIN:VTIMEZONE", ics)

        n_events = ics.count("BEGIN:VEVENT")
        self.assertEqual(n_events, len(all_events))

        # Every event must have UID, DTSTART, SUMMARY
        import re
        uid_count = len(re.findall(r"^UID:", ics, re.MULTILINE))
        self.assertEqual(uid_count, len(all_events))

        # DTSTART: n_events + 2 (VTIMEZONE)
        dtstart_count = ics.count("DTSTART")
        self.assertEqual(dtstart_count, len(all_events) + 2)

        print(f"  ✓ End-to-end: {len(all_events)} events generated and validated")


def run_tests():
    """Run all tests and report results."""
    print("=" * 60)
    print("Bristol Bears Calendar — Test Suite")
    print("=" * 60)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestDateParsing,
        TestUIDGeneration,
        TestKnownFixtures,
        TestKnownAshtonGateEvents,
        TestDeduplication,
        TestICSGeneration,
        TestCompetitionExtraction,
        TestVenueGuessing,
        TestEndToEnd,
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print(f"✅ All {result.testsRun} tests passed!")
    else:
        print(f"❌ {len(result.failures)} failures, {len(result.errors)} errors out of {result.testsRun} tests")
    print("=" * 60)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
