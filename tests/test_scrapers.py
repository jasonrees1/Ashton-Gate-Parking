"""
Step 6: Tests for scraper parsing logic and fallback data filtering.

Scraper tests mock SESSION.get / fetch so no network calls are made.
Fallback tests patch KNOWN_* lists + datetime.now so results are
time-independent — they won't rot as real dates pass.
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

from scraper import (
    scrape_bcfc,
    scrape_ashton_gate,
    get_known_fixtures,
    get_known_ashton_gate_events,
    get_known_bcfc_fixtures,
)
from tests.fixtures import (
    make_mock_response,
    BBC_JSON_HOME,
    BBC_JSON_AWAY,
    BBC_JSON_PAST,
    BBC_JSON_EMPTY,
    AG_HTML_MAJOR,
    AG_HTML_MINOR,
    AG_HTML_NO_TITLE,
    FROZEN_NOW,
)

TZ = ZoneInfo("Europe/London")


# ── scrape_bcfc() ─────────────────────────────────────────────────────────────

class TestScrapeBcfc(unittest.TestCase):

    def _run_with_json(self, json_data):
        """Run scrape_bcfc() with every BBC API week returning json_data."""
        with patch("scraper.SESSION") as mock_session:
            mock_session.get.return_value = make_mock_response(json_data)
            return scrape_bcfc()

    def test_home_fixture_included(self):
        events = self._run_with_json(BBC_JSON_HOME)
        self.assertEqual(len(events), 1)

    def test_home_fixture_title_format(self):
        events = self._run_with_json(BBC_JSON_HOME)
        self.assertEqual(events[0].title, "Bristol City vs Stoke City")

    def test_home_fixture_location_is_ashton_gate(self):
        events = self._run_with_json(BBC_JSON_HOME)
        self.assertIn("Ashton Gate", events[0].location)

    def test_home_fixture_categories_include_football(self):
        events = self._run_with_json(BBC_JSON_HOME)
        self.assertIn("Football", events[0].categories)

    def test_home_fixture_categories_include_bristol_city(self):
        events = self._run_with_json(BBC_JSON_HOME)
        self.assertIn("Bristol City", events[0].categories)

    def test_utc_kickoff_converted_to_bst_in_description(self):
        # BBC returns 11:30Z; in June BST = UTC+1, so description must say 12:30
        events = self._run_with_json(BBC_JSON_HOME)
        self.assertIn("12:30", events[0].description)

    def test_away_fixture_excluded(self):
        events = self._run_with_json(BBC_JSON_AWAY)
        self.assertEqual(len(events), 0)

    def test_past_fixture_excluded(self):
        events = self._run_with_json(BBC_JSON_PAST)
        self.assertEqual(len(events), 0)

    def test_empty_response_returns_empty_list(self):
        events = self._run_with_json(BBC_JSON_EMPTY)
        self.assertEqual(events, [])

    def test_api_error_handled_gracefully(self):
        with patch("scraper.SESSION") as mock_session:
            mock_session.get.side_effect = Exception("connection refused")
            events = scrape_bcfc()
        self.assertIsInstance(events, list)

    def test_no_duplicate_events_across_weeks(self):
        # Even if the same fixture appears in multiple weekly responses,
        # the UID-based dedup must prevent duplicates.
        events = self._run_with_json(BBC_JSON_HOME)
        uids = [e.uid for e in events]
        self.assertEqual(len(uids), len(set(uids)))


# ── scrape_ashton_gate() ──────────────────────────────────────────────────────

class TestScrapeAshtonGate(unittest.TestCase):

    def _run_with_html(self, html):
        soup = BeautifulSoup(html, "lxml")
        with patch("scraper.fetch", return_value=soup):
            return scrape_ashton_gate()

    def test_major_event_included(self):
        events = self._run_with_html(AG_HTML_MAJOR)
        self.assertEqual(len(events), 1)

    def test_major_event_title_prefixed(self):
        events = self._run_with_html(AG_HTML_MAJOR)
        self.assertTrue(events[0].title.startswith("[Ashton Gate]"))

    def test_major_event_location_is_ashton_gate(self):
        events = self._run_with_html(AG_HTML_MAJOR)
        self.assertIn("Ashton Gate", events[0].location)

    def test_minor_event_excluded(self):
        events = self._run_with_html(AG_HTML_MINOR)
        self.assertEqual(len(events), 0)

    def test_no_title_element_does_not_crash(self):
        try:
            self._run_with_html(AG_HTML_NO_TITLE)
        except Exception as e:
            self.fail(f"scrape_ashton_gate raised on missing title: {e}")

    def test_fetch_failure_returns_empty(self):
        with patch("scraper.fetch", return_value=None):
            events = scrape_ashton_gate()
        self.assertEqual(events, [])


# ── Fallback data filtering ───────────────────────────────────────────────────

class TestFallbackFiltering(unittest.TestCase):
    """
    Patch KNOWN_* lists with controlled synthetic data and freeze datetime.now.
    Tests that past events are excluded, future events included.
    Uses relative dates so tests never go stale.
    """

    def _past(self, days=10):
        return (FROZEN_NOW - timedelta(days=days)).strftime("%d %b %Y")

    def _future(self, days=10):
        return (FROZEN_NOW + timedelta(days=days)).strftime("%d %b %Y")

    def _patch_now(self):
        return patch("scraper.datetime")

    def _make_now_mock(self, mock_dt):
        mock_dt.now.return_value = FROZEN_NOW
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

    # ── get_known_fixtures() ───────────────────────────────────────────────

    def test_bears_past_event_filtered(self):
        synthetic = [
            (self._past(), "15:00", "Bristol Bears", "Past Team", "Gallagher Premiership"),
        ]
        with patch("scraper.KNOWN_BEARS_FIXTURES", synthetic), \
             patch("scraper.datetime") as mock_dt:
            self._make_now_mock(mock_dt)
            events = get_known_fixtures()
        self.assertEqual(len(events), 0)

    def test_bears_future_event_included(self):
        synthetic = [
            (self._future(), "15:00", "Bristol Bears", "Future Team", "Gallagher Premiership"),
        ]
        with patch("scraper.KNOWN_BEARS_FIXTURES", synthetic), \
             patch("scraper.datetime") as mock_dt:
            self._make_now_mock(mock_dt)
            events = get_known_fixtures()
        self.assertEqual(len(events), 1)
        self.assertIn("Future Team", events[0].title)

    def test_bears_mix_only_future_returned(self):
        synthetic = [
            (self._past(), "15:00", "Bristol Bears", "Past Team", "Gallagher Premiership"),
            (self._future(), "15:00", "Bristol Bears", "Future Team", "Gallagher Premiership"),
        ]
        with patch("scraper.KNOWN_BEARS_FIXTURES", synthetic), \
             patch("scraper.datetime") as mock_dt:
            self._make_now_mock(mock_dt)
            events = get_known_fixtures()
        self.assertEqual(len(events), 1)
        self.assertIn("Future Team", events[0].title)

    # ── get_known_ashton_gate_events() ─────────────────────────────────────

    def test_ag_past_event_filtered(self):
        synthetic = [(self._past(), "11:00", "Past Concert", "Concert")]
        with patch("scraper.KNOWN_AG_EVENTS", synthetic), \
             patch("scraper.datetime") as mock_dt:
            self._make_now_mock(mock_dt)
            events = get_known_ashton_gate_events()
        self.assertEqual(len(events), 0)

    def test_ag_future_event_included(self):
        synthetic = [(self._future(), "11:00", "Future Convention", "Convention")]
        with patch("scraper.KNOWN_AG_EVENTS", synthetic), \
             patch("scraper.datetime") as mock_dt:
            self._make_now_mock(mock_dt)
            events = get_known_ashton_gate_events()
        self.assertEqual(len(events), 1)
        self.assertIn("[Ashton Gate]", events[0].title)

    # ── get_known_bcfc_fixtures() ──────────────────────────────────────────

    def test_bcfc_past_event_filtered(self):
        synthetic = [(self._past(), "15:00", "Past FC", "EFL Championship")]
        with patch("scraper.KNOWN_BCFC_FIXTURES", synthetic), \
             patch("scraper.datetime") as mock_dt:
            self._make_now_mock(mock_dt)
            events = get_known_bcfc_fixtures()
        self.assertEqual(len(events), 0)

    def test_bcfc_future_event_included(self):
        synthetic = [(self._future(), "12:30", "Future City", "EFL Championship")]
        with patch("scraper.KNOWN_BCFC_FIXTURES", synthetic), \
             patch("scraper.datetime") as mock_dt:
            self._make_now_mock(mock_dt)
            events = get_known_bcfc_fixtures()
        self.assertEqual(len(events), 1)
        self.assertIn("Bristol City vs Future City", events[0].title)

    # ── Structural checks on returned events ──────────────────────────────

    def test_bears_events_have_required_fields(self):
        synthetic = [(self._future(), "15:00", "Bristol Bears", "Test FC", "Gallagher Premiership")]
        with patch("scraper.KNOWN_BEARS_FIXTURES", synthetic), \
             patch("scraper.datetime") as mock_dt:
            self._make_now_mock(mock_dt)
            events = get_known_fixtures()
        for ev in events:
            self.assertTrue(ev.uid)
            self.assertTrue(ev.title)
            self.assertIsNotNone(ev.start)
            self.assertIsNotNone(ev.end)
            self.assertGreater(ev.end, ev.start)

    def test_bears_home_fixture_location_is_ashton_gate(self):
        synthetic = [(self._future(), "15:00", "Bristol Bears", "Saracens", "Gallagher Premiership")]
        with patch("scraper.KNOWN_BEARS_FIXTURES", synthetic), \
             patch("scraper.datetime") as mock_dt:
            self._make_now_mock(mock_dt)
            events = get_known_fixtures()
        self.assertIn("Ashton Gate", events[0].location)

    def test_bcfc_events_have_football_category(self):
        synthetic = [(self._future(), "12:30", "Stoke City", "EFL Championship")]
        with patch("scraper.KNOWN_BCFC_FIXTURES", synthetic), \
             patch("scraper.datetime") as mock_dt:
            self._make_now_mock(mock_dt)
            events = get_known_bcfc_fixtures()
        for ev in events:
            self.assertIn("Football", ev.categories)


if __name__ == "__main__":
    unittest.main()
